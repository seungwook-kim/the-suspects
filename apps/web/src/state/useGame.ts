import { useCallback, useEffect, useReducer, useRef, useState } from 'react'
import { api } from '../api/client'
import type { Action, AgEvent, ClearHistory, CreateOptions, FinaleStep, PlayerView, ShareCard } from '../api/types'
import { addSave } from '../util/saves'
import { clientReducer, initialClientState } from './reducer'

export interface GameResult {
  history: ClearHistory
  card: ShareCard | null
}

// 초상화는 게임을 만든 뒤 서버가 백그라운드로 그린다(기본 사진 약 1분). 표정 사진은 그 감정이 처음 나올 때 서버가
// 그 사람 것만 그린다(약 10초). 그래서 게임을 열 때와 행동이 끝날 때마다 다시 묻고, 그리는 동안(pending) 몇 초마다 채운다.
export const PORTRAIT_POLL_MS = 3000
export const PORTRAIT_POLL_MAX_MS = 360_000

export function useGame() {
  const [state, dispatch] = useReducer(clientReducer, initialClientState)
  const [portraitKick, setPortraitKick] = useState(0) // 행동이 끝날 때마다 +1 → 사진 상태를 다시 묻는다
  const [portraitsPending, setPortraitsPending] = useState(false) // 서버가 초상화를 그리는 중이면 true("사진 준비 중" 표시)
  const gameIdRef = useRef<string | null>(null)
  const busyRef = useRef(false)
  const viewRef = useRef(state.view)
  viewRef.current = state.view

  const viewGameId = state.view?.game_id || null
  useEffect(() => {
    if (!viewGameId) {
      setPortraitsPending(false)
      return
    }
    let alive = true
    let timer: number | undefined
    const started = Date.now()
    const poll = async () => {
      try {
        const st = await api.portraits(viewGameId)
        if (!alive) return
        dispatch({ kind: 'portraits', urls: st.urls ?? {}, emotions: st.emotions ?? {} })
        setPortraitsPending(!!st.pending)
        if (!st.pending) return // 다 그렸거나(실패분은 SVG로 남음) 그리지 않는 중 → 멈춤
      } catch {
        /* 일시 오류는 다음 차례에 다시 */
      }
      if (alive && Date.now() - started < PORTRAIT_POLL_MAX_MS) timer = window.setTimeout(() => void poll(), PORTRAIT_POLL_MS)
      else if (alive) setPortraitsPending(false) // 기다릴 만큼 기다렸다 → 남은 인물은 그림 얼굴로
    }
    void poll()
    return () => {
      alive = false
      window.clearTimeout(timer)
    }
  }, [viewGameId, portraitKick])

  const fail = useCallback((e: unknown) => {
    dispatch({ kind: 'error', message: e instanceof Error ? e.message : '알 수 없는 오류가 났습니다.' })
  }, [])

  const resync = useCallback(async () => {
    const id = gameIdRef.current
    if (!id) return
    try {
      dispatch({ kind: 'set_view', view: await api.getGame(id) })
    } catch (e) {
      fail(e)
    }
  }, [fail])

  const consume = useCallback(
    async (stream: AsyncIterable<AgEvent>, opts: { tick?: boolean } = {}) => {
      if (busyRef.current) return
      busyRef.current = true
      dispatch({ kind: 'running', value: true })
      let sawError = false
      try {
        for await (const ev of stream) {
          if (ev.type === 'RUN_ERROR') sawError = true
          dispatch({ kind: 'event', ev })
        }
      } catch (e) {
        fail(e)
      } finally {
        busyRef.current = false
        dispatch({ kind: 'running', value: false })
        setPortraitKick((n) => n + 1) // 이번 행동으로 새 감정이 나왔으면 서버가 표정 사진을 그리기 시작했을 수 있다
      }
      if (opts.tick && !sawError) dispatch({ kind: 'tick_turn_away' })
    },
    [fail],
  )

  const startGame = useCallback(
    async (themeId: string, options?: CreateOptions) => {
      dispatch({ kind: 'reset' })
      try {
        const r = await api.createGame(themeId, options)
        gameIdRef.current = r.game_id
        dispatch({ kind: 'set_view', view: r.view })
        return true
      } catch (e) {
        fail(e)
        return false
      }
    },
    [fail],
  )

  // 사건 생성 작업이 끝나 이미 만들어진 게임으로 들어간다
  const adoptGame = useCallback((gameId: string, view: PlayerView) => {
    dispatch({ kind: 'reset' })
    gameIdRef.current = gameId
    dispatch({ kind: 'set_view', view })
  }, [])

  const act = useCallback(
    (action: Action) => {
      const id = gameIdRef.current
      if (!id) return Promise.resolve()
      return consume(api.action(id, action), { tick: true })
    },
    [consume],
  )

  const endDay = useCallback(() => {
    const id = gameIdRef.current
    if (!id) return Promise.resolve()
    return consume(api.night(id))
  }, [consume])

  const finaleStep = useCallback(
    (step: FinaleStep) => {
      const id = gameIdRef.current
      if (!id) return Promise.resolve()
      return consume(api.finale(id, step))
    },
    [consume],
  )

  const save = useCallback(async () => {
    const id = gameIdRef.current
    const v = viewRef.current
    if (!id || !v) return null
    try {
      const r = await api.save(id)
      addSave({
        slot_id: r.slot_id,
        game_id: id,
        slot_name: '',
        saved_at: r.saved_at,
        case_title: v.case_title,
        day: v.day,
      })
      return r
    } catch (e) {
      fail(e)
      return null
    }
  }, [fail])

  const load = useCallback(
    async (gameId: string, slotId: string) => {
      dispatch({ kind: 'reset' })
      try {
        const view = await api.load(gameId, slotId)
        gameIdRef.current = view.game_id || gameId
        dispatch({ kind: 'set_view', view })
        return view
      } catch (e) {
        fail(e)
        return null
      }
    },
    [fail],
  )

  const clearGame = useCallback(async (): Promise<GameResult | null> => {
    const id = gameIdRef.current
    if (!id) return null
    try {
      return await api.clear(id)
    } catch (e) {
      fail(e)
      return null
    }
  }, [fail])

  const openGame = useCallback(
    async (gameId: string) => {
      dispatch({ kind: 'reset' })
      try {
        const view = await api.getGame(gameId)
        gameIdRef.current = gameId
        dispatch({ kind: 'set_view', view })
        return view
      } catch (e) {
        fail(e)
        return null
      }
    },
    [fail],
  )

  const fetchSources = useCallback((statementId: string) => api.sources(gameIdRef.current ?? '', statementId), [])

  const resetAll = useCallback(() => {
    gameIdRef.current = null
    dispatch({ kind: 'reset' })
  }, [])

  return { state, dispatch, startGame, act, endDay, finaleStep, save, load, openGame, fetchSources, clearGame, resetAll, resync, adoptGame, gameIdRef, portraitsPending }
}

export type GameApi = ReturnType<typeof useGame>

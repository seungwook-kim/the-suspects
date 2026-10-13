import { useCallback, useReducer, useRef } from 'react'
import { api } from '../api/client'
import type { Action, AgEvent, ClearHistory, CreateOptions, FinaleStep, ShareCard } from '../api/types'
import { addSave } from '../util/saves'
import { clientReducer, initialClientState } from './reducer'

export interface GameResult {
  history: ClearHistory
  card: ShareCard | null
}

export function useGame() {
  const [state, dispatch] = useReducer(clientReducer, initialClientState)
  const gameIdRef = useRef<string | null>(null)
  const busyRef = useRef(false)
  const viewRef = useRef(state.view)
  viewRef.current = state.view

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

  return { state, dispatch, startGame, act, endDay, finaleStep, save, load, openGame, fetchSources, clearGame, resetAll, resync, gameIdRef }
}

export type GameApi = ReturnType<typeof useGame>

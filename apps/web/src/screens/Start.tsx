import { useEffect, useState } from 'react'
import { api, USE_MOCK } from '../api/client'
import type { CreateOptions, GameSummary, SaveSlotInfo, Theme } from '../api/types'
import { getPref, getSaves, setPref } from '../util/saves'

type Mood = '코믹' | '보통' | '진지'
type Difficulty = '쉬움' | '보통' | '어려움'

interface Props {
  busy: boolean
  error: string | null
  onStart: (themeId: string, options: CreateOptions) => void
  onCreateCase: (themeText: string, options: CreateOptions) => void
  onOpenGame: (gameId: string) => void
  onLoadSlot: (gameId: string, slotId: string) => void
  onHistory: () => void
}

const TONE: Record<Mood, NonNullable<CreateOptions['tone']>> = { 코믹: 'comic', 보통: 'balanced', 진지: 'serious' }
const DIFF: Record<Difficulty, NonNullable<CreateOptions['difficulty']>> = { 쉬움: 'easy', 보통: 'normal', 어려움: 'hard' }

export const CUSTOM_MAX = 80

export function Start({ busy, error, onStart, onCreateCase, onOpenGame, onLoadSlot, onHistory }: Props) {
  const [themes, setThemes] = useState<Theme[] | null>(null)
  const [loadErr, setLoadErr] = useState('')
  const [theme, setTheme] = useState<string | null>(null)
  const [custom, setCustom] = useState('')
  const [mood, setMood] = useState<Mood>(() => getPref('mood', '보통'))
  const [diff, setDiff] = useState<Difficulty>(() => getPref('diff', '보통'))
  const [minutes, setMinutes] = useState<number>(() => getPref('minutes', 40))
  const [showSaves, setShowSaves] = useState(false)
  const [games, setGames] = useState<GameSummary[] | null>(null)
  const [slots, setSlots] = useState<Record<string, SaveSlotInfo[]>>({})
  const [offline, setOffline] = useState(false) // 서버 목록 실패 -> 브라우저에 기억해 둔 세이브
  const localSaves = getSaves()

  const toggleSaves = async () => {
    if (showSaves) return setShowSaves(false)
    setShowSaves(true)
    try {
      setGames(await api.listGames())
      setOffline(false)
    } catch {
      setOffline(true)
    }
  }
  const openSlots = async (gameId: string) => {
    try {
      setSlots((s) => ({ ...s, [gameId]: [] }))
      const list = await api.listSaves(gameId)
      setSlots((s) => ({ ...s, [gameId]: list }))
    } catch {
      /* 슬롯 목록 실패는 조용히 비운다 */
    }
  }

  useEffect(() => {
    let alive = true
    api
      .themes()
      .then((t) => alive && setThemes(t))
      .catch((e) => alive && setLoadErr(e instanceof Error ? e.message : '주제를 불러오지 못했습니다.'))
    return () => {
      alive = false
    }
  }, [])

  const pick = <T,>(set: (v: T) => void, key: string) => (v: T) => {
    set(v)
    setPref(key, v)
  }

  const opts: CreateOptions = { tone: TONE[mood], difficulty: DIFF[diff], play_minutes: minutes as 20 | 40 | 60 }

  return (
    <div className="screen start">
      <h1>The Suspects</h1>
      <p className="lead">오늘은 어떤 사건을?</p>
      {USE_MOCK && <p className="mock-badge">목(mock) 모드 · 가짜 데이터로 실행 중</p>}

      <div className="theme-grid">
        {!themes && !loadErr && <p className="muted">주제를 불러오는 중…</p>}
        {loadErr && <p className="warn">{loadErr}</p>}
        {themes?.map((t) => (
          <button key={t.id} className={`theme-card${theme === t.id ? ' on' : ''}`} onClick={() => { setTheme(t.id); setCustom('') }}>
            <span className="emoji">{t.emoji}</span>
            <strong>{t.title}</strong>
            <span className="muted small">{t.description}</span>
          </button>
        ))}
      </div>

      <div className="custom-box">
        <label htmlFor="custom-theme">
          ✏️ 직접 만들기 <span className="lab">실험실</span>
          <span className="muted small"> — 결과가 들쭉날쭉할 수 있어요</span>
        </label>
        <div className="custom-row">
          <input
            id="custom-theme"
            value={custom}
            maxLength={CUSTOM_MAX}
            disabled={busy}
            onChange={(e) => {
              setCustom(e.target.value)
              if (e.target.value) setTheme(null)
            }}
            placeholder="예: 고등학교 축제 날 사라진 상장"
            aria-label="자유 주제"
          />
          <button className="primary" disabled={busy || custom.trim().length < 2} onClick={() => onCreateCase(custom.trim(), opts)}>
            사건 생성 ▶
          </button>
        </div>
        <span className="muted small char-count" aria-live="polite">{CUSTOM_MAX - custom.length}자 남음</span>
      </div>

      <div className="options">
        <Seg label="분위기" values={['코믹', '보통', '진지']} value={mood} onChange={pick(setMood, 'mood')} />
        <Seg label="난이도" values={['쉬움', '보통', '어려움']} value={diff} onChange={pick(setDiff, 'diff')} />
        <Seg label="플레이 시간" values={[20, 40, 60]} fmt={(v) => (v === 60 ? '1시간' : `${v}분`)} value={minutes} onChange={pick(setMinutes, 'minutes')} />
      </div>

      {error && <p className="warn" role="alert">{error}</p>}
      <div className="start-actions">
        <button className="primary big" disabled={!theme || busy} onClick={() => theme && onStart(theme, opts)}>
          {busy ? '사건 파일 작성 중…' : '사건 시작 ▶'}
        </button>
        <button disabled={busy} onClick={() => void toggleSaves()}>이어하기</button>
        <button onClick={onHistory} disabled={busy}>클리어 이력</button>
      </div>

      {showSaves && (
        <ul className="save-list">
          {!offline && games === null && <li className="muted">불러오는 중…</li>}
          {!offline && games?.length === 0 && <li className="muted">이어할 게임이 없습니다.</li>}
          {!offline &&
            games?.map((gm) => (
              <li key={gm.game_id}>
                <div className="save-row">
                  <button onClick={() => onOpenGame(gm.game_id)}>
                    <b>{gm.case_title}</b> · {gm.day}일차 · {new Date(gm.last_seen).toLocaleString('ko-KR')}
                  </button>
                  <button onClick={() => void openSlots(gm.game_id)}>저장 슬롯</button>
                </div>
                {slots[gm.game_id]?.map((sl) => (
                  <button key={sl.slot_id} className="slot" onClick={() => onLoadSlot(gm.game_id, sl.slot_id)}>
                    💾 {sl.name} · {new Date(sl.saved_at).toLocaleString('ko-KR')}
                  </button>
                ))}
                {slots[gm.game_id]?.length === 0 && <span className="muted small">저장 슬롯이 없습니다.</span>}
              </li>
            ))}
          {offline && (
            <>
              <li className="muted small">서버에서 목록을 받지 못해, 이 브라우저에 기억해 둔 저장본을 보여 줍니다.</li>
              {localSaves.length === 0 && <li className="muted">기억해 둔 저장본이 없습니다.</li>}
              {localSaves.map((sv) => (
                <li key={sv.slot_id}>
                  <button onClick={() => onLoadSlot(sv.game_id, sv.slot_id)}>
                    <b>{sv.case_title}</b> · {sv.day}일차 · {new Date(sv.saved_at).toLocaleString('ko-KR')}
                  </button>
                </li>
              ))}
            </>
          )}
        </ul>
      )}
      <p className="muted small privacy">자유 입력에는 개인정보를 적지 마세요. 클리어하면 사건 데이터는 삭제됩니다.</p>
    </div>
  )
}

function Seg<T extends string | number>({
  label, values, value, onChange, fmt,
}: {
  label: string
  values: T[]
  value: T
  onChange: (v: T) => void
  fmt?: (v: T) => string
}) {
  return (
    <div className="seg-row">
      <span>{label}</span>
      <div className="seg" role="radiogroup" aria-label={label}>
        {values.map((v) => (
          <button key={String(v)} role="radio" aria-checked={v === value} className={v === value ? 'on' : ''} onClick={() => onChange(v)}>
            {fmt ? fmt(v) : String(v)}
          </button>
        ))}
      </div>
    </div>
  )
}

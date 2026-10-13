import { useEffect, useState } from 'react'
import { api, USE_MOCK } from '../api/client'
import type { Theme } from '../api/types'
import { getPref, getSaves, setPref, type SaveRef } from '../util/saves'

type Mood = '코믹' | '보통' | '진지'
type Difficulty = '쉬움' | '보통' | '어려움'

interface Props {
  busy: boolean
  error: string | null
  onStart: (themeId: string) => void
  onResume: (save: SaveRef) => void
  onHistory: () => void
}

export function Start({ busy, error, onStart, onResume, onHistory }: Props) {
  const [themes, setThemes] = useState<Theme[] | null>(null)
  const [loadErr, setLoadErr] = useState('')
  const [theme, setTheme] = useState<string | null>(null)
  const [mood, setMood] = useState<Mood>(() => getPref('mood', '보통'))
  const [diff, setDiff] = useState<Difficulty>(() => getPref('diff', '보통'))
  const [minutes, setMinutes] = useState<number>(() => getPref('minutes', 40))
  const [showSaves, setShowSaves] = useState(false)
  const saves = getSaves()

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

  return (
    <div className="screen start">
      <h1>The Suspects</h1>
      <p className="lead">오늘은 어떤 사건을?</p>
      {USE_MOCK && <p className="mock-badge">목(mock) 모드 · 가짜 데이터로 실행 중</p>}

      <div className="theme-grid">
        {!themes && !loadErr && <p className="muted">주제를 불러오는 중…</p>}
        {loadErr && <p className="warn">{loadErr}</p>}
        {themes?.map((t) => (
          <button key={t.id} className={`theme-card${theme === t.id ? ' on' : ''}`} onClick={() => setTheme(t.id)}>
            <span className="emoji">{t.emoji}</span>
            <strong>{t.title}</strong>
            <span className="muted small">{t.description}</span>
          </button>
        ))}
      </div>

      <div className="custom-box">
        <label>
          ✏️ 직접 만들기 <span className="lab">실험실 — 준비 중</span>
        </label>
        <input disabled placeholder="예: 고등학교 축제 날 사라진 상장" aria-label="자유 주제 (준비 중)" />
      </div>

      <div className="options">
        <Seg label="분위기" values={['코믹', '보통', '진지']} value={mood} onChange={pick(setMood, 'mood')} />
        <Seg label="난이도" values={['쉬움', '보통', '어려움']} value={diff} onChange={pick(setDiff, 'diff')} />
        <Seg label="플레이 시간" values={[20, 40, 60]} fmt={(v) => (v === 60 ? '1시간' : `${v}분`)} value={minutes} onChange={pick(setMinutes, 'minutes')} />
        <p className="muted small">옵션은 곧 사건 생성에 반영됩니다. (지금은 고정 사건)</p>
      </div>

      {error && <p className="warn" role="alert">{error}</p>}
      <div className="start-actions">
        <button className="primary big" disabled={!theme || busy} onClick={() => theme && onStart(theme)}>
          {busy ? '사건 파일 작성 중…' : '사건 시작 ▶'}
        </button>
        <button disabled={saves.length === 0 || busy} onClick={() => setShowSaves((s) => !s)}>
          이어하기 {saves.length > 0 && `(${saves.length})`}
        </button>
        <button onClick={onHistory} disabled={busy}>클리어 이력</button>
      </div>

      {showSaves && (
        <ul className="save-list">
          {saves.map((s) => (
            <li key={s.slot_id}>
              <button onClick={() => onResume(s)}>
                <b>{s.case_title}</b> · {s.day}일차 · {new Date(s.saved_at).toLocaleString('ko-KR')}
              </button>
            </li>
          ))}
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

import { useEffect, useRef, useState, type CSSProperties } from 'react'
import { api, USE_MOCK } from '../api/client'
import type { CreateOptions, GameSummary, SaveSlotInfo, Theme } from '../api/types'
import { AI_PORTRAIT_NOTICE } from '../character/Portrait'
import { Icon, type IconName } from '../components/Icon'
import { getPref, getSaves, setPref } from '../util/saves'
import suspect1 from '../assets/lineup/suspect-01.webp'
import suspect2 from '../assets/lineup/suspect-02.webp'
import suspect3 from '../assets/lineup/suspect-03.webp'
import suspect4 from '../assets/lineup/suspect-04.webp'

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
  onAbout: () => void
}

const TONE: Record<Mood, NonNullable<CreateOptions['tone']>> = { 코믹: 'comic', 보통: 'balanced', 진지: 'serious' }
const DIFF: Record<Difficulty, NonNullable<CreateOptions['difficulty']>> = { 쉬움: 'easy', 보통: 'normal', 어려움: 'hard' }

export const CUSTOM_MAX = 80

const MOOD_ATTR: Record<Mood, string> = { 코믹: 'comic', 보통: 'normal', 진지: 'serious' }
// 사건 카드 아이콘은 순서대로 돌려 쓴다
const CASE_ICONS: IconName[] = ['database', 'buildings', 'package', 'bed']
const pad2 = (n: number) => String(n).padStart(2, '0')
// 첫 화면의 용의자 사진 카드(장식). 사진 보관함에서 고른 AI 생성 인물이며 사건 내용과 관계없다
const LINEUP = [suspect1, suspect2, suspect3, suspect4]

export function Start({ busy, error, onStart, onCreateCase, onOpenGame, onLoadSlot, onHistory, onAbout }: Props) {
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
  const customRef = useRef('')
  customRef.current = custom

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
      .then((t) => {
        if (!alive) return
        setThemes(t)
        // 직접 쓴 주제가 없으면 첫 사건을 골라 두어 바로 시작할 수 있게 한다
        if (!customRef.current) setTheme((cur) => cur ?? t[0]?.id ?? null)
      })
      .catch((e) => alive && setLoadErr(e instanceof Error ? e.message : '주제를 불러오지 못했습니다.'))
    return () => {
      alive = false
    }
  }, [])

  const pick = <T,>(set: (v: T) => void, key: string) => (v: T) => {
    set(v)
    setPref(key, v)
  }

  // 분위기는 고르는 자리에서 바로 보이게 한다(저장은 pick 이 한다)
  const pickMood = (v: Mood) => {
    document.documentElement.dataset.mood = MOOD_ATTR[v]
    pick(setMood, 'mood')(v)
  }

  const opts: CreateOptions = { tone: TONE[mood], difficulty: DIFF[diff], play_minutes: minutes as 20 | 40 | 60 }
  const customOk = custom.trim().length >= 2
  const chosen = themes?.find((t) => t.id === theme) ?? null
  const now = new Date()
  const stamp = `${now.getFullYear()}. ${pad2(now.getMonth() + 1)}. ${pad2(now.getDate())}.`

  return (
    <div className="screen start">
      <header className="start-hero">
        <div className="hero-copy">
          <p className="eyebrow">사건 접수 · {stamp}</p>
          <h1 className="hero-title">
            The Suspects
            <span className="hero-ko">용의자들</span>
          </h1>
          <p className="hero-lead">모두가 무언가를 숨기고 있다. 증거를 모으고, 진술 속 모순을 찾아, 범인을 지목하세요.</p>
          <ol className="hero-steps" aria-label="진행 순서">
            <li><span className="mono">01</span><Icon name="magnifying-glass" />현장 조사</li>
            <li><span className="mono">02</span><Icon name="chat-circle-text" />심문과 증거 제시</li>
            <li><span className="mono">03</span><Icon name="seal-check" />범인 지목</li>
          </ol>
          <p className="ai-notice" role="note" data-testid="ai-notice">
            <Icon name="info" />
            <span>{AI_PORTRAIT_NOTICE}</span>
          </p>
          {USE_MOCK && <p className="start-mock muted small">목(mock) 모드 · 가짜 데이터로 실행 중</p>}
        </div>
        <figure className="mugshots" aria-hidden="true">
          {LINEUP.map((src, i) => (
            <div key={src} className="mugshot" style={{ '--i': i } as CSSProperties}>
              <img src={src} alt="" width={300} height={400} />
              <span className="mugshot-plate mono">용의자 {pad2(i + 1)}</span>
            </div>
          ))}
          <span className="mugshots-clip"><Icon name="paperclip" /></span>
          <span className="stamp mugshots-stamp">수사 중</span>
        </figure>
      </header>

      <section className="paper has-tab start-file" aria-labelledby="start-cases-h">
        <span className="folder-tab">사건 고르기</span>
        <h2 id="start-cases-h" className="sr-only">사건 고르기</h2>
        {!themes && !loadErr && <p className="muted">주제를 불러오는 중…</p>}
        {loadErr && <p className="warn-text" role="alert">{loadErr}</p>}
        <div className="start-cases">
          <div className="start-presets" role="radiogroup" aria-label="사건">
            {themes?.map((t, i) => (
              <button
                key={t.id}
                type="button"
                role="radio"
                aria-checked={theme === t.id}
                className={`theme-card start-case${theme === t.id ? ' on' : ''}`}
                onClick={() => { setTheme(t.id); setCustom('') }}
              >
                <span className="start-case-icon"><Icon name={CASE_ICONS[i % CASE_ICONS.length]} /></span>
                <span className="start-case-text">
                  <span className="start-case-no mono">사건 {pad2(i + 1)}</span>
                  <strong>{t.title}</strong>
                  <span className="start-case-desc">{t.description}</span>
                </span>
                <span className="start-case-on"><Icon name="check-circle" />선택됨</span>
              </button>
            ))}
          </div>

          <div className={`start-custom${custom ? ' is-active' : ''}`}>
            <div className="start-custom-head">
              <Icon name="lightbulb" />
              <label htmlFor="custom-theme"><strong>직접 만들기</strong></label>
              <span className="kind">실험실</span>
              <span className="start-count mono muted small" aria-live="polite">{CUSTOM_MAX - custom.length}자 남음</span>
            </div>
            <p className="muted small">원하는 주제를 한 줄로 적으면 사건을 새로 씁니다. 결과가 들쭉날쭉할 수 있어요.</p>
            <div className="start-custom-row">
              <input
                id="custom-theme"
                className="field"
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
              <button
                type="button"
                className={`btn${customOk && !busy ? ' btn-cta' : ''}`}
                disabled={busy || !customOk}
                onClick={() => onCreateCase(custom.trim(), opts)}
              >
                <span className="btn-label"><Icon name="paper-plane-tilt" />사건 생성</span>
                {!busy && !customOk && <small className="btn-reason">주제를 입력하세요</small>}
              </button>
            </div>
          </div>
        </div>

        <div className="start-options" role="group" aria-label="수사 조건">
          <Seg label="분위기" values={['코믹', '보통', '진지']} value={mood} onChange={pickMood} />
          <Seg label="난이도" values={['쉬움', '보통', '어려움']} value={diff} onChange={pick(setDiff, 'diff')} />
          <Seg label="플레이 시간" values={[20, 40, 60]} fmt={(v) => (v === 60 ? '1시간' : `${v}분`)} value={minutes} onChange={pick(setMinutes, 'minutes')} />
        </div>
      </section>

      {error && <p className="warn-text" role="alert">{error}</p>}
      <div className="start-go">
        <div className="start-go-main">
          <button type="button" className="btn btn-cta btn-lg" disabled={!theme || busy} onClick={() => theme && onStart(theme, opts)}>
            <span className="btn-label"><Icon name="play" />{busy ? '사건 파일 작성 중…' : '사건 시작'}</span>
            {!busy && <small className="btn-reason">{chosen ? chosen.title : custom ? '직접 만든 주제는 위의 "사건 생성"으로' : '사건을 고르세요'}</small>}
          </button>
        </div>
        <div className="start-go-side">
          <button type="button" className="btn" disabled={busy} onClick={() => void toggleSaves()} aria-expanded={showSaves}>
            <span className="btn-label"><Icon name="floppy-disk" />이어하기</span>
          </button>
          <button type="button" className="btn" onClick={onHistory} disabled={busy}>
            <span className="btn-label"><Icon name="notebook" />클리어 이력</span>
          </button>
        </div>
      </div>

      {showSaves && (
        <ul className="start-saves paper">
          {!offline && games === null && <li className="muted">불러오는 중…</li>}
          {!offline && games?.length === 0 && <li className="muted">이어할 게임이 없습니다.</li>}
          {!offline &&
            games?.map((gm) => (
              <li key={gm.game_id}>
                <div className="start-save-row">
                  <button type="button" className="btn btn-quiet" onClick={() => onOpenGame(gm.game_id)}>
                    <span className="btn-label"><b>{gm.case_title}</b> · {gm.day}일차 · {new Date(gm.last_seen).toLocaleString('ko-KR')}</span>
                  </button>
                  <button type="button" className="btn btn-sm" onClick={() => void openSlots(gm.game_id)}>
                    <span className="btn-label">저장 슬롯</span>
                  </button>
                </div>
                {slots[gm.game_id]?.map((sl) => (
                  <button key={sl.slot_id} type="button" className="btn btn-quiet start-slot" onClick={() => onLoadSlot(gm.game_id, sl.slot_id)}>
                    <span className="btn-label"><Icon name="floppy-disk" />{sl.name} · {new Date(sl.saved_at).toLocaleString('ko-KR')}</span>
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
                  <button type="button" className="btn btn-quiet" onClick={() => onLoadSlot(sv.game_id, sv.slot_id)}>
                    <span className="btn-label"><b>{sv.case_title}</b> · {sv.day}일차 · {new Date(sv.saved_at).toLocaleString('ko-KR')}</span>
                  </button>
                </li>
              ))}
            </>
          )}
        </ul>
      )}

      <footer className="start-foot">
        <p>자유 입력에는 개인정보를 적지 마세요. 클리어하면 사건 데이터는 삭제됩니다.</p>
        <button type="button" className="start-about" onClick={onAbout}>정보 · 라이선스</button>
      </footer>
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
    <div className="start-seg-row">
      <span className="start-legend" id={`seg-${label}`}>{label}</span>
      <div className="seg" role="radiogroup" aria-labelledby={`seg-${label}`}>
        {values.map((v) => (
          <button key={String(v)} type="button" role="radio" aria-checked={v === value} className={v === value ? 'on' : ''} onClick={() => onChange(v)}>
            {fmt ? fmt(v) : String(v)}
          </button>
        ))}
      </div>
    </div>
  )
}

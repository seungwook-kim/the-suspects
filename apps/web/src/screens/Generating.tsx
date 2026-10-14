import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import type { CaseJob, CreateOptions, PlayerView } from '../api/types'
import { PortraitPending } from '../character/Portrait'
import { Icon } from '../components/Icon'
import { Cast } from './Briefing'

interface Props {
  themeText: string
  options: CreateOptions
  onReady: (gameId: string, view: PlayerView) => void
  onRejected: (message: string) => void
  onFallback: (themeId: string) => void
  onHome: () => void
}

const POLL_MS = 1000
const MAX_QUIET_FAILS = 3

export function Generating({ themeText, options, onReady, onRejected, onFallback, onHome }: Props) {
  const [job, setJob] = useState<CaseJob | null>(null)
  const [netError, setNetError] = useState(false)
  const [attempt, setAttempt] = useState(0)
  const jobIdRef = useRef<Promise<string> | null>(null)
  const cb = useRef({ onRejected, options, themeText })
  cb.current = { onRejected, options, themeText }

  useEffect(() => {
    let alive = true
    let timer: number | undefined
    let fails = 0

    const tick = async () => {
      try {
        jobIdRef.current ??= api.createCase(cb.current.themeText, cb.current.options).then((r) => r.job_id)
        let id: string
        try {
          id = await jobIdRef.current
        } catch (e) {
          jobIdRef.current = null // 생성 요청 자체가 실패하면 다시 시도할 때 새로 만든다
          throw e
        }
        const j = await api.caseJob(id)
        if (!alive) return
        fails = 0
        setJob(j)
        if (j.status === 'running') timer = window.setTimeout(tick, POLL_MS)
        else if (j.status === 'rejected') cb.current.onRejected(j.message ?? '이 주제로는 사건을 만들 수 없어요.')
      } catch {
        if (!alive) return
        fails += 1
        if (fails > MAX_QUIET_FAILS) setNetError(true)
        else timer = window.setTimeout(tick, POLL_MS)
      }
    }
    void tick()
    return () => {
      alive = false
      if (timer !== undefined) window.clearTimeout(timer)
    }
  }, [attempt])

  const retry = useCallback(() => {
    setNetError(false)
    setAttempt((n) => n + 1)
  }, [])

  if (netError) {
    return (
      <div className="screen gen">
        <div className="gen-error">
          <Icon name="warning-circle" className="gen-error-icon" />
          <p className="warn-text" role="alert">서버와 연결이 불안정해요. 사건 파일을 불러오지 못했습니다.</p>
          <div className="actions is-center">
            <button type="button" className="btn btn-cta" onClick={retry}><span className="btn-label">다시 시도</span></button>
            <button type="button" className="btn" onClick={onHome}><span className="btn-label">처음으로</span></button>
          </div>
        </div>
      </div>
    )
  }

  if (job?.status === 'failed') {
    return (
      <div className="screen gen">
        <div className="gen-error">
          <Icon name="warning-circle" className="gen-error-icon" />
          <p className="warn-text" role="alert">{job.message ?? '사건을 만들지 못했어요.'}</p>
          <div className="actions is-center">
            {job.fallback_theme_id && (
              <button type="button" className="btn btn-cta" onClick={() => onFallback(job.fallback_theme_id!)}>
                <span className="btn-label">기본 사건으로 시작</span>
              </button>
            )}
            <button type="button" className="btn" onClick={onHome}><span className="btn-label">처음으로</span></button>
          </div>
        </div>
      </div>
    )
  }

  const preview = job?.preview ?? null
  const ready = job?.status === 'ready' && !!job.game_id && !!job.view
  const stageText = job?.stage_text ?? '사건 파일 작성 중…'
  const stage = job?.stage ?? 1
  const total = job?.total ?? 5

  // 단계 칸: 글자("단계 N / M")를 꼭 같이 둔다
  const steps = (done: number) => (
    <span className="cells" aria-hidden="true">
      {Array.from({ length: total }, (_, i) => (
        <i key={i} className={i < done ? 'on' : ''} />
      ))}
    </span>
  )

  if (!preview) {
    return (
      <div className="screen gen">
        <div className="loading-file" role="status" aria-live="polite">
          <Icon name="notebook" />
          <p>{stageText.replace(/…$/, '')}<span className="dots" /></p>
          {steps(stage)}
          <p className="muted small">단계 {stage} / {total} · 1~3분쯤 걸려요</p>
        </div>
        <div className="actions is-center">
          <button type="button" className="btn" onClick={onHome}><span className="btn-label">취소</span></button>
        </div>
      </div>
    )
  }

  return (
    <div className="screen gen gen-preview">
      <p className="eyebrow">사건 브리핑 <span className="kind">실험실</span></p>
      <h1>{preview.title}</h1>
      <p className="gen-summary paper">{preview.incident_summary}</p>

      <h2 className="section-title">등장인물</h2>
      {/* 사진은 아직 그리는 중이라 "사진 준비 중"으로 보인다 */}
      <PortraitPending.Provider value={true}>
        <Cast characters={preview.characters} />
      </PortraitPending.Provider>

      <div className="gen-status" role="status" aria-live="polite">
        <span>{stageText}</span>
        {steps(stage - (ready ? 0 : 1))}
        <span className="mono muted small">단계 {stage} / {total}</span>
      </div>
      <div className="actions">
        <button type="button" className="btn btn-cta btn-lg" disabled={!ready} onClick={() => job?.game_id && job.view && onReady(job.game_id, job.view)}>
          <span className="btn-label"><Icon name="magnifying-glass" />수사 시작</span>
          {!ready && <small className="btn-reason">사건 파일을 마무리하는 중</small>}
        </button>
        <button type="button" className="btn" onClick={onHome}><span className="btn-label">취소</span></button>
      </div>
    </div>
  )
}

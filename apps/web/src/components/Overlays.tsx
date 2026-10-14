import { useEffect, type ReactNode } from 'react'
import type { ClientState, UiAction } from '../state/reducer'
import { Icon } from './Icon'

interface Props {
  state: ClientState
  dispatch: (a: UiAction) => void
  /** 화면이 따로 띄우는 토스트(새 모순, 저장 등). 같은 줄에 쌓인다 */
  children?: ReactNode
}

export function Overlays({ state, dispatch, children }: Props) {
  const { cutin, director, night, overheard, error } = state

  useEffect(() => {
    if (!cutin) return
    const id = window.setTimeout(() => dispatch({ kind: 'clear_cutin' }), 1500)
    return () => window.clearTimeout(id)
  }, [cutin, dispatch])

  useEffect(() => {
    if (!director) return
    const id = window.setTimeout(() => dispatch({ kind: 'clear_director' }), 7000)
    return () => window.clearTimeout(id)
  }, [director, dispatch])

  const names = new Map(state.view?.characters.map((c) => [c.id, c.name]) ?? [])
  const nightCells = night ? Math.max(1, night.total) : 0

  return (
    <>
      {night && (
        <div className="night-overlay" role="status" aria-live="polite">
          <Icon name="moon" />
          <h2>밤이 깊어 갑니다</h2>
          <p>{night.text}</p>
          <div className="night-bar">
            <span className="cells" role="img" aria-label={`진행 ${night.step}/${nightCells}`}>
              {Array.from({ length: nightCells }, (_, i) => (
                <i key={i} className={i < night.step ? 'on' : ''} />
              ))}
            </span>
          </div>
        </div>
      )}

      {cutin && (
        <div key={cutin.key} className={`cutin style-${cutin.style ?? 'default'}`} aria-live="assertive">
          <span>{cutin.text}</span>
        </div>
      )}

      <div className="toast-stack" role="status" aria-live="polite">
        {children}
        {director && (
          <aside key={director.key} className="toast director">
            <b className="toast-title"><Icon name="info" />{director.title}</b>
            <p>{director.text}</p>
            <button type="button" className="btn btn-icon toast-close" onClick={() => dispatch({ kind: 'clear_director' })} aria-label="닫기">
              <span className="btn-label"><Icon name="x" /></span>
            </button>
          </aside>
        )}
        {overheard && (
          <aside className="toast overheard">
            <b className="toast-title"><Icon name="chat-circle-text" />엿들은 말</b>
            {overheard.lines.map((l, i) => (
              <p key={i}>
                <strong>{names.get(l.speakerId) ?? l.speakerId}</strong> {l.text}
              </p>
            ))}
            <button type="button" className="btn btn-icon toast-close" onClick={() => dispatch({ kind: 'clear_overheard' })} aria-label="닫기">
              <span className="btn-label"><Icon name="x" /></span>
            </button>
          </aside>
        )}
      </div>

      {error && (
        <div className="error-banner" role="alert">
          <span className="warn-text"><Icon name="warning-circle" />{error}</span>
          <button type="button" className="btn btn-sm" onClick={() => dispatch({ kind: 'error', message: '' })}>
            <span className="btn-label">닫기</span>
          </button>
        </div>
      )}
    </>
  )
}

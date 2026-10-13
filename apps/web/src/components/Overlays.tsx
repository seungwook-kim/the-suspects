import { useEffect } from 'react'
import type { ClientState, UiAction } from '../state/reducer'

interface Props {
  state: ClientState
  dispatch: (a: UiAction) => void
}

export function Overlays({ state, dispatch }: Props) {
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

  return (
    <>
      {night && (
        <div className="night-overlay" role="status" aria-live="polite">
          <div className="moon">🌙</div>
          <h2>밤이 깊어 갑니다…</h2>
          <p>{night.text}</p>
          <div className="bar">
            <i style={{ width: `${Math.min(100, (night.step / Math.max(1, night.total)) * 100)}%` }} />
          </div>
        </div>
      )}

      {cutin && (
        <div key={cutin.key} className={`cutin style-${cutin.style ?? 'default'}`} aria-live="assertive">
          <span>{cutin.text}</span>
        </div>
      )}

      {director && (
        <aside key={director.key} className="toast director" role="status">
          <b>{director.title}</b>
          <p>{director.text}</p>
          <button className="x" onClick={() => dispatch({ kind: 'clear_director' })} aria-label="닫기">
            ×
          </button>
        </aside>
      )}

      {overheard && (
        <aside className="toast overheard" role="status">
          <b>👂 엿들었다</b>
          {overheard.lines.map((l, i) => (
            <p key={i}>
              <strong>{names.get(l.speakerId) ?? l.speakerId}</strong>: {l.text}
            </p>
          ))}
          <button className="x" onClick={() => dispatch({ kind: 'clear_overheard' })} aria-label="닫기">
            ×
          </button>
        </aside>
      )}

      {error && (
        <div className="error-banner" role="alert">
          <span>⚠ {error}</span>
          <button onClick={() => dispatch({ kind: 'error', message: '' })}>닫기</button>
        </div>
      )}
    </>
  )
}

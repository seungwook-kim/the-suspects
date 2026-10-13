import { useEffect, useState } from 'react'
import { Portrait } from '../character/Portrait'
import type { PlayerView } from '../api/types'

interface Props {
  view: PlayerView | null
  onBegin: () => void
}

export function Briefing({ view, onBegin }: Props) {
  const [shown, setShown] = useState(0)
  const total = view?.characters.length ?? 0

  // 등장인물을 하나씩 나타나게 한다
  useEffect(() => {
    if (!view || shown >= total) return
    const id = window.setTimeout(() => setShown((n) => n + 1), shown === 0 ? 900 : 800)
    return () => window.clearTimeout(id)
  }, [view, shown, total])

  if (!view) {
    return (
      <div className="screen briefing">
        <div className="file-loading">
          <div className="folder">📁</div>
          <p>사건 파일 작성 중<span className="dots" /></p>
        </div>
      </div>
    )
  }

  return (
    <div className="screen briefing">
      <p className="eyebrow">사건 브리핑</p>
      <h1>{view.case_title}</h1>
      <p className="summary">{view.incident_summary}</p>

      <h2>등장인물</h2>
      <div className="cast">
        {view.characters.map((c, i) => (
          <article key={c.id} className={`cast-card${i < shown ? ' in' : ''}`} aria-hidden={i >= shown}>
            <Portrait seed={c.face_seed} appearance={c.appearance} emotion="neutral" width={110} still />
            <div>
              <strong>{c.name}</strong>
              <span className="muted"> · {c.role} · {c.age}세</span>
              <p>{c.one_liner}</p>
            </div>
          </article>
        ))}
      </div>

      <div className="brief-actions">
        <button className="primary big" onClick={onBegin}>
          {shown >= total ? '수사 시작 ▶' : '건너뛰고 수사 시작 ▶'}
        </button>
      </div>
    </div>
  )
}

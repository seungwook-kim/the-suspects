import { useEffect, useState } from 'react'
import { AI_PORTRAIT_NOTICE, Portrait } from '../character/Portrait'
import type { PlayerView, PublicCharacter } from '../api/types'

interface Props {
  view: PlayerView | null
  onBegin: () => void
}

// 등장인물 카드. 하나씩 나타나고, 다 나타난 뒤 onDone 이 true 로 알려진다.
export function Cast({ characters, onShown }: { characters: PublicCharacter[]; onShown?: (n: number) => void }) {
  const [shown, setShown] = useState(0)
  const total = characters.length

  useEffect(() => {
    if (shown >= total) return
    const id = window.setTimeout(() => setShown((n) => n + 1), shown === 0 ? 900 : 800)
    return () => window.clearTimeout(id)
  }, [shown, total])

  useEffect(() => onShown?.(shown), [shown, onShown])

  return (
    <>
      <p className="ai-notice" role="note" data-testid="ai-notice">🤖 {AI_PORTRAIT_NOTICE}</p>
      <div className="cast">
        {characters.map((c, i) => (
          <article key={c.id} className={`cast-card${i < shown ? ' in' : ''}`} aria-hidden={i >= shown} data-testid="cast-card">
            <Portrait seed={c.face_seed} appearance={c.appearance} emotion="neutral" width={110} still portraitUrl={c.portrait_url} portraitEmotions={c.portrait_emotions} name={c.name} />
            <div>
              <strong>{c.name}</strong>
              <span className="muted"> · {c.role} · {c.age}세</span>
              <p>{c.one_liner}</p>
            </div>
          </article>
        ))}
      </div>
    </>
  )
}

export function Briefing({ view, onBegin }: Props) {
  const [shown, setShown] = useState(0)
  const total = view?.characters.length ?? 0

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
      <Cast characters={view.characters} onShown={setShown} />

      <div className="brief-actions">
        <button className="primary big" onClick={onBegin}>
          {shown >= total ? '수사 시작 ▶' : '건너뛰고 수사 시작 ▶'}
        </button>
      </div>
    </div>
  )
}

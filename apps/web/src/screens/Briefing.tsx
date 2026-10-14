import { useEffect, useState } from 'react'
import { AI_PORTRAIT_NOTICE, Portrait } from '../character/Portrait'
import { Icon } from '../components/Icon'
import type { PlayerView, PublicCharacter } from '../api/types'

interface Props {
  view: PlayerView | null
  onBegin: () => void
}

// 등장인물 카드. 하나씩 나타나고, 다 나타나면 onShown 으로 개수가 알려진다.
// 나타나는 움직임은 CSS(briefing.css)에서 불투명도 + 살짝 아래에서, 모션 줄이기 설정이면 바로 보인다.
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
      <p className="notice brief-notice" role="note" data-testid="ai-notice">
        <Icon name="info" />
        <span>{AI_PORTRAIT_NOTICE}</span>
      </p>
      <ul className="brief-cast">
        {characters.map((c, i) => (
          <li key={c.id} className={`paper brief-card cast-card${i < shown ? ' in' : ''}`} aria-hidden={i >= shown} data-testid="cast-card">
            <article className="person is-row">
              <div className="person-photo">
                <Portrait seed={c.face_seed} appearance={c.appearance} emotion="neutral" still portraitUrl={c.portrait_url} portraitEmotions={c.portrait_emotions} name={c.name} />
              </div>
              <h3 className="person-name">{c.name}</h3>
              <p className="person-role">{c.role} · {c.age}세</p>
              <p className="person-line">{c.one_liner}</p>
            </article>
          </li>
        ))}
      </ul>
    </>
  )
}

export function Briefing({ view, onBegin }: Props) {
  const [shown, setShown] = useState(0)
  const total = view?.characters.length ?? 0

  if (!view) {
    return (
      <div className="screen briefing">
        <div className="loading-file" role="status">
          <Icon name="notebook" />
          <p>사건 파일 작성 중<span className="dots" /></p>
        </div>
      </div>
    )
  }

  return (
    <div className="screen briefing">
      <section className="paper has-tab brief-sheet" aria-labelledby="brief-title">
        <span className="folder-tab">사건 브리핑</span>
        <h1 id="brief-title">{view.case_title}</h1>
        <p className="brief-summary">{view.incident_summary}</p>
      </section>

      <section className="brief-people" aria-labelledby="brief-people-h">
        <h2 id="brief-people-h">등장인물 {total}명</h2>
        <Cast characters={view.characters} onShown={setShown} />
      </section>

      <div className="brief-start">
        <button type="button" className="btn btn-cta btn-lg" onClick={onBegin}>
          <span className="btn-label"><Icon name="notebook" />{shown >= total ? '수사 시작' : '건너뛰고 수사 시작'}</span>
        </button>
      </div>
    </div>
  )
}

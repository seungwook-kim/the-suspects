import type { CSSProperties } from 'react'
import type { PlayerView } from '../api/types'
import { Portrait } from '../character/Portrait'
import type { ClientState, DialogueLine } from '../state/reducer'
import { useTypewriter } from './DialogueBox'
import { Icon } from './Icon'

const ROLE_LABEL: Record<string, string> = { narrator: '내레이션', partner: '파트너', chief: '반장', npc: '' }

interface Props {
  state: ClientState
  busy: boolean
  onInvestigate: () => void
  onTalk: (npcId: string) => void
  onMove: (locationId: string) => void
}

/** 수사 화면 가운데: 지금 있는 장소 카드(설명·현장 조사·이곳의 사람·단톡방). 추천 질문은 그 사람을 심문할 때 행동바에 나온다 */
export function PlaceCard({ state, busy, onInvestigate, onTalk, onMove }: Props) {
  const view = state.view!
  const loc = view.locations.find((l) => l.id === view.player_location)
  const here = view.characters.filter((c) => c.location_id === view.player_location)
  const reachable = view.locations.filter((l) => l.id !== view.player_location && (loc?.connections.includes(l.id) || l.connections.includes(view.player_location)))
  const line = state.dialogue && state.dialogue.role !== 'npc' ? state.dialogue : null
  const out = view.actions_left <= 0
  const visited = new Set(view.visited_locations ?? [view.player_location])

  return (
    <section className="paper place-card has-tab" aria-labelledby="place-name">
      <span className="folder-tab">현장</span>
      <div className="pc-head">
        <h2 id="place-name">{loc?.name ?? '현장'}</h2>
        <span className="state-tag">현재 위치</span>
      </div>
      {loc?.description && <p className="pc-desc">{loc.description}</p>}
      {!!loc?.overlays.length && (
        <ul className="pc-tags" aria-label="눈에 띄는 것">
          {loc.overlays.map((o) => (
            <li key={o} className="kind">{o}</li>
          ))}
        </ul>
      )}

      {line && <Narration key={line.messageId} line={line} />}

      <div className="pc-act">
        <button type="button" className="btn btn-cta btn-lg" disabled={busy || out} onClick={onInvestigate}>
          <span className="btn-label"><Icon name="magnifying-glass" />현장 조사</span>
          {(busy || out) && <small className="btn-reason">{busy ? '진행 중' : '오늘 행동을 다 썼음'}</small>}
        </button>
      </div>

      <div className="pc-block">
        <h3 className="section-title">이곳에 있는 사람</h3>
        {here.length === 0 ? (
          <p className="muted small">이곳에는 아무도 없다.</p>
        ) : (
          <ul className="people">
            {here.map((c) => (
              <li key={c.id}>
                <button type="button" className="person" onClick={() => onTalk(c.id)} disabled={busy} aria-label={`${c.name}에게 말 걸기`}>
                  <span className="person-photo" style={{ '--photo-w': '100%' } as CSSProperties}>
                    <Portrait seed={c.face_seed} appearance={c.appearance} emotion={state.emotions[c.id] ?? c.emotion} still portraitUrl={c.portrait_url} portraitEmotions={c.portrait_emotions} name={c.name} />
                  </span>
                  <span className="person-name">{c.name}</span>
                  <span className="person-role">{c.role}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {reachable.length > 0 && (
        <div className="pc-block pc-moves">
          <h3 className="section-title">이어진 장소로 이동</h3>
          <ul className="chip-row">
            {reachable.map((l) => (
              <li key={l.id}>
                <button type="button" className="chip" disabled={busy || (out && !visited.has(l.id))} onClick={() => onMove(l.id)}>
                  <Icon name="map-trifold" />{l.name}
                  {!visited.has(l.id) && <span className="chip-to">· 처음 · 행동 1</span>}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {view.feed.length > 0 && <Feed view={view} />}
    </section>
  )
}

export function Feed({ view, limit = 4 }: { view: PlayerView; limit?: number }) {
  return (
    <div className="pc-block feed">
      <h3 className="section-title"><Icon name="chats-circle" /> 단톡방</h3>
      <ul>
        {view.feed.slice(-limit).map((f) => (
          <li key={f.id}>
            <span className="feed-chan mono">{f.channel}</span> <b>{f.author}</b> {f.text}
          </li>
        ))}
      </ul>
    </div>
  )
}

function Narration({ line }: { line: DialogueLine }) {
  const { shown, typing } = useTypewriter(line.text)
  const active = typing || !line.done
  return (
    <p className="pc-narration" aria-live="polite">
      <b className="who">{ROLE_LABEL[line.role] ?? ''}</b>
      <span>{shown}{active && <span className="caret" aria-hidden="true">▌</span>}</span>
    </p>
  )
}

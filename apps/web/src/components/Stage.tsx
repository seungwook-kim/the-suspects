import { useCallback, useState } from 'react'
import type { ClientState } from '../state/reducer'
import { Portrait } from '../character/Portrait'
import { DialogueBox } from './DialogueBox'
import { dotColor } from './MapPanel'

interface Props {
  state: ClientState
  interrogeeId: string | null
  busy: boolean
  onTalk: (npcId: string) => void
  onLeave: () => void
  onInvestigate: () => void
  onDropEvidence: (npcId: string, evidenceId: string) => void
}

export function Stage({ state, interrogeeId, busy, onTalk, onLeave, onInvestigate, onDropEvidence }: Props) {
  const view = state.view!
  const [typing, setTyping] = useState(false)
  const [dragOver, setDragOver] = useState(false)
  const onTyping = useCallback((t: boolean) => setTyping(t), [])
  const loc = view.locations.find((l) => l.id === view.player_location)
  const npc = interrogeeId ? view.characters.find((c) => c.id === interrogeeId) : null
  const here = view.characters.filter((c) => c.location_id === view.player_location)
  const line = state.dialogue
  const speaker = line?.speakerId ? view.characters.find((c) => c.id === line.speakerId) : null
  const awayLeft = npc ? state.turnAway[npc.id] : undefined

  // 심문 장면
  if (npc) {
    const emotion = state.emotions[npc.id] ?? npc.emotion
    const speaking = typing && line?.role === 'npc' && line.speakerId === npc.id
    return (
      <div className="stage interrogation">
        <button className="leave" onClick={onLeave}>← 심문 끝내기</button>
        <div
          className={`portrait-wrap${dragOver ? ' dragover' : ''}${awayLeft ? ' away' : ''}`}
          onDragOver={(e) => {
            if (awayLeft) return
            e.preventDefault()
            setDragOver(true)
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => {
            e.preventDefault()
            setDragOver(false)
            const id = e.dataTransfer.getData('text/evidence')
            if (id && !awayLeft) onDropEvidence(npc.id, id)
          }}
        >
          <Portrait
            seed={npc.face_seed}
            appearance={npc.appearance}
            emotion={emotion}
            speaking={speaking}
            width={230}
            portraitUrl={npc.portrait_url}
            name={npc.name}
            eager
            className={awayLeft ? 'turned' : ''}
          />
          {awayLeft ? (
            <div className="away-note">🚪 등을 돌렸다 · {awayLeft}번 행동 뒤에 다시 말을 걸 수 있다</div>
          ) : (
            <div className="drop-hint">증거 카드를 여기로 끌어다 놓으면 제시합니다</div>
          )}
        </div>
        <div className="nameplate">
          <strong>{npc.name}</strong> <span>{npc.role}</span>
        </div>
        {line ? (
          <DialogueBox key={line.messageId} line={line} speakerName={speaker?.name ?? null} onTyping={onTyping} />
        ) : (
          <div className="dialogue empty">
            <p>{npc.one_liner || '말을 걸어 보자.'}</p>
          </div>
        )}
        {busy && !line?.text && <div className="thinking">음…</div>}
      </div>
    )
  }

  // 현장 장면: 지도·현장·수첩이 주인공, 대화창은 없다
  return (
    <div className="stage scene">
      <div className="scene-bg" style={{ background: `linear-gradient(160deg, var(--surface-2), var(--surface))` }}>
        <div className="scene-icon" aria-hidden>📍</div>
        <h2>{loc?.name ?? '현장'}</h2>
        <p>{loc?.description}</p>
        {loc?.overlays.map((o) => (
          <span key={o} className="chip-mini">{o}</span>
        ))}
        <button className="primary" disabled={busy || view.actions_left <= 0} onClick={onInvestigate}>
          🔍 현장 조사
        </button>
      </div>
      <div className="here-people">
        {here.length === 0 && <span className="muted">이곳에는 아무도 없다.</span>}
        {here.map((c) => (
          <button key={c.id} className="person" onClick={() => onTalk(c.id)} disabled={busy} title={`${c.name}에게 말 걸기`}>
            <Portrait seed={c.face_seed} appearance={c.appearance} emotion={state.emotions[c.id] ?? c.emotion} width={64} still portraitUrl={c.portrait_url} name={c.name} />
            <span style={{ borderColor: dotColor(c.face_seed) }}>{c.name}</span>
          </button>
        ))}
      </div>
      {line && line.role !== 'npc' && (
        <DialogueBox key={line.messageId} line={line} speakerName={null} onTyping={onTyping} />
      )}
      {!line && <p className="muted center">인물을 눌러 심문을 시작하거나, 지도에서 이동하세요.</p>}
    </div>
  )
}

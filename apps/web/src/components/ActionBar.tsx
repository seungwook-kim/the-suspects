import { useState } from 'react'
import type { PlayerView } from '../api/types'

interface Props {
  view: PlayerView
  interrogeeId: string | null
  busy: boolean
  locked: boolean // NPC 가 등을 돌림
  selectedEvidence: string | null
  onChip: (chipId: string, targetNpc: string) => void
  onAsk: (text: string) => void
  onPresent: () => void
  onBluff: () => void
}

export function ActionBar({ view, interrogeeId, busy, locked, selectedEvidence, onChip, onAsk, onPresent, onBluff }: Props) {
  const [text, setText] = useState('')
  const out = view.actions_left <= 0
  const ev = selectedEvidence ? view.evidence.find((e) => e.id === selectedEvidence) : null
  const submit = () => {
    const t = text.trim()
    if (!t || busy || locked || out) return
    onAsk(t)
    setText('')
  }
  return (
    <div className="actionbar">
      <div className="chips" aria-label="질문 추천">
        {view.chips.length === 0 && <span className="muted small">추천 질문이 아직 없습니다.</span>}
        {view.chips.map((c) => (
          <button
            key={c.id}
            className={`chip kind-${c.kind}`}
            disabled={busy || out}
            onClick={() => onChip(c.id, c.target_npc)}
            title={view.characters.find((x) => x.id === c.target_npc)?.name}
          >
            {c.kind === 'present' ? '📎 ' : c.kind === 'bluff' ? '🎭 ' : ''}
            {c.label}
          </button>
        ))}
      </div>
      {interrogeeId ? (
        <form
          className="inputrow"
          onSubmit={(e) => {
            e.preventDefault()
            submit()
          }}
        >
          <input
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={locked ? '상대가 등을 돌렸다…' : '직접 질문 입력…'}
            disabled={busy || locked || out}
            maxLength={200}
            aria-label="직접 질문"
          />
          <button type="submit" disabled={busy || locked || out || !text.trim()}>질문</button>
          <button
            type="button"
            className="present"
            disabled={busy || locked || out || !ev}
            onClick={onPresent}
            title={ev ? `${ev.name} 제시` : '수첩에서 증거 카드를 먼저 고르세요'}
          >
            📎 제시{ev ? `: ${ev.name}` : ''}
          </button>
          <button type="button" className="bluff" disabled={busy || locked || out || view.bluff_claims.length === 0} onClick={onBluff}>
            🎭 블러핑
          </button>
        </form>
      ) : (
        <p className="muted small hint-line">인물을 눌러 심문하면 질문 입력창이 열립니다. 입력 없이도 이동·조사·증거 제시로 수사를 진행할 수 있습니다.</p>
      )}
      {out && <p className="warn small">오늘의 행동을 모두 썼습니다. "하루 끝내기"를 눌러 밤을 보내세요.</p>}
    </div>
  )
}

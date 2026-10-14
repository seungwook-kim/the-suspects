import { useRef, useState } from 'react'
import type { PlayerView, PublicCharacter } from '../api/types'
import { EvidenceCard } from './EvidenceCard'
import { chipText } from '../util/format'
import { Icon } from './Icon'
import { Popover } from './Popover'

interface Props {
  view: PlayerView
  npc: PublicCharacter
  busy: boolean
  locked: boolean // NPC 가 등을 돌림
  selectedEvidence: string | null
  onSelectEvidence: (id: string | null) => void
  onChip: (chipId: string, targetNpc: string) => void
  onAsk: (text: string) => void
  onPresent: (evidenceId: string) => void
  onBluff: () => void
  /** 휴대폰: 수첩 시트 열기 */
  onOpenNotebook?: () => void
  contraCount: number
  newContra: boolean
}

/** 심문 행동바: 추천 질문 · 직접 질문 · 증거 제시 · 블러핑. 막힌 버튼은 두 번째 줄에 이유를 쓴다(D13). */
export function ActionBar({ view, npc, busy, locked, selectedEvidence, onSelectEvidence, onChip, onAsk, onPresent, onBluff, onOpenNotebook, contraCount, newContra }: Props) {
  const [text, setText] = useState('')
  const [picking, setPicking] = useState(false)
  const presentRef = useRef<HTMLButtonElement>(null)
  const out = view.actions_left <= 0
  const blocked = busy ? '답을 기다리는 중' : locked ? '등을 돌렸다' : out ? '오늘 행동을 다 썼음' : null
  const askReason = blocked ?? (!text.trim() ? '질문을 입력하세요' : null)
  const bluffReason = blocked ?? (view.bluff_claims.length === 0 ? '쓸 주장이 없음' : null)
  // 추천 질문은 지금 심문 중인 사람 것만 보여 준다(다른 사람 것까지 섞이면 어지럽다)
  const chips = view.chips.filter((c) => c.target_npc === npc.id)

  const submit = () => {
    const t = text.trim()
    if (!t || askReason) return
    onAsk(t)
    setText('')
  }

  return (
    <section className="actionbar" aria-label="심문 행동">
      {chips.length > 0 && (
        <div className="chips-row">
          <span className="chips-label" id="chips-label">추천 질문</span>
          <div className="chips" aria-labelledby="chips-label">
            {chips.map((c) => (
              <button key={c.id} type="button" className="chip" disabled={!!blocked} onClick={() => onChip(c.id, c.target_npc)}>
                {c.kind === 'present' && <Icon name="paperclip" />}
                {c.kind === 'bluff' && <Icon name="mask-happy" />}
                {chipText(c.label, npc.name)}
              </button>
            ))}
          </div>
        </div>
      )}
      <div className="action-rows">
        <form
          className="ask-row"
          autoComplete="off"
          onSubmit={(e) => {
            e.preventDefault()
            submit()
          }}
        >
          <label className="sr-only" htmlFor="ask-input">직접 질문</label>
          <input
            id="ask-input"
            className="field"
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={locked ? '상대가 등을 돌렸다' : `${npc.name}에게 직접 질문`}
            disabled={!!blocked}
            maxLength={200}
          />
          <button type="submit" className="btn btn-cta" disabled={!!askReason}>
            <span className="btn-label"><Icon name="paper-plane-tilt" />질문</span>
            {askReason && <small className="btn-reason">{askReason}</small>}
          </button>
        </form>
        <div className="tool-row">
          {onOpenNotebook && (
            <button type="button" className="btn" onClick={onOpenNotebook}>
              <span className="btn-label"><Icon name="notebook" />수첩</span>
              <small className="btn-reason">{newContra ? `새 모순 ${contraCount}` : `모순 ${contraCount}`}</small>
            </button>
          )}
          <button
            ref={presentRef}
            type="button"
            className="btn"
            aria-expanded={picking}
            aria-haspopup="dialog"
            disabled={!!blocked}
            onClick={() => setPicking((v) => !v)}
          >
            <span className="btn-label"><Icon name="paperclip" />증거 제시</span>
            {blocked && <small className="btn-reason">{blocked}</small>}
          </button>
          <button type="button" className="btn" disabled={!!bluffReason} onClick={onBluff}>
            <span className="btn-label"><Icon name="mask-happy" />블러핑</span>
            {bluffReason && <small className="btn-reason">{bluffReason}</small>}
          </button>
        </div>
      </div>
      {picking && (
        <EvidencePicker
          view={view}
          npc={npc}
          anchorRef={presentRef}
          selected={selectedEvidence}
          onSelect={onSelectEvidence}
          onClose={() => setPicking(false)}
          onConfirm={(id) => {
            setPicking(false)
            onPresent(id)
          }}
        />
      )}
    </section>
  )
}

interface PickerProps {
  view: PlayerView
  npc: PublicCharacter
  anchorRef: React.RefObject<HTMLButtonElement | null>
  selected: string | null
  onSelect: (id: string | null) => void
  onClose: () => void
  onConfirm: (id: string) => void
}

/** 증거 제시 목록: 증거만 담는다(D18). 카드 고르기 → 확정 두 번이면 끝. 휴대폰에서는 같은 요소가 하단 시트. */
function EvidencePicker({ view, npc, anchorRef, selected, onSelect, onClose, onConfirm }: PickerProps) {
  const ev = selected ? view.evidence.find((e) => e.id === selected) : null
  return (
    <Popover anchorRef={anchorRef} onClose={onClose} label={`${npc.name}에게 제시할 증거 고르기`} align="end">
      <div className="drawer-head">
        <h2>{npc.name}에게 제시할 증거</h2>
        <button type="button" className="btn btn-icon" onClick={onClose} aria-label="닫기">
          <span className="btn-label"><Icon name="x" /></span>
        </button>
      </div>
      <div className="pop-body">
        {view.evidence.length === 0 ? (
          <p className="empty-note">가진 증거가 없습니다. 장소를 조사해 보세요.</p>
        ) : (
          <div className="card-list">
            {view.evidence.map((e) => (
              <EvidenceCard key={e.id} evidence={e} selected={selected === e.id} clamp={80} onClick={() => onSelect(selected === e.id ? null : e.id)} />
            ))}
          </div>
        )}
      </div>
      <div className="pop-foot">
        <button type="button" className="btn btn-cta" disabled={!ev} onClick={() => ev && onConfirm(ev.id)}>
          <span className="btn-label"><Icon name="paperclip-fill" />{ev ? `이 증거를 ${npc.name}에게 제시` : '증거 제시'}</span>
          {!ev && <small className="btn-reason">증거를 고르세요</small>}
        </button>
      </div>
    </Popover>
  )
}

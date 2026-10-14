import type { DragEvent } from 'react'
import type { PublicEvidence } from '../api/types'
import { Icon } from './Icon'

interface Props {
  evidence: PublicEvidence
  /** 고른 카드: 굵은 잉크 테두리 + 아래 줄 글자(기본 "제시 대기") */
  selected?: boolean
  selectedLabel?: string
  /** 내용 줄을 보여 줄지 (기본 true) */
  showBody?: boolean
  /** 내용을 이 글자 수에서 자른다 */
  clamp?: number
  disabled?: boolean
  onClick?: () => void
  /** 데스크톱 보너스: 초상화로 끌어다 놓기 */
  draggable?: boolean
  onDragStart?: (e: DragEvent<HTMLElement>) => void
}

/** 증거 카드 한 장. 수첩·증거 제시 목록·최종 추리·블러핑이 같은 모양을 쓴다(D18). 누를 수 있으면 button, 아니면 article. */
export function EvidenceCard({ evidence: e, selected, selectedLabel = '제시 대기', showBody = true, clamp, disabled, onClick, draggable, onDragStart }: Props) {
  const body = clamp && e.content.length > clamp ? `${e.content.slice(0, clamp)}…` : e.content
  const inner = (
    <>
      <span className="card-head">
        <strong>{e.name}</strong>
        <span className="kind">{e.kind}</span>
      </span>
      {showBody && <span className="card-body">{body}</span>}
      <span className="pending-label">
        <Icon name="paperclip-fill" />
        {selectedLabel}
      </span>
    </>
  )
  const cls = `evidence-card${selected ? ' selected' : ''}`
  if (!onClick) {
    return (
      <article className={cls} draggable={draggable} onDragStart={onDragStart}>
        {inner}
      </article>
    )
  }
  return (
    <button type="button" className={cls} aria-pressed={!!selected} disabled={disabled} onClick={onClick} draggable={draggable} onDragStart={onDragStart}>
      {inner}
    </button>
  )
}

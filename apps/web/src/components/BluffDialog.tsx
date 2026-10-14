import { useEffect, useRef, useState } from 'react'
import type { PlayerView } from '../api/types'
import { EvidenceCard } from './EvidenceCard'
import { Icon } from './Icon'

interface Props {
  view: PlayerView
  npcId: string
  initialEvidence: string | null
  onCancel: () => void
  onConfirm: (claimId: string, subject: string | null, evidenceIds: string[]) => void
}

/** 블러핑 흐름: 1) 주장 종류 선택 -> 2) 근거 증거 카드 선택 -> 확정 */
export function BluffDialog({ view, npcId, initialEvidence, onCancel, onConfirm }: Props) {
  const [step, setStep] = useState<1 | 2>(1)
  const [claim, setClaim] = useState<string | null>(null)
  const [subject, setSubject] = useState<string>('')
  const [picked, setPicked] = useState<string[]>(initialEvidence ? [initialEvidence] : [])
  const ref = useRef<HTMLDivElement>(null)
  const cancelRef = useRef(onCancel)
  cancelRef.current = onCancel
  const target = view.characters.find((c) => c.id === npcId)
  const toggle = (id: string) => setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]))
  const others = view.characters.filter((c) => c.id !== npcId)

  // 열리면 첫 단추로 포커스, Esc 로 닫기, 닫히면 연 단추로 포커스를 돌려준다
  useEffect(() => {
    const prev = document.activeElement as HTMLElement | null
    ref.current?.querySelector<HTMLElement>('button, select')?.focus()
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') cancelRef.current()
    }
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('keydown', onKey)
      prev?.focus?.()
    }
  }, [])

  return (
    <div className="modal-back" role="dialog" aria-modal="true" aria-labelledby="bluff-title">
      <div ref={ref} className="paper modal">
        <h3 id="bluff-title"><Icon name="mask-happy" />{target?.name}에게 블러핑</h3>
        <p className="muted small">사실이 아닌 주장을 던져 반응을 떠봅니다. 근거가 약하면 신뢰를 잃을 수 있어요.</p>
        {step === 1 && (
          <>
            <p className="section-title">1단계 · 어떤 주장을 할까?</p>
            <div className="choices" role="radiogroup" aria-label="주장">
              {view.bluff_claims.map((c) => (
                <button key={c.id} type="button" role="radio" aria-checked={claim === c.id} className="chip" onClick={() => setClaim(c.id)}>
                  {claim === c.id && <Icon name="check-circle" />}
                  {c.label}
                </button>
              ))}
            </div>
            <label className="field-label">
              주장 대상 (선택)
              <select className="field" value={subject} onChange={(e) => setSubject(e.target.value)}>
                <option value="">지정 안 함</option>
                {others.map((c) => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </select>
            </label>
            <div className="modal-actions">
              <button type="button" className="btn" onClick={onCancel}><span className="btn-label">취소</span></button>
              <button type="button" className="btn btn-cta" disabled={!claim} onClick={() => setStep(2)}>
                <span className="btn-label">다음: 근거 고르기</span>
                {!claim && <small className="btn-reason">주장을 고르세요</small>}
              </button>
            </div>
          </>
        )}
        {step === 2 && (
          <>
            <p className="section-title">2단계 · 근거로 삼을 증거 카드 (여러 장 가능)</p>
            {view.evidence.length === 0 && <p className="muted">가진 증거가 없습니다. 근거 없이 떠볼 수도 있어요.</p>}
            <div className="card-list bluff-cards">
              {view.evidence.map((e) => (
                <EvidenceCard key={e.id} evidence={e} showBody={false} selected={picked.includes(e.id)} selectedLabel="근거로 씀" onClick={() => toggle(e.id)} />
              ))}
            </div>
            <div className="modal-actions">
              <button type="button" className="btn" onClick={() => setStep(1)}><span className="btn-label"><Icon name="arrow-left" />뒤로</span></button>
              <button type="button" className="btn" onClick={onCancel}><span className="btn-label">취소</span></button>
              <button type="button" className="btn btn-cta" onClick={() => claim && onConfirm(claim, subject || null, picked)}>
                <span className="btn-label"><Icon name="mask-happy" />블러핑 던지기 ({picked.length}장)</span>
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

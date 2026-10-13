import { useState } from 'react'
import type { PlayerView } from '../api/types'

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
  const target = view.characters.find((c) => c.id === npcId)
  const toggle = (id: string) => setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]))
  const others = view.characters.filter((c) => c.id !== npcId)

  return (
    <div className="modal-back" role="dialog" aria-modal="true" aria-label="블러핑">
      <div className="modal">
        <h3>🎭 {target?.name}에게 블러핑</h3>
        <p className="muted small">사실이 아닌 주장을 던져 반응을 떠봅니다. 근거가 약하면 신뢰를 잃을 수 있어요.</p>
        {step === 1 && (
          <>
            <h4>1. 어떤 주장을 할까?</h4>
            <div className="choices">
              {view.bluff_claims.map((c) => (
                <button key={c.id} className={`choice${claim === c.id ? ' on' : ''}`} onClick={() => setClaim(c.id)}>
                  {c.label}
                </button>
              ))}
            </div>
            <label className="field">
              <span className="small muted">주장 대상 (선택)</span>
              <select value={subject} onChange={(e) => setSubject(e.target.value)}>
                <option value="">지정 안 함</option>
                {others.map((c) => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </select>
            </label>
            <div className="modal-actions">
              <button onClick={onCancel}>취소</button>
              <button className="primary" disabled={!claim} onClick={() => setStep(2)}>다음: 근거 고르기</button>
            </div>
          </>
        )}
        {step === 2 && (
          <>
            <h4>2. 근거로 삼을 증거 카드 (여러 장 가능)</h4>
            {view.evidence.length === 0 && <p className="muted">가진 증거가 없습니다. 근거 없이 떠볼 수도 있어요.</p>}
            <div className="choices cards">
              {view.evidence.map((e) => (
                <button key={e.id} className={`choice ev${picked.includes(e.id) ? ' on' : ''}`} onClick={() => toggle(e.id)}>
                  <b>{e.name}</b>
                </button>
              ))}
            </div>
            <div className="modal-actions">
              <button onClick={() => setStep(1)}>← 뒤로</button>
              <button onClick={onCancel}>취소</button>
              <button className="primary" onClick={() => claim && onConfirm(claim, subject || null, picked)}>
                블러핑 던지기 ({picked.length}장)
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

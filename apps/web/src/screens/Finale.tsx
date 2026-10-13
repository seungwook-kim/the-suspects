import { useCallback, useState } from 'react'
import { DialogueBox } from '../components/DialogueBox'
import { Overlays } from '../components/Overlays'
import { Portrait } from '../character/Portrait'
import { FINALE_STAGES, FINALE_STAGE_LABEL } from '../api/types'
import type { GameApi } from '../state/useGame'
import { endingText } from '../util/format'

interface Props {
  g: GameApi
  onBack: () => void
  onResult: () => void
}

export function Finale({ g, onBack, onResult }: Props) {
  const { state, dispatch, finaleStep } = g
  const view = state.view!
  const f = state.finale
  const ending = state.ending?.ending ?? (view.ending !== 'none' ? view.ending : null)
  const [pick, setPick] = useState<string | null>(null)
  const [selEv, setSelEv] = useState<string | null>(null)
  const [typing, setTyping] = useState(false)
  const onTyping = useCallback((t: boolean) => setTyping(t), [])
  const busy = state.running

  // 선택 순서가 단서가 되지 않도록 이름순으로 보여 준다
  const suspects = [...view.characters].sort((a, b) => a.name.localeCompare(b.name, 'ko'))
  const accused = f ? view.characters.find((c) => c.id === f.accused_id) : null
  const line = state.dialogue
  const emotion = accused ? state.emotions[accused.id] ?? accused.emotion : 'neutral'

  // 1) 범인 지목
  if (!f && !ending) {
    return (
      <div className="screen finale">
        <p className="eyebrow">최종 추리 쇼</p>
        <h1>범인은 이 중에 있다</h1>
        <p className="muted">용의자를 모두 모았다. 한 명을 지목하면 기회·수단·동기를 증거로 밝혀야 한다. 목숨은 3개.</p>
        <div className="suspect-grid">
          {suspects.map((c) => (
            <button key={c.id} className={`suspect${pick === c.id ? ' on' : ''}`} onClick={() => setPick(c.id)}>
              <Portrait seed={c.face_seed} appearance={c.appearance} emotion={state.emotions[c.id] ?? c.emotion} width={120} still />
              <strong>{c.name}</strong>
              <span className="muted small">{c.role}</span>
            </button>
          ))}
        </div>
        <div className="brief-actions">
          <button onClick={onBack}>← 더 수사하기</button>
          <button className="primary big" disabled={!pick || busy} onClick={() => pick && void finaleStep({ type: 'start', accused_id: pick })}>
            이 사람을 지목한다
          </button>
        </div>
        <Overlays state={state} dispatch={dispatch} />
      </div>
    )
  }

  const stage = f?.stage ?? 'done'
  const filled = f?.filled ?? []
  const lives = f?.lives ?? 0
  const evidence = view.evidence

  return (
    <div className="screen finale show">
      <p className="eyebrow">최종 추리 쇼</p>
      <div className="finale-top">
        <div className="lives" aria-label={`목숨 ${lives}개`}>
          {[0, 1, 2].map((i) => (
            <span key={i} className={i < lives ? 'on' : 'off'}>♥</span>
          ))}
        </div>
        <ol className="steps">
          {FINALE_STAGES.map((s) => (
            <li key={s} className={filled.includes(s) ? 'done' : stage === s ? 'now' : ''}>
              {filled.includes(s) ? '✔ ' : ''}
              {FINALE_STAGE_LABEL[s]}
            </li>
          ))}
        </ol>
      </div>

      {accused && (
        <div className={`finale-stage${f?.last === 'wrong' ? ' hit' : ''}`}>
          <Portrait seed={accused.face_seed} appearance={accused.appearance} emotion={emotion} speaking={typing} width={220} />
          <div>
            <div className="nameplate"><strong>{accused.name}</strong> <span>{accused.role}</span></div>
            {line ? (
              <DialogueBox key={line.messageId} line={line} speakerName={accused.name} onTyping={onTyping} />
            ) : (
              <div className="dialogue empty"><p>…</p></div>
            )}
          </div>
        </div>
      )}

      {f?.last === 'correct' && !ending && <p className="ok-note">✔ 맞다! 다음 단계로.</p>}
      {f?.last === 'wrong' && !ending && <p className="warn">✖ 증거가 맞지 않는다. 목숨이 하나 줄었다.</p>}

      {!ending && stage !== 'done' && (
        <section className="finale-ev">
          <h3>{FINALE_STAGE_LABEL[stage]}를 밝힐 증거를 제시하세요</h3>
          <div className="ev-row">
            {evidence.map((e) => (
              <button key={e.id} className={`ev-card${selEv === e.id ? ' selected' : ''}`} onClick={() => setSelEv(e.id)} disabled={busy}>
                <strong>{e.name}</strong>
                <span className="muted small">{e.content.slice(0, 54)}{e.content.length > 54 ? '…' : ''}</span>
              </button>
            ))}
          </div>
          <button
            className="primary big"
            disabled={!selEv || busy}
            onClick={() => {
              if (selEv) void finaleStep({ type: 'present', stage, evidence_id: selEv })
              setSelEv(null)
            }}
          >
            📎 증거 제시
          </button>
        </section>
      )}

      {!ending && stage === 'done' && (
        <div className="brief-actions">
          <button className="primary big" disabled={busy} onClick={() => void finaleStep({ type: 'confirm' })}>
            추리 확정 ▶
          </button>
        </div>
      )}

      {ending && (
        <section className={`ending ${ending}`}>
          <h2>{endingText(ending).title}</h2>
          <p>{endingText(ending).body}</p>
          <button className="primary big" onClick={onResult} disabled={busy}>결과 카드 보기 ▶</button>
        </section>
      )}
      <Overlays state={state} dispatch={dispatch} />
    </div>
  )
}

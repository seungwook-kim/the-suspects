import { useCallback, useState } from 'react'
import type { CSSProperties } from 'react'
import { DialogueBox } from '../components/DialogueBox'
import { EvidenceCard } from '../components/EvidenceCard'
import { Icon } from '../components/Icon'
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

const MAX_LIVES = 3

/** 남은 기회 칸 + 글자 ("남은 기회 2/3"). 칸만으로는 알리지 않는다. */
function LivesCells({ lives }: { lives: number }) {
  return (
    <span className="fin-lives">
      <span className="cells is-lg" aria-hidden="true">
        {Array.from({ length: MAX_LIVES }, (_, i) => (
          <i key={i} className={i < lives ? 'on' : ''} />
        ))}
      </span>
      <span className="fin-lives-text">
        남은 기회 <b>{lives}/{MAX_LIVES}</b>
      </span>
    </span>
  )
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
      <div className="screen finale fin-pick">
        <p className="eyebrow">최종 추리 쇼</p>
        <h1 className="fin-title">지목할 사람을 고르세요</h1>
        <p className="fin-lead">용의자 {suspects.length}명을 이름순으로 놓았습니다. 한 명을 지목하면 기회 · 수단 · 동기를 증거로 밝혀야 합니다.</p>
        <ul className="fin-suspects" aria-label="용의자">
          {suspects.map((c) => (
            <li key={c.id}>
              <button type="button" className="person is-tile" aria-pressed={pick === c.id} onClick={() => setPick(c.id)}>
                <div className="person-photo">
                  <Portrait seed={c.face_seed} appearance={c.appearance} emotion={state.emotions[c.id] ?? c.emotion} still portraitUrl={c.portrait_url} portraitEmotions={c.portrait_emotions} name={c.name} />
                </div>
                <span className="person-name">{c.name}</span>
                <span className="person-role">{c.role}</span>
                <span className="sel-label"><Icon name="check-circle" />지목</span>
              </button>
            </li>
          ))}
        </ul>
        <p className="notice fin-hint">
          <Icon name="info" />
          <span>지목하면 기회 · 수단 · 동기를 증거로 밝혀야 합니다. 남은 기회 {MAX_LIVES}번이고, 증거가 맞지 않으면 1번씩 줄어듭니다.</span>
        </p>
        <div className="fin-bar">
          <div className="actions">
            <button type="button" className="btn" onClick={onBack}>
              <span className="btn-label"><Icon name="arrow-left" />더 수사하기</span>
            </button>
            <button type="button" className="btn btn-cta btn-lg" disabled={!pick || busy} onClick={() => pick && void finaleStep({ type: 'start', accused_id: pick })}>
              <span className="btn-label"><Icon name="seal-check" />이 사람을 지목한다</span>
              {!pick && <small className="btn-reason">용의자를 고르세요</small>}
            </button>
          </div>
        </div>
        <Overlays state={state} dispatch={dispatch} />
      </div>
    )
  }

  const stage = f?.stage ?? 'done'
  const filled = f?.filled ?? []
  const lives = f?.lives ?? 0
  const evidence = view.evidence
  const last = f?.last?.result

  // 3) 엔딩: 사건 기록철의 결론 페이지
  if (ending) {
    const text = endingText(ending)
    return (
      <div className="screen finale fin-end">
        <p className="eyebrow">최종 추리 쇼</p>
        <article className={`paper has-tab fin-conclusion ending ${ending}`}>
          <span className="folder-tab">결론</span>
          <h1 className="fin-title">{text.title}</h1>
          {accused && <p className="fin-conclusion-who">지목한 사람: <b>{accused.name}</b> <span>{accused.role}</span></p>}
          <p className="fin-conclusion-body">{text.body}</p>
          <div className="actions">
            <button type="button" className="btn btn-cta btn-lg" onClick={onResult} disabled={busy}>
              <span className="btn-label"><Icon name="notebook" />결과 카드 보기</span>
            </button>
          </div>
        </article>
        <Overlays state={state} dispatch={dispatch} />
      </div>
    )
  }

  // 2) 증거 제시 쇼 / 추리 확정
  return (
    <div className="screen finale fin-show">
      <p className="eyebrow">최종 추리 쇼</p>
      <div className="fin-build">
        <article className="paper has-tab fin-dossier" aria-label="최종 추리 조서">
          <span className="folder-tab">최종 추리 조서</span>
          {accused && (
            <div className="fin-who">
              <div className="person-photo" style={{ '--photo-w': '136px' } as CSSProperties}>
                <Portrait seed={accused.face_seed} appearance={accused.appearance} emotion={emotion} speaking={typing} portraitUrl={accused.portrait_url} portraitEmotions={accused.portrait_emotions} name={accused.name} eager />
              </div>
              <div className="fin-id">
                <h1 className="fin-title">{accused.name}</h1>
                <p className="fin-role">{accused.role}</p>
                <div aria-live="polite"><LivesCells lives={lives} /></div>
              </div>
            </div>
          )}

          <ol className="fin-steps" aria-label="밝혀야 할 세 가지">
            {FINALE_STAGES.map((s) => {
              const done = filled.includes(s)
              const now = !done && stage === s
              return (
                <li key={s} className={done ? 'is-done' : now ? 'is-now' : ''} aria-current={now ? 'step' : undefined}>
                  <span className="fin-step-label">{FINALE_STAGE_LABEL[s]}</span>
                  <span className="fin-step-state">
                    {done ? <><Icon name="check-circle" />밝힘</> : now ? '지금 밝힐 차례' : '대기'}
                  </span>
                </li>
              )
            })}
          </ol>

          {accused && (
            <div className="fin-speech">
              {line ? (
                <DialogueBox key={line.messageId} line={line} speakerName={accused.name} onTyping={onTyping} />
              ) : (
                <div className="dialogue empty"><span className="dialogue-who">{accused.name}</span><p className="dialogue-said">…</p></div>
              )}
            </div>
          )}

          <div aria-live="polite">
            {last === 'correct' && (
              <p className="fin-note"><Icon name="check-circle" /><span><b>맞음.</b> 증거가 들어맞았습니다. 다음 단계로 갑니다.</span></p>
            )}
            {(last === 'wrong' || last === 'rebutted') && (
              <p className="fin-note is-wrong"><Icon name="warning-circle" /><span><b>틀림.</b> 증거가 맞지 않습니다. 남은 기회가 하나 줄어 {lives}/{MAX_LIVES}이 되었습니다.</span></p>
            )}
          </div>

          {stage === 'done' && (
            <div className="actions">
              <button type="button" className="btn btn-cta btn-lg" disabled={busy} onClick={() => void finaleStep({ type: 'confirm' })}>
                <span className="btn-label"><Icon name="seal-check" />추리 확정</span>
              </button>
            </div>
          )}
        </article>

        {stage !== 'done' && (
          <section className="paper fin-ev" aria-labelledby="fin-ev-title">
            <header className="fin-ev-head">
              <h2 id="fin-ev-title">{FINALE_STAGE_LABEL[stage]}: 밝힐 증거를 제시하세요</h2>
              <p>증거 {evidence.length}개 중 하나를 고르세요.</p>
            </header>
            <div className="card-list">
              {evidence.map((e) => (
                <EvidenceCard key={e.id} evidence={e} selected={selEv === e.id} clamp={80} disabled={busy} onClick={() => setSelEv(e.id)} />
              ))}
            </div>
            <div className="fin-bar">
              <button
                type="button"
                className="btn btn-cta btn-lg"
                disabled={!selEv || busy}
                onClick={() => {
                  if (selEv) void finaleStep({ type: 'present', stage, evidence_id: selEv })
                  setSelEv(null)
                }}
              >
                <span className="btn-label"><Icon name="paperclip" />증거 제시</span>
                {!selEv && <small className="btn-reason">증거를 고르세요</small>}
              </button>
            </div>
          </section>
        )}
      </div>
      <Overlays state={state} dispatch={dispatch} />
    </div>
  )
}

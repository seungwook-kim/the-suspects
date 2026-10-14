import { useState } from 'react'
import type { PlayerView, SourceItem } from '../api/types'
import { formatDayTime } from '../util/format'
import { EvidenceCard } from './EvidenceCard'
import { Icon } from './Icon'

export type NotebookTab = 'evidence' | 'statements' | 'contradictions' | 'gauge'

interface Props {
  view: PlayerView
  tab: NotebookTab
  onTab: (t: NotebookTab) => void
  newContradictions: string[]
  selectedEvidence: string | null
  onSelectEvidence: (id: string | null) => void
  onSeen: () => void
  loadSources: (statementId: string) => Promise<SourceItem[]>
  /** 심문 중이면 증거 카드를 골라 "증거 제시"에 쓸 수 있다 */
  canPresent: boolean
  onFinale: () => void
  /** 휴대폰 시트일 때 닫기 단추 */
  onClose?: () => void
}

const TAB_LABEL: Record<NotebookTab, string> = { evidence: '증거', statements: '진술', contradictions: '모순', gauge: '충분도' }

/** 수첩: 증거·진술·모순·충분도. 새 모순이 생겨도 탭을 강제로 바꾸지 않는다(토스트로 알림, D10/회의 결정). */
export function NotebookPanel({ view, tab, onTab, newContradictions, selectedEvidence, onSelectEvidence, onSeen, loadSources, canPresent, onFinale, onClose }: Props) {
  const [openStatement, setOpenStatement] = useState<string | null>(null)
  const [sources, setSources] = useState<Record<string, SourceItem[] | 'loading' | 'error'>>({})
  const nb = view.notebook

  const toggleStatement = (id: string) => {
    const open = openStatement === id
    setOpenStatement(open ? null : id)
    if (!open && !Array.isArray(sources[id])) {
      setSources((m) => ({ ...m, [id]: 'loading' }))
      loadSources(id)
        .then((list) => setSources((m) => ({ ...m, [id]: list })))
        .catch(() => setSources((m) => ({ ...m, [id]: 'error' })))
    }
  }
  const nameOf = (id: string) => view.characters.find((c) => c.id === id)?.name ?? id
  const evOf = (id: string) => view.evidence.find((e) => e.id === id)
  const stOf = (id: string) => nb.statements.find((s) => s.id === id)
  const counts: Record<NotebookTab, number | null> = {
    evidence: view.evidence.length,
    statements: nb.statements.length,
    contradictions: nb.contradictions.length,
    gauge: null,
  }
  const pick = (t: NotebookTab) => {
    onTab(t)
    if (t === 'contradictions') onSeen()
  }

  return (
    <section className="notebook" aria-labelledby="nb-title">
      <div className="drawer-head">
        <h2 id="nb-title">수첩</h2>
        {onClose && (
          <button type="button" className="btn btn-icon" onClick={onClose} aria-label="수첩 닫기">
            <span className="btn-label"><Icon name="x" /></span>
          </button>
        )}
      </div>
      <div className="tabs" role="tablist" aria-label="수첩 탭">
        {(Object.keys(TAB_LABEL) as NotebookTab[]).map((t) => (
          <button
            key={t}
            type="button"
            role="tab"
            id={`nb-tab-${t}`}
            aria-controls={`nb-panel-${t}`}
            aria-selected={tab === t}
            tabIndex={tab === t ? 0 : -1}
            className="tab"
            onClick={() => pick(t)}
          >
            {TAB_LABEL[t]}
            {counts[t] !== null && (
              <span className={`tab-badge${t === 'contradictions' && newContradictions.length > 0 ? ' is-new' : ''}`}>
                {counts[t]}
                {t === 'contradictions' && newContradictions.length > 0 && <span className="sr-only">, 새 모순 있음</span>}
              </span>
            )}
          </button>
        ))}
      </div>

      <div className="nb-body" role="tabpanel" id={`nb-panel-${tab}`} aria-labelledby={`nb-tab-${tab}`}>
        {tab === 'evidence' && (
          <>
            {view.evidence.length === 0 ? (
              <p className="empty-note">아직 모은 증거가 없습니다. 장소를 조사해 보세요.</p>
            ) : (
              <p className="nb-note">
                {canPresent ? '카드를 눌러 고르면 "증거 제시"에서 바로 쓸 수 있습니다. 사진 위로 끌어다 놓아도 됩니다.' : '증거 제시는 심문 중에 합니다. 여기서는 모은 증거를 읽습니다.'}
              </p>
            )}
            <div className="card-list">
              {view.evidence.map((e) =>
                canPresent ? (
                  <EvidenceCard
                    key={e.id}
                    evidence={e}
                    selected={selectedEvidence === e.id}
                    onClick={() => onSelectEvidence(selectedEvidence === e.id ? null : e.id)}
                    draggable
                    onDragStart={(ev) => {
                      ev.dataTransfer.setData('text/evidence', e.id)
                      ev.dataTransfer.effectAllowed = 'move'
                      onSelectEvidence(e.id)
                    }}
                  />
                ) : (
                  <EvidenceCard key={e.id} evidence={e} />
                ),
              )}
            </div>
          </>
        )}

        {tab === 'statements' && (
          <div className="card-list">
            {nb.statements.length === 0 && <p className="empty-note">아직 진술이 없습니다. 인물에게 질문해 보세요.</p>}
            {[...nb.statements].reverse().map((s) => {
              const contras = nb.contradictions.filter((c) => c.statement_id === s.id)
              const open = openStatement === s.id
              const src = sources[s.id]
              return (
                <article key={s.id} className={`st-card${contras.length ? ' contra' : ''}${open ? ' is-open' : ''}`}>
                  <div className="card-head">
                    <span className="who">{nameOf(s.npc_id)}</span>
                    <span className="mono muted small">{formatDayTime(Math.floor(s.game_time / 1440) + 1, s.game_time)}</span>
                  </div>
                  <p className="card-body">
                    {contras.length ? <span className="claim is-flagged">&ldquo;{s.content}&rdquo;</span> : <>&ldquo;{s.content}&rdquo;</>}
                  </p>
                  {contras.map((c) => (
                    <p key={c.id} className="flag-line">
                      <span className="stamp is-lead">모순</span>
                      {evOf(c.evidence_id)?.name ?? '증거'}와 어긋남
                    </p>
                  ))}
                  <button type="button" className="btn btn-sm st-toggle" aria-expanded={open} onClick={() => toggleStatement(s.id)}>
                    <span className="btn-label"><Icon name={open ? 'caret-up' : 'caret-down'} />{open ? '출처 접기' : '출처 보기'}</span>
                  </button>
                  {open && (
                    <div className="source">
                      {src === 'loading' && <p className="muted">원문을 불러오는 중…</p>}
                      {src === 'error' && <p className="warn-text"><Icon name="warning-circle" />원문을 불러오지 못했습니다.</p>}
                      {Array.isArray(src) && src.length === 0 && <p className="muted">열람할 수 있는 원문이 없습니다.</p>}
                      {Array.isArray(src) &&
                        src.map((it, i) => (
                          <div key={i}>
                            <p><span className="kind">{it.kind}</span> <strong>{it.title}</strong></p>
                            <p>{it.content}</p>
                          </div>
                        ))}
                    </div>
                  )}
                </article>
              )
            })}
          </div>
        )}

        {tab === 'contradictions' && (
          <div className="card-list">
            {nb.contradictions.length === 0 && <p className="empty-note">진술과 증거가 어긋나는 곳을 찾으면 여기에 "모순" 도장과 함께 정리됩니다.</p>}
            {[...nb.contradictions].reverse().map((c) => {
              const st = stOf(c.statement_id)
              const e = evOf(c.evidence_id)
              return (
                <article key={c.id} className={`contra-card${newContradictions.includes(c.id) ? ' is-fresh' : ''}`}>
                  <p><span className="stamp is-lead">모순</span><span className="title hl">{st ? nameOf(st.npc_id) : '누군가'}의 진술</span></p>
                  {st && <p className="card-body">진술: &ldquo;{st.content}&rdquo;</p>}
                  {e && <p className="card-body">증거: {e.name}</p>}
                  {c.note && <p className="card-body muted">{c.note}</p>}
                </article>
              )
            })}
          </div>
        )}

        {tab === 'gauge' && (
          <>
            <p className="nb-note">용의자별 증거 충분도 (5칸). 범인을 밝힐 증거가 모였다고 생각되면 최종 추리로 넘어가세요.</p>
            <div className="gauge-list">
              {view.characters.map((c) => {
                const g = view.sufficiency_gauge[c.id] ?? 0
                return (
                  <div key={c.id} className="gauge-row">
                    <span>{c.name}</span>
                    <span className="cells" role="img" aria-label={`충분도 ${g}/5`}>
                      {[0, 1, 2, 3, 4].map((i) => (
                        <i key={i} className={i < g ? 'on' : ''} />
                      ))}
                    </span>
                    <span className="mono small" aria-hidden="true">{g}/5</span>
                  </div>
                )
              })}
            </div>
            <div className="nb-foot">
              <button type="button" className="btn" onClick={onFinale}>
                <span className="btn-label"><Icon name="seal-check" />최종 추리로</span>
                <small className="btn-reason">되돌릴 수 없음</small>
              </button>
            </div>
          </>
        )}
      </div>
    </section>
  )
}

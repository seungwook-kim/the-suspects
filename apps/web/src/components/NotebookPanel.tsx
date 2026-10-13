import { useEffect, useState } from 'react'
import type { PlayerView, SourceItem } from '../api/types'
import { formatDayTime } from '../util/format'

type Tab = 'evidence' | 'statements' | 'contradictions' | 'gauge'

interface Props {
  view: PlayerView
  newContradictions: string[]
  selectedEvidence: string | null
  onSelectEvidence: (id: string | null) => void
  onSeen: () => void
  loadSources: (statementId: string) => Promise<SourceItem[]>
}

export function NotebookPanel({ view, newContradictions, selectedEvidence, onSelectEvidence, onSeen, loadSources }: Props) {
  const [tab, setTab] = useState<Tab>('evidence')
  const [openStatement, setOpenStatement] = useState<string | null>(null)
  const [openEvidence, setOpenEvidence] = useState<string | null>(null)
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

  // 새 모순이 생기면 모순 탭으로 잠깐 눈길을 끈다
  useEffect(() => {
    if (newContradictions.length) setTab('contradictions')
  }, [newContradictions.length])

  return (
    <section className="notebook" aria-label="수첩">
      <h2>수첩</h2>
      <div className="tabs" role="tablist">
        <TabBtn cur={tab} id="evidence" set={setTab}>증거 {view.evidence.length}</TabBtn>
        <TabBtn cur={tab} id="statements" set={setTab}>진술 {nb.statements.length}</TabBtn>
        <TabBtn cur={tab} id="contradictions" set={(t) => { setTab(t); onSeen() }} warn={newContradictions.length > 0}>
          모순 {nb.contradictions.length} {nb.contradictions.length > 0 && '⚠'}
        </TabBtn>
        <TabBtn cur={tab} id="gauge" set={setTab}>충분도</TabBtn>
      </div>

      <div className="nb-body">
        {tab === 'evidence' && (
          <>
            {view.evidence.length === 0 && <p className="muted">아직 모은 증거가 없습니다. 장소를 조사해 보세요.</p>}
            <p className="muted small">{view.evidence.length > 0 && '카드를 눌러 선택하고, 인물에게 "제시"하거나 초상화로 끌어다 놓으세요.'}</p>
            {view.evidence.map((e) => (
              <article
                key={e.id}
                className={`ev-card${selectedEvidence === e.id ? ' selected' : ''}`}
                draggable
                onDragStart={(ev) => {
                  ev.dataTransfer.setData('text/evidence', e.id)
                  ev.dataTransfer.effectAllowed = 'move'
                  onSelectEvidence(e.id)
                }}
                onClick={() => {
                  onSelectEvidence(selectedEvidence === e.id ? null : e.id)
                  setOpenEvidence(openEvidence === e.id ? null : e.id)
                }}
              >
                <header>
                  <strong>{e.name}</strong>
                  <span className="kind">{e.kind}</span>
                </header>
                {(openEvidence === e.id || selectedEvidence === e.id) && <p>{e.content}</p>}
              </article>
            ))}
          </>
        )}

        {tab === 'statements' && (
          <>
            {nb.statements.length === 0 && <p className="muted">아직 진술이 없습니다. 인물에게 질문해 보세요.</p>}
            {nb.statements.map((s) => {
              const contra = nb.contradictions.some((c) => c.statement_id === s.id)
              const open = openStatement === s.id
              return (
                <article
                  key={s.id}
                  className={`st-card${contra ? ' contra' : ''}`}
                  onClick={() => toggleStatement(s.id)}
                >
                  <header>
                    <strong>{nameOf(s.npc_id)}</strong>
                    <span className="muted small">{formatDayTime(Math.floor(s.game_time / 1440) + 1, s.game_time)}</span>
                    {contra && <span className="warn">⚠</span>}
                  </header>
                  <p>&ldquo;{s.content}&rdquo;</p>
                  {open && (
                    <div className="source">
                      <b>출처</b>
                      {sources[s.id] === 'loading' && <p className="muted">원문을 불러오는 중…</p>}
                      {sources[s.id] === 'error' && <p className="warn">원문을 불러오지 못했습니다.</p>}
                      {Array.isArray(sources[s.id]) && (sources[s.id] as SourceItem[]).length === 0 && (
                        <p className="muted">열람할 수 있는 원문이 없습니다.</p>
                      )}
                      {Array.isArray(sources[s.id]) &&
                        (sources[s.id] as SourceItem[]).map((it, i) => (
                          <div key={i} className="source-item">
                            <p>
                              <span className="kind">{it.kind}</span> <strong>{it.title}</strong>
                            </p>
                            <p>{it.content}</p>
                          </div>
                        ))}
                      {nb.contradictions
                        .filter((c) => c.statement_id === s.id)
                        .map((c) => (
                          <p key={c.id} className="warn">
                            ⚠ {evOf(c.evidence_id)?.name ?? c.evidence_id}와(과) 어긋남
                          </p>
                        ))}
                    </div>
                  )}
                </article>
              )
            })}
          </>
        )}

        {tab === 'contradictions' && (
          <>
            {nb.contradictions.length === 0 && <p className="muted">모순을 찾으면 여기에 ⚠ 표시로 정리됩니다.</p>}
            {nb.contradictions.map((c) => {
              const st = stOf(c.statement_id)
              const e = evOf(c.evidence_id)
              return (
                <article key={c.id} className={`contra-card${newContradictions.includes(c.id) ? ' fresh' : ''}`}>
                  <header>
                    <span className="warn">⚠</span>
                    <strong>{st ? nameOf(st.npc_id) : '진술'}의 말이 맞지 않는다</strong>
                  </header>
                  {st && <p>진술: &ldquo;{st.content}&rdquo;</p>}
                  {e && <p>증거: {e.name}</p>}
                  {c.note && <p className="muted">{c.note}</p>}
                </article>
              )
            })}
          </>
        )}

        {tab === 'gauge' && (
          <>
            <p className="muted small">용의자별 증거 충분도 (5칸)</p>
            {view.characters.map((c) => {
              const g = view.sufficiency_gauge[c.id] ?? 0
              return (
                <div key={c.id} className="gauge-row">
                  <span>{c.name}</span>
                  <span className="cells" aria-label={`${g}/5`}>
                    {[0, 1, 2, 3, 4].map((i) => (
                      <i key={i} className={i < g ? 'on' : ''} />
                    ))}
                  </span>
                </div>
              )
            })}
          </>
        )}
      </div>
    </section>
  )
}

function TabBtn({
  cur, id, set, children, warn,
}: {
  cur: Tab
  id: Tab
  set: (t: Tab) => void
  children: React.ReactNode
  warn?: boolean
}) {
  return (
    <button role="tab" aria-selected={cur === id} className={`tab${cur === id ? ' on' : ''}${warn ? ' alert' : ''}`} onClick={() => set(id)}>
      {children}
    </button>
  )
}

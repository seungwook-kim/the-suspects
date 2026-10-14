import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties } from 'react'
import type { PlayerView, PublicCharacter } from '../api/types'
import { Portrait } from '../character/Portrait'
import { ActionBar } from '../components/ActionBar'
import { BluffDialog } from '../components/BluffDialog'
import { Dossier } from '../components/Dossier'
import { Icon } from '../components/Icon'
import { MapPanel } from '../components/MapPanel'
import { NotebookPanel, type NotebookTab } from '../components/NotebookPanel'
import { Overlays } from '../components/Overlays'
import { Feed, PlaceCard } from '../components/PlaceCard'
import { Sheet } from '../components/Popover'
import { StatusStrip } from '../components/StatusStrip'
import type { GameApi } from '../state/useGame'
import { chipText } from '../util/format'
import { MQ_PHONE, MQ_WIDE, useMedia } from '../util/useMedia'

interface Props {
  g: GameApi
  theme: 'light' | 'dark'
  onToggleTheme: () => void
  onFinale: () => void
  onHome: () => void
  onAbout: () => void
}

/** 게임 화면. 수사(지도·장소 카드·수첩)와 심문(이 장소·조서·수첩 + 행동바) 두 모드를 오간다.
 * 1100px 이상 3열 / 721~1099px 2열(지도·이 장소는 서랍) / 720px 이하 한 열 + 하단 행동바 + 시트(D12). */
export function Main({ g, theme, onToggleTheme, onFinale, onHome, onAbout }: Props) {
  const { state, dispatch, act, endDay, save } = g
  const view = state.view!
  const wide = useMedia(MQ_WIDE)
  const phone = useMedia(MQ_PHONE)
  const [interrogee, setInterrogee] = useState<string | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [bluffing, setBluffing] = useState(false)
  const [side, setSide] = useState(false) // 지도 / 이 장소 서랍
  const [noteOpen, setNoteOpen] = useState(false) // 휴대폰 수첩 시트
  const [noteTab, setNoteTab] = useState<NotebookTab>('evidence')
  const [toasts, setToasts] = useState<{ id: number; kind: 'contra' | 'saved'; text: string }[]>([])
  const barRef = useRef<HTMLElement | null>(null)

  // NPC 가 말하면 그 사람과의 심문 장면으로 전환
  const speakerId = state.dialogue?.role === 'npc' ? state.dialogue.speakerId : null
  useEffect(() => {
    if (speakerId) setInterrogee(speakerId)
  }, [speakerId])

  // 심문 중인 사람이 다른 장소로 가 버렸다면(밤 이후 등) 장면을 닫는다
  const npc = interrogee ? (view.characters.find((c) => c.id === interrogee) ?? null) : null
  useEffect(() => {
    if (npc && npc.location_id !== view.player_location) setInterrogee(null)
  }, [npc, view.player_location])

  // 새 모순: 수첩 탭을 바꾸지 않고 토스트로 알린다
  const fresh = state.newContradictions
  const seenContra = useRef(0)
  useEffect(() => {
    if (fresh.length > seenContra.current) {
      const c = view.notebook.contradictions.find((x) => x.id === fresh[fresh.length - 1])
      const st = c && view.notebook.statements.find((s) => s.id === c.statement_id)
      const who = st ? view.characters.find((x) => x.id === st.npc_id)?.name : null
      const ev = c && view.evidence.find((e) => e.id === c.evidence_id)
      pushToast('contra', `${who ?? '누군가'}의 진술이 ${ev?.name ?? '증거'}와 어긋난다.`, 9000)
    }
    seenContra.current = fresh.length
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fresh.length])

  // 휴대폰 하단 행동바 높이 → 본문 아래 여백과 토스트 위치(--actionbar-h)
  useLayoutEffect(() => {
    const el = barRef.current
    const root = document.documentElement
    if (!el) {
      root.style.setProperty('--actionbar-h', '0px')
      return
    }
    const set = () => root.style.setProperty('--actionbar-h', `${Math.ceil(el.getBoundingClientRect().height)}px`)
    set()
    const ro = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(set) : null
    ro?.observe(el)
    return () => {
      ro?.disconnect()
      root.style.setProperty('--actionbar-h', '0px')
    }
  })

  const busy = state.running
  const locked = !!(interrogee && state.turnAway[interrogee])
  const nameOf = (id: string) => view.characters.find((c) => c.id === id)?.name ?? ''

  function pushToast(kind: 'contra' | 'saved', text: string, ms: number) {
    const id = Date.now() + Math.random()
    setToasts((t) => [...t.filter((x) => x.kind !== kind), { id, kind, text }])
    window.setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), ms)
  }
  const openContradictions = () => {
    setNoteTab('contradictions')
    dispatch({ kind: 'clear_new_contradictions' })
    setToasts((t) => t.filter((x) => x.kind !== 'contra'))
    if (phone) setNoteOpen(true)
  }

  const talk = (id: string) => {
    if (busy) return
    setInterrogee(id)
    setSide(false)
    dispatch({ kind: 'clear_dialogue' })
  }
  const leave = () => {
    setInterrogee(null)
    setSelected(null)
    setSide(false)
    dispatch({ kind: 'clear_dialogue' })
  }
  const move = (loc: string) => {
    if (busy || loc === view.player_location) return
    setInterrogee(null)
    setSelected(null)
    setSide(false)
    dispatch({ kind: 'clear_dialogue' })
    void act({ type: 'move', location_id: loc })
  }
  const ask = (npcId: string, text: string) => dispatch({ kind: 'asked', npcId, text })
  const present = (npcId: string, evidenceId: string) => {
    setSelected(null)
    ask(npcId, `증거 제시: ${view.evidence.find((e) => e.id === evidenceId)?.name ?? '증거'}`)
    void act({ type: 'present', npc_id: npcId, evidence_id: evidenceId })
  }
  const chip = (chipId: string, npcId: string) => {
    const c = view.chips.find((x) => x.id === chipId)
    setInterrogee(npcId)
    if (c) ask(npcId, c.kind === 'present' && c.evidence_id ? `증거 제시: ${view.evidence.find((e) => e.id === c.evidence_id)?.name ?? c.label}` : chipText(c.label, nameOf(npcId)))
    void act({ type: 'chip', chip_id: chipId })
  }
  const doSave = async () => {
    const r = await save()
    if (r) pushToast('saved', '저장했습니다.', 2500)
  }
  const contraCount = view.notebook.contradictions.length
  const notebook = (onClose?: () => void) => (
    <NotebookPanel
      view={view}
      tab={noteTab}
      onTab={setNoteTab}
      newContradictions={fresh}
      selectedEvidence={selected}
      onSelectEvidence={setSelected}
      onSeen={() => dispatch({ kind: 'clear_new_contradictions' })}
      loadSources={g.fetchSources}
      canPresent={!!npc}
      onFinale={onFinale}
      onClose={onClose}
    />
  )
  const sidePanel = (onClose?: () => void) =>
    npc ? (
      <HerePanel view={view} npc={npc} busy={busy} onTalk={talk} onLeave={leave} onClose={onClose} />
    ) : (
      <section className="map-section" aria-labelledby="map-title">
        <div className="drawer-head">
          <h2 id="map-title">지도</h2>
          {onClose && (
            <button type="button" className="btn btn-icon" onClick={onClose} aria-label="지도 닫기">
              <span className="btn-label"><Icon name="x" /></span>
            </button>
          )}
        </div>
        <p className="map-help">실선으로 이어진 칸을 눌러 이동합니다. 점은 그곳에 있는 사람입니다.</p>
        <MapPanel view={view} interrogeeId={interrogee} locked={busy} onMove={move} onTalk={talk} />
      </section>
    )

  return (
    <div className={`game ${npc ? 'is-interrogating' : 'is-investigating'}`}>
      <StatusStrip
        view={view}
        busy={busy}
        interrogating={!!npc}
        theme={theme}
        onOpenSide={wide ? undefined : phone && !npc ? undefined : () => setSide(true)}
        sideLabel={npc ? '이 장소' : '지도'}
        onBack={leave}
        onEndDay={() => void endDay()}
        onSave={() => void doSave()}
        onFinale={onFinale}
        onAbout={onAbout}
        onHome={onHome}
        onToggleTheme={onToggleTheme}
      />

      {wide && <aside className="paper side-col">{sidePanel()}</aside>}

      <main className="stage-col">
        {npc ? (
          <Dossier
            state={state}
            npc={npc}
            selectedEvidence={selected}
            busy={busy}
            compact={phone}
            onLeave={leave}
            onDropEvidence={present}
          />
        ) : (
          <PlaceCard state={state} busy={busy} onInvestigate={() => void act({ type: 'investigate', location_id: view.player_location })} onTalk={talk} onMove={move} onChip={chip} />
        )}
      </main>

      {!phone && <aside className="paper note-col">{notebook()}</aside>}

      {npc ? (
        <div ref={(el) => { barRef.current = el }} className="bar-slot">
          <ActionBar
            view={view}
            npc={npc}
            busy={busy}
            locked={locked}
            selectedEvidence={selected}
            onSelectEvidence={setSelected}
            onChip={chip}
            onAsk={(text) => {
              ask(npc.id, text)
              void act({ type: 'ask', npc_id: npc.id, text })
            }}
            onPresent={(evId) => present(npc.id, evId)}
            onBluff={() => setBluffing(true)}
            onOpenNotebook={phone ? () => setNoteOpen(true) : undefined}
            contraCount={contraCount}
            newContra={fresh.length > 0}
          />
        </div>
      ) : (
        phone && (
          <section ref={(el) => { barRef.current = el }} className="actionbar invest-bar" aria-label="수사 행동">
            <div className="tool-row">
              <button type="button" className="btn" onClick={() => setSide(true)}>
                <span className="btn-label"><Icon name="map-trifold" />지도</span>
              </button>
              <button type="button" className="btn" onClick={() => setNoteOpen(true)}>
                <span className="btn-label"><Icon name="notebook" />수첩</span>
                <small className="btn-reason">{fresh.length ? `새 모순 ${contraCount}` : `모순 ${contraCount}`}</small>
              </button>
              <button type="button" className="btn btn-cta" disabled={busy || view.actions_left <= 0} onClick={() => void act({ type: 'investigate', location_id: view.player_location })}>
                <span className="btn-label"><Icon name="magnifying-glass" />현장 조사</span>
                {(busy || view.actions_left <= 0) && <small className="btn-reason">{busy ? '진행 중' : '행동 없음'}</small>}
              </button>
            </div>
          </section>
        )
      )}

      {side && !wide && (
        <Sheet onClose={() => setSide(false)} label={npc ? '이 장소' : '지도'} side={phone ? 'bottom' : 'side'}>
          {sidePanel(() => setSide(false))}
        </Sheet>
      )}
      {noteOpen && phone && (
        <Sheet onClose={() => setNoteOpen(false)} label="수첩" className="note-sheet">
          {notebook(() => setNoteOpen(false))}
        </Sheet>
      )}

      {bluffing && npc && (
        <BluffDialog
          view={view}
          npcId={npc.id}
          initialEvidence={selected}
          onCancel={() => setBluffing(false)}
          onConfirm={(claim, subject, ev) => {
            setBluffing(false)
            setSelected(null)
            ask(npc.id, `블러핑: ${view.bluff_claims.find((c) => c.id === claim)?.label ?? ''}${subject ? ` (${nameOf(subject)})` : ''}`)
            void act({ type: 'bluff', npc_id: npc.id, claim_id: claim, claim_subject: subject, basis_evidence_ids: ev })
          }}
        />
      )}
      <Overlays state={state} dispatch={dispatch}>
        {toasts.map((t) =>
          t.kind === 'contra' ? (
            <aside key={t.id} className="toast is-contra">
              <b className="toast-title"><span className="stamp is-lead">모순</span>새 모순을 찾았다</b>
              <p>{t.text}</p>
              <div className="toast-actions">
                <button type="button" className="btn btn-sm" onClick={openContradictions}>
                  <span className="btn-label"><Icon name="notebook" />수첩에서 보기</span>
                </button>
              </div>
              <button type="button" className="btn btn-icon toast-close" onClick={() => setToasts((x) => x.filter((y) => y.id !== t.id))} aria-label="닫기">
                <span className="btn-label"><Icon name="x" /></span>
              </button>
            </aside>
          ) : (
            <aside key={t.id} className="toast">
              <b className="toast-title"><Icon name="check-circle" />{t.text}</b>
            </aside>
          ),
        )}
      </Overlays>
    </div>
  )
}

interface HereProps {
  view: PlayerView
  npc: PublicCharacter
  busy: boolean
  onTalk: (id: string) => void
  onLeave: () => void
  onClose?: () => void
}

/** 심문 중 왼쪽 열: 지금 장소와 그곳의 사람(다른 사람으로 바로 넘어가기), 단톡방 */
function HerePanel({ view, npc, busy, onTalk, onLeave, onClose }: HereProps) {
  const loc = view.locations.find((l) => l.id === view.player_location)
  const here = view.characters.filter((c) => c.location_id === view.player_location)
  return (
    <section className="here-panel" aria-labelledby="here-title">
      <div className="drawer-head">
        <h2 id="here-title">이 장소</h2>
        {onClose && (
          <button type="button" className="btn btn-icon" onClick={onClose} aria-label="이 장소 닫기">
            <span className="btn-label"><Icon name="x" /></span>
          </button>
        )}
      </div>
      <div className="here-body">
        <p className="here-name"><Icon name="map-trifold" />{loc?.name}</p>
        <div>
          <h3 className="section-title">이 장소에 있는 사람</h3>
          <ul className="here-people">
            {here.map((c) => (
              <li key={c.id}>
                <button
                  type="button"
                  className="person is-row"
                  style={{ '--photo-w': '48px' } as CSSProperties}
                  aria-pressed={c.id === npc.id}
                  disabled={busy && c.id !== npc.id}
                  onClick={() => c.id !== npc.id && onTalk(c.id)}
                >
                  <span className="person-photo">
                    <Portrait seed={c.face_seed} appearance={c.appearance} emotion="neutral" still portraitUrl={c.portrait_url} name={c.name} />
                  </span>
                  <span className="person-name">{c.name}</span>
                  <span className="person-role">{c.id === npc.id ? '심문 중' : c.role}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
        <button type="button" className="btn btn-quiet" onClick={onLeave}>
          <span className="btn-label"><Icon name="arrow-left" />수사 화면으로</span>
        </button>
        {view.feed.length > 0 && <Feed view={view} limit={3} />}
      </div>
    </section>
  )
}

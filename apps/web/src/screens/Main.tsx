import { useEffect, useRef, useState } from 'react'
import { ActionBar } from '../components/ActionBar'
import { BluffDialog } from '../components/BluffDialog'
import { MapPanel } from '../components/MapPanel'
import { NotebookPanel } from '../components/NotebookPanel'
import { Overlays } from '../components/Overlays'
import { Stage } from '../components/Stage'
import type { GameApi } from '../state/useGame'
import { dayPeriod, formatTime } from '../util/format'

interface Props {
  g: GameApi
  onFinale: () => void
  onHome: () => void
}

export function Main({ g, onFinale, onHome }: Props) {
  const { state, dispatch, act, endDay, save } = g
  const view = state.view!
  const [interrogee, setInterrogee] = useState<string | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [bluffing, setBluffing] = useState(false)
  const [saveMsg, setSaveMsg] = useState('')
  const maxRef = useRef({ day: view.day, max: view.actions_left })
  const feedEnd = useRef<HTMLDivElement>(null)

  if (maxRef.current.day !== view.day) maxRef.current = { day: view.day, max: view.actions_left }
  if (view.actions_left > maxRef.current.max) maxRef.current.max = view.actions_left

  // NPC 가 말하면 그 사람과의 심문 장면으로 전환
  const speakerId = state.dialogue?.role === 'npc' ? state.dialogue.speakerId : null
  useEffect(() => {
    if (speakerId) setInterrogee(speakerId)
  }, [speakerId])

  // 심문 중인 사람이 다른 장소로 가 버렸다면(밤 이후 등) 장면을 닫는다
  const iChar = interrogee ? view.characters.find((c) => c.id === interrogee) : null
  useEffect(() => {
    if (iChar && iChar.location_id !== view.player_location) setInterrogee(null)
  }, [iChar, view.player_location])

  useEffect(() => {
    feedEnd.current?.scrollIntoView({ block: 'nearest' })
  }, [view.feed.length])

  const busy = state.running
  const locked = !!(interrogee && state.turnAway[interrogee])

  const talk = (id: string) => {
    if (busy) return
    setInterrogee(id)
    dispatch({ kind: 'clear_dialogue' })
  }
  const leave = () => {
    setInterrogee(null)
    dispatch({ kind: 'clear_dialogue' })
  }
  const move = (loc: string) => {
    if (busy || loc === view.player_location) return
    setInterrogee(null)
    dispatch({ kind: 'clear_dialogue' })
    void act({ type: 'move', location_id: loc })
  }
  const doSave = async () => {
    const r = await save()
    setSaveMsg(r ? '저장했습니다 ✓' : '')
    window.setTimeout(() => setSaveMsg(''), 2500)
  }

  return (
    <div className="game">
      <header className="topbar">
        <div>
          <strong>{view.case_title}</strong>
          {view.reputation_band && <span className="band">{view.reputation_band}</span>}
        </div>
        <div className="top-actions">
          <button onClick={doSave} disabled={busy}>💾 저장</button>
          {saveMsg && <span className="saved">{saveMsg}</span>}
          <button onClick={onHome}>처음으로</button>
        </div>
      </header>

      <aside className="pane map-pane">
        <h2>지도</h2>
        <MapPanel view={view} interrogeeId={interrogee} locked={busy} onMove={move} onTalk={talk} />
        <p className="muted small">이어진 장소를 눌러 이동 · 점을 눌러 말 걸기</p>
      </aside>

      <main className="pane stage-pane">
        <Stage
          state={state}
          interrogeeId={interrogee}
          busy={busy}
          onTalk={talk}
          onLeave={leave}
          onInvestigate={() => void act({ type: 'investigate', location_id: view.player_location })}
          onDropEvidence={(npc, ev) => {
            setSelected(null)
            void act({ type: 'present', npc_id: npc, evidence_id: ev })
          }}
        />
      </main>

      <aside className="pane note-pane">
        <NotebookPanel
          view={view}
          newContradictions={state.newContradictions}
          selectedEvidence={selected}
          onSelectEvidence={setSelected}
          onSeen={() => dispatch({ kind: 'clear_new_contradictions' })}
        />
      </aside>

      <div className="action-pane">
        <ActionBar
          view={view}
          interrogeeId={interrogee}
          busy={busy}
          locked={locked}
          selectedEvidence={selected}
          onChip={(id, npc) => {
            setInterrogee(npc)
            void act({ type: 'chip', chip_id: id })
          }}
          onAsk={(text) => interrogee && void act({ type: 'ask', npc_id: interrogee, text })}
          onPresent={() => {
            if (interrogee && selected) {
              void act({ type: 'present', npc_id: interrogee, evidence_id: selected })
              setSelected(null)
            }
          }}
          onBluff={() => setBluffing(true)}
        />
      </div>

      <footer className="bottombar">
        <div className="feed" aria-label="단톡방 피드">
          {view.feed.slice(-6).map((f) => (
            <p key={f.id}>
              <span className="chan">📱 {f.channel}</span> <b>{f.author}</b>: {f.text}
            </p>
          ))}
          <div ref={feedEnd} />
        </div>
        <div className="status">
          <span>{view.day}일차</span>
          <span>{dayPeriod(view.clock)} {formatTime(view.clock)}</span>
          <span className={view.actions_left <= 2 ? 'low' : ''}>
            행동 {view.actions_left}/{maxRef.current.max}
          </span>
          <button onClick={() => void endDay()} disabled={busy}>🌙 하루 끝내기</button>
          <button className="primary" onClick={onFinale} disabled={busy}>🔎 최종 추리</button>
        </div>
      </footer>

      {bluffing && interrogee && (
        <BluffDialog
          view={view}
          npcId={interrogee}
          initialEvidence={selected}
          onCancel={() => setBluffing(false)}
          onConfirm={(claim, subject, ev) => {
            setBluffing(false)
            setSelected(null)
            void act({ type: 'bluff', npc_id: interrogee, claim_id: claim, claim_subject: subject, basis_evidence_ids: ev })
          }}
        />
      )}
      <Overlays state={state} dispatch={dispatch} />
    </div>
  )
}

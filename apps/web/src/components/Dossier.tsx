import { useCallback, useEffect, useState } from 'react'
import type { Emotion, PublicCharacter } from '../api/types'
import { Portrait } from '../character/Portrait'
import type { ClientState, DialogueLine, QaEntry } from '../state/reducer'
import { useTypewriter } from './DialogueBox'
import { Icon } from './Icon'

export const EMOTION_LABEL: Record<Emotion, string> = { neutral: '평온', nervous: '긴장', flustered: '당황', angry: '분노', sad: '슬픔', happy: '기쁨' }
const ROLE_LABEL: Record<string, string> = { narrator: '내레이션', partner: '파트너', chief: '반장' }

interface Props {
  state: ClientState
  npc: PublicCharacter
  selectedEvidence: string | null
  busy: boolean
  /** 휴대폰: 이전 문답을 접어 둔다(D10: 데스크톱 3쌍, 휴대폰 1쌍) */
  compact: boolean
  onLeave: () => void
  onDropEvidence: (npcId: string, evidenceId: string) => void
}

/** 심문 조서: 사진·이름·대사를 한 장의 종이로 묶는다(D3). 표정은 사진 교체 + 이름 옆 글자 칩(D11). */
export function Dossier({ state, npc, selectedEvidence, busy, compact, onLeave, onDropEvidence }: Props) {
  const view = state.view!
  const [typing, setTyping] = useState(false)
  const [dragOver, setDragOver] = useState(false)
  const onTyping = useCallback((t: boolean) => setTyping(t), [])
  const emotion = state.emotions[npc.id] ?? npc.emotion
  const awayLeft = state.turnAway[npc.id]
  const ev = selectedEvidence ? view.evidence.find((e) => e.id === selectedEvidence) : null

  // 모순으로 판정된 진술. 대답 안에 그 문장이 있으면 그 부분에 형광 띠·이중 밑줄·"모순" 도장을 붙인다
  const nb = view.notebook
  const flagged = nb.contradictions
    .map((c) => nb.statements.find((s) => s.id === c.statement_id && s.npc_id === npc.id)?.content.trim())
    .filter((t): t is string => !!t)

  // 이 사람과의 문답. 이번 접속의 기록이 없으면(불러온 게임) 진술로 대신한다
  const logged = state.log.filter((e) => e.npcId === npc.id)
  const entries: QaEntry[] = logged.length
    ? logged
    : nb.statements.filter((s) => s.npc_id === npc.id).map((s) => ({ id: s.id, npcId: npc.id, q: null, a: s.content }))

  const line = state.dialogue
  const live = line && line.role === 'npc' && line.speakerId === npc.id ? line : null
  const narration = line && line.role !== 'npc' ? line : null
  const waiting = state.asked?.npcId === npc.id ? state.asked.text : null
  const last = entries[entries.length - 1] ?? null
  const nowEntry = live ? (entries.find((e) => e.id === live.messageId) ?? null) : waiting ? null : last
  const nowQ = live ? (waiting ?? nowEntry?.q ?? null) : waiting ?? last?.q ?? null
  const earlier = entries.filter((e) => e !== nowEntry && (!live || e.id !== live.messageId)).slice(-2)

  const [earlierPick, setEarlierPick] = useState<boolean | null>(null) // 사용자가 직접 접거나 편 상태. 없으면 폭에 따른다
  const showEarlier = earlierPick ?? !compact

  return (
    <div className="dossier-wrap">
      <section className="paper dossier has-tab" aria-label={`심문 조서: ${npc.name}`}>
        <span className="folder-tab">심문 조서</span>
        <div className="dossier-body">
          <div className="dossier-top">
            <button type="button" className="btn btn-sm" onClick={onLeave}>
              <span className="btn-label"><Icon name="arrow-left" />심문 끝내기</span>
            </button>
          </div>

          <div
            className={`portrait-box${dragOver ? ' is-dragover' : ''}`}
            onDragOver={(e) => {
              if (awayLeft || busy) return
              e.preventDefault()
              setDragOver(true)
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => {
              e.preventDefault()
              setDragOver(false)
              const id = e.dataTransfer.getData('text/evidence')
              if (id && !awayLeft && !busy) onDropEvidence(npc.id, id)
            }}
          >
            <span className="portrait-clip" aria-hidden="true"><Icon name="paperclip" /></span>
            <Portrait
              seed={npc.face_seed}
              appearance={npc.appearance}
              emotion={emotion}
              speaking={typing}
              portraitUrl={npc.portrait_url}
              portraitEmotions={npc.portrait_emotions}
              name={npc.name}
              eager
              cover={awayLeft ? `등을 돌렸다\n${awayLeft}번 행동 뒤에\n다시 말을 걸 수 있다` : dragOver ? '놓으면 이 증거를 제시합니다' : null}
            />
          </div>

          <div className="dossier-head">
            <span className="emotion-chip" aria-live="polite"><span>표정</span> <b>{EMOTION_LABEL[emotion]}</b></span>
            <h2>{npc.name}</h2>
            <p className="role">{npc.role} · {npc.age}세</p>
            <p className="meta">
              {busy && !live?.text && <span className="status-text">생각하는 중</span>}
              {ev && (
                <span className="pending-tag">
                  <Icon name="paperclip-fill" />
                  <span>제시 대기: <b>{ev.name}</b></span>
                </span>
              )}
            </p>
          </div>

          <div className="dossier-log">
            {earlier.length > 0 && (
              <div className="earlier">
                <button type="button" className="earlier-toggle" aria-expanded={showEarlier} onClick={() => setEarlierPick(!showEarlier)}>
                  <Icon name={showEarlier ? 'caret-up' : 'caret-down'} />
                  <span>이전 문답 {earlier.length}개</span>
                </button>
                {showEarlier &&
                  earlier.map((e) => (
                    <div key={e.id} className="qa">
                      {e.q && <p className="q"><b>형사</b>{e.q}</p>}
                      <p className="a">
                        <b>{npc.name}</b>
                        <Marked text={e.a} flagged={flagged} />
                      </p>
                    </div>
                  ))}
              </div>
            )}
          </div>

          <div className="dossier-now" aria-live="polite">
            {nowQ && (
              <p className="q"><b className="who">형사</b><span className="said">{nowQ}</span></p>
            )}
            {narration ? (
              <Narration key={narration.messageId} line={narration} />
            ) : live ? (
              <p className="a">
                <b className="who">{npc.name}</b>
                <TypedAnswer key={live.messageId} line={live} flagged={flagged} onTyping={onTyping} />
              </p>
            ) : waiting ? (
              <p className="a"><b className="who">{npc.name}</b><span className="said muted">…</span></p>
            ) : last ? (
              <p className="a">
                <b className="who">{npc.name}</b>
                <span className="said"><Marked text={last.a} flagged={flagged} /></span>
              </p>
            ) : (
              <p className="a"><b className="who">{npc.name}</b><span className="said muted">{npc.one_liner || '말을 걸어 보자.'}</span></p>
            )}
          </div>
        </div>
      </section>
    </div>
  )
}

/** NPC 대답: 글자가 하나씩 찍히고, 다 찍힌 뒤 모순이면 형광 띠 → 도장 순서로 표시한다 */
function TypedAnswer({ line, flagged, onTyping }: { line: DialogueLine; flagged: string[]; onTyping: (t: boolean) => void }) {
  const { shown, typing } = useTypewriter(line.text)
  const active = typing || !line.done
  useEffect(() => {
    onTyping(active)
    return () => onTyping(false)
  }, [active, onTyping])
  if (!active && findClaim(line.text, flagged)) return <span className="said"><Marked text={line.text} flagged={flagged} fresh /></span>
  return (
    <span className="said">
      {shown}
      {active && <span className="caret" aria-hidden="true">▌</span>}
    </span>
  )
}

/** 대답 속 모순 문장의 위치. 진술이 대답의 일부면 그 부분, 대답이 진술 안에 들어가면 대답 전체 */
export function findClaim(text: string, flagged: string[]): [number, number] | null {
  let best: [number, number] | null = null
  for (const f of flagged) {
    const i = text.indexOf(f)
    if (i >= 0 && (!best || f.length > best[1] - best[0])) best = [i, i + f.length]
    else if (!best && text.trim() && f.includes(text.trim())) best = [0, text.length]
  }
  return best
}

/** 모순 문장 표시. fresh 면 형광 띠가 300ms 동안 그어지고 그다음 도장이 찍힌다(마운트 다음 프레임에 켜야 전환이 보인다) */
function Marked({ text, flagged, fresh }: { text: string; flagged: string[]; fresh?: boolean }) {
  const [on, setOn] = useState(!fresh)
  useEffect(() => {
    if (!fresh) return
    const id = window.requestAnimationFrame(() => setOn(true))
    return () => window.cancelAnimationFrame(id)
  }, [fresh])
  const at = findClaim(text, flagged)
  if (!at) return <>{text}</>
  return (
    <>
      {text.slice(0, at[0])}
      <span className={`claim${on ? ' is-flagged' : ''}`}>{text.slice(at[0], at[1])}</span>
      {on && <span className={`stamp${fresh ? ' is-fresh' : ''}`} aria-label="모순">모순</span>}
      {text.slice(at[1])}
    </>
  )
}

function Narration({ line }: { line: DialogueLine }) {
  const { shown, typing } = useTypewriter(line.text)
  const active = typing || !line.done
  return (
    <p className="a is-narration">
      <b className="who">{ROLE_LABEL[line.role] ?? ''}</b>
      <span className="said">{shown}{active && <span className="caret" aria-hidden="true">▌</span>}</span>
    </p>
  )
}

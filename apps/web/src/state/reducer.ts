// AG-UI 이벤트 -> 클라이언트 상태. 순수 함수라서 테스트하기 쉽다.
import { applyPatch } from '../api/jsonpatch'
import type {
  AgEvent,
  Chip,
  CutinValue,
  DirectorValue,
  Emotion,
  EndingValue,
  FeedItem,
  FinaleValue,
  MessageRole,
  NightProgressValue,
  NotebookAdded,
  OverheardValue,
  PlayerView,
} from '../api/types'

export interface DialogueLine {
  messageId: string
  role: MessageRole
  speakerId: string | null
  text: string
  done: boolean
}

/** 심문 조서의 문답 한 쌍. 질문은 화면에서 보낸 것이고(칩·직접 질문·증거 제시), 답은 NPC 대사 원문이다. */
export interface QaEntry {
  id: string // 답 메시지 id
  npcId: string
  q: string | null
  a: string
}

export interface ClientState {
  view: PlayerView | null
  dialogue: DialogueLine | null
  log: QaEntry[] // 이번 접속에서 오간 문답(이전 문답 표시용). 불러온 게임은 비어 있고, 그때는 진술로 대신한다
  asked: { npcId: string; text: string } | null // 답을 기다리는 질문
  emotions: Record<string, Emotion> // 이벤트로 덮어쓴 표정(스냅샷이 오면 비움)
  turnAway: Record<string, number> // npcId -> 풀리기까지 남은 행동 수
  cutin: (CutinValue & { key: number }) | null
  director: (DirectorValue & { key: number }) | null
  night: NightProgressValue | null
  overheard: OverheardValue | null
  newContradictions: string[] // 방금 생긴 모순 id (수첩 강조용)
  finale: FinaleValue | null
  ending: EndingValue | null
  error: string | null
  running: boolean
  needsResync: boolean
  seq: number
}

export const initialClientState: ClientState = {
  view: null,
  dialogue: null,
  log: [],
  asked: null,
  emotions: {},
  turnAway: {},
  cutin: null,
  director: null,
  night: null,
  overheard: null,
  newContradictions: [],
  finale: null,
  ending: null,
  error: null,
  running: false,
  needsResync: false,
  seq: 0,
}

function uniqPush<T extends { id: string }>(list: T[], items: T[]): T[] {
  const have = new Set(list.map((x) => x.id))
  const add = items.filter((x) => !have.has(x.id))
  return add.length ? [...list, ...add] : list
}

function mergeNotebook(view: PlayerView, added: NotebookAdded): PlayerView {
  const nb = view.notebook
  const evidence_ids = [...nb.evidence_ids]
  for (const id of added.evidence_ids ?? []) if (!evidence_ids.includes(id)) evidence_ids.push(id)
  return {
    ...view,
    notebook: {
      ...nb,
      evidence_ids,
      statements: uniqPush(nb.statements, added.statements ?? []),
      contradictions: uniqPush(nb.contradictions, added.contradictions ?? []),
    },
  }
}

export function applyEvent(s: ClientState, ev: AgEvent): ClientState {
  switch (ev.type) {
    case 'RUN_STARTED':
      return { ...s, running: true, error: null }
    case 'RUN_FINISHED':
      return { ...s, running: false, night: null, asked: null }
    case 'RUN_ERROR':
      return { ...s, running: false, night: null, asked: null, error: ev.message || '알 수 없는 오류가 났습니다.' }

    case 'TEXT_MESSAGE_START':
      return {
        ...s,
        dialogue: {
          messageId: ev.messageId,
          role: ev.role,
          speakerId: ev.speakerId ?? null,
          text: '',
          done: false,
        },
      }
    case 'TEXT_MESSAGE_CONTENT':
      if (!s.dialogue || s.dialogue.messageId !== ev.messageId) return s
      return { ...s, dialogue: { ...s.dialogue, text: s.dialogue.text + ev.delta } }
    case 'TEXT_MESSAGE_END': {
      const d = s.dialogue
      if (!d || d.messageId !== ev.messageId) return s
      const done = { ...s, dialogue: { ...d, done: true } }
      if (d.role !== 'npc' || !d.speakerId || !d.text) return done
      const q = s.asked?.npcId === d.speakerId ? s.asked.text : null
      return { ...done, asked: null, log: [...s.log, { id: d.messageId, npcId: d.speakerId, q, a: d.text }] }
    }

    case 'STATE_SNAPSHOT':
      return { ...s, view: ev.snapshot, emotions: {}, needsResync: false, ending: s.ending }
    case 'STATE_DELTA': {
      if (!s.view) return { ...s, needsResync: true }
      try {
        const view = applyPatch(s.view, ev.delta)
        // 서버는 델타를 notebook 이벤트보다 먼저 보낸다. 델타로 새로 생긴 모순도 "새 모순"으로 표시한다
        const before = new Set(s.view.notebook.contradictions.map((c) => c.id))
        const fresh = view.notebook.contradictions.map((c) => c.id).filter((id) => !before.has(id) && !s.newContradictions.includes(id))
        return { ...s, view, newContradictions: fresh.length ? [...s.newContradictions, ...fresh] : s.newContradictions }
      } catch {
        // 패치가 어긋나면 화면을 멈추지 않고 GET 으로 다시 맞춘다.
        return { ...s, needsResync: true }
      }
    }

    case 'CUSTOM':
      return applyCustom(s, ev.name, ev.value)
    default:
      return s
  }
}

function applyCustom(s: ClientState, name: string, value: unknown): ClientState {
  const seq = s.seq + 1
  switch (name) {
    case 'emotion': {
      const v = value as { npcId: string; emotion: Emotion }
      return { ...s, emotions: { ...s.emotions, [v.npcId]: v.emotion } }
    }
    case 'notebook': {
      const added = (value as { added?: NotebookAdded }).added ?? {}
      if (!s.view) return s
      const have = new Set(s.view.notebook.contradictions.map((c) => c.id))
      const fresh = (added.contradictions ?? []).filter((c) => !have.has(c.id) && !s.newContradictions.includes(c.id)).map((c) => c.id)
      return {
        ...s,
        view: mergeNotebook(s.view, added),
        newContradictions: [...s.newContradictions, ...fresh],
      }
    }
    case 'feed': {
      if (!s.view) return s
      return { ...s, view: { ...s.view, feed: uniqPush(s.view.feed, [value as FeedItem]) } }
    }
    case 'chips': {
      if (!s.view) return s
      return { ...s, view: { ...s.view, chips: (value as { chips: Chip[] }).chips } }
    }
    case 'cutin':
      return { ...s, seq, cutin: { ...(value as CutinValue), key: seq } }
    case 'turn_away': {
      const v = value as { npcId: string; untilActions: number }
      return { ...s, turnAway: { ...s.turnAway, [v.npcId]: v.untilActions } }
    }
    case 'director':
      return { ...s, seq, director: { ...(value as DirectorValue), key: seq } }
    case 'night_progress':
      return { ...s, night: value as NightProgressValue }
    case 'overheard':
      return { ...s, overheard: value as OverheardValue }
    case 'finale': {
      const f = value as FinaleValue
      return { ...s, finale: f.accused_id ? f : null } // 지목을 무르면 지목 화면으로
    }
    case 'ending':
      return { ...s, ending: value as EndingValue }
    default:
      return s // 모르는 CUSTOM 이벤트는 무시
  }
}

export type UiAction =
  | { kind: 'event'; ev: AgEvent }
  | { kind: 'set_view'; view: PlayerView }
  | { kind: 'portraits'; urls: Record<string, string>; emotions?: Record<string, Record<string, string>> }
  | { kind: 'clear_cutin' }
  | { kind: 'clear_director' }
  | { kind: 'clear_overheard' }
  | { kind: 'clear_new_contradictions' }
  | { kind: 'clear_dialogue' }
  | { kind: 'asked'; npcId: string; text: string }
  | { kind: 'error'; message: string }
  | { kind: 'running'; value: boolean }
  | { kind: 'tick_turn_away' }
  | { kind: 'reset' }

export function clientReducer(s: ClientState, a: UiAction): ClientState {
  switch (a.kind) {
    case 'event':
      return applyEvent(s, a.ev)
    case 'set_view':
      return { ...s, view: a.view, emotions: {}, needsResync: false }
    case 'portraits': {
      // 나중에 완성된 초상화·표정 주소만 채운다 (바뀐 게 없으면 같은 상태 → 다시 그리지 않음)
      if (!s.view) return s
      const emo = a.emotions ?? {}
      let changed = false
      const characters = s.view.characters.map((c) => {
        let next = c
        const url = a.urls[c.id]
        if (url && url !== c.portrait_url) next = { ...next, portrait_url: url }
        const add = emo[c.id]
        if (add) {
          const cur = c.portrait_emotions ?? {}
          if (Object.keys(add).some((k) => add[k] && add[k] !== cur[k])) next = { ...next, portrait_emotions: { ...cur, ...add } }
        }
        if (next !== c) changed = true
        return next
      })
      if (!changed) return s
      return { ...s, view: { ...s.view, characters } }
    }
    case 'clear_cutin':
      return { ...s, cutin: null }
    case 'clear_director':
      return { ...s, director: null }
    case 'clear_overheard':
      return { ...s, overheard: null }
    case 'clear_new_contradictions':
      return { ...s, newContradictions: [] }
    case 'clear_dialogue':
      return { ...s, dialogue: null }
    case 'asked':
      return { ...s, asked: { npcId: a.npcId, text: a.text } }
    case 'error':
      return { ...s, error: a.message, running: false, night: null }
    case 'running':
      return { ...s, running: a.value }
    case 'tick_turn_away': {
      const next: Record<string, number> = {}
      for (const [k, v] of Object.entries(s.turnAway)) if (v > 1) next[k] = v - 1
      return { ...s, turnAway: next }
    }
    case 'reset':
      return initialClientState
  }
}

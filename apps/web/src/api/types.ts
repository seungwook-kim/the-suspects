// server/schemas.py 의 클라이언트용 모델과 docs/api-contract.md 를 그대로 옮긴 타입.

export type Emotion = 'neutral' | 'nervous' | 'flustered' | 'angry' | 'sad' | 'happy'
export const EMOTIONS: Emotion[] = ['neutral', 'nervous', 'flustered', 'angry', 'sad', 'happy']

export interface PublicCharacter {
  id: string
  name: string
  role: string
  age: number
  gender: 'M' | 'F' | 'X'
  appearance: Record<string, string>
  face_seed: number
  location_id: string | null
  emotion: Emotion
  one_liner: string
  /** AI 초상화 주소. 처음엔 null 이었다가 나중에 채워질 수 있다. 없으면 절차적 SVG 로 그린다. */
  portrait_url?: string | null
}

export interface PublicLocation {
  id: string
  name: string
  description: string
  connections: string[]
  background_ref: string | null
  overlays: string[]
}

export interface PublicEvidence {
  id: string
  name: string
  kind: string
  content: string
}

export interface Chip {
  id: string
  label: string
  target_npc: string
  kind: 'ask' | 'present' | 'bluff'
  evidence_id: string | null
}

export interface FeedItem {
  id: string
  channel: string
  author: string
  text: string
  game_time: number
}

export interface NotebookStatement {
  id: string
  npc_id: string
  content: string
  game_time: number
  memory_id: string | null
  source_ids: string[]
}

export interface Contradiction {
  id: string
  statement_id: string
  evidence_id: string
  lie_id: string
  note: string
}

export interface Notebook {
  evidence_ids: string[]
  statements: NotebookStatement[]
  contradictions: Contradiction[]
  relations_known: Record<string, unknown>[]
  board_links: Record<string, unknown>[]
  sufficiency: Record<string, number>
}

export interface BluffClaim {
  id: string
  label: string
}

export interface PlayerView {
  game_id: string
  case_title: string
  incident_summary: string
  day: number
  phase: string // briefing | day | night | finale | ended
  clock: number
  actions_left: number
  player_location: string
  locations: PublicLocation[]
  characters: PublicCharacter[]
  evidence: PublicEvidence[]
  notebook: Notebook
  sufficiency_gauge: Record<string, number>
  reputation_band: string
  chips: Chip[]
  feed: FeedItem[]
  bluff_claims: BluffClaim[]
  ending: string // none | success | escaped | wrong_accusation
  actions_total: number // 하루 전체 행동 수
  max_days: number // 수사 기한(일)
}

export interface Theme {
  id: string
  title: string
  emoji: string
  description: string
  preset: boolean
}

export interface ClearHistory {
  id: string
  player_id: string
  case_title: string
  theme: string
  cleared_at: string
  success: boolean
  real_minutes: number
  game_days: number
  question_count: number
  grade: 'S' | 'A' | 'B' | 'C' | null
  titles: string[]
  reputation: number
  culprit: { name?: string; role?: string }
  characters: { name: string; role: string; face_seed: number; appearance: Record<string, string> }[]
  highlight: string
  fingerprint: Record<string, unknown>
}

export interface ShareCard {
  emoji_line: string // 예: "🔍🔍❌🔍✅"
  share_text: string
  theme_color: string // #RRGGBB
}

export interface CreateOptions {
  tone?: 'comic' | 'balanced' | 'serious'
  difficulty?: 'easy' | 'normal' | 'hard'
  play_minutes?: 20 | 40 | 60
}

export interface CasePreview {
  title: string
  incident_summary: string
  characters: PublicCharacter[] // location_id 는 null
}

export interface CaseJob {
  job_id: string
  status: 'running' | 'ready' | 'failed' | 'rejected'
  stage: number
  total: number
  stage_text: string
  preview: CasePreview | null
  game_id: string | null
  view: PlayerView | null
  message: string | null
  fallback_theme_id: string | null
}

export interface GameSummary {
  game_id: string
  case_title: string
  day: number
  last_seen: string
}

export interface SaveSlotInfo {
  slot_id: string
  name: string
  kind: string
  saved_at: string
}

export interface SourceItem {
  kind: string
  title: string
  content: string
}

export type Action =
  | { type: 'move'; location_id: string }
  | { type: 'investigate'; location_id: string }
  | { type: 'ask'; npc_id: string; text: string }
  | { type: 'chip'; chip_id: string }
  | { type: 'present'; npc_id: string; evidence_id: string }
  | {
      type: 'bluff'
      npc_id: string
      claim_id: string
      claim_subject: string | null
      basis_evidence_ids: string[]
    }
  | { type: 'warrant'; system: string; target_id: string; basis_evidence_ids: string[] }
  | { type: 'apologize'; npc_id: string }
  | { type: 'hint' }

export type FinaleStage = 'opportunity' | 'means' | 'motive'
export const FINALE_STAGES: FinaleStage[] = ['opportunity', 'means', 'motive']
export const FINALE_STAGE_LABEL: Record<FinaleStage, string> = {
  opportunity: '기회',
  means: '수단',
  motive: '동기',
}

export type FinaleStep =
  | { type: 'start'; accused_id: string }
  | { type: 'present'; stage: FinaleStage; evidence_id: string }
  | { type: 'confirm' }

// ---- AG-UI 이벤트 ----
export type MessageRole = 'npc' | 'narrator' | 'partner' | 'chief'

export interface JsonPatchOp {
  op: 'add' | 'remove' | 'replace' | 'move' | 'copy' | 'test'
  path: string
  from?: string
  value?: unknown
}

export type AgEvent =
  | { type: 'RUN_STARTED'; runId?: string }
  | { type: 'RUN_FINISHED'; runId?: string }
  | { type: 'RUN_ERROR'; message: string; code?: string }
  | { type: 'TEXT_MESSAGE_START'; messageId: string; role: MessageRole; speakerId?: string | null }
  | { type: 'TEXT_MESSAGE_CONTENT'; messageId: string; delta: string }
  | { type: 'TEXT_MESSAGE_END'; messageId: string }
  | { type: 'STATE_SNAPSHOT'; snapshot: PlayerView }
  | { type: 'STATE_DELTA'; delta: JsonPatchOp[] }
  | { type: 'CUSTOM'; name: string; value: unknown }

// ---- CUSTOM value 모양 ----
export interface NotebookAdded {
  evidence_ids?: string[]
  statements?: NotebookStatement[]
  contradictions?: Contradiction[]
}
export interface CutinValue {
  text: string
  style?: string
}
export interface DirectorValue {
  eventId: string
  title: string
  text: string
}
export interface NightProgressValue {
  step: number
  total: number
  text: string
}
export interface OverheardValue {
  locationId: string
  lines: { speakerId: string; text: string }[]
}
export interface EndingValue {
  ending: string
  replay?: unknown
}
// 계약에 없음: 최종 추리 쇼 진행 상태(제안). 백엔드가 보내 줘야 한다.
export interface FinaleValue {
  accused_id: string
  stage: FinaleStage | 'done'
  lives: number
  filled: FinaleStage[]
  last?: { result: 'correct' | 'wrong' | 'rebutted'; evidence_id?: string } | null
}

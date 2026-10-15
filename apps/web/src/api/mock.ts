// 목(mock) 백엔드. 계약(docs/api-contract.md)과 같은 모양의 REST 응답과 AG-UI 이벤트를 만든다.
// VITE_USE_MOCK=1 일 때만 쓰인다. 사건 비밀(범인 등)은 이 파일 안에만 있고 화면 코드는 모른다.
import { josa } from '../util/format'
import type { Api } from './client'
import type {
  Action,
  AgEvent,
  ClearHistory,
  Contradiction,
  Emotion,
  FeedItem,
  FinaleStage,
  FinaleStep,
  FinaleValue,
  JsonPatchOp,
  MessageRole,
  NotebookStatement,
  PlayerView,
  PublicCharacter,
  PublicEvidence,
  ShareCard,
  Theme,
  CaseJob,
  CasePreview,
} from './types'

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms))

// ---------------------------------------------------------------- 사건 데이터
const THEMES: Theme[] = [
  {
    id: 'demo_db_deleted',
    title: '사라진 운영 DB',
    emoji: '💾',
    description: '서비스 오픈 전날 밤 운영 DB가 삭제됐다. 감사 로그까지 지워졌다.',
    preset: true,
  },
  { id: 'apartment_murder', title: '아파트 살인사건', emoji: '🏢', description: '단지 안에서 일어난 사건. 모두가 서로를 알고 있다.', preset: true },
  { id: 'parcel_theft', title: '택배 도난 소동', emoji: '📦', description: '현관 앞 택배가 계속 사라진다. 범인은 누구일까?', preset: true },
  { id: 'hotel_locked_room', title: '호텔 밀실', emoji: '🏨', description: '안에서 잠긴 객실, 사라진 투숙객.', preset: true },
]

const CHARACTERS: PublicCharacter[] = [
  { id: 'npc_dba', name: '오민재', role: 'DBA', age: 41, gender: 'M', face_seed: 48211, appearance: { hair: 'short', hair_color: '#2f2a28', outfit: 'office_lanyard', accessory: 'glasses' }, location_id: 'loc_server_room', emotion: 'neutral', one_liner: '백업 담당. 말수가 적고 늘 야근한다.', portrait_url: null },
  { id: 'npc_cleaner', name: '박순자', role: '야간 청소 담당', age: 58, gender: 'F', face_seed: 90177, appearance: { hair: 'bun', hair_color: '#8a8a8a', outfit: 'cleaner_uniform', accessory: 'mop' }, location_id: 'loc_pantry', emotion: 'neutral', one_liner: '10년째 이 건물의 밤을 지켜 온 사람.', portrait_url: null },
  { id: 'npc_newbie', name: '정하늘', role: '신입 개발자', age: 26, gender: 'F', face_seed: 31337, appearance: { hair: 'long', hair_color: '#3b2a20', outfit: 'hoodie', accessory: 'laptop' }, location_id: 'loc_office', emotion: 'neutral', one_liner: '입사 3개월 차. 오픈 전날까지 코드를 고치고 있었다.', portrait_url: null },
  { id: 'npc_cto', name: '최강진', role: 'CTO', age: 47, gender: 'M', face_seed: 7741, appearance: { hair: 'side', hair_color: '#1f1f24', outfit: 'suit', accessory: 'badge' }, location_id: 'loc_cto_room', emotion: 'neutral', one_liner: '오픈 일정에 모든 걸 걸었다.', portrait_url: null },
  { id: 'npc_freelancer', name: '윤태오', role: '외주 개발자', age: 34, gender: 'M', face_seed: 120934, appearance: { hair: 'curly', hair_color: '#5a3a22', outfit: 'casual', accessory: 'cap' }, location_id: 'loc_meeting', emotion: 'neutral', one_liner: '계약이 이번 달에 끝난다.', portrait_url: null },
]

const LOCATIONS = [
  { id: 'loc_lobby', name: '로비', description: '출입 게이트와 CCTV가 있는 1층 로비.', connections: ['loc_office', 'loc_pantry'] },
  { id: 'loc_office', name: '개발팀 사무실', description: '모니터 불빛이 아직 남아 있는 사무실.', connections: ['loc_lobby', 'loc_server_room', 'loc_meeting'] },
  { id: 'loc_server_room', name: '서버실', description: '차가운 바람이 나오는 출입 제한 구역.', connections: ['loc_office', 'loc_pantry'] },
  { id: 'loc_meeting', name: '회의실', description: '화이트보드에 오픈 일정이 적혀 있다.', connections: ['loc_office', 'loc_cto_room'] },
  { id: 'loc_pantry', name: '탕비실', description: '커피 냄새와 포스트잇이 가득한 게시판.', connections: ['loc_lobby', 'loc_server_room'] },
  { id: 'loc_cto_room', name: 'CTO실', description: '정돈된 책상. 서랍 하나가 살짝 열려 있다.', connections: ['loc_meeting'] },
].map((l) => ({ ...l, background_ref: null, overlays: [] as string[] }))

const EVIDENCE_AT: Record<string, PublicEvidence> = {
  loc_lobby: { id: 'ev_cctv_note', name: '로비 CCTV 캡처', kind: 'image', content: '01:05 청소 카트를 끌고 엘리베이터에 타는 사람. 모자에 가려 얼굴은 보이지 않는다. CTO는 이 시각 로비를 지나가지 않았다.' },
  loc_server_room: { id: 'ev_access_log', name: '서버실 출입 기록', kind: 'log', content: '01:12 서버실 문 열림. 사용 카드: 시설 관리용 마스터키(청소 용역 배정). 개인 사원증 기록은 없음.' },
  loc_office: { id: 'ev_chat_edit', name: '메신저 수정 이력', kind: 'log', content: 'DBA의 "11시에 퇴근합니다" 메시지는 01:30에 수정됐다. 원래 시각은 12:58 접속 중.' },
  loc_pantry: { id: 'ev_admin_note', name: '관리자 비밀번호 포스트잇', kind: 'note', content: '탕비실 게시판 뒤에 붙은 포스트잇. 운영 DB 관리자 비밀번호가 그대로 적혀 있다. 누구나 볼 수 있었다.' },
  loc_cto_room: { id: 'ev_notice', name: '용역 계약 해지 통보서', kind: 'doc', content: '다음 달부터 야간 청소 용역을 종료한다는 내부 통보서 초안. 청소 담당자들에게는 아직 알리지 않았다.' },
}

const FINALE_VALID: Record<FinaleStage, string> = {
  opportunity: 'ev_access_log',
  means: 'ev_admin_note',
  motive: 'ev_notice',
}
const CULPRIT = 'npc_cleaner' // 목 모드 전용. 화면은 모른다.

interface Line { text: string; emotion: Emotion }
const ASK_LINES: Record<string, Line[]> = {
  npc_dba: [
    { text: '어젯밤요? 11시에 퇴근했습니다. 백업은 점검 끝내 놨고요.', emotion: 'neutral' },
    { text: '그 뒤로는 모릅니다. 집에서 자고 있었으니까요.', emotion: 'nervous' },
    { text: '저를 의심하시는 겁니까? 기분이 좋진 않네요.', emotion: 'angry' },
  ],
  npc_cleaner: [
    { text: '아이고, 형사님. 나는 평소처럼 청소만 했지요. 서버실은 근처에도 안 갔어요.', emotion: 'neutral' },
    { text: '밤마다 카트 끌고 다니는 게 일인데, 뭘 본 게 있겠어요.', emotion: 'sad' },
    { text: '나 같은 사람이 그런 걸 알기나 하겠어요…', emotion: 'sad' },
  ],
  npc_newbie: [
    { text: '저, 저요? 어제는 막차 시간까지 코드 고치고 있었어요!', emotion: 'flustered' },
    { text: '오민재 선배가 가끔 새벽에도 접속하긴 해요. 아, 이건 비밀인데…', emotion: 'nervous' },
    { text: '진짜 아무것도 몰라요. 믿어 주세요, 형사님.', emotion: 'sad' },
  ],
  npc_cto: [
    { text: '지금 오픈이 코앞인데 이런 일이라니. 빨리 정리해 주시죠.', emotion: 'angry' },
    { text: '어젯밤엔 집에 일찍 갔습니다. 회사엔 오지 않았어요.', emotion: 'neutral' },
    { text: '비용 문제라면 얼마든지 말씀하세요. 다만 조용히 처리해 주십시오.', emotion: 'nervous' },
  ],
  npc_freelancer: [
    { text: '저는 외주라 서버 권한도 없어요. 어제는 회의실에서 문서만 봤습니다.', emotion: 'neutral' },
    { text: '계약이 곧 끝나서 신경이 곤두서 있긴 했죠. 그래도 DB를 지우다니요.', emotion: 'nervous' },
    { text: '오해하지 마세요. 저는 그럴 이유가 없습니다.', emotion: 'angry' },
  ],
}
const STATEMENTS: Record<string, string[]> = {
  npc_dba: ['어젯밤 11시에 퇴근했다.', '퇴근 뒤에는 집에서 잤다.'],
  npc_cleaner: ['서버실 근처에는 가지 않았다.', '밤새 평소처럼 청소만 했다.'],
  npc_newbie: ['막차 시간까지 사무실에서 코드를 고쳤다.', '오민재가 새벽에 접속하는 걸 본 적 있다.'],
  npc_cto: ['어젯밤에는 회사에 오지 않았다.', '오픈 일정에 문제가 없어야 한다.'],
  npc_freelancer: ['어제는 회의실에서 문서만 봤다.', '서버 권한이 없다.'],
}
const CONTRA: { id: string; npc: string; statementIdx: number; evidence: string; note: string; line: Line }[] = [
  { id: 'ct_dba', npc: 'npc_dba', statementIdx: 0, evidence: 'ev_chat_edit', note: '11시에 퇴근했다고 했지만 12:58에도 접속 중이었다.', line: { text: '그, 그건… 메시지를 잘못 고친 거지, 별 뜻은 없습니다!', emotion: 'flustered' } },
  { id: 'ct_cleaner', npc: 'npc_cleaner', statementIdx: 0, evidence: 'ev_access_log', note: '서버실에 가지 않았다고 했지만 청소 용역 마스터키로 문이 열렸다.', line: { text: '그, 그게… 문이 열려 있나 보려고 잠깐… 아이고, 내가 왜 이러나.', emotion: 'flustered' } },
  { id: 'ct_cto', npc: 'npc_cto', statementIdx: 0, evidence: 'ev_cctv_note', note: '회사에 오지 않았다고 했지만 같은 시각 로비 CCTV에 정장 차림 사람이 한 명 더 있다.', line: { text: '…그 화면 속 사람이 나라는 증거는 없지 않습니까.', emotion: 'angry' } },
]
const FEED_POOL: Omit<FeedItem, 'id' | 'game_time'>[] = [
  { channel: '사내 메신저', author: '익명', text: '오늘 새로 온 형사 봤어? 서버실 쪽으로 갔다던데.' },
  { channel: '사내 메신저', author: '총무팀', text: '[공지] 오늘 야간 전기 점검은 연기합니다.' },
  { channel: '사내 메신저', author: '익명', text: '어제 새벽에 로비에서 카트 소리 났음. 원래 그 시간에 청소하던가?' },
  { channel: '단톡방', author: '개발팀', text: '오픈 일정 그대로 가는 거죠…? 복구 가능한 건가요?' },
  { channel: '단톡방', author: '정하늘', text: '저 진짜 아무것도 안 했어요 ㅠㅠ' },
]
const BLUFF_CLAIMS = [
  { id: 'claim_accomplice_confessed', label: '공범이 자백했다' },
  { id: 'claim_cctv_caught', label: 'CCTV에 찍혔다' },
  { id: 'claim_log_restored', label: '삭제된 로그를 복구했다' },
  { id: 'claim_witness', label: '목격자가 있다' },
]
const MAX_ACTIONS = 12
const DAY_START = 9 * 60

// ---------------------------------------------------------------- 게임 상태
interface MockGame {
  view: PlayerView
  questions: number
  startedAt: number
  nonsense: number
  asked: Record<string, number>
  feedIdx: number
  actionCount: number
  finale: { accused: string; lives: number; filled: FinaleStage[] } | null
}
const games = new Map<string, MockGame>()
let idSeq = 0
const nid = (p: string) => `${p}_${Date.now().toString(36)}_${++idSeq}`

function newView(gameId: string): PlayerView {
  return {
    game_id: gameId,
    case_title: '사라진 운영 DB',
    incident_summary:
      '서비스 오픈 전날 밤, 운영 DB가 통째로 삭제됐다. 백업 스냅샷은 손상됐고 감사 로그와 변경 이력까지 지워져 누가 했는지 알 수 없다. 건물에는 그날 밤 다섯 사람이 남아 있었다. 오픈까지 남은 시간은 사흘.',
    day: 1,
    phase: 'briefing',
    clock: DAY_START,
    actions_left: MAX_ACTIONS,
    player_location: 'loc_lobby',
    visited_locations: ['loc_lobby'],
    locations: structuredClone(LOCATIONS),
    characters: structuredClone(CHARACTERS),
    evidence: [],
    notebook: { evidence_ids: [], statements: [], contradictions: [], relations_known: [], board_links: [], sufficiency: {} },
    sufficiency_gauge: Object.fromEntries(CHARACTERS.map((c) => [c.id, 0])),
    reputation_band: '신참 형사',
    chips: [],
    feed: [{ id: 'feed_0', channel: '사내 메신저', author: '총무팀', text: '[공지] 어젯밤 시스템 장애와 관련해 형사님이 방문하셨습니다. 협조 부탁드립니다.', game_time: DAY_START }],
    bluff_claims: structuredClone(BLUFF_CLAIMS),
    ending: 'none',
    actions_total: MAX_ACTIONS,
    max_days: 5,
  }
}

function startMockGame(preview?: CasePreview): { game_id: string; view: PlayerView } {
  const id = nid('game')
  const g: MockGame = { view: newView(id), questions: 0, startedAt: Date.now(), nonsense: 0, asked: {}, feedIdx: 0, actionCount: 0, finale: null }
  if (preview) {
    g.view.case_title = preview.title
    g.view.incident_summary = preview.incident_summary
  }
  g.view.chips = makeChips(g)
  games.set(id, g)
  return { game_id: id, view: structuredClone(g.view) }
}

// ---- 자유 주제 사건 생성 작업 (경과 시간으로 단계가 올라간다)
const JOB_STAGES = ['사건 파일 작성 중…', '인물 소개서 정리 중…', '용의자 명단 정리 중…', '증거와 알리바이 맞추는 중…', '마지막 검수 중…']
const JOB_STAGE_MS = 1400
const BAD_WORDS = ['야한', '성인물']
interface MockJob {
  text: string
  startedAt: number
  game: { game_id: string; view: PlayerView } | null
}
const caseJobs = new Map<string, MockJob>()

function mockPreview(text: string): CasePreview {
  const short = text.length > 16 ? `${text.slice(0, 16)}…` : text
  return {
    title: `${short} 사건`,
    incident_summary: `"${text}" — 소문은 순식간에 퍼졌고, 그 자리에 있던 다섯 사람은 저마다 할 말이 있다. 누군가는 분명 거짓말을 하고 있다.`,
    characters: CHARACTERS.map((c) => ({ ...structuredClone(c), location_id: null })),
  }
}

function mockJobState(jobId: string, j: MockJob): CaseJob {
  const base = { job_id: jobId, total: JOB_STAGES.length, preview: null, game_id: null, view: null, message: null, fallback_theme_id: null }
  const elapsed = Date.now() - j.startedAt
  if (BAD_WORDS.some((w) => j.text.includes(w))) {
    return { ...base, status: 'rejected', stage: 1, stage_text: JOB_STAGES[0], message: '이 주제로는 사건을 만들 수 없어요. 다른 소재로 다시 시도해 주세요.' }
  }
  const stage = Math.min(JOB_STAGES.length, Math.floor(elapsed / JOB_STAGE_MS) + 1)
  const preview = stage >= 3 ? mockPreview(j.text) : null
  if (j.text.includes('실패') && stage >= 4) {
    return { ...base, status: 'failed', stage, stage_text: JOB_STAGES[stage - 1], preview, message: '사건을 끝까지 만들지 못했어요. 기본 사건으로 시작할 수 있습니다.', fallback_theme_id: 'demo_db_deleted' }
  }
  if (elapsed >= JOB_STAGE_MS * JOB_STAGES.length) {
    j.game ??= startMockGame(mockPreview(j.text))
    return { ...base, status: 'ready', stage: JOB_STAGES.length, stage_text: '수사 준비 완료', preview: mockPreview(j.text), game_id: j.game.game_id, view: structuredClone(j.game.view) }
  }
  return { ...base, status: 'running', stage, stage_text: JOB_STAGES[stage - 1], preview }
}

function makeChips(g: MockGame): PlayerView['chips'] {
  const v = g.view
  const here = v.characters.filter((c) => c.location_id === v.player_location)
  const chips: PlayerView['chips'] = here.slice(0, 2).map((c, i) => ({
    id: `chip_ask_${c.id}_${i}`, label: `${c.name}: 어젯밤 11시쯤 어디 계셨어요?`, target_npc: c.id, kind: 'ask' as const, evidence_id: null,
  }))
  for (const ev of v.evidence.slice(-2)) {
    const target = (ev.id === 'ev_access_log' || ev.id === 'ev_notice' ? 'npc_cleaner' : ev.id === 'ev_chat_edit' ? 'npc_dba' : 'npc_cto')
    chips.push({ id: `chip_pr_${ev.id}`, label: `${ev.name} 제시`, target_npc: target, kind: 'present', evidence_id: ev.id })
  }
  return chips
}

const ev = (e: AgEvent): AgEvent => e
const custom = (name: string, value: unknown): AgEvent => ({ type: 'CUSTOM', name, value })
const delta = (...delta: JsonPatchOp[]): AgEvent => ({ type: 'STATE_DELTA', delta })

async function* speak(role: MessageRole, speakerId: string | null, text: string, emotion?: Emotion): AsyncGenerator<AgEvent> {
  const messageId = nid('msg')
  if (emotion && speakerId) yield custom('emotion', { npcId: speakerId, emotion })
  yield ev({ type: 'TEXT_MESSAGE_START', messageId, role, speakerId })
  const chars = [...text]
  for (let i = 0; i < chars.length; i += 3) {
    yield ev({ type: 'TEXT_MESSAGE_CONTENT', messageId, delta: chars.slice(i, i + 3).join('') })
    await sleep(25)
  }
  yield ev({ type: 'TEXT_MESSAGE_END', messageId })
}

function spend(g: MockGame, minutes = 25): AgEvent[] {
  const v = g.view
  v.actions_left = Math.max(0, v.actions_left - 1)
  v.clock += minutes
  g.actionCount += 1
  const ops: JsonPatchOp[] = [
    { op: 'replace', path: '/actions_left', value: v.actions_left },
    { op: 'replace', path: '/clock', value: v.clock },
  ]
  if (v.phase === 'briefing') {
    v.phase = 'day'
    ops.push({ op: 'replace', path: '/phase', value: 'day' })
  }
  return [delta(...ops)]
}

function maybeFeed(g: MockGame): AgEvent[] {
  if (g.actionCount % 3 !== 0) return []
  const base = FEED_POOL[g.feedIdx % FEED_POOL.length]
  g.feedIdx += 1
  const item: FeedItem = { ...base, id: nid('feed'), game_time: g.view.clock }
  return [custom('feed', item)]
}

function refreshChips(g: MockGame): AgEvent[] {
  g.view.chips = makeChips(g)
  return [custom('chips', { chips: g.view.chips })]
}

function bumpGauge(g: MockGame, npc: string, by: number): JsonPatchOp {
  const next = Math.min(5, (g.view.sufficiency_gauge[npc] ?? 0) + by)
  g.view.sufficiency_gauge[npc] = next
  return { op: 'add', path: `/sufficiency_gauge/${npc}`, value: next }
}

function addEvidence(g: MockGame, e: PublicEvidence): AgEvent[] {
  if (g.view.notebook.evidence_ids.includes(e.id)) return []
  g.view.evidence.push(e)
  g.view.notebook.evidence_ids.push(e.id)
  return [
    delta({ op: 'add', path: '/evidence/-', value: e }),
    custom('notebook', { added: { evidence_ids: [e.id] } }),
  ]
}

// ---------------------------------------------------------------- 행동
async function* runAction(g: MockGame, a: Action): AsyncGenerator<AgEvent> {
  const v = g.view
  yield { type: 'RUN_STARTED', runId: nid('run') }
  const freeMove = a.type === 'move' && (v.visited_locations ?? [v.player_location]).includes(a.location_id)
  if (v.actions_left <= 0 && a.type !== 'hint' && !freeMove) {
    yield* speak('narrator', null, '오늘 쓸 수 있는 행동을 모두 썼다. 하루를 마무리해야 한다.')
    yield { type: 'RUN_FINISHED' }
    return
  }
  switch (a.type) {
    case 'move': {
      const loc = v.locations.find((l) => l.id === a.location_id)
      const cur = v.locations.find((l) => l.id === v.player_location)
      const linked = loc && cur && (cur.connections.includes(loc.id) || loc.connections.includes(cur.id))
      if (!loc || !linked) {
        yield* speak('narrator', null, '그곳으로 바로 갈 수는 없다. 이어진 장소로 이동하자.')
        break
      }
      // 처음 가는 장소만 행동을 쓴다(서버 규칙 actions.move_revisit = 0 과 같다)
      const visited = v.visited_locations ?? (v.visited_locations = [v.player_location])
      const first = !visited.includes(loc.id)
      v.player_location = loc.id
      yield delta({ op: 'replace', path: '/player_location', value: loc.id })
      if (first) {
        visited.push(loc.id)
        yield delta({ op: 'add', path: '/visited_locations/-', value: loc.id })
        yield* spend(g, 15)
      } else if (v.phase === 'briefing') {
        v.phase = 'day'
        yield delta({ op: 'replace', path: '/phase', value: 'day' })
      }
      yield* speak('narrator', null, `${loc.name}에 도착했다. ${loc.description}`)
      const here = v.characters.filter((c) => c.location_id === loc.id)
      if (here.length >= 2) {
        yield custom('overheard', {
          locationId: loc.id,
          lines: [
            { speakerId: here[0].id, text: '…그 얘기는 여기서 하지 말죠. 형사가 와 있어요.' },
            { speakerId: here[1].id, text: '알겠어요. 일단 모른 척하고 있어요.' },
          ],
        })
      }
      yield* maybeFeed(g)
      yield* refreshChips(g)
      break
    }
    case 'investigate': {
      const e = EVIDENCE_AT[a.location_id]
      yield* spend(g, 30)
      if (!e || a.location_id !== v.player_location) {
        yield* speak('narrator', null, '여기서는 더 조사할 게 없다.')
      } else if (v.notebook.evidence_ids.includes(e.id)) {
        yield* speak('narrator', null, '이미 살펴본 곳이다. 새로 나올 것은 없다.')
      } else {
        yield* speak('narrator', null, `${josa(e.name, '을/를')} 발견했다. 수첩에 적어 두자.`)
        yield* addEvidence(g, e)
        yield custom('cutin', { text: '단서 발견!', style: 'find' })
      }
      yield* maybeFeed(g)
      yield* refreshChips(g)
      break
    }
    case 'ask':
      yield* ask(g, a.npc_id, a.text)
      break
    case 'chip': {
      const chip = v.chips.find((c) => c.id === a.chip_id)
      if (!chip) {
        yield* speak('narrator', null, '그 질문은 지금 할 수 없다.')
      } else if (chip.kind === 'present' && chip.evidence_id) {
        yield* present(g, chip.target_npc, chip.evidence_id)
      } else {
        yield* ask(g, chip.target_npc, chip.label)
      }
      break
    }
    case 'present':
      yield* present(g, a.npc_id, a.evidence_id)
      break
    case 'bluff':
      yield* bluff(g, a.npc_id, a.claim_id, a.basis_evidence_ids)
      break
    case 'warrant':
      yield* speak('chief', null, '영장은 목 모드에서 지원하지 않습니다.')
      break
    case 'apologize':
      yield custom('emotion', { npcId: a.npc_id, emotion: 'neutral' })
      yield* speak('narrator', null, '정중히 사과하자 상대의 표정이 조금 풀렸다.')
      break
    case 'hint':
      yield* speak('partner', null, '선배, 서버실 출입 기록부터 확인해 보죠. 그리고 탕비실 게시판도요.')
      break
  }
  yield { type: 'RUN_FINISHED' }
}

async function* ask(g: MockGame, npcId: string, text: string): AsyncGenerator<AgEvent> {
  const v = g.view
  const npc = v.characters.find((c) => c.id === npcId)
  if (!npc) {
    yield* speak('narrator', null, '그런 사람은 여기 없다.')
    return
  }
  yield* spend(g, 20)
  g.questions += 1
  const nonsense = text.trim().length < 2 || /^[ㄱ-ㅎㅏ-ㅣ\s.?!~]*$/.test(text)
  if (nonsense) {
    g.nonsense += 1
    if (g.nonsense >= 4) {
      yield* speak('npc', npcId, '바빠요. 나중에 오세요.', 'angry')
      yield custom('turn_away', { npcId, untilActions: 3 })
      return
    }
    if (g.nonsense === 3) {
      yield* speak('npc', npcId, '…지금 장난하시는 겁니까?', 'angry')
      yield* refreshChips(g)
      return
    }
    yield* speak('npc', npcId, '네? 무슨 말씀이신지…', 'nervous')
    return
  }
  g.nonsense = Math.max(0, g.nonsense - 1)
  const n = g.asked[npcId] ?? 0
  g.asked[npcId] = n + 1
  const pool = ASK_LINES[npcId] ?? [{ text: '글쎄요, 잘 모르겠습니다.', emotion: 'neutral' as Emotion }]
  const line = pool[n % pool.length]
  yield* speak('npc', npcId, line.text, line.emotion)
  const st = STATEMENTS[npcId]?.[n]
  if (st) {
    const s: NotebookStatement = { id: `st_${npcId}_${n}`, npc_id: npcId, content: st, game_time: v.clock, memory_id: `mem_${npcId}_${n}`, source_ids: [] }
    v.notebook.statements.push(s)
    yield delta({ op: 'add', path: '/notebook/statements/-', value: s })
    yield custom('notebook', { added: { statements: [s] } })
  }
  if (n % 2 === 1) yield delta(bumpGauge(g, npcId, 1))
  yield* maybeFeed(g)
}

async function* present(g: MockGame, npcId: string, evidenceId: string): AsyncGenerator<AgEvent> {
  const v = g.view
  const e = v.evidence.find((x) => x.id === evidenceId)
  if (!e || !v.characters.some((c) => c.id === npcId)) {
    yield* speak('narrator', null, '제시할 수 없는 증거다.')
    return
  }
  yield* spend(g, 20)
  g.questions += 1
  const c = CONTRA.find((x) => x.npc === npcId && x.evidence === evidenceId)
  const st = c && v.notebook.statements.find((s) => s.id === `st_${npcId}_${c.statementIdx}`)
  if (c && st && !v.notebook.contradictions.some((x) => x.id === c.id)) {
    const con: Contradiction = { id: c.id, statement_id: st.id, evidence_id: evidenceId, lie_id: `lie_${c.id}`, note: c.note }
    v.notebook.contradictions.push(con)
    yield custom('cutin', { text: '이의 있음!', style: 'objection' })
    await sleep(500)
    yield* speak('npc', npcId, c.line.text, c.line.emotion)
    yield delta({ op: 'add', path: '/notebook/contradictions/-', value: con })
    yield custom('notebook', { added: { contradictions: [con] } })
    yield delta(bumpGauge(g, npcId, 2))
  } else if (c && !st) {
    yield* speak('npc', npcId, '그게 뭔데요? 아직 그 얘기는 들은 적이 없는데요.', 'nervous')
  } else {
    yield* speak('npc', npcId, `${e.name}이라… 그게 저와 무슨 상관이죠?`, 'nervous')
    yield delta(bumpGauge(g, npcId, 1))
  }
  yield* maybeFeed(g)
}

async function* bluff(g: MockGame, npcId: string, claimId: string, basis: string[]): AsyncGenerator<AgEvent> {
  const claim = g.view.bluff_claims.find((x) => x.id === claimId)
  yield* spend(g, 25)
  g.questions += 1
  yield custom('cutin', { text: claim ? claim.label : '블러핑', style: 'bluff' })
  await sleep(500)
  if (npcId === CULPRIT && basis.length >= 2) {
    yield* speak('npc', npcId, '…알았어요, 다 말할게요. 서버실에 간 건 맞아요. 하지만 내가 지운 게 아니라, 시키는 대로…', 'sad')
    yield delta(bumpGauge(g, npcId, 2))
  } else if (npcId === CULPRIT && basis.length === 1) {
    yield* speak('npc', npcId, '그, 그런 게 있을 리가…! 거짓말이죠?', 'flustered')
    yield delta(bumpGauge(g, npcId, 1))
  } else {
    yield* speak('npc', npcId, '증거도 없이 사람을 떠보시는 겁니까? 불쾌하네요.', 'angry')
  }
}

// ---------------------------------------------------------------- 밤
async function* runNight(g: MockGame): AsyncGenerator<AgEvent> {
  yield { type: 'RUN_STARTED', runId: nid('run') }
  const steps = ['사람들이 하나둘 퇴근한다…', '서버실의 불이 꺼진다…', '복도에서 발소리가 들린다…', '단톡방에 메시지가 쌓인다…', '창밖이 밝아 온다…']
  for (let i = 0; i < steps.length; i++) {
    yield custom('night_progress', { step: i + 1, total: steps.length, text: steps[i] })
    await sleep(700)
  }
  const v = g.view
  v.day += 1
  v.phase = 'day'
  v.actions_left = MAX_ACTIONS
  v.clock = (v.day - 1) * 1440 + DAY_START
  v.player_location = 'loc_lobby'
  const spots = LOCATIONS.map((l) => l.id)
  v.characters.forEach((c, i) => {
    c.location_id = spots[(spots.indexOf(c.location_id ?? 'loc_lobby') + v.day + i) % spots.length]
    c.emotion = 'neutral'
  })
  g.nonsense = 0
  v.chips = makeChips(g)
  yield { type: 'STATE_SNAPSHOT', snapshot: structuredClone(v) }
  yield custom('director', { eventId: `dir_day${v.day}`, title: '익명 제보', text: '"청소 카트에서 이상한 소리가 났다는 얘기가 있어요." 누군가 메신저로 보낸 메시지다.' })
  const item: FeedItem = { id: nid('feed'), channel: '사내 메신저', author: '익명', text: '밤사이 누가 서버실 근처에서 서성이던데?', game_time: v.clock }
  yield custom('feed', item)
  yield { type: 'RUN_FINISHED' }
}

// ---------------------------------------------------------------- 최종 추리
async function* runFinale(g: MockGame, step: FinaleStep): AsyncGenerator<AgEvent> {
  const v = g.view
  yield { type: 'RUN_STARTED', runId: nid('run') }
  const f = g.finale
  const emit = (accused: string, stage: FinaleValue['stage'], lives: number, filled: FinaleStage[], last: FinaleValue['last'] = null) =>
    custom('finale', { accused_id: accused, stage, lives, filled, last } satisfies FinaleValue)
  const end = async function* (ending: string): AsyncGenerator<AgEvent> {
    v.ending = ending
    v.phase = 'ended'
    yield delta({ op: 'replace', path: '/ending', value: ending }, { op: 'replace', path: '/phase', value: 'ended' })
    yield custom('ending', { ending })
  }
  if (step.type === 'start') {
    g.finale = { accused: step.accused_id, lives: 3, filled: [] }
    v.phase = 'finale'
    yield delta({ op: 'replace', path: '/phase', value: 'finale' })
    yield custom('cutin', { text: '범인은 당신입니다!', style: 'accuse' })
    await sleep(600)
    yield* speak('npc', step.accused_id, '제, 제가요? 증거 있으세요?', 'nervous')
    yield emit(step.accused_id, 'opportunity', 3, [])
  } else if (!f) {
    yield { type: 'RUN_ERROR', message: '최종 추리가 시작되지 않았습니다.', code: 'finale_not_started' }
    return
  } else if (step.type === 'present') {
    const ok = f.accused === CULPRIT && FINALE_VALID[step.stage] === step.evidence_id && !f.filled.includes(step.stage)
    if (ok) {
      f.filled.push(step.stage)
      yield custom('cutin', { text: '이의 있음!', style: 'objection' })
      await sleep(500)
      const done = f.filled.length === 3
      yield* speak('npc', f.accused, done ? '…더는 숨길 수가 없네요.' : '그건… 그건 우연이에요!', done ? 'sad' : 'flustered')
      const nextStage = (['opportunity', 'means', 'motive'] as FinaleStage[]).find((s) => !f.filled.includes(s)) ?? 'done'
      yield emit(f.accused, nextStage, f.lives, [...f.filled], { result: 'correct', evidence_id: step.evidence_id })
    } else {
      f.lives -= 1
      yield* speak('npc', f.accused, '그게 증거라고요? 어림도 없어요.', 'angry')
      const nextStage = (['opportunity', 'means', 'motive'] as FinaleStage[]).find((s) => !f.filled.includes(s)) ?? 'done'
      yield emit(f.accused, nextStage, f.lives, [...f.filled], { result: 'wrong', evidence_id: step.evidence_id })
      if (f.lives <= 0) {
        yield* end(f.accused === CULPRIT ? 'escaped' : 'wrong_accusation')
      }
    }
  } else if (step.type === 'confirm') {
    if (f.filled.length === 3) {
      yield* speak('chief', null, '수고했다, 형사. 사건 종결이다.')
      yield* end('success')
    } else {
      yield { type: 'RUN_ERROR', message: '아직 기회·수단·동기를 모두 밝히지 못했습니다.', code: 'finale_incomplete' }
      return
    }
  }
  yield { type: 'RUN_FINISHED' }
}

// ---------------------------------------------------------------- 저장 / 이력
const LS_SAVES = 'mock.saves'
const LS_HIST = 'mock.history'
function lsGet<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key)
    return raw ? (JSON.parse(raw) as T) : fallback
  } catch {
    return fallback
  }
}
function lsSet(key: string, value: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch {
    /* 저장 불가 환경 */
  }
}

function grade(q: number): 'S' | 'A' | 'B' | 'C' {
  return q <= 15 ? 'S' : q <= 30 ? 'A' : q <= 50 ? 'B' : 'C'
}

export const mockApi: Api = {
  async themes() {
    await sleep(150)
    return THEMES
  },
  async createGame(themeId, options) {
    void themeId // 목은 항상 같은 사건
    void options // 목은 옵션을 무시한다
    await sleep(500)
    return startMockGame()
  },
  async createCase(themeText) {
    const text = themeText.trim()
    if (text.length < 2 || text.length > 80) throw new Error('요청 실패 (400) 주제는 2~80자여야 합니다.')
    await sleep(150)
    const job_id = nid('job')
    caseJobs.set(job_id, { text, startedAt: Date.now(), game: null })
    return { job_id }
  },
  async caseJob(jobId) {
    const j = caseJobs.get(jobId)
    if (!j) throw new Error('요청 실패 (404) 없는 작업입니다.')
    return mockJobState(jobId, j)
  },
  async listGames() {
    const out = new Map<string, { game_id: string; case_title: string; day: number; last_seen: string }>()
    for (const [id, g] of games) out.set(id, { game_id: id, case_title: g.view.case_title, day: g.view.day, last_seen: new Date().toISOString() })
    const saves = lsGet<Record<string, { view: PlayerView; at?: string }>>(LS_SAVES, {})
    for (const sv of Object.values(saves)) {
      const id = sv.view.game_id
      if (!out.has(id)) out.set(id, { game_id: id, case_title: sv.view.case_title, day: sv.view.day, last_seen: sv.at ?? new Date().toISOString() })
    }
    return [...out.values()]
  },
  async listSaves(id) {
    const saves = lsGet<Record<string, { view: PlayerView; name?: string; at?: string }>>(LS_SAVES, {})
    return Object.entries(saves)
      .filter(([, sv]) => sv.view.game_id === id)
      .map(([slot_id, sv]) => ({ slot_id, name: sv.name || `${sv.view.day}일차 저장`, kind: 'manual', saved_at: sv.at ?? new Date().toISOString() }))
  },
  async sources(id, statementId) {
    const g = games.get(id)
    const st = g?.view.notebook.statements.find((x) => x.id === statementId)
    if (!st) return []
    const who = g!.view.characters.find((c) => c.id === st.npc_id)?.name ?? '진술자'
    return [{ kind: 'statement', title: `${who}의 진술 원문`, content: `"${st.content}" (게임 시각 ${Math.floor(st.game_time / 60) % 24}시경, 심문 중)` }]
  },
  async portraits() {
    return { pending: false, urls: {}, emotions: {} } // 목 모드는 AI 사진 없이 절차적 SVG
  },
  async prepare() {
    return { prepared: 0 } // 목은 답을 바로 만들므로 미리 만들 것이 없다
  },
  async getGame(id) {
    let g = games.get(id)
    if (!g) {
      // 새로고침 뒤: 가장 최근 세이브로 되살린다(목 모드 전용)
      const saves = lsGet<Record<string, { view: PlayerView; questions: number; asked: Record<string, number>; at?: string }>>(LS_SAVES, {})
      const mine = Object.values(saves).filter((x) => x.view.game_id === id).sort((a, b) => (b.at ?? '').localeCompare(a.at ?? ''))[0]
      if (!mine) throw new Error('게임을 찾을 수 없습니다 (404)')
      g = { view: mine.view, questions: mine.questions, startedAt: Date.now(), nonsense: 0, asked: mine.asked ?? {}, feedIdx: 0, actionCount: 0, finale: null }
      games.set(id, g)
    }
    return structuredClone(g.view)
  },
  async *action(id, a) {
    const g = games.get(id)
    if (!g) return yield { type: 'RUN_ERROR', message: '게임을 찾을 수 없습니다.', code: '404' }
    yield* runAction(g, a)
  },
  async *night(id) {
    const g = games.get(id)
    if (!g) return yield { type: 'RUN_ERROR', message: '게임을 찾을 수 없습니다.', code: '404' }
    yield* runNight(g)
  },
  async *finale(id, step) {
    const g = games.get(id)
    if (!g) return yield { type: 'RUN_ERROR', message: '게임을 찾을 수 없습니다.', code: '404' }
    yield* runFinale(g, step)
  },
  async save(id, slotName) {
    const g = games.get(id)
    if (!g) throw new Error('게임을 찾을 수 없습니다 (404)')
    const slot_id = nid('slot')
    const saves = lsGet<Record<string, unknown>>(LS_SAVES, {})
    saves[slot_id] = { view: g.view, questions: g.questions, asked: g.asked, name: slotName ?? '', at: new Date().toISOString() }
    lsSet(LS_SAVES, saves)
    return { slot_id, saved_at: new Date().toISOString() }
  },
  async load(id, slotId) {
    const saves = lsGet<Record<string, { view: PlayerView; questions: number; asked: Record<string, number> }>>(LS_SAVES, {})
    const s = saves[slotId]
    if (!s) throw new Error('세이브를 찾을 수 없습니다 (404)')
    const view = { ...s.view, game_id: id }
    const g: MockGame = { view, questions: s.questions, startedAt: Date.now(), nonsense: 0, asked: s.asked ?? {}, feedIdx: 0, actionCount: 0, finale: null }
    games.set(id, g)
    return structuredClone(view)
  },
  async clear(id) {
    const g = games.get(id)
    if (!g) throw new Error('게임을 찾을 수 없습니다 (404)')
    const culprit = g.view.characters.find((c) => c.id === CULPRIT)!
    const success = g.view.ending === 'success'
    const history: ClearHistory = {
      id: nid('hist'),
      player_id: 'player',
      case_title: g.view.case_title,
      theme: '💾 사라진 운영 DB',
      cleared_at: new Date().toISOString(),
      success,
      real_minutes: Math.max(1, Math.round((Date.now() - g.startedAt) / 60000)),
      game_days: g.view.day,
      question_count: g.questions,
      grade: success ? grade(g.questions) : null,
      titles: success ? ['동네 괴짜 형사'] : [],
      reputation: success ? 12 : -3,
      culprit: { name: culprit.name, role: culprit.role },
      characters: g.view.characters.map((c) => ({ name: c.name, role: c.role, face_seed: c.face_seed, appearance: c.appearance })),
      highlight: g.view.notebook.contradictions.length
        ? '출입 기록 한 장으로 "근처에도 안 갔다"는 말을 깨뜨렸다'
        : '발품으로 서버실과 탕비실을 샅샅이 뒤졌다',
      fingerprint: {},
    }
    const hist = lsGet<ClearHistory[]>(LS_HIST, [])
    lsSet(LS_HIST, [history, ...hist].slice(0, 30))
    const line = '🔍'.repeat(Math.min(history.game_days, 4)) + (success ? '✅' : '❌')
    const card: ShareCard | null = success
      ? { emoji_line: line, share_text: `${line} ${history.question_count}질문 만에 해결`, theme_color: '#3b6ea5' }
      : null
    games.delete(id)
    return { history, card }
  },
  async history() {
    return lsGet<ClearHistory[]>(LS_HIST, [])
  },
}

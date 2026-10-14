import { mockApi } from './mock'
import { readSseJson } from './sse'
import type {
  Action,
  AgEvent,
  CaseJob,
  ClearHistory,
  CreateOptions,
  FinaleStep,
  GameSummary,
  PlayerView,
  PortraitStatus,
  SaveSlotInfo,
  ShareCard,
  SourceItem,
  Theme,
} from './types'

export interface Api {
  themes(): Promise<Theme[]>
  createGame(themeId: string, options?: CreateOptions): Promise<{ game_id: string; view: PlayerView }>
  createCase(themeText: string, options?: CreateOptions): Promise<{ job_id: string }>
  caseJob(jobId: string): Promise<CaseJob>
  listGames(): Promise<GameSummary[]>
  listSaves(gameId: string): Promise<SaveSlotInfo[]>
  sources(gameId: string, statementId: string): Promise<SourceItem[]>
  getGame(gameId: string): Promise<PlayerView>
  portraits(gameId: string): Promise<PortraitStatus>
  /** 심문 중인 인물의 추천 질문 답을 서버가 미리 만들게 알린다(기다리지 않음). */
  prepare(gameId: string, npcId: string): Promise<{ prepared: number }>
  action(gameId: string, action: Action): AsyncIterable<AgEvent>
  night(gameId: string): AsyncIterable<AgEvent>
  finale(gameId: string, step: FinaleStep): AsyncIterable<AgEvent>
  save(gameId: string, slotName?: string): Promise<{ slot_id: string; saved_at: string }>
  load(gameId: string, slotId: string): Promise<PlayerView>
  clear(gameId: string): Promise<{ history: ClearHistory; card: ShareCard | null }>
  history(): Promise<ClearHistory[]>
}

const BASE = '/api'

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = ''
    try {
      detail = await res.text()
    } catch {
      /* 본문 없음 */
    }
    throw new Error(`요청 실패 (${res.status}) ${detail.slice(0, 200)}`)
  }
  return (await res.json()) as T
}

function post(path: string, body?: unknown): Promise<Response> {
  return fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream, application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
}

async function* stream(path: string, body?: unknown): AsyncGenerator<AgEvent> {
  let res: Response
  try {
    res = await post(path, body)
  } catch {
    yield { type: 'RUN_ERROR', message: '서버에 연결할 수 없습니다.', code: 'network' }
    return
  }
  if (!res.ok) {
    yield { type: 'RUN_ERROR', message: `서버 오류 (${res.status})`, code: String(res.status) }
    return
  }
  try {
    for await (const ev of readSseJson<AgEvent>(res)) yield ev
  } catch {
    yield { type: 'RUN_ERROR', message: '연결이 끊어졌습니다.', code: 'stream' }
  }
}

export const httpApi: Api = {
  themes: () => fetch(`${BASE}/themes`).then((r) => json<Theme[]>(r)),
  createGame: async (themeId, options) => json(await post('/games', { theme_id: themeId, options })),
  createCase: async (themeText, options) => json(await post('/cases', { theme_text: themeText, options })),
  caseJob: (id) => fetch(`${BASE}/cases/${encodeURIComponent(id)}`).then((r) => json<CaseJob>(r)),
  listGames: () => fetch(`${BASE}/games`).then((r) => json<GameSummary[]>(r)),
  listSaves: (id) => fetch(`${BASE}/games/${id}/saves`).then((r) => json<SaveSlotInfo[]>(r)),
  sources: (id, st) => fetch(`${BASE}/games/${id}/sources/${encodeURIComponent(st)}`).then((r) => json<SourceItem[]>(r)),
  getGame: (id) => fetch(`${BASE}/games/${id}`).then((r) => json<PlayerView>(r)),
  portraits: (id) => fetch(`${BASE}/games/${id}/portraits`).then((r) => json<PortraitStatus>(r)),
  prepare: async (id, npcId) => json(await post(`/games/${id}/prepare`, { npc_id: npcId })),
  action: (id, action) => stream(`/games/${id}/actions`, action),
  night: (id) => stream(`/games/${id}/night`),
  finale: (id, step) => stream(`/games/${id}/finale`, step),
  save: async (id, slotName) => json(await post(`/games/${id}/save`, { slot_name: slotName })),
  load: async (id, slotId) => json(await post(`/games/${id}/load`, { slot_id: slotId })),
  clear: async (id) => json(await post(`/games/${id}/clear`)),
  history: () => fetch(`${BASE}/history`).then((r) => json<ClearHistory[]>(r)),
}

export const USE_MOCK = import.meta.env.VITE_USE_MOCK === '1'
export const api: Api = USE_MOCK ? mockApi : httpApi

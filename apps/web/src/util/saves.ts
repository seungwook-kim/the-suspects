// 계약에 세이브 슬롯 목록 API 가 없어, 저장할 때 받은 slot_id 를 브라우저에 기억해 둔다. (제안: GET /api/saves)
export interface SaveRef {
  slot_id: string
  game_id: string
  slot_name: string
  saved_at: string
  case_title: string
  day: number
}

const KEY = 'suspects.saves'

export function getSaves(): SaveRef[] {
  try {
    const raw = localStorage.getItem(KEY)
    return raw ? (JSON.parse(raw) as SaveRef[]) : []
  } catch {
    return []
  }
}

export function addSave(ref: SaveRef) {
  try {
    const list = [ref, ...getSaves().filter((s) => s.slot_id !== ref.slot_id)].slice(0, 20)
    localStorage.setItem(KEY, JSON.stringify(list))
  } catch {
    /* 저장 불가 */
  }
}

export function removeSave(slotId: string) {
  try {
    localStorage.setItem(KEY, JSON.stringify(getSaves().filter((s) => s.slot_id !== slotId)))
  } catch {
    /* 무시 */
  }
}

export function getPref<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(`suspects.${key}`)
    return raw ? (JSON.parse(raw) as T) : fallback
  } catch {
    return fallback
  }
}

export function setPref(key: string, value: unknown) {
  try {
    localStorage.setItem(`suspects.${key}`, JSON.stringify(value))
  } catch {
    /* 무시 */
  }
}

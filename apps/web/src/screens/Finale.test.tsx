import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { PlayerView, PublicCharacter } from '../api/types'
import { initialClientState, type ClientState } from '../state/reducer'
import type { GameApi } from '../state/useGame'
import { Finale } from './Finale'

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const chars: PublicCharacter[] = ['다은', '가람', '나래'].map((name, i) => ({
  id: `c${i}`, name, role: '직원', age: 30, gender: 'X', appearance: {}, face_seed: i + 1, location_id: null, emotion: 'neutral', one_liner: '',
}))
const view = {
  game_id: 'g', case_title: '사건', incident_summary: '', day: 1, phase: 'finale', clock: 0, actions_left: 3, player_location: 'l',
  locations: [], characters: chars,
  evidence: [{ id: 'e1', name: '출입 기록', kind: '기록', content: '서버실 출입 기록' }],
  notebook: { evidence: [], statements: [], contradictions: [] }, sufficiency_gauge: {}, reputation_band: '', chips: [], feed: [], bluff_claims: [],
  ending: 'none', actions_total: 3, max_days: 3,
} as unknown as PlayerView

let root: Root
let host: HTMLElement
const finaleStep = vi.fn()
const mk = (patch: Partial<ClientState>): GameApi => ({ state: { ...initialClientState, view, ...patch }, dispatch: () => {}, finaleStep }) as unknown as GameApi
const render = (g: GameApi, onResult = () => {}) => act(() => root.render(<Finale g={g} onBack={() => {}} onResult={onResult} />))
const btn = (label: string) => [...host.querySelectorAll('button')].find((b) => b.textContent?.includes(label)) as HTMLButtonElement

beforeEach(() => {
  finaleStep.mockReset()
  host = document.createElement('div')
  document.body.appendChild(host)
  root = createRoot(host)
})
afterEach(() => {
  act(() => root.unmount())
  host.remove()
})

describe('Finale', () => {
  it('1단계: 이름순 타일, 고르기 전엔 이유 글자, 고르면 지목', () => {
    render(mk({}))
    const names = [...host.querySelectorAll('.person-name')].map((n) => n.textContent)
    expect(names).toEqual(['가람', '나래', '다은'])
    expect(btn('이 사람을 지목한다').disabled).toBe(true)
    expect(host.textContent).toContain('용의자를 고르세요')
    act(() => btn('나래').click())
    expect(host.querySelector('[aria-pressed="true"] .sel-label')?.textContent).toContain('지목')
    act(() => btn('이 사람을 지목한다').click())
    expect(finaleStep).toHaveBeenCalledWith({ type: 'start', accused_id: 'c2' })
  })

  it('2단계: 남은 기회 글자, 단계 표시, 증거 제시, 틀림 안내', () => {
    render(mk({ finale: { accused_id: 'c0', stage: 'means', lives: 2, filled: ['opportunity'], last: { result: 'wrong' } } }))
    expect(host.textContent).toContain('남은 기회 2/3')
    expect(host.textContent).toContain('밝힘')
    expect(host.textContent).toContain('수단: 밝힐 증거')
    expect(host.textContent).toContain('틀림')
    expect(btn('증거 제시').disabled).toBe(true)
    act(() => btn('출입 기록').click())
    act(() => btn('증거 제시').click())
    expect(finaleStep).toHaveBeenCalledWith({ type: 'present', stage: 'means', evidence_id: 'e1' })
  })

  it('엔딩: 제목·본문·결과 카드 보기', () => {
    const onResult = vi.fn()
    render(mk({ finale: { accused_id: 'c0', stage: 'done', lives: 1, filled: ['opportunity', 'means', 'motive'] }, ending: { ending: 'success' } }), onResult)
    expect(host.textContent).toContain('사건 해결')
    act(() => btn('결과 카드 보기').click())
    expect(onResult).toHaveBeenCalled()
  })

  it('무고한 사람을 지목해 반박을 들으면: 증거 칸 대신 그래도 지목 / 다시 고르기', () => {
    render(mk({ finale: { accused_id: 'c1', stage: 'opportunity', lives: 3, filled: [], last: null, pending: true } }))
    expect(host.textContent).toContain('가람이 반박합니다')
    expect(host.textContent).not.toContain('밝힐 증거를 제시하세요')
    act(() => btn('다시 고른다').click())
    expect(finaleStep).toHaveBeenCalledWith({ type: 'retract' })
    act(() => btn('그래도 지목한다').click())
    expect(finaleStep).toHaveBeenCalledWith({ type: 'confirm' })
  })

  it('지목 직후(실제 서버): 다음에 밝힐 단계의 증거 칸이 열린다', () => {
    render(mk({ finale: { accused_id: 'c0', stage: 'opportunity', lives: 3, filled: [], last: null, pending: false } }))
    expect(host.textContent).toContain('기회: 밝힐 증거를 제시하세요')
    expect(btn('추리 확정')).toBeUndefined()
  })
})

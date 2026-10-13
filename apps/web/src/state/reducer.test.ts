import { describe, expect, it } from 'vitest'
import type { AgEvent, PlayerView, PublicCharacter } from '../api/types'
import { applyEvent, clientReducer, initialClientState, type ClientState } from './reducer'

const view = (): PlayerView => ({
  game_id: 'g1', case_title: 't', incident_summary: 's', day: 1, phase: 'day', clock: 540, actions_left: 12,
  player_location: 'a', locations: [], characters: [], evidence: [],
  notebook: { evidence_ids: [], statements: [], contradictions: [], relations_known: [], board_links: [], sufficiency: {} },
  sufficiency_gauge: {}, reputation_band: '', chips: [], feed: [], bluff_claims: [], ending: 'none', actions_total: 12, max_days: 5,
})

const run = (events: AgEvent[], s: ClientState = initialClientState) => events.reduce(applyEvent, s)

describe('AG-UI 리듀서', () => {
  it('대사 이벤트가 글자를 이어 붙인다', () => {
    const s = run([
      { type: 'RUN_STARTED' },
      { type: 'TEXT_MESSAGE_START', messageId: 'm1', role: 'npc', speakerId: 'npc_dba' },
      { type: 'TEXT_MESSAGE_CONTENT', messageId: 'm1', delta: '안녕' },
      { type: 'TEXT_MESSAGE_CONTENT', messageId: 'm1', delta: '하세요' },
      { type: 'TEXT_MESSAGE_CONTENT', messageId: 'other', delta: '무시' },
      { type: 'TEXT_MESSAGE_END', messageId: 'm1' },
    ])
    expect(s.running).toBe(true)
    expect(s.dialogue).toMatchObject({ text: '안녕하세요', done: true, speakerId: 'npc_dba', role: 'npc' })
  })

  it('STATE_SNAPSHOT 후 STATE_DELTA(JSON Patch)가 적용된다', () => {
    const s = run([
      { type: 'STATE_SNAPSHOT', snapshot: view() },
      {
        type: 'STATE_DELTA',
        delta: [
          { op: 'replace', path: '/actions_left', value: 11 },
          { op: 'add', path: '/feed/-', value: { id: 'f1', channel: '단톡방', author: 'a', text: 'hi', game_time: 1 } },
          { op: 'add', path: '/sufficiency_gauge/npc_dba', value: 2 },
        ],
      },
    ])
    expect(s.view!.actions_left).toBe(11)
    expect(s.view!.feed).toHaveLength(1)
    expect(s.view!.sufficiency_gauge.npc_dba).toBe(2)
    expect(s.needsResync).toBe(false)
  })

  it('어긋난 델타는 화면을 멈추지 않고 재동기화를 요청한다', () => {
    const s = run([
      { type: 'STATE_SNAPSHOT', snapshot: view() },
      { type: 'STATE_DELTA', delta: [{ op: 'replace', path: '/없는/경로', value: 1 }] },
    ])
    expect(s.needsResync).toBe(true)
    expect(s.view!.actions_left).toBe(12)
    expect(run([{ type: 'STATE_DELTA', delta: [] }]).needsResync).toBe(true) // 뷰가 없을 때
  })

  it('CUSTOM: notebook 은 중복 없이 합치고 새 모순을 표시한다', () => {
    const con = { id: 'c1', statement_id: 'st1', evidence_id: 'e1', lie_id: 'l1', note: '' }
    const ev: AgEvent = { type: 'CUSTOM', name: 'notebook', value: { added: { evidence_ids: ['e1'], contradictions: [con] } } }
    const s = run([{ type: 'STATE_SNAPSHOT', snapshot: view() }, ev, ev])
    expect(s.view!.notebook.evidence_ids).toEqual(['e1'])
    expect(s.view!.notebook.contradictions).toHaveLength(1)
    expect(s.newContradictions).toEqual(['c1'])
  })

  it('CUSTOM: emotion, feed, chips, cutin, director, night_progress, turn_away, overheard, ending', () => {
    const s = run([
      { type: 'STATE_SNAPSHOT', snapshot: view() },
      { type: 'CUSTOM', name: 'emotion', value: { npcId: 'n1', emotion: 'angry' } },
      { type: 'CUSTOM', name: 'feed', value: { id: 'f1', channel: 'c', author: 'a', text: 't', game_time: 0 } },
      { type: 'CUSTOM', name: 'chips', value: { chips: [{ id: 'k', label: 'l', target_npc: 'n1', kind: 'ask', evidence_id: null }] } },
      { type: 'CUSTOM', name: 'cutin', value: { text: '이의 있음!', style: 'x' } },
      { type: 'CUSTOM', name: 'director', value: { eventId: 'e', title: '전화', text: '따르릉' } },
      { type: 'CUSTOM', name: 'night_progress', value: { step: 1, total: 3, text: '…' } },
      { type: 'CUSTOM', name: 'turn_away', value: { npcId: 'n1', untilActions: 2 } },
      { type: 'CUSTOM', name: 'overheard', value: { locationId: 'a', lines: [{ speakerId: 'n1', text: 'x' }] } },
      { type: 'CUSTOM', name: 'ending', value: { ending: 'success' } },
      { type: 'CUSTOM', name: 'unknown_future_event', value: {} },
    ])
    expect(s.emotions.n1).toBe('angry')
    expect(s.view!.feed).toHaveLength(1)
    expect(s.view!.chips[0].id).toBe('k')
    expect(s.cutin?.text).toBe('이의 있음!')
    expect(s.director?.title).toBe('전화')
    expect(s.night?.step).toBe(1)
    expect(s.turnAway.n1).toBe(2)
    expect(s.overheard?.lines).toHaveLength(1)
    expect(s.ending?.ending).toBe('success')
  })

  it('스냅샷은 표정 덮어쓰기를 비우고, RUN_FINISHED 는 밤 오버레이를 닫는다', () => {
    let s = run([
      { type: 'CUSTOM', name: 'emotion', value: { npcId: 'n1', emotion: 'sad' } },
      { type: 'CUSTOM', name: 'night_progress', value: { step: 1, total: 2, text: '' } },
    ])
    s = run([{ type: 'STATE_SNAPSHOT', snapshot: view() }, { type: 'RUN_FINISHED' }], s)
    expect(s.emotions).toEqual({})
    expect(s.night).toBeNull()
    expect(s.running).toBe(false)
  })

  it('RUN_ERROR 는 오류 문구를 남기고 멈춘다', () => {
    const s = run([{ type: 'RUN_STARTED' }, { type: 'RUN_ERROR', message: '문제', code: 'x' }])
    expect(s.error).toBe('문제')
    expect(s.running).toBe(false)
  })

  it('finale 이벤트의 last 는 {result, evidence_id} 객체', () => {
    const s = run([{ type: 'CUSTOM', name: 'finale', value: { accused_id: 'n1', stage: 'means', lives: 2, filled: ['opportunity'], last: { result: 'wrong', evidence_id: 'e1' } } }])
    expect(s.finale?.last?.result).toBe('wrong')
    expect(s.finale?.lives).toBe(2)
  })

  it('turn_away 는 행동할 때마다 줄어든다', () => {
    let s = run([{ type: 'CUSTOM', name: 'turn_away', value: { npcId: 'n1', untilActions: 2 } }])
    s = clientReducer(s, { kind: 'tick_turn_away' })
    expect(s.turnAway.n1).toBe(1)
    s = clientReducer(s, { kind: 'tick_turn_away' })
    expect(s.turnAway.n1).toBeUndefined()
  })

  it('나중에 완성된 초상화 주소만 채우고, 바뀐 게 없으면 같은 상태를 돌려준다', () => {
    const ch = (id: string): PublicCharacter => ({
      id, name: id, role: 'r', age: 30, gender: 'F', appearance: {}, face_seed: 1, location_id: null, emotion: 'neutral', one_liner: '',
    })
    let s = clientReducer(initialClientState, { kind: 'set_view', view: { ...view(), characters: [ch('a'), ch('b')] } })
    s = clientReducer(s, { kind: 'portraits', urls: { a: '/api/portraits/g1/a.webp?v=1' } })
    expect(s.view!.characters.map((c) => c.portrait_url ?? null)).toEqual(['/api/portraits/g1/a.webp?v=1', null])
    const same = clientReducer(s, { kind: 'portraits', urls: { a: '/api/portraits/g1/a.webp?v=1' } })
    expect(same).toBe(s)
  })
})

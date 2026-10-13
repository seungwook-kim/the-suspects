import { describe, expect, it } from 'vitest'
import { applyEvent, initialClientState, type ClientState } from '../state/reducer'
import { mockApi } from './mock'
import type { AgEvent } from './types'

async function drain(s: ClientState, it: AsyncIterable<AgEvent>): Promise<ClientState> {
  for await (const ev of it) s = applyEvent(s, ev)
  return s
}

describe('목 모드 한 판', () => {
  it('조사 -> 질문 -> 증거 제시(모순) -> 밤 -> 최종 추리 -> 결과 카드', { timeout: 30000 }, async () => {
    const { game_id, view } = await mockApi.createGame('demo_db_deleted')
    let s: ClientState = applyEvent(initialClientState, { type: 'STATE_SNAPSHOT', snapshot: view })
    expect(s.view!.actions_total).toBe(12)
    expect(s.view!.max_days).toBeGreaterThan(0)
    expect(s.view!.characters).toHaveLength(5)
    expect(s.view!.locations).toHaveLength(6)

    s = await drain(s, mockApi.action(game_id, { type: 'move', location_id: 'loc_pantry' }))
    s = await drain(s, mockApi.action(game_id, { type: 'investigate', location_id: 'loc_pantry' }))
    s = await drain(s, mockApi.action(game_id, { type: 'move', location_id: 'loc_server_room' }))
    s = await drain(s, mockApi.action(game_id, { type: 'investigate', location_id: 'loc_server_room' }))
    expect(s.view!.evidence.map((e) => e.id)).toEqual(['ev_admin_note', 'ev_access_log'])
    s = await drain(s, mockApi.action(game_id, { type: 'ask', npc_id: 'npc_cleaner', text: '어젯밤 어디 계셨어요?' }))
    expect(s.dialogue?.text.length).toBeGreaterThan(0)
    s = await drain(s, mockApi.action(game_id, { type: 'present', npc_id: 'npc_cleaner', evidence_id: 'ev_access_log' }))
    expect(s.view!.notebook.contradictions).toHaveLength(1)
    expect(s.cutin?.text).toBe('이의 있음!')
    expect(s.view!.actions_left).toBeLessThan(12)

    // 진술 출처 원문, 게임 목록
    const stId = s.view!.notebook.statements[0].id
    const src = await mockApi.sources(game_id, stId)
    expect(src[0].content).toContain(s.view!.notebook.statements[0].content)
    expect((await mockApi.listGames()).some((x) => x.game_id === game_id)).toBe(true)
    const slot = await mockApi.save(game_id, '테스트')
    expect((await mockApi.listSaves(game_id)).map((x) => x.slot_id)).toContain(slot.slot_id)

    s = await drain(s, mockApi.night(game_id))
    expect(s.view!.day).toBe(2)
    expect(s.view!.actions_left).toBe(12)

    // 증거 하나 더(사무실/CTO실) 모은 뒤 최종 추리
    for (const [loc, from] of [['loc_office', 'loc_lobby'], ['loc_meeting', 'loc_office'], ['loc_cto_room', 'loc_meeting']] as const) {
      void from
      s = await drain(s, mockApi.action(game_id, { type: 'move', location_id: loc }))
    }
    expect(s.view!.player_location).toBe('loc_cto_room')
    s = await drain(s, mockApi.action(game_id, { type: 'investigate', location_id: 'loc_cto_room' }))
    s = await drain(s, mockApi.finale(game_id, { type: 'start', accused_id: 'npc_cleaner' }))
    for (const [stage, evidence_id] of [['opportunity', 'ev_access_log'], ['means', 'ev_admin_note'], ['motive', 'ev_notice']] as const)
      s = await drain(s, mockApi.finale(game_id, { type: 'present', stage, evidence_id }))
    expect(s.finale?.stage).toBe('done')
    s = await drain(s, mockApi.finale(game_id, { type: 'confirm' }))
    expect(s.ending?.ending).toBe('success')

    const { history, card } = await mockApi.clear(game_id)
    expect(card?.share_text).toContain('질문 만에 해결')
    expect(card?.theme_color).toMatch(/^#[0-9a-f]{6}$/i)
    expect(history.success).toBe(true)
    expect(history.characters).toHaveLength(5)
  })

  it('실패한 판은 card 가 null', { timeout: 30000 }, async () => {
    const { game_id } = await mockApi.createGame('demo_db_deleted', { tone: 'comic', difficulty: 'easy', play_minutes: 20 })
    let s: ClientState = initialClientState
    s = await drain(s, mockApi.finale(game_id, { type: 'start', accused_id: 'npc_cto' }))
    for (let i = 0; i < 3; i++) s = await drain(s, mockApi.finale(game_id, { type: 'present', stage: 'opportunity', evidence_id: 'x' }))
    expect(s.ending?.ending).toBe('wrong_accusation')
    const { history, card } = await mockApi.clear(game_id)
    expect(history.success).toBe(false)
    expect(card).toBeNull()
  })
})

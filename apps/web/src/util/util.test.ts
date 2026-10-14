import { describe, expect, it } from 'vitest'
import type { ClearHistory } from '../api/types'
import { buildShareText, chipText, dayPeriod, formatDayTime, plainTitle } from './format'
import { layoutGraph, separateBoxes } from './layout'

describe('시간·공유 문구', () => {
  it('분 단위 clock 을 N일차 HH:MM 으로', () => {
    expect(formatDayTime(2, 1440 + 9 * 60 + 5)).toBe('2일차 09:05')
    expect(dayPeriod(14 * 60)).toBe('오후')
    expect(dayPeriod(2 * 60)).toBe('새벽')
  })

  const h = { case_title: '사라진 운영 DB', question_count: 23, success: true, game_days: 3, grade: 'A' } as ClearHistory
  it('텍스트 복사 형식', () => {
    expect(buildShareText(h, { emoji_line: '🔍🔍❌🔍✅', share_text: '🔍🔍❌🔍✅ 23질문 만에 해결', theme_color: '#3b6ea5' })).toBe('🔍🔍❌🔍✅ 23질문 만에 해결')
    expect(buildShareText(h)).toContain('🔍🔍🔍✅ 23질문 만에 해결')
    expect(buildShareText({ ...h, success: false }, null)).toContain('❌')
  })
})

describe('지도 자동 배치', () => {
  const ids = ['a', 'b', 'c', 'd', 'e', 'f']
  const edges: [string, string][] = [['a', 'b'], ['b', 'c'], ['c', 'd'], ['d', 'e'], ['e', 'f'], ['a', 'f'], ['b', 'e']]
  it('결정적이고 화면 안에 들어온다', () => {
    const l1 = layoutGraph(ids, edges, 270, 330, { x: 56, y: 33 })
    const l2 = layoutGraph(ids, edges, 270, 330, { x: 56, y: 33 })
    expect(l1).toEqual(l2)
    for (const n of l1) {
      expect(n.x).toBeGreaterThanOrEqual(56 - 0.001)
      expect(n.x).toBeLessThanOrEqual(270 - 56 + 0.001)
      expect(n.y).toBeGreaterThanOrEqual(33 - 0.001)
      expect(n.y).toBeLessThanOrEqual(330 - 33 + 0.001)
    }
  })
  it('노드가 서로 겹치지 않는다', () => {
    const l = layoutGraph(ids, edges, 270, 330, { x: 56, y: 33 })
    for (let i = 0; i < l.length; i++)
      for (let j = i + 1; j < l.length; j++) expect(Math.hypot(l[i].x - l[j].x, l[i].y - l[j].y)).toBeGreaterThan(20)
  })
  it('빈 그래프와 노드 1개', () => {
    expect(layoutGraph([], [], 100, 100, { x: 1, y: 1 })).toEqual([])
    expect(layoutGraph(['x'], [], 100, 100, { x: 1, y: 1 })).toHaveLength(1)
  })
  it('separateBoxes: 겹친 칸을 떼어 놓고 화면 안에 둔다', () => {
    const nodes = [
      { id: 'a', x: 100, y: 100 },
      { id: 'b', x: 110, y: 105 },
      { id: 'c', x: 100, y: 100 },
    ]
    const out = separateBoxes(nodes, 270, 400, 100, 50)
    for (let i = 0; i < out.length; i++)
      for (let j = i + 1; j < out.length; j++)
        expect(Math.abs(out[i].x - out[j].x) >= 100 || Math.abs(out[i].y - out[j].y) >= 50).toBe(true)
    for (const n of out) {
      expect(n.x).toBeGreaterThanOrEqual(50)
      expect(n.x).toBeLessThanOrEqual(220)
    }
    expect(separateBoxes(nodes, 270, 400, 100, 50)).toEqual(out)
  })
  it('chipText: 앞에 붙은 "이름:"은 그 사람 이름일 때만 뗀다', () => {
    expect(chipText('정하늘: 어젯밤 어디 계셨어요?', '정하늘')).toBe('어젯밤 어디 계셨어요?')
    expect(chipText('오민재: 백업은요?', '정하늘')).toBe('오민재: 백업은요?')
    expect(chipText('감사 로그에 대해', '정하늘')).toBe('감사 로그에 대해')
  })
  it('plainTitle: 앞의 이모지만 뗀다', () => {
    expect(plainTitle('💾 사라진 운영 DB')).toBe('사라진 운영 DB')
    expect(plainTitle('🏨️ 호텔 밀실')).toBe('호텔 밀실')
    expect(plainTitle('사건 01')).toBe('사건 01')
  })
})

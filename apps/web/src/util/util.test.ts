import { describe, expect, it } from 'vitest'
import type { ClearHistory } from '../api/types'
import { buildShareText, dayPeriod, formatDayTime } from './format'
import { layoutGraph } from './layout'

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
})

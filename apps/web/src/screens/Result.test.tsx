import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { describe, expect, it } from 'vitest'
import type { ClearHistory } from '../api/types'
import { ResultCard } from './Result'

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const h = {
  id: 'h_1', player_id: 'p', case_title: '사건', theme: '사라진 운영 DB', cleared_at: '', success: true, real_minutes: 12,
  game_days: 2, question_count: 9, grade: 'A', titles: [], reputation: 0, culprit: { name: '추성만', role: '청소원' },
  characters: [
    { name: '추성만', role: '청소원', face_seed: 1, appearance: {}, portrait_url: '/api/history/h_1/photos/0.webp' },
    { name: '남궁철', role: '경비원', face_seed: 2, appearance: {}, portrait_url: null },
  ],
  highlight: '', fingerprint: {},
} as unknown as ClearHistory

describe('ResultCard', () => {
  it('클리어할 때 남긴 사진이 있으면 사진, 없으면 코드로 그린 얼굴', () => {
    const host = document.createElement('div')
    const root = createRoot(host)
    act(() => root.render(<ResultCard h={h} />))
    const imgs = [...host.querySelectorAll('.res-faces img')].map((i) => i.getAttribute('src'))
    expect(imgs).toContain('/api/history/h_1/photos/0.webp')
    expect(host.querySelectorAll('.res-faces figure').length).toBe(2)
    expect(host.querySelectorAll('.res-faces svg').length).toBeGreaterThan(0) // 사진 없는 사람은 그림 얼굴
    act(() => root.unmount())
  })
})

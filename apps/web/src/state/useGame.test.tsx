import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { PlayerView, PortraitStatus, PublicCharacter } from '../api/types'

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const portraits = vi.fn<(id: string) => Promise<PortraitStatus>>()
vi.mock('../api/client', () => ({
  USE_MOCK: false,
  api: { portraits: (id: string) => portraits(id) },
}))

import { PORTRAIT_POLL_MS, useGame, type GameApi } from './useGame'

const ch = (id: string): PublicCharacter => ({
  id, name: id, role: 'r', age: 30, gender: 'F', appearance: {}, face_seed: 1, location_id: null, emotion: 'neutral', one_liner: '',
})
const view = { game_id: 'g1', characters: [ch('a'), ch('b')] } as unknown as PlayerView

let root: Root
let host: HTMLElement
let g: GameApi
function Probe() {
  g = useGame()
  return null
}
const flush = async (ms = 0) => {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms)
  })
}

beforeEach(() => {
  vi.useFakeTimers()
  portraits.mockReset()
  host = document.createElement('div')
  document.body.appendChild(host)
  root = createRoot(host)
  act(() => root.render(<Probe />))
})
afterEach(() => {
  act(() => root.unmount())
  host.remove()
  vi.useRealTimers()
})

describe('초상화 기다리기', () => {
  it('그리는 동안 몇 초마다 주소를 받아 채우고, 다 그리면 멈춘다', async () => {
    portraits
      .mockResolvedValueOnce({ pending: true, urls: {} })
      .mockResolvedValueOnce({ pending: true, urls: { a: '/p/a.webp' } })
      .mockResolvedValue({ pending: false, urls: { a: '/p/a.webp', b: '/p/b.webp' } })
    act(() => g.adoptGame('g1', view))
    await flush()
    expect(portraits).toHaveBeenCalledWith('g1')
    expect(g.state.view!.characters.every((c) => !c.portrait_url)).toBe(true)

    await flush(PORTRAIT_POLL_MS)
    expect(g.state.view!.characters.map((c) => c.portrait_url ?? null)).toEqual(['/p/a.webp', null])

    await flush(PORTRAIT_POLL_MS)
    expect(g.state.view!.characters.map((c) => c.portrait_url)).toEqual(['/p/a.webp', '/p/b.webp'])
    const n = portraits.mock.calls.length
    await flush(PORTRAIT_POLL_MS * 5)
    expect(portraits).toHaveBeenCalledTimes(n) // 다 채워지면 더 묻지 않음
  })

  it('서버가 그리지 않는 중이면(키 없음 등) 한 번만 묻고 SVG로 둔다', async () => {
    portraits.mockResolvedValue({ pending: false, urls: {} })
    act(() => g.adoptGame('g1', view))
    await flush(PORTRAIT_POLL_MS * 5)
    expect(portraits).toHaveBeenCalledTimes(1)
  })
})

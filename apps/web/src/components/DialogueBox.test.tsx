import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { TYPE_CATCHUP_TICKS, useTypewriter } from './DialogueBox'

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

let shown = ''
function Probe({ text }: { text: string }) {
  shown = useTypewriter(text, 30).shown
  return null
}

describe('useTypewriter', () => {
  let root: Root
  let el: HTMLDivElement
  beforeEach(() => {
    vi.useFakeTimers()
    el = document.createElement('div')
    root = createRoot(el)
  })
  afterEach(() => {
    act(() => root.unmount())
    vi.useRealTimers()
  })

  // 타이머 한 번마다 다시 그려야 다음 타이머가 걸리므로 30ms씩 나눠 진행한다
  const tick = (ms: number) => {
    for (let i = 0; i < Math.round(ms / 30); i++) act(() => void vi.advanceTimersByTime(30))
  }

  it('짧은 대사는 한 글자씩 찍는다', () => {
    act(() => root.render(<Probe text="집에 있었어요." />))
    tick(30)
    expect(shown).toBe('집')
    tick(30 * 7)
    expect(shown).toBe('집에 있었어요.')
  })

  it('밀린 글자가 많으면 1.2초 안에 따라잡는다', () => {
    const long = '가'.repeat(200)
    act(() => root.render(<Probe text={long} />))
    tick(30 * TYPE_CATCHUP_TICKS + 30 * 5) // 40번 남짓이면 다 보인다(한 글자씩이면 6초)
    expect(shown.length).toBe(200)
  })

  it('조각이 이어 붙어도 앞서 보인 글은 그대로 두고 이어서 찍는다', () => {
    act(() => root.render(<Probe text="퇴근했어요." />))
    tick(30 * 6)
    expect(shown).toBe('퇴근했어요.')
    act(() => root.render(<Probe text="퇴근했어요. 11시쯤이요." />))
    tick(30)
    expect(shown).toBe('퇴근했어요. ')
  })
})

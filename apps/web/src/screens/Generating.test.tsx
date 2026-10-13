import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { CaseJob, PlayerView, PublicCharacter } from '../api/types'

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const createCase = vi.fn()
const caseJob = vi.fn()
vi.mock('../api/client', () => ({
  USE_MOCK: false,
  api: {
    createCase: (...a: unknown[]) => createCase(...a),
    caseJob: (...a: unknown[]) => caseJob(...a),
    themes: () => Promise.resolve([{ id: 't1', title: '프리셋', emoji: '📦', description: '설명', preset: true }]),
  },
}))

import { Generating } from './Generating'
import { Start } from './Start'

const chars: PublicCharacter[] = [1, 2].map((n) => ({
  id: `c${n}`, name: `인물${n}`, role: '직원', age: 30, gender: 'X', appearance: {}, face_seed: n, location_id: null, emotion: 'neutral', one_liner: `소개${n}`,
}))
const job = (o: Partial<CaseJob>): CaseJob => ({
  job_id: 'j1', status: 'running', stage: 1, total: 5, stage_text: '사건 파일 작성 중…', preview: null, game_id: null, view: null, message: null, fallback_theme_id: null, ...o,
})
const preview = { title: '문제의 사건', incident_summary: '요약 문장', characters: chars }

let root: Root
let host: HTMLElement
const flush = async (ms = 0) => {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms)
  })
}
const btn = (label: string) => [...host.querySelectorAll('button')].find((b) => b.textContent?.includes(label)) as HTMLButtonElement | undefined

beforeEach(() => {
  vi.useFakeTimers()
  createCase.mockReset().mockResolvedValue({ job_id: 'j1' })
  caseJob.mockReset()
  host = document.createElement('div')
  document.body.appendChild(host)
  root = createRoot(host)
})
afterEach(() => {
  act(() => root.unmount())
  host.remove()
  vi.useRealTimers()
})

const noop = () => {}
const render = (props: Partial<Parameters<typeof Generating>[0]> = {}) =>
  act(() => {
    root.render(<Generating themeText="테스트 주제" options={{}} onReady={noop} onRejected={noop} onFallback={noop} onHome={noop} {...props} />)
  })

describe('Start 자유 주제', () => {
  it('빈 문자열/공백이면 사건 생성 버튼이 꺼져 있고, 글자가 있으면 켜진다', async () => {
    const onCreateCase = vi.fn()
    act(() => {
      root.render(<Start busy={false} error={null} onStart={noop} onCreateCase={onCreateCase} onOpenGame={noop} onLoadSlot={noop} onHistory={noop} />)
    })
    await flush()
    const input = host.querySelector('#custom-theme') as HTMLInputElement
    expect(btn('사건 생성')!.disabled).toBe(true)
    const set = (v: string) =>
      act(() => {
        Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, v)
        input.dispatchEvent(new Event('input', { bubbles: true }))
      })
    set('   ')
    expect(btn('사건 생성')!.disabled).toBe(true)
    set('도서관의 비밀')
    expect(btn('사건 생성')!.disabled).toBe(false)
    expect(host.textContent).toContain('73자 남음')
    act(() => btn('사건 생성')!.click())
    expect(onCreateCase).toHaveBeenCalledWith('도서관의 비밀', expect.any(Object))
  })

  it('프리셋을 고르면 입력이 비워진다', async () => {
    act(() => {
      root.render(<Start busy={false} error={null} onStart={noop} onCreateCase={noop} onOpenGame={noop} onLoadSlot={noop} onHistory={noop} />)
    })
    await flush()
    const input = host.querySelector('#custom-theme') as HTMLInputElement
    act(() => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, '직접 쓴 주제')
      input.dispatchEvent(new Event('input', { bubbles: true }))
    })
    act(() => (host.querySelector('.theme-card') as HTMLButtonElement).click())
    expect(input.value).toBe('')
    expect(btn('사건 생성')!.disabled).toBe(true)
  })
})

describe('Generating', () => {
  it('미리보기 전에는 단계 문구만, 생기면 인물 카드를 보여 주고 ready 에서만 수사 시작이 켜진다', async () => {
    const view = { game_id: 'g1', phase: 'briefing' } as PlayerView
    const onReady = vi.fn()
    caseJob
      .mockResolvedValueOnce(job({}))
      .mockResolvedValueOnce(job({ stage: 3, stage_text: '용의자 명단 정리 중…', preview }))
      .mockResolvedValue(job({ status: 'ready', stage: 5, stage_text: '완료', preview, game_id: 'g1', view }))
    render({ onReady })
    await flush()
    expect(host.querySelectorAll('[data-testid="cast-card"]')).toHaveLength(0)
    expect(host.textContent).toContain('1 / 5')

    await flush(1000)
    expect(host.querySelectorAll('[data-testid="cast-card"]')).toHaveLength(2)
    expect(host.textContent).toContain('문제의 사건')
    expect(host.textContent).toContain('용의자 명단 정리 중…')
    expect(btn('수사 시작')!.disabled).toBe(true)

    await flush(1000)
    expect(btn('수사 시작')!.disabled).toBe(false)
    act(() => btn('수사 시작')!.click())
    expect(onReady).toHaveBeenCalledWith('g1', view)
  })

  it('rejected 면 사유를 넘기고 폴링을 멈춘다', async () => {
    const onRejected = vi.fn()
    caseJob.mockResolvedValue(job({ status: 'rejected', message: '만들 수 없는 주제예요' }))
    render({ onRejected })
    await flush()
    expect(onRejected).toHaveBeenCalledWith('만들 수 없는 주제예요')
    await flush(3000)
    expect(caseJob).toHaveBeenCalledTimes(1)
  })

  it('failed 면 기본 사건으로 시작 버튼이 fallback 주제를 시작한다', async () => {
    const onFallback = vi.fn()
    caseJob.mockResolvedValue(job({ status: 'failed', message: '실패했어요', fallback_theme_id: 'demo_db_deleted' }))
    render({ onFallback })
    await flush()
    expect(host.textContent).toContain('실패했어요')
    act(() => btn('기본 사건으로 시작')!.click())
    expect(onFallback).toHaveBeenCalledWith('demo_db_deleted')
    expect(btn('처음으로')).toBeTruthy()
  })

  it('네트워크 오류는 조용히 재시도하다가 다시 시도 버튼을 보여 준다', async () => {
    caseJob.mockRejectedValue(new Error('x'))
    render()
    await flush()
    expect(host.textContent).not.toContain('다시 시도')
    await flush(4000)
    expect(btn('다시 시도')).toBeTruthy()
    caseJob.mockResolvedValue(job({ stage: 2 }))
    act(() => btn('다시 시도')!.click())
    await flush()
    expect(host.textContent).toContain('2 / 5')
  })

  it('언마운트하면 폴링이 멈춘다', async () => {
    caseJob.mockResolvedValue(job({}))
    render()
    await flush()
    const n = caseJob.mock.calls.length
    act(() => root.render(<div />))
    await flush(5000)
    expect(caseJob).toHaveBeenCalledTimes(n)
  })
})

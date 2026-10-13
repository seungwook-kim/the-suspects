import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { Portrait, resetPortraitFailures } from './Portrait'

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

let host: HTMLDivElement
let root: Root
beforeEach(() => {
  host = document.createElement('div')
  document.body.appendChild(host)
  root = createRoot(host)
  resetPortraitFailures()
})
afterEach(() => {
  act(() => root.unmount())
  host.remove()
  vi.unstubAllGlobals()
})

const show = (el: React.ReactElement) => act(() => root.render(el))
const stubMotion = (reduce: boolean) =>
  vi.stubGlobal('matchMedia', (q: string) => ({ matches: reduce && q.includes('reduce'), addEventListener: () => {}, removeEventListener: () => {} }))

describe('Portrait', () => {
  it('portrait_url 이 있으면 img 를 보여 준다', () => {
    show(<Portrait seed={1} portraitUrl="/api/portraits/k/a.png" name="오민재" />)
    const img = host.querySelector('img')!
    expect(img.getAttribute('src')).toBe('/api/portraits/k/a.png')
    expect(img.alt).toBe('오민재')
    expect(img.getAttribute('loading')).toBe('lazy')
    expect(img.getAttribute('decoding')).toBe('async')
  })

  it('eager 이면 lazy 를 쓰지 않는다', () => {
    show(<Portrait seed={1} portraitUrl="/p.png" name="가" eager />)
    expect(host.querySelector('img')!.getAttribute('loading')).toBeNull()
  })

  it('url 이 null 이면 SVG 를 그린다', () => {
    show(<Portrait seed={1} portraitUrl={null} />)
    expect(host.querySelector('img')).toBeNull()
    expect(host.querySelector('svg')).not.toBeNull()
  })

  it('이미지 로드가 실패하면 SVG 로 대체하고 다시 되돌아오지 않는다', () => {
    show(<Portrait seed={1} portraitUrl="/broken.png" name="가" />)
    act(() => {
      host.querySelector('img')!.dispatchEvent(new Event('error'))
    })
    expect(host.querySelector('img')).toBeNull()
    expect(host.querySelector('svg')).not.toBeNull()
    show(<Portrait seed={1} portraitUrl="/broken.png" name="가" emotion="angry" />)
    expect(host.querySelector('img')).toBeNull()
  })

  it('null 에서 url 로 바뀌면 사진으로 바뀌고 로드되면 보이게 된다', () => {
    show(<Portrait seed={1} portraitUrl={null} />)
    show(<Portrait seed={1} portraitUrl="/late.png" />)
    const img = host.querySelector('img')!
    expect(img.classList.contains('loaded')).toBe(false)
    act(() => {
      img.dispatchEvent(new Event('load'))
    })
    expect(host.querySelector('img')!.classList.contains('loaded')).toBe(true)
  })

  it('감정에 맞는 표정 사진이 있으면 그것을 보여 주고, 없으면 기본 사진으로', () => {
    show(<Portrait seed={1} portraitUrl="/base.png" portraitEmotions={{ angry: '/angry.png' }} emotion="angry" />)
    expect([...host.querySelectorAll('img')].map((i) => i.getAttribute('src'))).toEqual(['/angry.png'])
    expect(host.querySelector('.portrait-tint')).toBeNull()
    expect(host.textContent).toContain('💢')
    show(<Portrait seed={1} portraitUrl="/base.png" portraitEmotions={{ angry: '/angry.png' }} emotion="sad" />)
    expect(host.querySelector('img:last-of-type')!.getAttribute('src')).toBe('/base.png')
  })

  it('사진을 바꾸는 동안 이전 사진을 남겨 두었다가 새 사진이 불러와지면 치운다', () => {
    const emo = { angry: '/angry.png' }
    show(<Portrait seed={1} portraitUrl="/base.png" portraitEmotions={emo} emotion="neutral" />)
    act(() => {
      host.querySelector('img')!.dispatchEvent(new Event('load'))
    })
    show(<Portrait seed={1} portraitUrl="/base.png" portraitEmotions={emo} emotion="angry" />)
    const imgs = [...host.querySelectorAll('img')]
    expect(imgs.map((i) => i.getAttribute('src'))).toEqual(['/base.png', '/angry.png'])
    expect(imgs[0].classList.contains('loaded')).toBe(true)
    act(() => {
      imgs[1].dispatchEvent(new Event('load'))
    })
    expect([...host.querySelectorAll('img')].map((i) => i.getAttribute('src'))).toEqual(['/angry.png'])
  })

  it('표정 사진 로드가 실패하면 기본 사진으로 돌아간다', () => {
    show(<Portrait seed={1} portraitUrl="/base.png" portraitEmotions={{ angry: '/bad.png' }} emotion="angry" />)
    act(() => {
      host.querySelector('img')!.dispatchEvent(new Event('error'))
    })
    expect([...host.querySelectorAll('img')].map((i) => i.getAttribute('src'))).toEqual(['/base.png'])
  })

  it('분노는 붉은 색조와 💢, 당황은 흔들림과 💦', () => {
    stubMotion(false)
    show(<Portrait seed={1} portraitUrl="/p.png" emotion="angry" />)
    expect(host.querySelector('.portrait-tint')).not.toBeNull()
    expect(host.textContent).toContain('💢')
    show(<Portrait seed={1} portraitUrl="/p.png" emotion="flustered" />)
    expect(host.querySelector('.fx-shake')).not.toBeNull()
    expect(host.textContent).toContain('💦')
    show(<Portrait seed={1} portraitUrl="/p.png" emotion="neutral" />)
    expect(host.querySelector('.fx-shake, .fx-tremble, .portrait-tint, .portrait-badge')).toBeNull()
  })

  it('말하는 동안 들썩이고, 긴장은 떨린다', () => {
    stubMotion(false)
    show(<Portrait seed={1} portraitUrl="/p.png" emotion="nervous" speaking />)
    expect(host.querySelector('.fx-bob')).not.toBeNull()
    expect(host.querySelector('.fx-tremble')).not.toBeNull()
  })

  it('움직임 줄이기 설정이면 흔들림·떨림·들썩임이 없다', () => {
    stubMotion(true)
    show(<Portrait seed={1} portraitUrl="/p.png" emotion="flustered" speaking />)
    expect(host.querySelector('.fx-shake, .fx-tremble, .fx-bob')).toBeNull()
    expect(host.querySelector('.calm')).not.toBeNull()
    expect(host.textContent).toContain('💦')
  })
})

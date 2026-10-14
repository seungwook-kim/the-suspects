import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { Portrait, PortraitPending, resetPortraitFailures } from './Portrait'

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

describe('Portrait', () => {
  it('portrait_url 이 있으면 img 를 보여 준다', () => {
    show(<Portrait seed={1} portraitUrl="/api/portraits/k/a.png" name="오민재" />)
    const img = host.querySelector('img')!
    expect(img.getAttribute('src')).toBe('/api/portraits/k/a.png')
    expect(img.alt).toBe('오민재, AI로 생성한 가상의 인물 사진')
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

  it('서버가 그리는 중이면 그림 얼굴 대신 "사진 준비 중" 칸을 보여 준다', () => {
    show(
      <PortraitPending.Provider value={true}>
        <Portrait seed={1} portraitUrl={null} name="서도윤" />
      </PortraitPending.Provider>,
    )
    expect(host.querySelector('svg')).toBeNull()
    expect(host.querySelector('.avatar-pending')?.getAttribute('aria-label')).toBe('서도윤, 사진 준비 중')
    expect(host.textContent).toContain('서')
    expect(host.textContent).toContain('사진 준비 중')
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
    expect(img.classList.contains('is-front')).toBe(false)
    act(() => {
      img.dispatchEvent(new Event('load'))
    })
    expect(host.querySelector('img')!.classList.contains('is-front')).toBe(true)
  })

  it('감정에 맞는 표정 사진이 있으면 그것을 보여 주고, 없으면 기본 사진으로', () => {
    show(<Portrait seed={1} portraitUrl="/base.png" portraitEmotions={{ angry: '/angry.png' }} emotion="angry" />)
    expect([...host.querySelectorAll('img')].map((i) => i.getAttribute('src'))).toEqual(['/angry.png'])
    show(<Portrait seed={1} portraitUrl="/base.png" portraitEmotions={{ angry: '/angry.png' }} emotion="sad" />)
    expect(host.querySelector('img:last-of-type')!.getAttribute('src')).toBe('/base.png')
  })

  it('표정이 바뀌면 이전 사진 위로 새 사진이 겹쳐 나타나고(크로스페이드), 끝나면 이전 사진을 치운다', () => {
    vi.useFakeTimers()
    try {
      const emo = { angry: '/angry.png' }
      show(<Portrait seed={1} portraitUrl="/base.png" portraitEmotions={emo} emotion="neutral" />)
      act(() => {
        host.querySelector('img')!.dispatchEvent(new Event('load'))
      })
      show(<Portrait seed={1} portraitUrl="/base.png" portraitEmotions={emo} emotion="angry" />)
      let imgs = [...host.querySelectorAll('img')]
      expect(imgs.map((i) => i.getAttribute('src'))).toEqual(['/base.png', '/angry.png'])
      expect(imgs.map((i) => i.classList.contains('is-front'))).toEqual([true, false])
      act(() => {
        imgs[1].dispatchEvent(new Event('load'))
      })
      imgs = [...host.querySelectorAll('img')]
      expect(imgs.map((i) => i.getAttribute('src'))).toEqual(['/base.png', '/angry.png'])
      expect(imgs.every((i) => i.classList.contains('is-front'))).toBe(true)
      act(() => {
        vi.advanceTimersByTime(300)
      })
      expect([...host.querySelectorAll('img')].map((i) => i.getAttribute('src'))).toEqual(['/angry.png'])
    } finally {
      vi.useRealTimers()
    }
  })

  it('표정 사진 로드가 실패하면 기본 사진으로 돌아간다', () => {
    show(<Portrait seed={1} portraitUrl="/base.png" portraitEmotions={{ angry: '/bad.png' }} emotion="angry" />)
    act(() => {
      host.querySelector('img')!.dispatchEvent(new Event('error'))
    })
    expect([...host.querySelectorAll('img')].map((i) => i.getAttribute('src'))).toEqual(['/base.png'])
  })

  it('사진은 감정 효과로 변형하지 않는다(흔들림·색조·뱃지·반전 없음)', () => {
    for (const emotion of ['angry', 'flustered', 'nervous', 'sad', 'happy'] as const) {
      show(<Portrait seed={1} portraitUrl="/p.png" emotion={emotion} speaking />)
      expect(host.querySelector('.fx-shake, .fx-tremble, .fx-bob, .portrait-tint, .portrait-badge')).toBeNull()
      expect(host.textContent).not.toMatch(/💦|💢/)
    }
  })

  it('cover 글자를 사진 위 덮개로 보여 준다', () => {
    show(<Portrait seed={1} portraitUrl="/p.png" cover="등을 돌렸다" />)
    expect(host.querySelector('.away-cover')?.textContent).toBe('등을 돌렸다')
  })
})

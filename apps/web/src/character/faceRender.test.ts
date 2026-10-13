import { describe, expect, it } from 'vitest'
import { EMOTIONS } from '../api/types'
import { faceParams, HAIR_STYLES, OUTFITS, renderPortraitSvg } from './faceRender'

const app = { hair: 'short', hair_color: '#3b2f2f', outfit: 'cleaner_uniform', accessory: 'mop' }

describe('절차적 초상화', () => {
  it('같은 시드는 항상 같은 SVG', () => {
    expect(renderPortraitSvg(1234, app)).toBe(renderPortraitSvg(1234, app))
    expect(renderPortraitSvg(1234, app, { emotion: 'angry' })).toBe(renderPortraitSvg(1234, app, { emotion: 'angry' }))
  })

  it('다른 시드는 다른 SVG (이웃한 시드도)', () => {
    const set = new Set<string>()
    for (let s = 1; s <= 40; s++) set.add(renderPortraitSvg(s, app))
    expect(set.size).toBe(40)
    expect(renderPortraitSvg(1, app)).not.toBe(renderPortraitSvg(2, app))
  })

  it('얼굴 비율은 연속값이라 시드마다 값이 다르다', () => {
    const widths = new Set<number>()
    for (let s = 0; s < 30; s++) widths.add(faceParams(s).fw)
    expect(widths.size).toBe(30)
    const p = faceParams(99)
    expect(p.fw).toBeGreaterThanOrEqual(54)
    expect(p.fw).toBeLessThanOrEqual(66)
  })

  it('표정 6종은 같은 얼굴에서 서로 다른 그림이고 효과가 붙는다', () => {
    const svgs = EMOTIONS.map((e) => renderPortraitSvg(7, app, { emotion: e }))
    expect(new Set(svgs).size).toBe(EMOTIONS.length)
    expect(renderPortraitSvg(7, app, { emotion: 'flustered' })).toContain('💦')
    expect(renderPortraitSvg(7, app, { emotion: 'angry' })).toContain('💢')
  })

  it('입 여닫기와 눈 깜빡임이 그림을 바꾼다', () => {
    const base = renderPortraitSvg(5, app)
    expect(renderPortraitSvg(5, app, { mouthOpen: 0.9 })).not.toBe(base)
    expect(renderPortraitSvg(5, app, { blink: true })).not.toBe(base)
  })

  it('옷장과 머리 모양을 모두 그릴 수 있다', () => {
    for (const outfit of OUTFITS) expect(renderPortraitSvg(3, { outfit }).startsWith('<svg')).toBe(true)
    for (const hair of HAIR_STYLES) expect(renderPortraitSvg(3, { hair }).endsWith('</svg>')).toBe(true)
    for (const accessory of ['glasses', 'cap', 'badge', 'mop', 'radio', 'laptop', 'apron'])
      expect(renderPortraitSvg(3, { accessory })).not.toBe(renderPortraitSvg(3, {}))
    expect(renderPortraitSvg(3, { outfit: 'nope', hair: 'nope' })).toContain('<svg')
  })

  it('NaN 같은 좌표가 SVG 에 섞이지 않는다', () => {
    for (let s = 0; s < 50; s++) {
      for (const e of EMOTIONS) expect(renderPortraitSvg(s * 7919, app, { emotion: e, mouthOpen: 0.5 })).not.toMatch(/NaN|undefined/)
    }
  })
})

describe('사람 비율', () => {
  it('눈은 머리 세로 중앙 근처, 눈 폭은 얼굴 폭의 약 1/5', () => {
    for (let s = 0; s < 40; s++) {
      const p = faceParams(s * 131 + 7)
      expect(Math.abs(p.ey - (p.ty + p.chinY) / 2)).toBeLessThan(4)
      const ratio = (p.eyeW * 2) / (p.fw * 2)
      expect(ratio).toBeGreaterThan(0.17)
      expect(ratio).toBeLessThan(0.23)
    }
  })
})

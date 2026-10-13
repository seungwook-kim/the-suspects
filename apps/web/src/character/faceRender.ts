// 절차적 SVG 상반신 초상화. face_seed 에서 얼굴 비율을 "연속값"으로 뽑는다(저장된 부품 조합이 아님).
// 같은 입력은 항상 같은 문자열을 낸다(순수 함수). 표정은 눈·눈썹·입 파라미터만 바꾼다.
import type { Emotion } from '../api/types'
import { clamp, lerp, seededRng } from './rng'

export const PORTRAIT_W = 240
export const PORTRAIT_H = 300
const INK = '#2E3440'
const CX = 120

export const HAIR_STYLES = ['short', 'side', 'long', 'bun', 'curly', 'buzz', 'ponytail', 'bald'] as const
export const OUTFITS = [
  'suit', 'casual', 'hoodie', 'cleaner_uniform', 'security_uniform', 'chef',
  'doctor', 'delivery', 'school_uniform', 'work_clothes', 'office_lanyard',
] as const
export type HairStyle = (typeof HAIR_STYLES)[number]
export type Outfit = (typeof OUTFITS)[number]

export interface PortraitOpts {
  emotion?: Emotion
  /** 0~1. 대사 중 입 여닫기에 쓴다. */
  mouthOpen?: number
  blink?: boolean
  /** 배경 사각형을 그릴지 */
  bg?: boolean
}

// ---- 색 유틸 ----
const f1 = (n: number) => (Math.round(n * 10) / 10).toString()
const hsl = (h: number, s: number, l: number) => `hsl(${f1(h)},${f1(s)}%,${f1(l)}%)`

function hexToHsl(hex: string): [number, number, number] | null {
  const m = /^#([0-9a-f]{6})$/i.exec(hex.trim())
  if (!m) return null
  const n = parseInt(m[1], 16)
  const r = ((n >> 16) & 255) / 255
  const g = ((n >> 8) & 255) / 255
  const b = (n & 255) / 255
  const max = Math.max(r, g, b)
  const min = Math.min(r, g, b)
  const l = (max + min) / 2
  let h = 0
  let s = 0
  if (max !== min) {
    const d = max - min
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min)
    if (max === r) h = (g - b) / d + (g < b ? 6 : 0)
    else if (max === g) h = (b - r) / d + 2
    else h = (r - g) / d + 4
    h *= 60
  }
  return [h, s * 100, l * 100]
}

// ---- 시드에서 뽑는 연속값 ----
export interface FaceParams {
  skinH: number; skinS: number; skinL: number
  hairH: number; hairS: number; hairL: number
  irisH: number; irisS: number; irisL: number
  fw: number; ty: number; ey: number; chinY: number; jw: number; cw: number; chinRound: number
  earR: number; neckW: number; shoulder: number
  eyeGap: number; eyeW: number; eyeH: number; eyeAngle: number
  browThick: number; browLen: number; browGap: number; browAngle: number
  noseLen: number; noseW: number; mouthDrop: number; mouthW: number; smileBias: number
  hairVol: number; hairLift: number; fringe: number; part: number
  hairStyle: HairStyle
  outfitH: number; outfitS: number; outfitL: number; accentH: number
  bgH: number
}

const pick = <T,>(r: () => number, arr: readonly T[]): T => arr[Math.floor(r() * arr.length) % arr.length]

export function faceParams(seed: number, appearance: Record<string, string> = {}): FaceParams {
  const r = seededRng(seed)
  const u = (a: number, b: number) => lerp(a, b, r())

  // 피부: 밝은 톤 ~ 어두운 톤이 고르게 나오도록 명도를 균등 추출
  const skinL = u(36, 86)
  const skinH = u(12, 34)
  const skinS = u(28, 58)
  // 머리색 (appearance.hair_color 가 있으면 그것을 따른다)
  const hairLen = r()
  const hairHair = u(15, 40)
  const hc = appearance.hair_color ? hexToHsl(appearance.hair_color) : null
  const hairH = hc ? hc[0] : hairHair
  const hairS = hc ? hc[1] : u(10, 50)
  const hairL = hc ? hc[2] : hairLen < 0.12 ? u(60, 80) : u(8, 36)
  // 눈동자
  const irisT = r()
  const irisH = irisT < 0.75 ? u(18, 32) : u(150, 220)
  const irisS = irisT < 0.75 ? 45 : 32
  const irisL = irisT < 0.75 ? u(18, 32) : u(34, 46)

  const fw = u(52, 74)
  const ty = u(60, 74)
  const ey = u(132, 142)
  const chinY = u(204, 224)
  const jw = fw * u(0.62, 0.95)
  const cw = u(8, 30)
  const chinRound = u(4, 16)
  const earR = u(6, 10)
  const neckW = u(18, 28)
  const shoulder = u(100, 116)

  const eyeGap = u(22, 33)
  const eyeW = u(6.5, 10)
  const eyeH = u(5.5, 9.5)
  const eyeAngle = u(-8, 10)
  const browThick = u(2.4, 6)
  const browLen = u(1.7, 2.4)
  const browGap = u(8, 15)
  const browAngle = u(-4, 6)

  const noseLen = u(8, 22)
  const noseW = u(5, 13)
  const mouthDrop = u(12, 22)
  const mouthW = u(9, 20)
  const smileBias = u(0, 4)

  const hairVol = u(4, 16)
  const hairLift = u(8, 24)
  const fringe = u(10, 30)
  const part = u(-0.5, 0.5)
  const styleFromAppearance = appearance.hair as string | undefined
  const rolled = pick(r, HAIR_STYLES)
  const hairStyle: HairStyle = (HAIR_STYLES as readonly string[]).includes(styleFromAppearance ?? '')
    ? (styleFromAppearance as HairStyle)
    : styleFromAppearance === 'none'
      ? 'bald'
      : rolled

  const outfitH = u(0, 360)
  const outfitS = u(18, 48)
  const outfitL = u(26, 52)
  const accentH = u(0, 360)
  const bgH = u(0, 360)

  return {
    skinH, skinS, skinL, hairH, hairS, hairL, irisH, irisS, irisL,
    fw, ty, ey, chinY, jw, cw, chinRound, earR, neckW, shoulder,
    eyeGap, eyeW, eyeH, eyeAngle, browThick, browLen, browGap, browAngle,
    noseLen, noseW, mouthDrop, mouthW, smileBias,
    hairVol, hairLift, fringe, part, hairStyle,
    outfitH, outfitS, outfitL, accentH, bgH,
  }
}

// ---- 표정 -> 눈·눈썹·입 파라미터 ----
interface EmoParams {
  eyeSx: number; eyeSy: number; eyeTilt: number // 눈 크기 배율, 눈꼬리 각도 가산
  browInner: number; browOuter: number; browRaise: number
  lookX: number
}
const EMO: Record<Emotion, EmoParams> = {
  neutral: { eyeSx: 1, eyeSy: 1, eyeTilt: 0, browInner: 0, browOuter: 0, browRaise: 0, lookX: 0 },
  nervous: { eyeSx: 1, eyeSy: 1.05, eyeTilt: 0, browInner: -5, browOuter: -1, browRaise: -4, lookX: 2.5 },
  flustered: { eyeSx: 1.12, eyeSy: 1.3, eyeTilt: 0, browInner: -4, browOuter: -7, browRaise: -6, lookX: -1.5 },
  angry: { eyeSx: 1, eyeSy: 0.8, eyeTilt: 7, browInner: 7, browOuter: -2, browRaise: 1, lookX: 0 },
  sad: { eyeSx: 1, eyeSy: 0.95, eyeTilt: -9, browInner: -6, browOuter: 3, browRaise: 0, lookX: 0 },
  happy: { eyeSx: 1, eyeSy: 1, eyeTilt: 0, browInner: -2, browOuter: -3, browRaise: -3, lookX: 0 },
}

const stroke = (w = 1.8) => `stroke="${INK}" stroke-width="${w}" stroke-linejoin="round" stroke-linecap="round"`

// ---------------------------------------------------------------- 메인
export function renderPortraitSvg(
  seed: number,
  appearance: Record<string, string> = {},
  opts: PortraitOpts = {},
): string {
  const emotion: Emotion = opts.emotion ?? 'neutral'
  const p = faceParams(seed, appearance)
  const e = EMO[emotion] ?? EMO.neutral
  const mouthOpen = clamp(opts.mouthOpen ?? 0, 0, 1)
  const out: string[] = []

  const skin = hsl(p.skinH, p.skinS, p.skinL)
  const skinShade = hsl(p.skinH, p.skinS + 4, p.skinL - 9)
  const hair = hsl(p.hairH, p.hairS, p.hairL)
  const hairDark = hsl(p.hairH, p.hairS, Math.max(4, p.hairL - 8))
  const browColor = hsl(p.hairH, p.hairS, clamp(p.hairL - 6, 6, 50))

  out.push(
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${PORTRAIT_W} ${PORTRAIT_H}" width="${PORTRAIT_W}" height="${PORTRAIT_H}" role="img">`,
  )
  if (opts.bg !== false) {
    out.push(`<rect width="${PORTRAIT_W}" height="${PORTRAIT_H}" rx="18" fill="${hsl(p.bgH, 28, 88)}"/>`)
    out.push(`<circle cx="${CX}" cy="150" r="104" fill="${hsl(p.bgH, 30, 93)}"/>`)
  }

  // 뒷머리
  out.push(hairBack(p, hair))

  // 목
  const neckTop = p.chinY - 24
  out.push(
    `<path d="M${f1(CX - p.neckW)},${f1(neckTop)} L${f1(CX - p.neckW)},262 L${f1(CX + p.neckW)},262 L${f1(CX + p.neckW)},${f1(neckTop)} Z" fill="${skinShade}" ${stroke(1.5)}/>`,
  )

  // 몸 + 옷
  out.push(outfitSvg(appearance.outfit, p, skin, skinShade))

  // 귀
  for (const s of [-1, 1]) {
    const ex = CX + s * (p.fw + 1)
    out.push(
      `<ellipse cx="${f1(ex)}" cy="${f1(p.ey + 12)}" rx="${f1(p.earR)}" ry="${f1(p.earR * 1.5)}" fill="${skin}" ${stroke(1.5)}/>`,
      `<ellipse cx="${f1(ex + s * 1)}" cy="${f1(p.ey + 12)}" rx="${f1(p.earR * 0.45)}" ry="${f1(p.earR * 0.8)}" fill="${skinShade}"/>`,
    )
  }

  // 얼굴
  const face = facePath(p)
  out.push(`<path d="${face}" fill="${skin}" ${stroke(1.8)}/>`)
  if (emotion === 'angry') out.push(`<path d="${face}" fill="#E4572E" opacity="0.2"/>`)
  if (emotion === 'happy' || emotion === 'flustered' || emotion === 'nervous') {
    const op = emotion === 'happy' ? 0.3 : 0.38
    for (const s of [-1, 1]) {
      out.push(`<ellipse cx="${f1(CX + s * (p.eyeGap + 9))}" cy="${f1(p.ey + 24)}" rx="9" ry="5" fill="#ff7b7b" opacity="${op}"/>`)
    }
  }

  // 코
  const noseY = p.ey + 8 + p.noseLen
  out.push(
    `<path d="M${f1(CX + 1)},${f1(p.ey + 4)} Q${f1(CX + p.noseW * 0.5)},${f1(p.ey + 4 + p.noseLen * 0.7)} ${f1(CX)},${f1(noseY)}" fill="none" stroke="${skinShade}" stroke-width="2.4" stroke-linecap="round"/>`,
    `<path d="M${f1(CX - p.noseW * 0.5)},${f1(noseY + 1)} Q${f1(CX)},${f1(noseY + 4)} ${f1(CX + p.noseW * 0.5)},${f1(noseY + 1)}" fill="none" ${stroke(1.6)}/>`,
  )

  // 눈
  const eyeTilt = p.eyeAngle + e.eyeTilt
  for (const s of [-1, 1]) {
    const ex = CX + s * p.eyeGap
    const ey = p.ey
    const rx = p.eyeW * e.eyeSx
    const ry = p.eyeH * e.eyeSy
    const rot = -s * eyeTilt
    if (emotion === 'happy') {
      // 반달 눈
      out.push(
        `<path d="M${f1(ex - rx)},${f1(ey + 2)} Q${f1(ex)},${f1(ey - ry * 1.4)} ${f1(ex + rx)},${f1(ey + 2)}" fill="none" stroke="${INK}" stroke-width="2.6" stroke-linecap="round" transform="rotate(${f1(rot)} ${f1(ex)} ${f1(ey)})"/>`,
      )
    } else if (opts.blink) {
      out.push(
        `<path d="M${f1(ex - rx)},${f1(ey)} Q${f1(ex)},${f1(ey + 3)} ${f1(ex + rx)},${f1(ey)}" fill="none" stroke="${INK}" stroke-width="2.4" stroke-linecap="round" transform="rotate(${f1(rot)} ${f1(ex)} ${f1(ey)})"/>`,
      )
    } else {
      const ir = Math.min(rx, ry) * 0.92
      const lookX = e.lookX * (s === 1 ? 1 : 1)
      out.push(
        `<g transform="rotate(${f1(rot)} ${f1(ex)} ${f1(ey)})">`,
        `<ellipse cx="${f1(ex)}" cy="${f1(ey)}" rx="${f1(rx)}" ry="${f1(ry)}" fill="#fff" ${stroke(1.5)}/>`,
        `<circle cx="${f1(ex + lookX)}" cy="${f1(ey)}" r="${f1(ir)}" fill="${hsl(p.irisH, p.irisS, p.irisL)}"/>`,
        `<circle cx="${f1(ex + lookX)}" cy="${f1(ey)}" r="${f1(ir * 0.5)}" fill="#14161b"/>`,
        `<circle cx="${f1(ex + lookX - ir * 0.3)}" cy="${f1(ey - ir * 0.35)}" r="${f1(ir * 0.22)}" fill="#fff"/>`,
        angryLid(emotion, ex, ey, rx, ry, s, skin),
        `</g>`,
      )
    }
  }

  // 눈썹
  for (const s of [-1, 1]) {
    const innerX = CX + s * (p.eyeGap - p.eyeW * 0.9)
    const outerX = CX + s * (p.eyeGap + p.eyeW * p.browLen * 0.55)
    const baseY = p.ey - p.eyeH - p.browGap + e.browRaise
    const yIn = baseY + e.browInner
    const yOut = baseY + e.browOuter - p.browAngle
    const midY = (yIn + yOut) / 2 - 2.5
    out.push(
      `<path d="M${f1(innerX)},${f1(yIn)} Q${f1((innerX + outerX) / 2)},${f1(midY)} ${f1(outerX)},${f1(yOut)}" fill="none" stroke="${browColor}" stroke-width="${f1(p.browThick)}" stroke-linecap="round"/>`,
    )
  }

  // 입
  const mouthY = Math.min(noseY + p.mouthDrop, p.chinY - 13)
  out.push(mouthSvg(emotion, p, mouthY, mouthOpen))

  // 앞머리
  out.push(hairFront(p, hair, hairDark))

  // 소품
  out.push(accessorySvg(appearance.accessory, p))

  // 감정 효과
  out.push(effectSvg(emotion, p))

  out.push('</svg>')
  return out.join('')
}

function angryLid(emotion: Emotion, ex: number, ey: number, rx: number, ry: number, s: number, skin: string): string {
  // 화난 눈(안쪽이 낮음)·슬픈 눈(바깥쪽이 낮음): 위쪽 눈꺼풀을 피부색 삼각형으로 덮어 눈매를 만든다.
  if (emotion !== 'angry' && emotion !== 'sad') return ''
  const x1 = ex - s * (rx + 1.5) // 안쪽
  const x2 = ex + s * (rx + 1.5) // 바깥쪽
  const top = ey - ry - 2
  const low = ey - ry * 0.05
  const pts = emotion === 'angry' ? [[x1, top], [x2, top], [x1, low]] : [[x1, top], [x2, top], [x2, low]]
  const line = emotion === 'angry' ? [[x1, low], [x2, top + 2]] : [[x2, low], [x1, top + 2]]
  const fmt = (arr: number[][]) => arr.map(([x, y]) => `${f1(x)},${f1(y)}`).join(' L')
  return (
    `<path d="M${fmt(pts)} Z" fill="${skin}"/>` +
    `<path d="M${fmt(line)}" stroke="${INK}" stroke-width="2" stroke-linecap="round"/>`
  )
}

function facePath(p: FaceParams): string {
  const topCtrl = (p.ty - 0.25 * p.ey) / 0.75
  const span = p.chinY - p.ey
  const midY = p.ey + span * 0.45
  const lowY = p.chinY - span * 0.18
  return (
    `M${f1(CX - p.fw)},${f1(p.ey)} C${f1(CX - p.fw)},${f1(topCtrl)} ${f1(CX + p.fw)},${f1(topCtrl)} ${f1(CX + p.fw)},${f1(p.ey)} ` +
    `C${f1(CX + p.fw)},${f1(midY)} ${f1(CX + p.jw)},${f1(lowY)} ${f1(CX + p.cw)},${f1(p.chinY)} ` +
    `Q${f1(CX)},${f1(p.chinY + p.chinRound)} ${f1(CX - p.cw)},${f1(p.chinY)} ` +
    `C${f1(CX - p.jw)},${f1(lowY)} ${f1(CX - p.fw)},${f1(midY)} ${f1(CX - p.fw)},${f1(p.ey)} Z`
  )
}

// ---------------------------------------------------------------- 입
function mouthSvg(emotion: Emotion, p: FaceParams, y: number, open: number): string {
  const w = p.mouthW
  const sb = p.smileBias
  if (open > 0.05) {
    const rx = w * (0.4 + 0.3 * open)
    const ry = 1.8 + open * 8
    return (
      `<ellipse cx="${CX}" cy="${f1(y + ry * 0.4)}" rx="${f1(rx)}" ry="${f1(ry)}" fill="#5c2323" ${stroke(1.6)}/>` +
      (ry > 5 ? `<ellipse cx="${CX}" cy="${f1(y + ry * 0.9)}" rx="${f1(rx * 0.55)}" ry="${f1(ry * 0.32)}" fill="#d9707a"/>` : '')
    )
  }
  switch (emotion) {
    case 'nervous': {
      const m = w * 0.7
      return `<path d="M${f1(CX - m)},${f1(y + 1)} Q${f1(CX - m * 0.4)},${f1(y - 2.5)} ${f1(CX)},${f1(y + 1)} Q${f1(CX + m * 0.4)},${f1(y + 4)} ${f1(CX + m)},${f1(y)}" fill="none" ${stroke(2)}/>`
    }
    case 'flustered':
      return `<path d="M${f1(CX - w)},${f1(y)} Q${f1(CX - w / 2)},${f1(y - 6)} ${f1(CX)},${f1(y + 1)} Q${f1(CX + w / 2)},${f1(y + 8)} ${f1(CX + w)},${f1(y - 1)}" fill="none" ${stroke(2.2)}/>`
    case 'angry':
      return (
        `<path d="M${f1(CX - w * 0.9)},${f1(y + 2)} L${f1(CX + w * 0.9)},${f1(y + 2)}" fill="none" ${stroke(3)}/>` +
        `<path d="M${f1(CX - w * 0.9)},${f1(y + 2)} l-1.5,2.5 M${f1(CX + w * 0.9)},${f1(y + 2)} l1.5,2.5" fill="none" ${stroke(1.8)}/>`
      )
    case 'sad':
      return `<path d="M${f1(CX - w * 0.8)},${f1(y + 5)} Q${f1(CX)},${f1(y - 4)} ${f1(CX + w * 0.8)},${f1(y + 5)}" fill="none" ${stroke(2.2)}/>`
    case 'happy':
      return (
        `<path d="M${f1(CX - w)},${f1(y - 1)} Q${f1(CX)},${f1(y + w * 1.0)} ${f1(CX + w)},${f1(y - 1)} Z" fill="#5c2323" ${stroke(1.8)}/>` +
        `<path d="M${f1(CX - w * 0.7)},${f1(y + 1)} Q${f1(CX)},${f1(y + 3.5)} ${f1(CX + w * 0.7)},${f1(y + 1)} L${f1(CX + w * 0.6)},${f1(y + 3)} Q${f1(CX)},${f1(y + 5.5)} ${f1(CX - w * 0.6)},${f1(y + 3)} Z" fill="#fff"/>`
      )
    default:
      return `<path d="M${f1(CX - w)},${f1(y)} Q${f1(CX)},${f1(y + 2 + sb)} ${f1(CX + w)},${f1(y)}" fill="none" ${stroke(2.2)}/>`
  }
}

// ---------------------------------------------------------------- 머리카락
function hairBack(p: FaceParams, hair: string): string {
  const { fw, ty, ey, hairVol: v, hairStyle: st } = p
  const body = `fill="${hair}" ${stroke(1.8)}`
  switch (st) {
    case 'long':
      return `<path d="M${f1(CX - fw - v)},${f1(ey - 24)} C${f1(CX - fw - v - 16)},${f1(ey + 50)} ${f1(CX - fw - v - 8)},250 ${f1(CX - fw + 6)},266 L${f1(CX + fw - 6)},266 C${f1(CX + fw + v + 8)},250 ${f1(CX + fw + v + 16)},${f1(ey + 50)} ${f1(CX + fw + v)},${f1(ey - 24)} C${f1(CX + fw + v)},${f1(ty - 22)} ${f1(CX - fw - v)},${f1(ty - 22)} ${f1(CX - fw - v)},${f1(ey - 24)} Z" ${body}/>`
    case 'bun': {
      const r = 14 + v * 0.6
      return `<circle cx="${CX}" cy="${f1(ty - 12)}" r="${f1(r)}" ${body}/>`
    }
    case 'ponytail':
      return `<path d="M${f1(CX + fw - 2)},${f1(ty + 14)} C${f1(CX + fw + 40)},${f1(ty + 4)} ${f1(CX + fw + 44)},${f1(ey + 50)} ${f1(CX + fw + 20)},${f1(ey + 66)} C${f1(CX + fw + 24)},${f1(ey + 40)} ${f1(CX + fw + 10)},${f1(ey + 10)} ${f1(CX + fw - 8)},${f1(ey - 10)} Z" ${body}/>`
    case 'curly': {
      const n = 9
      const parts: string[] = []
      for (let i = 0; i < n; i++) {
        const a = Math.PI * (1.02 + (i / (n - 1)) * 0.96)
        const rr = 11 + v * 0.5
        parts.push(`<circle cx="${f1(CX + Math.cos(a) * (fw + 4))}" cy="${f1((ty + ey) / 2 + Math.sin(a) * ((ey - ty) / 2 + 12))}" r="${f1(rr)}" ${body}/>`)
      }
      return parts.join('')
    }
    default:
      return ''
  }
}

function hairFront(p: FaceParams, hair: string, hairDark: string): string {
  const { fw, ty, ey, hairVol: v, hairLift: lift, fringe, part, hairStyle: st } = p
  const body = `fill="${hair}" ${stroke(1.8)}`
  if (st === 'bald') {
    return (
      `<path d="M${f1(CX - fw - 1)},${f1(ey - 6)} Q${f1(CX - fw - 3)},${f1(ey + 12)} ${f1(CX - fw + 1)},${f1(ey + 18)} L${f1(CX - fw + 6)},${f1(ey + 4)} Z" ${body}/>` +
      `<path d="M${f1(CX + fw + 1)},${f1(ey - 6)} Q${f1(CX + fw + 3)},${f1(ey + 12)} ${f1(CX + fw - 1)},${f1(ey + 18)} L${f1(CX + fw - 6)},${f1(ey + 4)} Z" ${body}/>`
    )
  }
  const vol = st === 'buzz' ? 1.5 : v
  const top = ty - (st === 'buzz' ? 4 : lift)
  const topCtrl = (top - 0.25 * (ey - 20)) / 0.75
  const hairlineY = ty + (st === 'buzz' ? 12 : fringe)
  const shift = part * fw * (st === 'side' ? 1.6 : 0.8)
  const lowSide = st === 'side' ? 14 : 0
  const outer =
    `M${f1(CX - fw - vol * 0.4)},${f1(ey - 4)} C${f1(CX - fw - vol)},${f1(topCtrl)} ${f1(CX + fw + vol)},${f1(topCtrl)} ${f1(CX + fw + vol * 0.4)},${f1(ey - 4)} `
  const back =
    `L${f1(CX + fw - 4)},${f1(ey - 22)} ` +
    `Q${f1(CX + shift + 10)},${f1(hairlineY - 14 + lowSide * (part > 0 ? 0 : 1))} ${f1(CX + shift)},${f1(hairlineY)} ` +
    `Q${f1(CX + shift - 18)},${f1(hairlineY + 10 + lowSide * (part > 0 ? 1 : 0))} ${f1(CX - fw + 4)},${f1(ey - 22)} Z`
  let extra = ''
  if (st !== 'buzz') {
    extra = `<path d="M${f1(CX + shift)},${f1(hairlineY - 2)} Q${f1(CX + shift * 0.6)},${f1(top + 10)} ${f1(CX + shift * 0.2)},${f1(top + 4)}" fill="none" stroke="${hairDark}" stroke-width="1.6" stroke-linecap="round" opacity="0.7"/>`
  }
  return `<path d="${outer}${back}" ${body}${st === 'buzz' ? ' opacity="0.9"' : ''}/>${extra}`
}

// ---------------------------------------------------------------- 옷
function outfitSvg(outfit: string | undefined, p: FaceParams, skin: string, skinShade: string): string {
  const sw = p.shoulder
  const nw = p.neckW
  const bodyD = `M${f1(CX - sw)},300 L${f1(CX - sw)},272 C${f1(CX - sw)},250 ${f1(CX - 60)},240 ${f1(CX - nw - 8)},238 L${f1(CX + nw + 8)},238 C${f1(CX + 60)},240 ${f1(CX + sw)},250 ${f1(CX + sw)},272 L${f1(CX + sw)},300 Z`
  const known = (OUTFITS as readonly string[]).includes(outfit ?? '')
  const kind = (known ? outfit : 'casual') as Outfit
  const main = (dh = 0, ds = 0, dl = 0) => hsl(p.outfitH + dh, clamp(p.outfitS + ds, 5, 70), clamp(p.outfitL + dl, 8, 94))
  const accent = hsl(p.accentH, 55, 48)
  const paint = (fill: string) => `fill="${fill}" ${stroke(1.8)}`
  const neckHole = `<path d="M${f1(CX - nw - 6)},238 Q${f1(CX)},${f1(262 + nw * 0.3)} ${f1(CX + nw + 6)},238 Z" fill="${skinShade}" ${stroke(1.5)}/>`
  const o: string[] = []

  switch (kind) {
    case 'suit': {
      const jacket = hsl(p.outfitH, 14, 24 + p.outfitL * 0.25)
      o.push(`<path d="${bodyD}" ${paint(jacket)}/>`)
      o.push(`<path d="M${f1(CX - 24)},238 L${f1(CX + 24)},238 L${f1(CX)},292 Z" fill="#fff" ${stroke(1.5)}/>`)
      o.push(`<path d="M${f1(CX - 26)},238 L${f1(CX - 4)},296 L${f1(CX - 36)},300 L${f1(CX - 46)},262 Z" ${paint(hsl(p.outfitH, 14, 30 + p.outfitL * 0.25))}/>`)
      o.push(`<path d="M${f1(CX + 26)},238 L${f1(CX + 4)},296 L${f1(CX + 36)},300 L${f1(CX + 46)},262 Z" ${paint(hsl(p.outfitH, 14, 30 + p.outfitL * 0.25))}/>`)
      o.push(`<path d="M${f1(CX - 5)},246 L${f1(CX + 5)},246 L${f1(CX + 7)},288 L${f1(CX)},296 L${f1(CX - 7)},288 Z" ${paint(accent)}/>`)
      break
    }
    case 'hoodie': {
      const c = main(0, 0, 4)
      o.push(`<path d="${bodyD}" ${paint(c)}/>`)
      o.push(`<path d="M${f1(CX - nw - 16)},242 Q${f1(CX)},${f1(222)} ${f1(CX + nw + 16)},242 L${f1(CX + nw + 8)},266 Q${f1(CX)},${f1(250)} ${f1(CX - nw - 8)},266 Z" ${paint(main(0, 0, -6))}/>`)
      o.push(`<path d="M${f1(CX - 10)},258 L${f1(CX - 12)},292 M${f1(CX + 10)},258 L${f1(CX + 12)},292" stroke="#fff" stroke-width="2.4" stroke-linecap="round"/>`)
      o.push(`<path d="M${f1(CX - 40)},300 L${f1(CX - 34)},282 L${f1(CX + 34)},282 L${f1(CX + 40)},300" fill="none" ${stroke(1.5)}/>`)
      break
    }
    case 'cleaner_uniform': {
      const c = hsl(190 + (p.outfitH % 30), 28, 46)
      o.push(`<path d="${bodyD}" ${paint(c)}/>`)
      o.push(neckHole)
      o.push(`<path d="M${f1(CX - nw - 8)},238 L${f1(CX)},272 L${f1(CX - 4)},300 L${f1(CX - 30)},300 Z" ${paint(hsl(190, 24, 40))}/>`)
      o.push(`<path d="M${f1(CX + nw + 8)},238 L${f1(CX)},272 L${f1(CX + 4)},300 L${f1(CX + 30)},300 Z" ${paint(hsl(190, 24, 40))}/>`)
      o.push(`<rect x="${CX + 22}" y="272" width="22" height="12" rx="2" fill="#fff" ${stroke(1.2)}/>`)
      break
    }
    case 'security_uniform': {
      const c = hsl(218, 30, 24)
      o.push(`<path d="${bodyD}" ${paint(c)}/>`)
      o.push(`<path d="M${f1(CX - 22)},238 L${f1(CX + 22)},238 L${f1(CX)},280 Z" fill="#cfe0f2" ${stroke(1.4)}/>`)
      o.push(`<path d="M${f1(CX - 4)},250 L${f1(CX + 4)},250 L${f1(CX + 5)},290 L${f1(CX)},294 L${f1(CX - 5)},290 Z" fill="#14161b"/>`)
      o.push(`<rect x="${CX - sw + 12}" y="246" width="26" height="9" rx="2" ${paint('#c9a63c')}/>`)
      o.push(`<rect x="${CX + sw - 38}" y="246" width="26" height="9" rx="2" ${paint('#c9a63c')}/>`)
      o.push(`<path d="M${f1(CX + 28)},268 l9,0 l0,12 l-4.5,5 l-4.5,-5 Z" ${paint('#d9b44a')}/>`)
      break
    }
    case 'chef': {
      o.push(`<path d="${bodyD}" ${paint('#f7f7f4')}/>`)
      o.push(neckHole)
      o.push(`<path d="M${f1(CX)},262 L${f1(CX)},300" stroke="${INK}" stroke-width="1.5"/>`)
      for (const dy of [272, 288]) {
        o.push(`<circle cx="${CX - 9}" cy="${dy}" r="2.6" fill="${INK}"/><circle cx="${CX + 9}" cy="${dy}" r="2.6" fill="${INK}"/>`)
      }
      o.push(`<path d="M${f1(CX - nw - 6)},240 Q${f1(CX)},262 ${f1(CX + nw + 6)},240 L${f1(CX + 8)},256 L${f1(CX - 8)},256 Z" ${paint(accent)}/>`)
      break
    }
    case 'doctor': {
      o.push(`<path d="${bodyD}" ${paint(hsl(176, 40, 56))}/>`)
      o.push(`<path d="M${f1(CX - nw - 8)},238 L${f1(CX - 6)},300 L${f1(CX - sw)},300 L${f1(CX - sw)},272 C${f1(CX - sw)},250 ${f1(CX - 60)},240 ${f1(CX - nw - 8)},238 Z" ${paint('#fbfbf8')}/>`)
      o.push(`<path d="M${f1(CX + nw + 8)},238 L${f1(CX + 6)},300 L${f1(CX + sw)},300 L${f1(CX + sw)},272 C${f1(CX + sw)},250 ${f1(CX + 60)},240 ${f1(CX + nw + 8)},238 Z" ${paint('#fbfbf8')}/>`)
      o.push(`<path d="M${f1(CX - 26)},244 C${f1(CX - 30)},290 ${f1(CX + 30)},290 ${f1(CX + 26)},244" fill="none" stroke="${INK}" stroke-width="2.4"/><circle cx="${CX + 8}" cy="288" r="4" fill="#9aa3b2" ${stroke(1.2)}/>`)
      break
    }
    case 'delivery': {
      o.push(`<path d="${bodyD}" ${paint(hsl(210, 14, 28))}/>`)
      o.push(`<path d="M${f1(CX - nw - 8)},238 L${f1(CX - 16)},300 L${f1(CX - sw)},300 L${f1(CX - sw)},272 C${f1(CX - sw)},250 ${f1(CX - 60)},240 ${f1(CX - nw - 8)},238 Z" ${paint('#f08a24')}/>`)
      o.push(`<path d="M${f1(CX + nw + 8)},238 L${f1(CX + 16)},300 L${f1(CX + sw)},300 L${f1(CX + sw)},272 C${f1(CX + sw)},250 ${f1(CX + 60)},240 ${f1(CX + nw + 8)},238 Z" ${paint('#f08a24')}/>`)
      o.push(`<path d="M${f1(CX - sw + 4)},282 L${f1(CX - 20)},282 M${f1(CX + 20)},282 L${f1(CX + sw - 4)},282" stroke="#f4f1ea" stroke-width="5"/>`)
      break
    }
    case 'school_uniform': {
      o.push(`<path d="${bodyD}" ${paint(hsl(222, 34, 26))}/>`)
      o.push(`<path d="M${f1(CX - 22)},238 L${f1(CX + 22)},238 L${f1(CX)},284 Z" fill="#fff" ${stroke(1.4)}/>`)
      o.push(`<path d="M${f1(CX - 8)},256 L${f1(CX)},262 L${f1(CX + 8)},256 L${f1(CX + 8)},268 L${f1(CX)},262 L${f1(CX - 8)},268 Z" ${paint('#c8453b')}/>`)
      o.push(`<path d="M${f1(CX - 26)},238 L${f1(CX - 3)},290 L${f1(CX - 34)},300 L${f1(CX - 44)},264 Z" ${paint(hsl(222, 34, 32))}/>`)
      o.push(`<path d="M${f1(CX + 26)},238 L${f1(CX + 3)},290 L${f1(CX + 34)},300 L${f1(CX + 44)},264 Z" ${paint(hsl(222, 34, 32))}/>`)
      break
    }
    case 'work_clothes': {
      const c = hsl(40 + (p.outfitH % 20), 30, 46)
      o.push(`<path d="${bodyD}" ${paint(c)}/>`)
      o.push(neckHole)
      o.push(`<path d="M${f1(CX - nw - 10)},238 L${f1(CX - 4)},266 L${f1(CX - 28)},262 Z M${f1(CX + nw + 10)},238 L${f1(CX + 4)},266 L${f1(CX + 28)},262 Z" ${paint(hsl(40, 28, 40))}/>`)
      o.push(`<rect x="${CX - 52}" y="274" width="26" height="22" rx="2" fill="none" ${stroke(1.5)}/><rect x="${CX + 26}" y="274" width="26" height="22" rx="2" fill="none" ${stroke(1.5)}/>`)
      break
    }
    case 'office_lanyard': {
      o.push(`<path d="${bodyD}" ${paint(main(0, -4, 12))}/>`)
      o.push(`<path d="M${f1(CX - 22)},238 L${f1(CX + 22)},238 L${f1(CX)},272 Z" fill="#fff" ${stroke(1.4)}/>`)
      o.push(`<path d="M${f1(CX - 14)},240 L${f1(CX - 4)},300 M${f1(CX + 14)},240 L${f1(CX + 4)},300" stroke="${accent}" stroke-width="3" fill="none"/>`)
      o.push(`<rect x="${CX - 14}" y="272" width="28" height="22" rx="3" fill="#fff" ${stroke(1.5)}/><circle cx="${CX}" cy="280" r="4" fill="${accent}"/><path d="M${f1(CX - 8)},288 L${f1(CX + 8)},288" stroke="${INK}" stroke-width="1.5"/>`)
      break
    }
    case 'casual':
    default: {
      o.push(`<path d="${bodyD}" ${paint(main())}/>`)
      o.push(`<path d="M${f1(CX - nw - 6)},238 Q${f1(CX)},${f1(262 + nw * 0.3)} ${f1(CX + nw + 6)},238" fill="${skinShade}" ${stroke(1.6)}/>`)
      o.push(`<path d="M${f1(CX - 30)},286 L${f1(CX + 30)},286" stroke="${main(0, 0, 14)}" stroke-width="5" opacity="0.5"/>`)
    }
  }
  void skin
  return o.join('')
}

// ---------------------------------------------------------------- 소품
function accessorySvg(acc: string | undefined, p: FaceParams): string {
  const sw = p.shoulder
  switch (acc) {
    case 'glasses': {
      const r = p.eyeW + 5
      const y = p.ey
      const gl = (s: number) => `<rect x="${f1(CX + s * p.eyeGap - r)}" y="${f1(y - r + 1)}" width="${f1(r * 2)}" height="${f1(r * 1.7)}" rx="${f1(r * 0.55)}" fill="#cfe7f7" fill-opacity="0.35" stroke="${INK}" stroke-width="2.2"/>`
      return (
        gl(-1) + gl(1) +
        `<path d="M${f1(CX - p.eyeGap + r)},${f1(y + 2)} L${f1(CX + p.eyeGap - r)},${f1(y + 2)}" stroke="${INK}" stroke-width="2"/>` +
        `<path d="M${f1(CX - p.eyeGap - r)},${f1(y + 2)} L${f1(CX - p.fw)},${f1(y + 4)} M${f1(CX + p.eyeGap + r)},${f1(y + 2)} L${f1(CX + p.fw)},${f1(y + 4)}" stroke="${INK}" stroke-width="2"/>`
      )
    }
    case 'cap': {
      const c = hsl(p.accentH, 45, 40)
      return (
        `<path d="M${f1(CX - p.fw - 5)},${f1(p.ey - 22)} C${f1(CX - p.fw - 5)},${f1(p.ty - 30)} ${f1(CX + p.fw + 5)},${f1(p.ty - 30)} ${f1(CX + p.fw + 5)},${f1(p.ey - 22)} Z" fill="${c}" ${stroke(1.8)}/>` +
        `<path d="M${f1(CX - p.fw - 6)},${f1(p.ey - 22)} Q${f1(CX + 14)},${f1(p.ey - 8)} ${f1(CX + p.fw + 26)},${f1(p.ey - 24)} Q${f1(CX + 20)},${f1(p.ey - 28)} ${f1(CX - p.fw - 6)},${f1(p.ey - 22)} Z" fill="${hsl(p.accentH, 45, 33)}" ${stroke(1.8)}/>`
      )
    }
    case 'badge':
      return `<path d="M${f1(CX - sw + 24)},262 l16,0 l0,18 l-8,8 l-8,-8 Z" fill="#d9b44a" ${stroke(1.6)}/><circle cx="${f1(CX - sw + 32)}" cy="270" r="3" fill="#fff4c4"/>`
    case 'mop':
      return (
        `<path d="M${f1(CX + sw + 6)},120 L${f1(CX + sw - 22)},300" stroke="#8a6a43" stroke-width="6" stroke-linecap="round"/>` +
        `<path d="M${f1(CX + sw - 8)},108 Q${f1(CX + sw + 6)},96 ${f1(CX + sw + 20)},108 L${f1(CX + sw + 26)},140 L${f1(CX + sw - 12)},138 Z" fill="#cfd3d9" ${stroke(1.6)}/>` +
        `<path d="M${f1(CX + sw - 2)},112 L${f1(CX + sw - 4)},136 M${f1(CX + sw + 8)},108 L${f1(CX + sw + 8)},138 M${f1(CX + sw + 18)},112 L${f1(CX + sw + 20)},138" stroke="${INK}" stroke-width="1.2" opacity="0.5"/>`
      )
    case 'radio':
      return (
        `<rect x="${f1(CX + sw - 52)}" y="256" width="24" height="34" rx="4" fill="#2E3440" ${stroke(1.4)}/>` +
        `<path d="M${f1(CX + sw - 34)},256 L${f1(CX + sw - 34)},226" stroke="${INK}" stroke-width="3" stroke-linecap="round"/>` +
        `<circle cx="${f1(CX + sw - 40)}" cy="268" r="4" fill="#9aa3b2"/><path d="M${f1(CX + sw - 46)},280 l12,0 m-12,4 l12,0" stroke="#9aa3b2" stroke-width="1.6"/>`
      )
    case 'laptop':
      return (
        `<path d="M${f1(CX - 54)},300 L${f1(CX - 48)},262 L${f1(CX + 48)},262 L${f1(CX + 54)},300 Z" fill="#aeb6c4" ${stroke(1.8)}/>` +
        `<circle cx="${CX}" cy="281" r="5" fill="#e8ecf2" ${stroke(1.2)}/>`
      )
    case 'apron':
      return (
        `<path d="M${f1(CX - 36)},258 L${f1(CX + 36)},258 L${f1(CX + 44)},300 L${f1(CX - 44)},300 Z" fill="${hsl(p.accentH, 30, 82)}" ${stroke(1.6)}/>` +
        `<path d="M${f1(CX - 30)},258 L${f1(CX - p.neckW)},240 M${f1(CX + 30)},258 L${f1(CX + p.neckW)},240" stroke="${INK}" stroke-width="2" fill="none"/>`
      )
    default:
      return ''
  }
}

// ---------------------------------------------------------------- 감정 효과 (이모지)
function effectSvg(emotion: Emotion, p: FaceParams): string {
  const x = CX + p.fw - 6
  const y = p.ty + 8
  switch (emotion) {
    case 'flustered':
      return `<text x="${f1(x)}" y="${f1(y)}" font-size="30" text-anchor="middle" font-family="'Apple Color Emoji','Segoe UI Emoji','Noto Color Emoji',sans-serif">💦</text>`
    case 'angry':
      return `<text x="${f1(x)}" y="${f1(y)}" font-size="30" text-anchor="middle" font-family="'Apple Color Emoji','Segoe UI Emoji','Noto Color Emoji',sans-serif">💢</text>`
    case 'nervous':
      return `<path d="M${f1(CX + p.fw - 8)},${f1(p.ey - 10)} q5,9 0,14 q-5,-5 0,-14 Z" fill="#8fd0f5" ${stroke(1.3)}/>`
    case 'sad':
      return `<path d="M${f1(CX - p.eyeGap - 3)},${f1(p.ey + p.eyeH + 3)} q4,9 0,13 q-4,-4 0,-13 Z" fill="#8fd0f5" ${stroke(1.2)}/>`
    default:
      return ''
  }
}

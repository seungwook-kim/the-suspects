// 절차적 SVG 상반신 초상화 (AI 초상화가 없거나 로드에 실패했을 때 쓰는 대체 그림).
// 반실사풍: 사람 비율(눈은 머리 세로 중앙, 눈 폭은 얼굴 폭의 1/5, 눈 사이는 눈 하나 폭), 부드러운 명암, 얇은 외곽선.
// face_seed 에서 얼굴 비율을 "연속값"으로 뽑는다(저장된 부품 조합이 아님). 같은 입력은 항상 같은 문자열을 낸다(순수 함수).
// 표정은 눈꺼풀·눈썹·입·뺨 파라미터만 바꾼다. 범인 여부는 그림에 드러내지 않는다(표정·색 편향 없음).
import type { Emotion } from '../api/types'
import { clamp, lerp, seededRng } from './rng'

export const PORTRAIT_W = 240
export const PORTRAIT_H = 300
const CX = 120
const LASH = '#2a211c'
const EDGE = 'rgba(18,20,26,0.34)'

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
const hsl = (h: number, s: number, l: number) => `hsl(${f1(h)},${f1(clamp(s, 0, 100))}%,${f1(clamp(l, 0, 100))}%)`
const op = (n: number) => Math.round(clamp(n, 0, 1) * 1000) / 1000

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

function hashStr(s: string): number {
  let h = 2166136261
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i)
    h = Math.imul(h, 16777619)
  }
  return h >>> 0
}

// ---- 시드에서 뽑는 연속값 ----
export interface FaceParams {
  skinH: number; skinS: number; skinL: number
  hairH: number; hairS: number; hairL: number
  irisH: number; irisS: number; irisL: number
  /** 머리 위(두개골 꼭대기) y, 눈 y(머리 세로 중앙), 턱 끝 y */
  ty: number; ey: number; chinY: number
  /** 광대 반폭, 턱선 반폭, 턱 평평한 부분 반폭, 턱 둥글기 */
  fw: number; jw: number; cw: number; chinRound: number
  earR: number; neckW: number; shoulder: number
  /** 눈: 반폭(≈ 얼굴 폭의 1/10 ×2 = 폭 1/5), 눈 중심의 x 오프셋, 윗눈꺼풀 높이, 눈꼬리 각도(도), 눈꺼풀 무거움 */
  eyeW: number; eyeGap: number; eyeH: number; eyeAngle: number; lidHeavy: number
  browThick: number; browLen: number; browGap: number; browAngle: number; browArch: number
  noseLen: number; noseW: number; noseBridge: number
  mouthDrop: number; mouthW: number; lipUp: number; lipLow: number; smileBias: number
  hairVol: number; hairLift: number; hairlineF: number; part: number
  hairStyle: HairStyle
  outfitH: number; outfitS: number; outfitL: number; accentH: number
  bgH: number
}

const pick = <T,>(r: () => number, arr: readonly T[]): T => arr[Math.floor(r() * arr.length) % arr.length]

export function faceParams(seed: number, appearance: Record<string, string> = {}): FaceParams {
  const r = seededRng(seed)
  const u = (a: number, b: number) => lerp(a, b, r())

  // 피부: 하나의 연속값(멜라닌)에서 밝은 톤 ~ 어두운 톤을 고르게 뽑는다
  const melanin = r()
  const skinL = lerp(82, 38, melanin)
  const skinH = u(15, 29)
  const skinS = lerp(40, 44, melanin) + u(-6, 8)
  // 머리색 (appearance.hair_color 가 있으면 그것을 따른다)
  const ht = r()
  const hh = u(0, 1)
  let rh: number, rs: number, rl: number
  if (ht < 0.1) { rh = 30; rs = 6 + hh * 6; rl = 58 + hh * 20 } //            흰머리·회색
  else if (ht < 0.17) { rh = 38 + hh * 8; rs = 45 + hh * 14; rl = 55 + hh * 12 } // 금발
  else if (ht < 0.25) { rh = 14 + hh * 8; rs = 48 + hh * 10; rl = 28 + hh * 10 } //  적갈색
  else if (ht < 0.5) { rh = 22 + hh * 8; rs = 34 + hh * 10; rl = 17 + hh * 13 } //   갈색
  else { rh = 20 + hh * 10; rs = 8 + hh * 22; rl = 8 + hh * 8 } //                   흑갈색·검정
  const hc = appearance.hair_color ? hexToHsl(appearance.hair_color) : null
  const hairH = hc ? hc[0] : rh
  const hairS = hc ? hc[1] : rs
  const hairL = hc ? Math.max(5, hc[2]) : rl
  // 눈동자: 갈색이 대부분, 가끔 헤이즐·회청
  const irisT = r()
  const irisH = irisT < 0.8 ? u(18, 30) : irisT < 0.9 ? u(60, 90) : u(190, 215)
  const irisS = irisT < 0.8 ? 48 : 28
  const irisL = irisT < 0.8 ? u(16, 30) : u(34, 46)

  // 머리 비율: 눈은 머리(꼭대기~턱) 세로 중앙
  const ty = u(52, 60)
  const chinY = u(208, 220)
  const ey = (ty + chinY) / 2 + u(-1, 3)
  const fw = u(54, 66)
  const jw = fw * u(0.68, 0.92)
  const cw = u(9, 17)
  const chinRound = u(4, 11)
  const earR = u(6.5, 9)
  const neckW = fw * u(0.5, 0.6)
  const shoulder = u(100, 116)

  const eyeW = fw * u(0.185, 0.215) // 눈 폭 = 얼굴 폭의 약 1/5 (반폭)
  const eyeGap = eyeW * u(1.9, 2.15) // 눈 사이 간격 ≈ 눈 하나 폭
  const eyeH = eyeW * u(0.5, 0.64)
  const eyeAngle = u(-2, 6)
  const lidHeavy = u(0.8, 1.15)
  const browThick = u(3.2, 5.6)
  const browLen = u(1.05, 1.4)
  const browGap = u(13, 17)
  const browAngle = u(-2, 3)
  const browArch = u(1.4, 3.6)

  const noseLen = u(-3, 4)
  const noseW = u(6, 9)
  const noseBridge = u(0.75, 1.2)
  const mouthDrop = u(0.3, 0.38)
  const mouthW = fw * u(0.3, 0.38)
  const lipUp = u(2.6, 4)
  const lipLow = u(3.6, 5.8)
  const smileBias = u(-0.4, 0.9)

  const hairVol = u(3, 10)
  const hairLift = u(6, 15)
  const hairlineF = u(0.28, 0.4)
  const part = u(-0.5, 0.5)
  const styleFromAppearance = appearance.hair as string | undefined
  const rolled = pick(r, HAIR_STYLES)
  const hairStyle: HairStyle = (HAIR_STYLES as readonly string[]).includes(styleFromAppearance ?? '')
    ? (styleFromAppearance as HairStyle)
    : styleFromAppearance === 'none'
      ? 'bald'
      : rolled

  const outfitH = u(0, 360)
  const outfitS = u(14, 36)
  const outfitL = u(24, 46)
  const accentH = u(0, 360)
  const bgH = u(0, 360)

  return {
    skinH, skinS, skinL, hairH, hairS, hairL, irisH, irisS, irisL,
    ty, ey, chinY, fw, jw, cw, chinRound, earR, neckW, shoulder,
    eyeW, eyeGap, eyeH, eyeAngle, lidHeavy,
    browThick, browLen, browGap, browAngle, browArch,
    noseLen, noseW, noseBridge, mouthDrop, mouthW, lipUp, lipLow, smileBias,
    hairVol, hairLift, hairlineF, part, hairStyle,
    outfitH, outfitS, outfitL, accentH, bgH,
  }
}

// ---- 표정 -> 눈꺼풀·눈썹·입·뺨 파라미터 (+ 는 아래/바깥쪽 방향은 각 항목 설명 참고) ----
interface EmoParams {
  open: number // 윗눈꺼풀 열림 배율
  lower: number // 아랫눈꺼풀 배율(웃을 때 올라옴)
  tilt: number // 눈꼬리 각도 가산(도, +면 바깥이 올라감)
  lidDrop: number // 바깥쪽 윗눈꺼풀 처짐(px)
  look: number // 시선 x
  brIn: number; brMid: number; brOut: number // 눈썹 안쪽·가운데·바깥 y 이동(px, +면 아래)
  cheek: number // 0~1 광대가 올라간 정도
  flush: number // 0~1 혈색
  curve: number // 입꼬리가 가운데보다 높은 정도(px, -면 처짐)
  up: number; low: number // 윗입술·아랫입술 두께 배율
  dl: number; dr: number // 입꼬리 좌우 y 보정(px)
  gap: number // 입이 벌어진 정도(px)
  mw: number // 입 폭 배율
  press: number // 입술을 다문 정도 0~1
  flare: number // 콧망울 벌어짐
}
const EMO: Record<Emotion, EmoParams> = {
  neutral: { open: 1, lower: 1, tilt: 0, lidDrop: 0, look: 0, brIn: 0, brMid: 0, brOut: 0, cheek: 0, flush: 0, curve: 0.3, up: 1, low: 1, dl: 0, dr: 0, gap: 0, mw: 1, press: 0, flare: 0 },
  nervous: { open: 1.08, lower: 1, tilt: 0, lidDrop: 0, look: 2.6, brIn: -4.5, brMid: -2.5, brOut: 0.5, cheek: 0, flush: 0.4, curve: -0.5, up: 0.8, low: 0.8, dl: 0.6, dr: -0.3, gap: 0, mw: 0.88, press: 0.55, flare: 0 },
  flustered: { open: 1.3, lower: 1.25, tilt: 0, lidDrop: 0, look: -1.6, brIn: -5, brMid: -6.5, brOut: -3, cheek: 0, flush: 0.9, curve: -0.2, up: 0.95, low: 1.05, dl: 2.4, dr: -1.8, gap: 2.2, mw: 0.95, press: 0, flare: 0 },
  angry: { open: 0.72, lower: 0.85, tilt: 2.5, lidDrop: 0, look: 0, brIn: 6.5, brMid: 2, brOut: -1, cheek: 0, flush: 0.4, curve: -1.4, up: 0.65, low: 0.65, dl: 0, dr: 0, gap: 0, mw: 0.95, press: 1, flare: 1 },
  sad: { open: 0.88, lower: 0.95, tilt: -3, lidDrop: 1.7, look: 0, brIn: -4.8, brMid: -1, brOut: 2.8, cheek: 0, flush: 0.1, curve: -2.6, up: 0.9, low: 1.05, dl: 0, dr: 0, gap: 0, mw: 0.9, press: 0.3, flare: 0 },
  happy: { open: 0.88, lower: 0.5, tilt: 0, lidDrop: 0, look: 0, brIn: -1.5, brMid: -2.5, brOut: -1, cheek: 1, flush: 0.3, curve: 3.6, up: 0.85, low: 0.95, dl: 0, dr: 0, gap: 2.6, mw: 1.08, press: 0, flare: 0 },
}

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
  const id = `f${hashStr(`${seed}|${JSON.stringify(appearance)}|${emotion}|${Math.round(mouthOpen * 20)}|${opts.blink ? 1 : 0}|${opts.bg === false ? 0 : 1}`).toString(36)}`
  const defs: string[] = []
  const out: string[] = []
  const ctx: Ctx = { p, e, emo: emotion, id, defs }

  // 피부 색조
  const sk = (dl: number, ds = 0, dh = 0) => hsl(p.skinH + dh, p.skinS + ds, p.skinL + dl)
  ctx.sk = sk

  defs.push(
    `<filter id="${id}b05" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="0.5"/></filter>`,
    `<filter id="${id}b1" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="1.1"/></filter>`,
    `<filter id="${id}b2" x="-40%" y="-40%" width="180%" height="180%"><feGaussianBlur stdDeviation="2.4"/></filter>`,
    `<filter id="${id}b4" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="4.5"/></filter>`,
  )

  out.push(
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${PORTRAIT_W} ${PORTRAIT_H}" width="${PORTRAIT_W}" height="${PORTRAIT_H}" role="img">`,
    '@@DEFS@@',
  )
  if (opts.bg !== false) {
    defs.push(
      `<radialGradient id="${id}bg" cx="0.5" cy="0.42" r="0.75"><stop offset="0" stop-color="${hsl(p.bgH, 12, 76)}"/><stop offset="1" stop-color="${hsl(p.bgH, 16, 48)}"/></radialGradient>`,
    )
    out.push(`<rect width="${PORTRAIT_W}" height="${PORTRAIT_H}" rx="18" fill="url(#${id}bg)"/>`)
  }

  const face = facePath(p)
  defs.push(`<clipPath id="${id}face"><path d="${face}"/></clipPath>`)

  out.push(hairBack(ctx))
  out.push(neckSvg(ctx))
  out.push(outfitSvg(appearance.outfit, ctx))
  out.push(earsSvg(ctx))
  out.push(faceSvg(ctx, face))
  const noseBaseY = noseBase(p)
  out.push(noseSvg(ctx, noseBaseY))
  out.push(eyesSvg(ctx, !!opts.blink))
  out.push(browsSvg(ctx))
  const mouthY = noseBaseY + (p.chinY - noseBaseY) * p.mouthDrop
  out.push(mouthSvg(ctx, mouthY, mouthOpen))
  out.push(hairFront(ctx))
  out.push(accessorySvg(appearance.accessory, ctx))
  out.push(effectSvg(emotion, p))
  out.push('</svg>')
  return out.join('').replace('@@DEFS@@', `<defs>${defs.join('')}</defs>`)
}

interface Ctx {
  p: FaceParams
  e: EmoParams
  emo: Emotion
  id: string
  defs: string[]
  sk?: (dl: number, ds?: number, dh?: number) => string
}
const skOf = (c: Ctx) => c.sk!

const noseBase = (p: FaceParams) => p.ey + (p.chinY - p.ey) * 0.4 + p.noseLen

// ---------------------------------------------------------------- 얼굴 윤곽
function facePath(p: FaceParams): string {
  const span = p.chinY - p.ey
  const jy = p.ey + span * 0.66
  const tY = p.ey - (p.ey - p.ty) * 0.3
  const kx = p.cw + 4
  const kyy = p.chinY - p.chinRound
  const cyy = p.chinY + p.chinRound / 3
  const R = (x: number) => f1(CX + x)
  const L = (x: number) => f1(CX - x)
  return (
    `M${f1(CX)},${f1(p.ty)} ` +
    `C${R(p.fw * 0.6)},${f1(p.ty)} ${R(p.fw)},${f1(p.ty + (p.ey - p.ty) * 0.2)} ${R(p.fw)},${f1(tY)} ` +
    `C${R(p.fw)},${f1(p.ey + span * 0.25)} ${R(p.jw + (p.fw - p.jw) * 0.25)},${f1(jy - span * 0.1)} ${R(p.jw)},${f1(jy)} ` +
    `C${R(p.jw - 2)},${f1(jy + span * 0.15)} ${R(kx + 6)},${f1(p.chinY - 2)} ${R(kx)},${f1(kyy)} ` +
    `C${R(kx * 0.8)},${f1(cyy)} ${L(kx * 0.8)},${f1(cyy)} ${L(kx)},${f1(kyy)} ` +
    `C${L(kx + 6)},${f1(p.chinY - 2)} ${L(p.jw - 2)},${f1(jy + span * 0.15)} ${L(p.jw)},${f1(jy)} ` +
    `C${L(p.jw + (p.fw - p.jw) * 0.25)},${f1(jy - span * 0.1)} ${L(p.fw)},${f1(p.ey + span * 0.25)} ${L(p.fw)},${f1(tY)} ` +
    `C${L(p.fw)},${f1(p.ty + (p.ey - p.ty) * 0.2)} ${L(p.fw * 0.6)},${f1(p.ty)} ${f1(CX)},${f1(p.ty)} Z`
  )
}

function faceSvg(c: Ctx, face: string): string {
  const { p, e, id } = c
  const sk = skOf(c)
  const span = p.chinY - p.ey
  const top = p.ty
  const h = p.chinY - top
  c.defs.push(
    `<radialGradient id="${id}skin" cx="0.38" cy="0.32" r="0.82"><stop offset="0" stop-color="${sk(7, 2)}"/><stop offset="0.55" stop-color="${sk(0)}"/><stop offset="1" stop-color="${sk(-10, 5, -2)}"/></radialGradient>`,
    `<linearGradient id="${id}jaw" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${sk(-30, 8, -3)}" stop-opacity="0"/><stop offset="0.62" stop-color="${sk(-30, 8, -3)}" stop-opacity="0"/><stop offset="1" stop-color="${sk(-30, 8, -3)}" stop-opacity="0.34"/></linearGradient>`,
    `<linearGradient id="${id}side" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="${sk(-30, 8, -3)}" stop-opacity="0.16"/><stop offset="0.28" stop-color="${sk(-30, 8, -3)}" stop-opacity="0"/><stop offset="0.6" stop-color="${sk(-30, 8, -3)}" stop-opacity="0"/><stop offset="1" stop-color="${sk(-30, 8, -3)}" stop-opacity="0.36"/></linearGradient>`,
  )
  const o: string[] = []
  o.push(`<path d="${face}" fill="url(#${id}skin)" stroke="${sk(-26, 6, -3)}" stroke-opacity="0.45" stroke-width="0.9"/>`)
  o.push(`<g clip-path="url(#${id}face)">`)
  const bx = CX - p.fw - 4
  const bw = p.fw * 2 + 8
  o.push(`<rect x="${f1(bx)}" y="${f1(top - 4)}" width="${f1(bw)}" height="${f1(h + 14)}" fill="url(#${id}side)"/>`)
  o.push(`<rect x="${f1(bx)}" y="${f1(top - 4)}" width="${f1(bw)}" height="${f1(h + 14)}" fill="url(#${id}jaw)"/>`)
  // 이마 하이라이트, 관자놀이·눈두덩 음영
  o.push(`<ellipse cx="${f1(CX - p.fw * 0.22)}" cy="${f1(top + 24)}" rx="${f1(p.fw * 0.5)}" ry="14" fill="#fff" opacity="0.16" filter="url(#${id}b4)"/>`)
  for (const s of [-1, 1]) {
    o.push(`<ellipse cx="${f1(CX + s * (p.fw - 5))}" cy="${f1(p.ey - 12)}" rx="7" ry="20" fill="${sk(-32, 8, -3)}" opacity="${s === 1 ? 0.2 : 0.1}" filter="url(#${id}b2)"/>`)
    // 눈두덩 아래 눈구멍 그림자
    o.push(`<ellipse cx="${f1(CX + s * p.eyeGap)}" cy="${f1(p.ey - 6)}" rx="${f1(p.eyeW * 1.35)}" ry="6" fill="${sk(-34, 8, -3)}" opacity="0.2" filter="url(#${id}b2)"/>`)
    // 뺨 혈색(번지는 정도의 은은한 색)
    const fl = 0.07 + e.flush * 0.17
    o.push(`<ellipse cx="${f1(CX + s * (p.eyeGap + 9))}" cy="${f1(p.ey + span * 0.3)}" rx="17" ry="11" fill="${hsl(5, 62, 56)}" opacity="${op(fl)}" filter="url(#${id}b4)"/>`)
    // 비순구(코 옆에서 입꼬리로)
    const nf = 0.1 + e.cheek * 0.2 + (e.curve < -1 ? 0.1 : 0)
    const nbY = noseBase(p)
    o.push(`<path d="M${f1(CX + s * (p.noseW + 3))},${f1(nbY - 2)} Q${f1(CX + s * (p.mouthW + 7))},${f1(nbY + 9)} ${f1(CX + s * (p.mouthW + 3))},${f1(nbY + (p.chinY - nbY) * p.mouthDrop + 1)}" fill="none" stroke="${sk(-34, 8, -3)}" stroke-width="1.6" stroke-linecap="round" opacity="${op(nf)}" filter="url(#${id}b1)"/>`)
    // 광대 하이라이트
    o.push(`<ellipse cx="${f1(CX + s * (p.eyeGap + 6))}" cy="${f1(p.ey + 15 - e.cheek * 3)}" rx="13" ry="${f1(6 + e.cheek * 2)}" fill="#fff" opacity="${s === -1 ? 0.13 + e.cheek * 0.1 : 0.06 + e.cheek * 0.08}" filter="url(#${id}b2)"/>`)
  }
  // 턱 하이라이트
  o.push(`<ellipse cx="${f1(CX - 3)}" cy="${f1(p.chinY - 9)}" rx="8" ry="4" fill="#fff" opacity="0.1" filter="url(#${id}b2)"/>`)
  // 표정에 따른 색조
  if (c.emo === 'angry') o.push(`<path d="${face}" fill="${hsl(8, 70, 50)}" opacity="0.09"/>`)
  if (c.emo === 'sad') o.push(`<path d="${face}" fill="${hsl(215, 30, 55)}" opacity="0.07"/>`)
  o.push('</g>')
  return o.join('')
}

function neckSvg(c: Ctx): string {
  const { p, id } = c
  const sk = skOf(c)
  const nt = p.chinY - 30
  const nw = p.neckW
  const d = `M${f1(CX - nw)},${f1(nt)} L${f1(CX - nw - 1)},266 L${f1(CX + nw + 1)},266 L${f1(CX + nw)},${f1(nt)} Z`
  c.defs.push(
    `<linearGradient id="${id}neck" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="${sk(-3)}"/><stop offset="0.45" stop-color="${sk(-5, 2)}"/><stop offset="1" stop-color="${sk(-20, 6, -2)}"/></linearGradient>`,
    `<clipPath id="${id}neckc"><path d="${d}"/></clipPath>`,
  )
  return (
    `<path d="${d}" fill="url(#${id}neck)"/>` +
    `<g clip-path="url(#${id}neckc)">` +
    // 턱 밑 그림자
    `<ellipse cx="${f1(CX + 3)}" cy="${f1(p.chinY + 6)}" rx="${f1(nw * 0.95)}" ry="15" fill="${sk(-34, 8, -3)}" opacity="0.34" filter="url(#${id}b2)"/>` +
    // 목 근육 결
    `<path d="M${f1(CX + nw * 0.45)},${f1(p.chinY + 14)} Q${f1(CX + nw * 0.55)},${f1(p.chinY + 40)} ${f1(CX + nw * 0.35)},262" fill="none" stroke="${sk(-30, 8, -3)}" stroke-width="3" opacity="0.18" filter="url(#${id}b2)"/>` +
    `<path d="M${f1(CX - nw * 0.4)},${f1(p.chinY + 18)} Q${f1(CX - nw * 0.6)},${f1(p.chinY + 40)} ${f1(CX - nw * 0.4)},262" fill="none" stroke="#fff" stroke-width="3" opacity="0.07" filter="url(#${id}b2)"/>` +
    `</g>`
  )
}

function earsSvg(c: Ctx): string {
  const { p, id } = c
  const sk = skOf(c)
  const o: string[] = []
  for (const s of [-1, 1]) {
    const ex = CX + s * (p.fw + 0.5)
    const cy = p.ey + 4
    const rx = p.earR
    const ry = p.earR * 1.85
    const shade = s === 1 ? 0 : 3
    o.push(
      `<ellipse cx="${f1(ex + s * 1.5)}" cy="${f1(cy)}" rx="${f1(rx)}" ry="${f1(ry)}" fill="${sk(-4 + shade, 3)}" stroke="${sk(-28, 6, -3)}" stroke-opacity="0.45" stroke-width="0.8"/>`,
      // 귓바퀴 안쪽 음영
      `<path d="M${f1(ex + s * 2.4)},${f1(cy - ry * 0.55)} Q${f1(ex + s * (rx + 0.8))},${f1(cy)} ${f1(ex + s * 2.4)},${f1(cy + ry * 0.6)}" fill="none" stroke="${sk(-26, 8, -3)}" stroke-width="1.6" stroke-linecap="round" opacity="0.5"/>`,
      `<ellipse cx="${f1(ex + s * 2)}" cy="${f1(cy + 1)}" rx="${f1(rx * 0.38)}" ry="${f1(ry * 0.5)}" fill="${sk(-22, 8, -3)}" opacity="0.38" filter="url(#${id}b05)"/>`,
    )
  }
  return o.join('')
}

// ---------------------------------------------------------------- 코
function noseSvg(c: Ctx, nbY: number): string {
  const { p, e, id } = c
  const sk = skOf(c)
  const o: string[] = []
  const shadow = sk(-36, 8, -3)
  const bridgeTop = p.ey - 3
  const nb = p.noseBridge
  // 콧대 옆 그림자: 빛이 왼쪽 위에서 오므로 오른쪽이 더 어둡다
  for (const s of [1, -1]) {
    const sop = (s === 1 ? 0.3 : 0.12) * nb
    o.push(
      `<path d="M${f1(CX + s * 4.5)},${f1(bridgeTop)} C${f1(CX + s * 5.5)},${f1(bridgeTop + (nbY - bridgeTop) * 0.35)} ${f1(CX + s * (p.noseW * 0.7))},${f1(nbY - 12)} ${f1(CX + s * (p.noseW * 0.85))},${f1(nbY - 4)}" fill="none" stroke="${shadow}" stroke-width="4" stroke-linecap="round" opacity="${op(sop)}" filter="url(#${id}b1)"/>`,
    )
  }
  // 콧대 하이라이트와 코끝
  o.push(
    `<path d="M${f1(CX - 1)},${f1(bridgeTop + 6)} L${f1(CX - 0.6)},${f1(nbY - 9)}" stroke="#fff" stroke-width="2.6" stroke-linecap="round" opacity="0.16" filter="url(#${id}b1)"/>`,
    `<ellipse cx="${f1(CX - 0.5)}" cy="${f1(nbY - 5)}" rx="4.6" ry="3.4" fill="#fff" opacity="0.15" filter="url(#${id}b1)"/>`,
  )
  // 코 밑 그림자와 콧방울, 콧구멍
  o.push(`<ellipse cx="${f1(CX + 1)}" cy="${f1(nbY + 3.5)}" rx="${f1(p.noseW * 1.05)}" ry="2.6" fill="${shadow}" opacity="0.3" filter="url(#${id}b1)"/>`)
  const flare = e.flare * 1.4
  for (const s of [-1, 1]) {
    const w = p.noseW + flare * 0.6
    o.push(
      `<path d="M${f1(CX + s * w * 0.5)},${f1(nbY - 7)} C${f1(CX + s * (w + 1.8))},${f1(nbY - 7)} ${f1(CX + s * (w + 2.4))},${f1(nbY - 0.5)} ${f1(CX + s * w * 0.62)},${f1(nbY + 1.6)}" fill="none" stroke="${shadow}" stroke-width="1" stroke-linecap="round" opacity="0.5"/>`,
      `<ellipse cx="${f1(CX + s * (w * 0.4 + 0.6))}" cy="${f1(nbY + 0.6)}" rx="${f1(2.7 + flare * 0.4)}" ry="1.35" transform="rotate(${f1(s * -14)} ${f1(CX + s * w * 0.4)} ${f1(nbY)})" fill="${sk(-52, 10, -4)}" opacity="${f1(0.55 + e.flare * 0.15)}"/>`,
    )
  }
  return o.join('')
}

// ---------------------------------------------------------------- 눈
function eyesSvg(c: Ctx, blink: boolean): string {
  const { p, e, id } = c
  const sk = skOf(c)
  const o: string[] = []
  const rx = p.eyeW
  const ht = p.eyeH * e.open * p.lidHeavy * (0.5 + 0.5 / p.lidHeavy) // 윗눈꺼풀이 무거울수록 열림이 약간 줄어든다
  const hb = p.eyeH * 0.55 * e.lower
  const tiltPx = rx * Math.tan(((p.eyeAngle + e.tilt) * Math.PI) / 180)
  const dx = rx * 2
  for (const s of [-1, 1]) {
    const ex = CX + s * p.eyeGap
    const ey = p.ey
    const ix = ex - s * rx // 안쪽(코 쪽) 눈초리
    const iy = ey + tiltPx * 0.35
    const ox = ex + s * rx // 바깥쪽 눈꼬리
    const oy = ey - tiltPx
    const upper = `C${f1(ix + s * dx * 0.22)},${f1(iy - ht * 1.33)} ${f1(ox - s * dx * 0.34)},${f1(oy - ht * 1.33 + e.lidDrop * 1.4)} ${f1(ox)},${f1(oy)}`
    const lower = `C${f1(ox - s * dx * 0.3)},${f1(oy + hb * 1.33)} ${f1(ix + s * dx * 0.3)},${f1(iy + hb * 1.33)} ${f1(ix)},${f1(iy)}`
    const shape = `M${f1(ix)},${f1(iy)} ${upper} ${lower} Z`
    const mx = ex
    const my = (iy + oy) / 2

    if (blink) {
      o.push(
        `<path d="${shape}" fill="${sk(-4, 2)}"/>`,
        `<path d="M${f1(ix)},${f1(iy)} Q${f1(mx)},${f1(my + 3.4)} ${f1(ox)},${f1(oy)}" fill="none" stroke="${LASH}" stroke-width="1.5" stroke-linecap="round" opacity="0.85"/>`,
      )
    } else {
      c.defs.push(`<clipPath id="${id}e${s > 0 ? 'r' : 'l'}"><path d="${shape}"/></clipPath>`)
      const ir = rx * 0.4
      const lowPeak = my + hb * 0.75
      const centered = my + (hb - ht) * 0.375
      const k = clamp((e.open - 1) * 3, 0, 1)
      const icy = lerp(lowPeak - ir + 0.3, centered, k)
      const icx = ex + e.look + s * 0.3
      c.defs.push(
        `<radialGradient id="${id}ir${s > 0 ? 'r' : 'l'}" cx="0.5" cy="0.5" r="0.5"><stop offset="0" stop-color="${hsl(p.irisH, p.irisS, p.irisL + 14)}"/><stop offset="0.55" stop-color="${hsl(p.irisH, p.irisS, p.irisL)}"/><stop offset="1" stop-color="${hsl(p.irisH, p.irisS, p.irisL - 8)}"/></radialGradient>`,
        `<linearGradient id="${id}sc${s > 0 ? 'r' : 'l'}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#b9b2ad"/><stop offset="0.35" stop-color="#ece7e2"/><stop offset="1" stop-color="#f4f0ec"/></linearGradient>`,
      )
      o.push(
        `<g clip-path="url(#${id}e${s > 0 ? 'r' : 'l'})">`,
        `<rect x="${f1(ex - rx - 2)}" y="${f1(oy - ht - 3)}" width="${f1(dx + 4)}" height="${f1(ht + hb + 8 + Math.abs(tiltPx))}" fill="url(#${id}sc${s > 0 ? 'r' : 'l'})"/>`,
        // 눈구석 살짝 붉은 기
        `<ellipse cx="${f1(ix + s * 1.2)}" cy="${f1(iy)}" rx="2.2" ry="2.4" fill="${hsl(8, 45, 62)}" opacity="0.45"/>`,
        `<circle cx="${f1(icx)}" cy="${f1(icy)}" r="${f1(ir)}" fill="url(#${id}ir${s > 0 ? 'r' : 'l'})"/>`,
        `<circle cx="${f1(icx)}" cy="${f1(icy)}" r="${f1(ir - 0.3)}" fill="none" stroke="#150f0c" stroke-width="0.9" opacity="0.9"/>`,
        `<circle cx="${f1(icx)}" cy="${f1(icy)}" r="${f1(ir * 0.42)}" fill="#0a0807"/>`,
        `<circle cx="${f1(icx - ir * 0.36)}" cy="${f1(icy - ir * 0.34)}" r="${f1(ir * 0.2)}" fill="#fff" opacity="0.95"/>`,
        `<circle cx="${f1(icx + ir * 0.38)}" cy="${f1(icy + ir * 0.42)}" r="${f1(ir * 0.1)}" fill="#fff" opacity="0.4"/>`,
        // 윗눈꺼풀이 드리운 그림자
        `<path d="M${f1(ix)},${f1(iy)} ${upper} L${f1(ox)},${f1(oy - ht - 4)} L${f1(ix)},${f1(iy - ht - 4)} Z" fill="#000" opacity="0.14" transform="translate(0 1.6)"/>`,
        `</g>`,
      )
      // 아랫눈꺼풀 선
      o.push(
        `<path d="M${f1(ox)},${f1(oy)} ${lower}" fill="none" stroke="${sk(-34, 8, -3)}" stroke-width="0.9" opacity="0.5"/>`,
        `<path d="M${f1(ox - s * dx * 0.12)},${f1(oy + hb * 0.95 + 1.8)} Q${f1(mx)},${f1(my + hb * 1.5 + 2.8)} ${f1(ix + s * dx * 0.15)},${f1(iy + hb * 0.95 + 1.8)}" fill="none" stroke="${sk(-30, 8, -3)}" stroke-width="1.4" opacity="${f1(0.14 + (1 - e.lower) * 0.14)}" filter="url(#${id}b05)"/>`,
      )
      // 속눈썹 선 (윗눈꺼풀)
      o.push(
        `<path d="M${f1(ix)},${f1(iy)} ${upper}" fill="none" stroke="${LASH}" stroke-width="1.55" stroke-linecap="round" opacity="0.92"/>`,
        `<path d="M${f1(ox)},${f1(oy)} L${f1(ox + s * 2.6)},${f1(oy - 1.3 - Math.max(0, tiltPx) * 0.2)}" stroke="${LASH}" stroke-width="1.2" stroke-linecap="round" opacity="0.8"/>`,
      )
    }
    // 쌍꺼풀(윗눈꺼풀 주름)
    const gap = (blink ? 3.5 : ht * 0.5 + 2.2) * p.lidHeavy
    o.push(
      `<path d="M${f1(ix + s * dx * 0.1)},${f1(iy - gap * 0.75)} Q${f1(mx)},${f1(my - (blink ? 2 : ht * 1.45) - gap)} ${f1(ox - s * dx * 0.04)},${f1(oy - gap * 0.4 - 0.5 + e.lidDrop * 0.4)}" fill="none" stroke="${sk(-38, 8, -3)}" stroke-width="1" stroke-linecap="round" opacity="${blink ? 0.3 : 0.5}"/>`,
    )
    // 눈물 (슬픔): 아랫눈꺼풀에 맺힌 물기
    if (!blink && c.emo === 'sad') {
      o.push(`<path d="M${f1(ex - s * rx * 0.2)},${f1(my + hb * 0.8)} q1.2,4.4 0,6.2 q-1.9,-1.7 0,-6.2 Z" fill="#cfe6f5" opacity="0.5"/>`)
    }
  }
  return o.join('')
}

// ---------------------------------------------------------------- 눈썹 (끝으로 갈수록 가는 획)
function browsSvg(c: Ctx): string {
  const { p, e, id } = c
  const o: string[] = []
  const gray = p.hairL > 56
  const col = gray ? hsl(p.hairH, p.hairS, clamp(p.hairL - 14, 30, 60)) : hsl(p.hairH, p.hairS + 4, clamp(p.hairL - 3, 5, 40))
  for (const s of [-1, 1]) {
    const xi = CX + s * (p.eyeGap - p.eyeW * 1.05)
    const xo = CX + s * (p.eyeGap + p.eyeW * (0.7 + p.browLen * 0.6))
    const baseY = p.ey - p.browGap
    const yi = baseY + 1.5 + e.brIn
    const yo = baseY + 2 + p.browAngle * -0.4 + e.brOut
    const ym = baseY - p.browArch + e.brMid
    const mx = (xi + xo) / 2
    const cx = 2 * mx - (xi + xo) / 2
    const cy = 2 * ym - (yi + yo) / 2
    const N = 12
    const top: string[] = []
    const bot: string[] = []
    for (let i = 0; i <= N; i++) {
      const t = i / N
      const bx = (1 - t) * (1 - t) * xi + 2 * (1 - t) * t * cx + t * t * xo
      const by = (1 - t) * (1 - t) * yi + 2 * (1 - t) * t * cy + t * t * yo
      const dxn = 2 * (1 - t) * (cx - xi) + 2 * t * (xo - cx)
      const dyn = 2 * (1 - t) * (cy - yi) + 2 * t * (yo - cy)
      const len = Math.hypot(dxn, dyn) || 1
      const nx = -dyn / len
      const ny = dxn / len
      const th = (p.browThick * Math.max(0.12, 1 - Math.pow(t, 1.7)) * (0.7 + 0.3 * Math.min(1, t * 5))) / 2
      top.push(`${f1(bx + nx * th * 1.0)},${f1(by + ny * th * 1.0)}`)
      bot.push(`${f1(bx - nx * th)},${f1(by - ny * th)}`)
    }
    o.push(`<path d="M${top.join(' L')} L${bot.reverse().join(' L')} Z" fill="${col}" opacity="0.88" filter="url(#${id}b05)"/>`)
  }
  return o.join('')
}

// ---------------------------------------------------------------- 입
function mouthSvg(c: Ctx, my: number, open: number): string {
  const { p, e, id } = c
  const sk = skOf(c)
  const w = p.mouthW * e.mw * (1 - open * 0.07)
  const gap = e.gap + open * 9
  const press = e.press
  const ut = p.lipUp * e.up * (1 - press * 0.15)
  const lt = p.lipLow * e.low * (1 - press * 0.15)
  const curve = e.curve + p.smileBias
  const yl = my - curve + e.dl
  const yr = my - curve + e.dr
  const yu = my - gap * 0.35
  const yd = my + gap * 0.65
  const lipH = Math.max(0, p.skinH - 10)
  const lipS = clamp(p.skinS + 8, 20, 62)
  const lipL = clamp(p.skinL * 0.74, 28, 62)
  const upCol = hsl(lipH, lipS, lipL - 6)
  const loCol = hsl(lipH, lipS, lipL + 2)
  const lineCol = hsl(lipH, 38, Math.max(10, lipL * 0.42))
  const Lx = CX - w
  const Rx = CX + w
  const ctrl = (yc: number) => f1(2 * yc - (yl + yr) / 2)
  const o: string[] = []

  // 입술 아래·위 그림자
  o.push(
    `<ellipse cx="${f1(CX)}" cy="${f1(my + lt + gap * 0.65 + 6)}" rx="${f1(w * 0.55)}" ry="3.2" fill="${sk(-36, 8, -3)}" opacity="${f1(0.2 + (curve < -1 ? 0.12 : 0))}" filter="url(#${id}b2)"/>`,
    `<ellipse cx="${f1(CX)}" cy="${f1(my - ut - 4)}" rx="${f1(w * 0.3)}" ry="2.6" fill="${sk(-36, 8, -3)}" opacity="0.14" filter="url(#${id}b1)"/>`,
  )

  const cav = `M${f1(Lx)},${f1(yl)} Q${f1(CX)},${ctrl(yu)} ${f1(Rx)},${f1(yr)} Q${f1(CX)},${ctrl(yd)} ${f1(Lx)},${f1(yl)} Z`
  if (gap > 1.2) {
    c.defs.push(`<clipPath id="${id}mo"><path d="${cav}"/></clipPath>`)
    o.push(
      `<path d="${cav}" fill="#3a1618"/>`,
      `<g clip-path="url(#${id}mo)">`,
      `<path d="M${f1(Lx)},${f1(yl - 1)} Q${f1(CX)},${ctrl(yu - 1)} ${f1(Rx)},${f1(yr - 1)} L${f1(Rx)},${f1(yr + Math.min(gap * 0.5, 4.5))} Q${f1(CX)},${ctrl(yu + Math.min(gap * 0.5, 4.5))} ${f1(Lx)},${f1(yl + Math.min(gap * 0.5, 4.5))} Z" fill="#ece6de"/>`,
      gap > 5 ? `<ellipse cx="${f1(CX)}" cy="${f1(yd - 1.2)}" rx="${f1(w * 0.5)}" ry="${f1(gap * 0.28)}" fill="#a85a5a"/>` : '',
      `</g>`,
    )
  }
  // 아랫입술
  o.push(
    `<path d="M${f1(Lx)},${f1(yl)} Q${f1(CX)},${ctrl(yd)} ${f1(Rx)},${f1(yr)} C${f1(CX + w * 0.66)},${f1(yd + lt * 1.3 + (yl + yr) / 2 - my)} ${f1(CX - w * 0.66)},${f1(yd + lt * 1.3 + (yl + yr) / 2 - my)} ${f1(Lx)},${f1(yl)} Z" fill="${loCol}"/>`,
    `<ellipse cx="${f1(CX - w * 0.1)}" cy="${f1(yd + lt * 0.55)}" rx="${f1(w * 0.3)}" ry="${f1(lt * 0.22)}" fill="#fff" opacity="0.22" filter="url(#${id}b1)"/>`,
  )
  // 윗입술 (큐피드 활)
  const bx = w * 0.3
  const bowTop = yu - ut
  o.push(
    `<path d="M${f1(Lx)},${f1(yl)} C${f1(Lx + w * 0.3)},${f1(yl - ut * 0.3)} ${f1(CX - bx - 3)},${f1(bowTop + 0.2)} ${f1(CX - bx)},${f1(bowTop)} Q${f1(CX - bx * 0.45)},${f1(bowTop - 0.2)} ${f1(CX)},${f1(bowTop + ut * 0.38)} Q${f1(CX + bx * 0.45)},${f1(bowTop - 0.2)} ${f1(CX + bx)},${f1(bowTop)} C${f1(CX + bx + 3)},${f1(bowTop + 0.2)} ${f1(Rx - w * 0.3)},${f1(yr - ut * 0.3)} ${f1(Rx)},${f1(yr)} Q${f1(CX)},${ctrl(yu)} ${f1(Lx)},${f1(yl)} Z" fill="${upCol}"/>`,
  )
  // 입 선 (가운데 선은 약하게, 양끝은 살짝 진하게)
  const lw = 1 + press * 0.7
  o.push(
    `<path d="M${f1(Lx)},${f1(yl)} Q${f1(CX)},${ctrl(yu)} ${f1(Rx)},${f1(yr)}" fill="none" stroke="${lineCol}" stroke-width="${f1(lw)}" stroke-linecap="round" opacity="${f1(0.78 + press * 0.15)}"/>`,
    `<circle cx="${f1(Lx)}" cy="${f1(yl)}" r="1.1" fill="${lineCol}" opacity="0.4"/>`,
    `<circle cx="${f1(Rx)}" cy="${f1(yr)}" r="1.1" fill="${lineCol}" opacity="0.4"/>`,
  )
  // 슬픔: 턱 끝에 생기는 주름 그림자
  if (c.emo === 'sad') {
    o.push(`<ellipse cx="${f1(CX)}" cy="${f1(my + lt + 9)}" rx="${f1(w * 0.45)}" ry="2.6" fill="${sk(-40, 8, -3)}" opacity="0.22" filter="url(#${id}b1)"/>`)
  }
  return o.join('')
}

// ---------------------------------------------------------------- 머리카락
function hairColors(c: Ctx) {
  const { p, id } = c
  const base = hsl(p.hairH, p.hairS, p.hairL)
  const hi = hsl(p.hairH, p.hairS * 0.9, clamp(p.hairL + 12, 0, 88))
  const dk = hsl(p.hairH, p.hairS, Math.max(3, p.hairL - 9))
  c.defs.push(
    `<linearGradient id="${id}hair" x1="0.15" y1="0" x2="0.85" y2="1"><stop offset="0" stop-color="${hi}"/><stop offset="0.45" stop-color="${base}"/><stop offset="1" stop-color="${dk}"/></linearGradient>`,
  )
  return { base, hi, dk }
}

function strands(c: Ctx, clipId: string, top: number, endY: number, spread: number, shift: number, n = 9): string {
  const { p, id } = c
  const { hi, dk } = hairColors(c)
  const o: string[] = [`<g clip-path="url(#${clipId})" fill="none" stroke-linecap="round">`]
  for (let i = 0; i < n; i++) {
    const u = (i / (n - 1)) * 2 - 1
    const wob = Math.sin(i * 2.3 + p.part * 6) * 3
    const x0 = CX + shift + u * 6
    const x1 = CX + shift + u * spread * 0.55 + wob
    const x2 = CX + u * spread * 1.0
    const d = `M${f1(x0)},${f1(top + 3)} C${f1(x1)},${f1(top + (endY - top) * 0.18)} ${f1(x2 + wob)},${f1(top + (endY - top) * 0.55)} ${f1(x2 + u * 4)},${f1(endY)}`
    o.push(`<path d="${d}" stroke="${i % 2 ? dk : hi}" stroke-width="${i % 2 ? 0.9 : 0.8}" opacity="${i % 2 ? 0.38 : 0.3}"/>`)
  }
  o.push(
    `<ellipse cx="${f1(CX - spread * 0.35)}" cy="${f1(top + (endY - top) * 0.22)}" rx="${f1(spread * 0.4)}" ry="${f1((endY - top) * 0.1)}" fill="#fff" stroke="none" opacity="0.14" filter="url(#${id}b4)"/>`,
    `</g>`,
  )
  return o.join('')
}

function hairBack(c: Ctx): string {
  const { p, id } = c
  const { dk } = hairColors(c)
  const { fw, ty, ey, hairVol: v, hairStyle: st } = p
  const fill = `fill="url(#${id}hair)" stroke="${dk}" stroke-opacity="0.5" stroke-width="0.8"`
  switch (st) {
    case 'long': {
      const d = `M${f1(CX - fw - v - 2)},${f1(ey - 20)} C${f1(CX - fw - v - 18)},${f1(ey + 50)} ${f1(CX - fw - v - 10)},246 ${f1(CX - fw - 2)},268 L${f1(CX + fw + 2)},268 C${f1(CX + fw + v + 10)},246 ${f1(CX + fw + v + 18)},${f1(ey + 50)} ${f1(CX + fw + v + 2)},${f1(ey - 20)} C${f1(CX + fw + v)},${f1(ty - 14)} ${f1(CX - fw - v)},${f1(ty - 14)} ${f1(CX - fw - v - 2)},${f1(ey - 20)} Z`
      c.defs.push(`<clipPath id="${id}hb"><path d="${d}"/></clipPath>`)
      return `<path d="${d}" ${fill}/>` + strands(c, `${id}hb`, ty, 266, fw + v + 6, 0, 11)
    }
    case 'bun': {
      const r = 15 + v * 0.7
      const cx = CX + p.part * 10
      const cy = ty - 8
      c.defs.push(`<clipPath id="${id}hb"><circle cx="${f1(cx)}" cy="${f1(cy)}" r="${f1(r)}"/></clipPath>`)
      return `<circle cx="${f1(cx)}" cy="${f1(cy)}" r="${f1(r)}" ${fill}/>` + strands(c, `${id}hb`, cy - r, cy + r, r * 0.9, 0, 7)
    }
    case 'ponytail': {
      const d = `M${f1(CX + fw - 4)},${f1(ty + 16)} C${f1(CX + fw + 38)},${f1(ty + 6)} ${f1(CX + fw + 42)},${f1(ey + 46)} ${f1(CX + fw + 18)},${f1(ey + 70)} C${f1(CX + fw + 22)},${f1(ey + 42)} ${f1(CX + fw + 10)},${f1(ey + 10)} ${f1(CX + fw - 8)},${f1(ey - 12)} Z`
      return `<path d="${d}" ${fill}/>` + `<path d="M${f1(CX + fw + 6)},${f1(ty + 22)} C${f1(CX + fw + 28)},${f1(ty + 30)} ${f1(CX + fw + 30)},${f1(ey + 30)} ${f1(CX + fw + 18)},${f1(ey + 62)}" fill="none" stroke="${dk}" stroke-width="0.9" opacity="0.35"/>`
    }
    case 'curly': {
      const n = 11
      const parts: string[] = []
      for (let i = 0; i < n; i++) {
        const a = Math.PI * (0.96 + (i / (n - 1)) * 1.08)
        const rr = 11 + v * 0.6 + Math.sin(i * 1.9) * 1.5
        parts.push(`<circle cx="${f1(CX + Math.cos(a) * (fw + 5))}" cy="${f1((ty + ey) / 2 + 4 + Math.sin(a) * ((ey - ty) / 2 + 12))}" r="${f1(rr)}" ${fill}/>`)
      }
      return parts.join('')
    }
    default:
      return ''
  }
}

function hairFront(c: Ctx): string {
  const { p, id } = c
  const sk = skOf(c)
  const { dk } = hairColors(c)
  const { fw, ty, ey, hairVol: v, hairLift: lift, part, hairStyle: st } = p
  const o: string[] = []

  if (st === 'bald') {
    const sidesD = (s: number) =>
      `M${f1(CX + s * (fw + 1))},${f1(ey - 22)} Q${f1(CX + s * (fw + 5))},${f1(ey - 6)} ${f1(CX + s * (fw - 1))},${f1(ey + 8)} L${f1(CX + s * (fw - 5))},${f1(ey - 8)} Z`
    for (const s of [-1, 1]) o.push(`<path d="${sidesD(s)}" fill="url(#${id}hair)" opacity="0.8"/>`)
    // 반들거리는 머리 윗부분
    o.push(`<g clip-path="url(#${id}face)"><ellipse cx="${f1(CX - fw * 0.2)}" cy="${f1(ty + 12)}" rx="${f1(fw * 0.45)}" ry="9" fill="#fff" opacity="0.2" filter="url(#${id}b2)"/></g>`)
    return o.join('')
  }

  const buzz = st === 'buzz'
  const top = ty - (buzz ? 1.5 : lift)
  const vol = buzz ? 1.2 : v
  const topCtrl = (top - 0.25 * (ey - 6)) / 0.75
  const sideEnd = ey - 6
  const fd = st === 'side' ? 12 : st === 'long' ? 5 : st === 'curly' ? 3 : st === 'ponytail' ? -7 : st === 'bun' ? -5 : 0
  const hlY = ty + (ey - ty) * p.hairlineF + (buzz ? 6 : 0)
  const shift = part * fw * (st === 'side' ? 1.1 : 0.5)
  const hlR = hlY + (shift > 0 ? 0 : fd)
  const hlL = hlY + (shift > 0 ? fd : 0)
  const Tr = { x: CX + fw * 0.8, y: hlR + 12 }
  const Tl = { x: CX - fw * 0.8, y: hlL + 12 }
  const Pp = { x: CX + shift, y: hlY - 2 + fd * 0.4 }
  const d =
    `M${f1(CX - fw - vol)},${f1(sideEnd)} ` +
    `C${f1(CX - fw - vol - 2)},${f1(topCtrl)} ${f1(CX + fw + vol + 2)},${f1(topCtrl)} ${f1(CX + fw + vol)},${f1(sideEnd)} ` +
    `L${f1(CX + fw - 3)},${f1(sideEnd + 2)} ` +
    `C${f1(CX + fw)},${f1(sideEnd - 16)} ${f1(CX + fw * 0.92)},${f1(Tr.y + 12)} ${f1(Tr.x)},${f1(Tr.y)} ` +
    `C${f1(Tr.x - 7)},${f1(Tr.y - 9)} ${f1(Pp.x + (Tr.x - Pp.x) * 0.5)},${f1(Pp.y + 1)} ${f1(Pp.x)},${f1(Pp.y)} ` +
    `C${f1(Pp.x - (Pp.x - Tl.x) * 0.45)},${f1(Pp.y + 1 + fd * 0.25)} ${f1(Tl.x + 7)},${f1(Tl.y - 9)} ${f1(Tl.x)},${f1(Tl.y)} ` +
    `C${f1(CX - fw * 0.92)},${f1(Tl.y + 12)} ${f1(CX - fw)},${f1(sideEnd - 16)} ${f1(CX - fw + 3)},${f1(sideEnd + 2)} Z`
  c.defs.push(`<clipPath id="${id}hf"><path d="${d}"/></clipPath>`)
  const fill = `fill="url(#${id}hair)" stroke="${dk}" stroke-opacity="0.5" stroke-width="0.8"`
  o.push(`<path d="${d}" ${fill}${buzz ? ' opacity="0.62"' : ''}/>`)
  if (!buzz) {
    o.push(strands(c, `${id}hf`, top, hlY + 6, fw + vol, shift, 10))
    // 이마 경계의 부드러운 그림자: 머리선이 이마에 자연스럽게 얹히게 한다
    o.push(
      `<g clip-path="url(#${id}face)"><path d="M${f1(Tl.x)},${f1(Tl.y + 1)} C${f1(Tl.x + 14)},${f1(Pp.y + 4 + fd * 0.25)} ${f1(Pp.x - 6)},${f1(Pp.y + 4)} ${f1(Pp.x)},${f1(Pp.y + 3)} C${f1(Pp.x + 10)},${f1(Pp.y + 5)} ${f1(Tr.x - 10)},${f1(Tr.y - 6)} ${f1(Tr.x)},${f1(Tr.y + 1)}" fill="none" stroke="${sk(-40, 8, -3)}" stroke-width="4" opacity="0.2" filter="url(#${id}b1)"/></g>`,
    )
  }
  if (st === 'curly') {
    for (let i = 0; i < 9; i++) {
      const a = Math.PI * (1.08 + (i / 8) * 0.84)
      const rr = 7 + v * 0.4 + Math.sin(i * 2.4) * 1.2
      o.push(`<circle cx="${f1(CX + Math.cos(a) * (fw * 0.95))}" cy="${f1(hlY - 6 + Math.sin(a) * 28 + 18)}" r="${f1(rr)}" ${fill}/>`)
    }
  }
  if (st === 'long') {
    // 얼굴 옆으로 흘러내리는 앞머리 가닥
    for (const s of [-1, 1]) {
      const jw = p.jw
      const lock =
        `M${f1(CX + s * (fw - 3))},${f1(sideEnd)} ` +
        `C${f1(CX + s * (fw + 1))},${f1(ey + 24)} ${f1(CX + s * (jw + 3))},192 ${f1(CX + s * (jw - 2))},232 ` +
        `C${f1(CX + s * (jw - 4))},246 ${f1(CX + s * (jw - 2))},254 ${f1(CX + s * (jw + 6))},262 ` +
        `C${f1(CX + s * (fw + v + 14))},248 ${f1(CX + s * (fw + v + 10))},${f1(ey + 30)} ${f1(CX + s * (fw + v))},${f1(sideEnd - 2)} Z`
      o.push(`<path d="${lock}" ${fill}/>`)
      o.push(`<path d="M${f1(CX + s * (fw + 2))},${f1(ey - 2)} C${f1(CX + s * (fw + 6))},${f1(ey + 40)} ${f1(CX + s * (jw + 8))},210 ${f1(CX + s * (jw + 6))},256" fill="none" stroke="${dk}" stroke-width="0.9" opacity="0.35"/>`)
    }
  }
  if (st === 'ponytail') {
    o.push(`<ellipse cx="${f1(CX + fw + 1)}" cy="${f1(ty + 18)}" rx="4.5" ry="6" fill="${hsl(p.accentH, 40, 42)}" opacity="0.95"/>`)
  }
  return o.join('')
}

// ---------------------------------------------------------------- 옷
function outfitSvg(outfit: string | undefined, c: Ctx): string {
  const { p, id } = c
  const sk = skOf(c)
  const sw = p.shoulder
  const nw = p.neckW
  const nx = nw + 7
  const bodyD = `M${f1(CX - sw)},300 L${f1(CX - sw)},276 C${f1(CX - sw)},256 ${f1(CX - nx - 34)},242 ${f1(CX - nx)},238 L${f1(CX + nx)},238 C${f1(CX + nx + 34)},242 ${f1(CX + sw)},256 ${f1(CX + sw)},276 L${f1(CX + sw)},300 Z`
  const known = (OUTFITS as readonly string[]).includes(outfit ?? '')
  const kind = (known ? outfit : 'casual') as Outfit
  const main = (dh = 0, ds = 0, dl = 0) => hsl(p.outfitH + dh, clamp(p.outfitS + ds, 5, 70), clamp(p.outfitL + dl, 8, 94))
  const accent = hsl(p.accentH, 45, 46)
  const ln = `stroke="${EDGE}" stroke-width="0.9" stroke-linejoin="round"`
  const paint = (fill: string) => `fill="${fill}" ${ln}`
  const neckHole = `<path d="M${f1(CX - nx + 1)},238 Q${f1(CX)},${f1(262 + nw * 0.3)} ${f1(CX + nx - 1)},238 Z" fill="${sk(-14, 4)}" ${ln}/>`
  const o: string[] = []

  switch (kind) {
    case 'suit': {
      const jacket = hsl(p.outfitH, 12, 22 + p.outfitL * 0.22)
      o.push(`<path d="${bodyD}" ${paint(jacket)}/>`)
      o.push(`<path d="M${f1(CX - nx)},238 L${f1(CX + nx)},238 L${f1(CX)},292 Z" fill="#eceae6" ${ln}/>`)
      o.push(`<path d="M${f1(CX - nx + 1)},238 L${f1(CX - 4)},296 L${f1(CX - 36)},300 L${f1(CX - nx - 20)},262 Z" ${paint(hsl(p.outfitH, 12, 27 + p.outfitL * 0.22))}/>`)
      o.push(`<path d="M${f1(CX + nx - 1)},238 L${f1(CX + 4)},296 L${f1(CX + 36)},300 L${f1(CX + nx + 20)},262 Z" ${paint(hsl(p.outfitH, 12, 27 + p.outfitL * 0.22))}/>`)
      o.push(`<path d="M${f1(CX - 4.5)},246 L${f1(CX + 4.5)},246 L${f1(CX + 6)},286 L${f1(CX)},294 L${f1(CX - 6)},286 Z" ${paint(accent)}/>`)
      break
    }
    case 'hoodie': {
      const col = main(0, 0, 4)
      o.push(`<path d="${bodyD}" ${paint(col)}/>`)
      o.push(`<path d="M${f1(CX - nx - 8)},242 Q${f1(CX)},222 ${f1(CX + nx + 8)},242 L${f1(CX + nx + 2)},268 Q${f1(CX)},252 ${f1(CX - nx - 2)},268 Z" ${paint(main(0, 0, -6))}/>`)
      o.push(`<path d="M${f1(CX - 10)},258 L${f1(CX - 12)},292 M${f1(CX + 10)},258 L${f1(CX + 12)},292" stroke="#e8e4dc" stroke-width="2" stroke-linecap="round"/>`)
      o.push(`<path d="M${f1(CX - 40)},300 L${f1(CX - 34)},284 L${f1(CX + 34)},284 L${f1(CX + 40)},300" fill="none" ${ln}/>`)
      break
    }
    case 'cleaner_uniform': {
      const col = hsl(190 + (p.outfitH % 30), 22, 44)
      o.push(`<path d="${bodyD}" ${paint(col)}/>`)
      o.push(neckHole)
      o.push(`<path d="M${f1(CX - nx)},238 L${f1(CX)},272 L${f1(CX - 4)},300 L${f1(CX - 30)},300 Z" ${paint(hsl(190, 20, 38))}/>`)
      o.push(`<path d="M${f1(CX + nx)},238 L${f1(CX)},272 L${f1(CX + 4)},300 L${f1(CX + 30)},300 Z" ${paint(hsl(190, 20, 38))}/>`)
      o.push(`<rect x="${CX + 22}" y="274" width="22" height="12" rx="2" fill="#eceae6" ${ln}/>`)
      break
    }
    case 'security_uniform': {
      o.push(`<path d="${bodyD}" ${paint(hsl(218, 26, 23))}/>`)
      o.push(`<path d="M${f1(CX - 22)},238 L${f1(CX + 22)},238 L${f1(CX)},280 Z" fill="#c9d6e4" ${ln}/>`)
      o.push(`<path d="M${f1(CX - 4)},250 L${f1(CX + 4)},250 L${f1(CX + 5)},290 L${f1(CX)},294 L${f1(CX - 5)},290 Z" fill="#14161b"/>`)
      o.push(`<rect x="${CX - sw + 12}" y="248" width="26" height="9" rx="2" ${paint('#b99a3c')}/>`)
      o.push(`<rect x="${CX + sw - 38}" y="248" width="26" height="9" rx="2" ${paint('#b99a3c')}/>`)
      o.push(`<path d="M${f1(CX + 28)},268 l9,0 l0,12 l-4.5,5 l-4.5,-5 Z" ${paint('#c9a63c')}/>`)
      break
    }
    case 'chef': {
      o.push(`<path d="${bodyD}" ${paint('#f2f1ed')}/>`)
      o.push(neckHole)
      o.push(`<path d="M${f1(CX)},262 L${f1(CX)},300" stroke="${EDGE}" stroke-width="1"/>`)
      for (const dy of [272, 288]) {
        o.push(`<circle cx="${CX - 9}" cy="${dy}" r="2.4" fill="#d6d3cc" ${ln}/><circle cx="${CX + 9}" cy="${dy}" r="2.4" fill="#d6d3cc" ${ln}/>`)
      }
      o.push(`<path d="M${f1(CX - nx)},240 Q${f1(CX)},262 ${f1(CX + nx)},240 L${f1(CX + 8)},256 L${f1(CX - 8)},256 Z" ${paint(accent)}/>`)
      break
    }
    case 'doctor': {
      o.push(`<path d="${bodyD}" ${paint(hsl(176, 32, 52))}/>`)
      o.push(`<path d="M${f1(CX - nx)},238 L${f1(CX - 6)},300 L${f1(CX - sw)},300 L${f1(CX - sw)},276 C${f1(CX - sw)},256 ${f1(CX - nx - 34)},242 ${f1(CX - nx)},238 Z" ${paint('#f4f4f0')}/>`)
      o.push(`<path d="M${f1(CX + nx)},238 L${f1(CX + 6)},300 L${f1(CX + sw)},300 L${f1(CX + sw)},276 C${f1(CX + sw)},256 ${f1(CX + nx + 34)},242 ${f1(CX + nx)},238 Z" ${paint('#f4f4f0')}/>`)
      o.push(`<path d="M${f1(CX - 26)},246 C${f1(CX - 30)},290 ${f1(CX + 30)},290 ${f1(CX + 26)},246" fill="none" stroke="#3c4048" stroke-width="2"/><circle cx="${CX + 8}" cy="288" r="4" fill="#9aa3b2" ${ln}/>`)
      break
    }
    case 'delivery': {
      o.push(`<path d="${bodyD}" ${paint(hsl(210, 12, 27))}/>`)
      o.push(`<path d="M${f1(CX - nx)},238 L${f1(CX - 16)},300 L${f1(CX - sw)},300 L${f1(CX - sw)},276 C${f1(CX - sw)},256 ${f1(CX - nx - 34)},242 ${f1(CX - nx)},238 Z" ${paint('#d9822a')}/>`)
      o.push(`<path d="M${f1(CX + nx)},238 L${f1(CX + 16)},300 L${f1(CX + sw)},300 L${f1(CX + sw)},276 C${f1(CX + sw)},256 ${f1(CX + nx + 34)},242 ${f1(CX + nx)},238 Z" ${paint('#d9822a')}/>`)
      o.push(`<path d="M${f1(CX - sw + 4)},284 L${f1(CX - 20)},284 M${f1(CX + 20)},284 L${f1(CX + sw - 4)},284" stroke="#e8e4dc" stroke-width="4"/>`)
      break
    }
    case 'school_uniform': {
      o.push(`<path d="${bodyD}" ${paint(hsl(222, 28, 25))}/>`)
      o.push(`<path d="M${f1(CX - 22)},238 L${f1(CX + 22)},238 L${f1(CX)},284 Z" fill="#eceae6" ${ln}/>`)
      o.push(`<path d="M${f1(CX - 8)},256 L${f1(CX)},262 L${f1(CX + 8)},256 L${f1(CX + 8)},268 L${f1(CX)},262 L${f1(CX - 8)},268 Z" ${paint('#b3433b')}/>`)
      o.push(`<path d="M${f1(CX - nx)},238 L${f1(CX - 3)},290 L${f1(CX - 34)},300 L${f1(CX - 44)},264 Z" ${paint(hsl(222, 28, 31))}/>`)
      o.push(`<path d="M${f1(CX + nx)},238 L${f1(CX + 3)},290 L${f1(CX + 34)},300 L${f1(CX + 44)},264 Z" ${paint(hsl(222, 28, 31))}/>`)
      break
    }
    case 'work_clothes': {
      o.push(`<path d="${bodyD}" ${paint(hsl(40 + (p.outfitH % 20), 24, 44))}/>`)
      o.push(neckHole)
      o.push(`<path d="M${f1(CX - nx - 2)},238 L${f1(CX - 4)},266 L${f1(CX - 28)},262 Z M${f1(CX + nx + 2)},238 L${f1(CX + 4)},266 L${f1(CX + 28)},262 Z" ${paint(hsl(40, 22, 38))}/>`)
      o.push(`<rect x="${CX - 52}" y="276" width="26" height="22" rx="2" fill="none" ${ln}/><rect x="${CX + 26}" y="276" width="26" height="22" rx="2" fill="none" ${ln}/>`)
      break
    }
    case 'office_lanyard': {
      o.push(`<path d="${bodyD}" ${paint(main(0, -4, 12))}/>`)
      o.push(`<path d="M${f1(CX - 22)},238 L${f1(CX + 22)},238 L${f1(CX)},272 Z" fill="#eceae6" ${ln}/>`)
      o.push(`<path d="M${f1(CX - 14)},240 L${f1(CX - 4)},300 M${f1(CX + 14)},240 L${f1(CX + 4)},300" stroke="${accent}" stroke-width="2.6" fill="none"/>`)
      o.push(`<rect x="${CX - 14}" y="274" width="28" height="22" rx="3" fill="#f4f2ee" ${ln}/><circle cx="${CX}" cy="282" r="4" fill="${accent}"/><path d="M${f1(CX - 8)},290 L${f1(CX + 8)},290" stroke="#6b6f78" stroke-width="1.2"/>`)
      break
    }
    case 'casual':
    default: {
      o.push(`<path d="${bodyD}" ${paint(main())}/>`)
      o.push(`<path d="M${f1(CX - nx + 1)},238 Q${f1(CX)},${f1(262 + nw * 0.3)} ${f1(CX + nx - 1)},238 Z" fill="${sk(-14, 4)}" ${ln}/>`)
      o.push(`<path d="M${f1(CX - nx + 1)},238 Q${f1(CX)},${f1(262 + nw * 0.3)} ${f1(CX + nx - 1)},238" fill="none" stroke="${main(0, 0, -10)}" stroke-width="3"/>`)
    }
  }

  // 천의 주름과 명암: 왼쪽 위에서 빛, 오른쪽·아래·목 밑이 어둡다
  c.defs.push(
    `<linearGradient id="${id}bsh" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#000" stop-opacity="0"/><stop offset="0.5" stop-color="#000" stop-opacity="0.05"/><stop offset="1" stop-color="#000" stop-opacity="0.3"/></linearGradient>`,
    `<linearGradient id="${id}bv" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#000" stop-opacity="0.34"/><stop offset="0.3" stop-color="#000" stop-opacity="0.04"/><stop offset="1" stop-color="#000" stop-opacity="0.16"/></linearGradient>`,
    `<clipPath id="${id}body"><path d="${bodyD}"/></clipPath>`,
  )
  o.push(
    `<g clip-path="url(#${id}body)">`,
    `<rect x="${CX - sw}" y="236" width="${sw * 2}" height="66" fill="url(#${id}bsh)"/>`,
    `<rect x="${CX - sw}" y="236" width="${sw * 2}" height="66" fill="url(#${id}bv)"/>`,
    `<path d="M${f1(CX - sw + 8)},292 Q${f1(CX - sw + 30)},272 ${f1(CX - sw + 58)},262" fill="none" stroke="#000" stroke-width="3" opacity="0.1" filter="url(#${id}b1)"/>`,
    `<path d="M${f1(CX + sw - 8)},292 Q${f1(CX + sw - 30)},272 ${f1(CX + sw - 58)},262" fill="none" stroke="#000" stroke-width="3" opacity="0.14" filter="url(#${id}b1)"/>`,
    `<path d="M${f1(CX - sw + 14)},256 Q${f1(CX - sw + 40)},250 ${f1(CX - nx - 14)},244" fill="none" stroke="#fff" stroke-width="3" opacity="0.1" filter="url(#${id}b1)"/>`,
    `<ellipse cx="${f1(CX + 2)}" cy="240" rx="${f1(nw + 6)}" ry="8" fill="#000" opacity="0.18" filter="url(#${id}b2)"/>`,
    `</g>`,
  )
  return o.join('')
}

// ---------------------------------------------------------------- 소품
function accessorySvg(acc: string | undefined, c: Ctx): string {
  const { p } = c
  const sw = p.shoulder
  const ln = `stroke="${EDGE}" stroke-width="0.9" stroke-linejoin="round"`
  switch (acc) {
    case 'glasses': {
      const rw = p.eyeW + 5
      const rh = p.eyeH + 6
      const y = p.ey - 0.5
      const frame = hsl(p.accentH, 10, 16)
      const gl = (s: number) =>
        `<rect x="${f1(CX + s * p.eyeGap - rw)}" y="${f1(y - rh * 0.55)}" width="${f1(rw * 2)}" height="${f1(rh * 1.5)}" rx="${f1(rh * 0.5)}" fill="#dfeaf2" fill-opacity="0.16" stroke="${frame}" stroke-width="1.5"/>` +
        `<path d="M${f1(CX + s * p.eyeGap - rw * 0.7)},${f1(y - rh * 0.3)} L${f1(CX + s * p.eyeGap - rw * 0.2)},${f1(y - rh * 0.3)}" stroke="#fff" stroke-width="1.4" stroke-linecap="round" opacity="0.5"/>`
      return (
        gl(-1) + gl(1) +
        `<path d="M${f1(CX - p.eyeGap + rw)},${f1(y)} Q${f1(CX)},${f1(y - 3)} ${f1(CX + p.eyeGap - rw)},${f1(y)}" fill="none" stroke="${frame}" stroke-width="1.4"/>` +
        `<path d="M${f1(CX - p.eyeGap - rw)},${f1(y - 1)} L${f1(CX - p.fw + 1)},${f1(y + 1)} M${f1(CX + p.eyeGap + rw)},${f1(y - 1)} L${f1(CX + p.fw - 1)},${f1(y + 1)}" stroke="${frame}" stroke-width="1.4"/>`
      )
    }
    case 'cap': {
      const col = hsl(p.accentH, 36, 36)
      const crownTop = p.ty - 16
      const bY = p.ey - 24
      return (
        `<path d="M${f1(CX - p.fw - 3)},${f1(bY)} C${f1(CX - p.fw - 4)},${f1(crownTop + 2)} ${f1(CX + p.fw + 4)},${f1(crownTop + 2)} ${f1(CX + p.fw + 3)},${f1(bY)} Z" fill="${col}" ${ln}/>` +
        `<path d="M${f1(CX - p.fw - 3)},${f1(bY)} C${f1(CX - 12)},${f1(bY + 10)} ${f1(CX + 12)},${f1(bY + 10)} ${f1(CX + p.fw + 3)},${f1(bY)} C${f1(CX + 20)},${f1(bY - 5)} ${f1(CX - 20)},${f1(bY - 5)} ${f1(CX - p.fw - 3)},${f1(bY)} Z" fill="${hsl(p.accentH, 36, 28)}" ${ln}/>` +
        `<path d="M${f1(CX - p.fw * 0.5)},${f1(crownTop + 6)} Q${f1(CX - p.fw * 0.2)},${f1(crownTop + 2)} ${f1(CX + 4)},${f1(crownTop + 8)}" fill="none" stroke="#fff" stroke-width="3" opacity="0.12"/>`
      )
    }
    case 'badge':
      return `<path d="M${f1(CX - sw + 24)},262 l16,0 l0,18 l-8,8 l-8,-8 Z" fill="#c9a63c" ${ln}/><circle cx="${f1(CX - sw + 32)}" cy="270" r="3" fill="#f2e4a8"/>`
    case 'mop':
      return (
        `<path d="M${f1(CX + sw + 6)},120 L${f1(CX + sw - 22)},300" stroke="#8a6a43" stroke-width="5" stroke-linecap="round"/>` +
        `<path d="M${f1(CX + sw - 8)},108 Q${f1(CX + sw + 6)},96 ${f1(CX + sw + 20)},108 L${f1(CX + sw + 26)},140 L${f1(CX + sw - 12)},138 Z" fill="#c4c8ce" ${ln}/>` +
        `<path d="M${f1(CX + sw - 2)},112 L${f1(CX + sw - 4)},136 M${f1(CX + sw + 8)},108 L${f1(CX + sw + 8)},138 M${f1(CX + sw + 18)},112 L${f1(CX + sw + 20)},138" stroke="#2a2e36" stroke-width="1" opacity="0.4"/>`
      )
    case 'radio':
      return (
        `<rect x="${f1(CX + sw - 52)}" y="256" width="24" height="34" rx="4" fill="#2b2f37" ${ln}/>` +
        `<path d="M${f1(CX + sw - 34)},256 L${f1(CX + sw - 34)},228" stroke="#2b2f37" stroke-width="3" stroke-linecap="round"/>` +
        `<circle cx="${f1(CX + sw - 40)}" cy="268" r="4" fill="#9aa3b2"/><path d="M${f1(CX + sw - 46)},280 l12,0 m-12,4 l12,0" stroke="#9aa3b2" stroke-width="1.4"/>`
      )
    case 'laptop':
      return (
        `<path d="M${f1(CX - 54)},300 L${f1(CX - 48)},264 L${f1(CX + 48)},264 L${f1(CX + 54)},300 Z" fill="#a8b0be" ${ln}/>` +
        `<path d="M${f1(CX - 54)},300 L${f1(CX - 48)},264 L${f1(CX + 48)},264 L${f1(CX + 54)},300 Z" fill="url(#${c.id}bsh)"/>` +
        `<circle cx="${CX}" cy="281" r="5" fill="#dfe3ea" ${ln}/>`
      )
    case 'apron':
      return (
        `<path d="M${f1(CX - 36)},258 L${f1(CX + 36)},258 L${f1(CX + 44)},300 L${f1(CX - 44)},300 Z" fill="${hsl(p.accentH, 22, 78)}" ${ln}/>` +
        `<path d="M${f1(CX - 30)},258 L${f1(CX - p.neckW)},240 M${f1(CX + 30)},258 L${f1(CX + p.neckW)},240" stroke="${EDGE}" stroke-width="1.6" fill="none"/>`
      )
    default:
      return ''
  }
}

// ---------------------------------------------------------------- 감정 효과 (이모지·땀방울)
function effectSvg(emotion: Emotion, p: FaceParams): string {
  const x = CX + p.fw - 2
  const y = p.ty + 14
  const emojiFont = `font-family="'Apple Color Emoji','Segoe UI Emoji','Noto Color Emoji',sans-serif"`
  switch (emotion) {
    case 'flustered':
      return `<text x="${f1(x)}" y="${f1(y)}" font-size="28" text-anchor="middle" ${emojiFont}>💦</text>`
    case 'angry':
      return `<text x="${f1(x)}" y="${f1(y)}" font-size="28" text-anchor="middle" ${emojiFont}>💢</text>`
    case 'nervous':
      return `<path d="M${f1(CX + p.fw - 9)},${f1(p.ey - 22)} q4.5,8 0,12.5 q-4.5,-4.5 0,-12.5 Z" fill="#cde6f6" stroke="rgba(40,70,100,0.35)" stroke-width="0.7" opacity="0.85"/>`
    default:
      return ''
  }
}

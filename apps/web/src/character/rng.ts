// 시드 기반 결정적 난수. 같은 시드는 항상 같은 수열을 낸다.

export function mulberry32(seed: number): () => number {
  let a = seed >>> 0
  return () => {
    a = (a + 0x6d2b79f5) >>> 0
    let t = a
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

/** 이웃한 시드(1, 2, 3…)도 서로 멀리 떨어진 수열이 되도록 시드를 한 번 섞는다. */
export function scramble(seed: number): number {
  let h = (Math.floor(seed) | 0) ^ 0x9e3779b9
  h = Math.imul(h ^ (h >>> 16), 0x85ebca6b)
  h = Math.imul(h ^ (h >>> 13), 0xc2b2ae35)
  return (h ^ (h >>> 16)) >>> 0
}

export function seededRng(seed: number): () => number {
  return mulberry32(scramble(seed))
}

export const lerp = (a: number, b: number, t: number) => a + (b - a) * t
export const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v))

// 장소 노드 + 연결선 자동 배치. AI 가 장소와 연결 정보만 주면 코드가 그린다.
// 결정적(같은 입력 -> 같은 배치): 시작 위치는 BFS 순서로 원 위에 놓고, 스프링-반발 반복으로 다듬는다.
export interface LayoutNode {
  id: string
  x: number
  y: number
}

export function layoutGraph(
  ids: string[],
  edges: [string, string][],
  width: number,
  height: number,
  margin: { x: number; y: number },
): LayoutNode[] {
  const n = ids.length
  if (n === 0) return []
  if (n === 1) return [{ id: ids[0], x: width / 2, y: height / 2 }]

  const index = new Map(ids.map((id, i) => [id, i]))
  const adj: number[][] = ids.map(() => [])
  const uniq = new Set<string>()
  const E: [number, number][] = []
  for (const [a, b] of edges) {
    const i = index.get(a)
    const j = index.get(b)
    if (i === undefined || j === undefined || i === j) continue
    const key = i < j ? `${i}-${j}` : `${j}-${i}`
    if (uniq.has(key)) continue
    uniq.add(key)
    E.push([i, j])
    adj[i].push(j)
    adj[j].push(i)
  }

  // BFS 순서(연결되지 않은 노드는 뒤에 붙임)
  const order: number[] = []
  const seen = new Array(n).fill(false)
  for (let s = 0; s < n; s++) {
    if (seen[s]) continue
    const q = [s]
    seen[s] = true
    while (q.length) {
      const u = q.shift()!
      order.push(u)
      for (const v of adj[u]) if (!seen[v]) { seen[v] = true; q.push(v) }
    }
  }

  const pos = new Array(n)
  order.forEach((node, k) => {
    const a = (k / n) * Math.PI * 2 - Math.PI / 2
    pos[node] = [Math.cos(a) * 100, Math.sin(a) * 100 * (height / width) * 1.4]
  })

  const kk = 90
  for (let it = 0; it < 300; it++) {
    const t = 1 - it / 300
    const disp = pos.map(() => [0, 0])
    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        let dx = pos[i][0] - pos[j][0]
        let dy = pos[i][1] - pos[j][1]
        let d = Math.hypot(dx, dy)
        if (d < 0.01) { dx = 0.01 * (i - j); dy = 0.01; d = 0.02 }
        const f = (kk * kk) / d
        disp[i][0] += (dx / d) * f; disp[i][1] += (dy / d) * f
        disp[j][0] -= (dx / d) * f; disp[j][1] -= (dy / d) * f
      }
    }
    for (const [i, j] of E) {
      const dx = pos[i][0] - pos[j][0]
      const dy = pos[i][1] - pos[j][1]
      const d = Math.hypot(dx, dy) || 0.01
      const f = (d * d) / kk
      disp[i][0] -= (dx / d) * f; disp[i][1] -= (dy / d) * f
      disp[j][0] += (dx / d) * f; disp[j][1] += (dy / d) * f
    }
    for (let i = 0; i < n; i++) {
      const d = Math.hypot(disp[i][0], disp[i][1]) || 1
      const step = Math.min(d, 20 * t + 1)
      pos[i][0] += (disp[i][0] / d) * step
      pos[i][1] += (disp[i][1] / d) * step
    }
  }

  // 화면에 맞게 확대/축소
  const xs = pos.map((p: number[]) => p[0])
  const ys = pos.map((p: number[]) => p[1])
  const minX = Math.min(...xs), maxX = Math.max(...xs)
  const minY = Math.min(...ys), maxY = Math.max(...ys)
  const sx = maxX - minX || 1
  const sy = maxY - minY || 1
  const iw = width - margin.x * 2
  const ih = height - margin.y * 2
  return ids.map((id, i) => ({
    id,
    x: margin.x + ((pos[i][0] - minX) / sx) * iw,
    y: margin.y + ((pos[i][1] - minY) / sy) * ih,
  }))
}

/** 배치된 칸(폭 nw, 높이 nh)이 겹치면 겹친 만큼 서로 밀어내고 화면 안에 가둔다. 결정적. gap 은 칸 사이 최소 여백. */
export function separateBoxes(nodes: LayoutNode[], width: number, height: number, nw: number, nh: number, gap = 6): LayoutNode[] {
  const p = nodes.map((n) => ({ ...n }))
  const minX = nw / 2 + 2
  const maxX = width - nw / 2 - 2
  const minY = nh / 2 + 2
  const maxY = height - nh / 2 - 2
  for (let it = 0; it < 60; it++) {
    let moved = false
    for (let i = 0; i < p.length; i++) {
      for (let j = i + 1; j < p.length; j++) {
        const ox = nw + gap - Math.abs(p[i].x - p[j].x)
        const oy = nh + gap - Math.abs(p[i].y - p[j].y)
        if (ox <= 0 || oy <= 0) continue
        moved = true
        // 덜 겹친 방향으로 반씩 민다(같은 자리면 순서로 방향을 정한다)
        if (ox < oy) {
          const s = p[i].x < p[j].x || (p[i].x === p[j].x && i < j) ? -1 : 1
          p[i].x += (s * ox) / 2
          p[j].x -= (s * ox) / 2
        } else {
          const s = p[i].y < p[j].y || (p[i].y === p[j].y && i < j) ? -1 : 1
          p[i].y += (s * oy) / 2
          p[j].y -= (s * oy) / 2
        }
      }
    }
    for (const n of p) {
      n.x = Math.min(maxX, Math.max(minX, n.x))
      n.y = Math.min(maxY, Math.max(minY, n.y))
    }
    if (!moved) break
  }
  return p
}

/** 글자 폭 어림(em): 한글 1, 공백·가운뎃점 0.35, 그 밖(영문·숫자) 0.6. */
function emWidth(s: string): number {
  let w = 0
  for (const ch of s) w += /[가-힣]/.test(ch) ? 1 : /[\s·]/.test(ch) ? 0.35 : 0.6
  return w
}

/** 지도 칸 이름을 칸 안에 맞춘다: 12px로 들어가면 한 줄, 아니면 10.5px, 그래도 길면
 * 가운데에 가장 가까운 가운뎃점·띄어쓰기에서 두 줄("1층 로비·" / "보안데스크"). maxW는 쓸 수 있는 폭(px). */
export function fitLabel(name: string, maxW: number): { lines: string[]; size: number } {
  const w = emWidth(name)
  if (w * 12 <= maxW) return { lines: [name], size: 12 }
  if (w * 10.5 <= maxW) return { lines: [name], size: 10.5 }
  const chars = [...name]
  const cuts = chars.map((ch, i) => (ch === '·' || ch === ' ' ? i : -1)).filter((i) => i > 0 && i < chars.length - 1)
  const mid = chars.length / 2
  let first: string
  let second: string
  if (cuts.length) {
    const at = cuts.reduce((a, b) => (Math.abs(b - mid) < Math.abs(a - mid) ? b : a))
    first = chars.slice(0, chars[at] === '·' ? at + 1 : at).join('').trim()
    second = chars.slice(at + 1).join('').trim()
  } else {
    // 띄어쓰기도 가운뎃점도 없으면 글자 가운데에서 나눈다
    first = chars.slice(0, Math.ceil(mid)).join('')
    second = chars.slice(Math.ceil(mid)).join('')
  }
  const size = Math.min(10.5, Math.max(8, Math.floor((maxW / Math.max(emWidth(first), emWidth(second))) * 2) / 2))
  return { lines: [first, second], size }
}

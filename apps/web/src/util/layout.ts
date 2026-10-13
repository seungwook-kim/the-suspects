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

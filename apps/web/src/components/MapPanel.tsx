import { useMemo } from 'react'
import type { PlayerView } from '../api/types'
import { layoutGraph } from '../util/layout'

const W = 270
const H = 330
const NW = 100
const NH = 50

export function dotColor(seed: number): string {
  // 인물 점 색: 얼굴 시드에서만 정한다(사건 정보와 무관).
  return `hsl(${(Math.abs(seed) * 47) % 360}, 48%, 72%)`
}

interface Props {
  view: PlayerView
  interrogeeId: string | null
  locked?: boolean
  onMove: (locationId: string) => void
  onTalk: (npcId: string) => void
}

export function MapPanel({ view, interrogeeId, locked, onMove, onTalk }: Props) {
  const ids = view.locations.map((l) => l.id)
  const edges = useMemo(() => {
    const e: [string, string][] = []
    for (const l of view.locations) for (const c of l.connections) e.push([l.id, c])
    return e
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view.locations.map((l) => `${l.id}:${l.connections.join(',')}`).join('|')])
  const pos = useMemo(
    () => new Map(layoutGraph(ids, edges, W, H, { x: NW / 2 + 6, y: NH / 2 + 8 }).map((n) => [n.id, n])),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [ids.join('|'), edges],
  )
  const here = view.locations.find((l) => l.id === view.player_location)
  const reachable = new Set<string>(here?.connections ?? [])
  for (const l of view.locations) if (l.connections.includes(view.player_location)) reachable.add(l.id)

  return (
    <svg className="map" viewBox={`0 0 ${W} ${H}`} role="group" aria-label="지도">
      {edges.map(([a, b], i) => {
        const pa = pos.get(a)
        const pb = pos.get(b)
        if (!pa || !pb) return null
        const hot = a === view.player_location || b === view.player_location
        return <line key={i} x1={pa.x} y1={pa.y} x2={pb.x} y2={pb.y} className={hot ? 'edge hot' : 'edge'} />
      })}
      {view.locations.map((l) => {
        const p = pos.get(l.id)
        if (!p) return null
        const isHere = l.id === view.player_location
        const can = reachable.has(l.id)
        const people = view.characters.filter((c) => c.location_id === l.id)
        return (
          <g
            key={l.id}
            transform={`translate(${p.x - NW / 2},${p.y - NH / 2})`}
            className={`node${isHere ? ' here' : ''}${can ? ' can' : ''}${locked ? ' locked' : ''}`}
          >
            <rect
              width={NW}
              height={NH}
              rx={9}
              onClick={() => !locked && can && onMove(l.id)}
              tabIndex={can && !locked ? 0 : -1}
              role="button"
              aria-label={`${l.name}${isHere ? ' (현재 위치)' : can ? ' 으로 이동' : ''}`}
              onKeyDown={(e) => e.key === 'Enter' && !locked && can && onMove(l.id)}
            />
            <text x={NW / 2} y={19} textAnchor="middle" className="node-name" pointerEvents="none">
              {l.name}
            </text>
            {isHere && (
              <text x={8} y={14} className="node-pin" pointerEvents="none">
                📍
              </text>
            )}
            {people.map((c, i) => {
              const x = NW / 2 - ((people.length - 1) * 21) / 2 + i * 21
              const talkable = isHere && !locked
              return (
                <g
                  key={c.id}
                  className={`dot${interrogeeId === c.id ? ' active' : ''}${talkable ? ' talk' : ''}`}
                  transform={`translate(${x},35)`}
                  onClick={(ev) => {
                    ev.stopPropagation()
                    if (locked) return
                    if (isHere) onTalk(c.id)
                    else if (can) onMove(l.id)
                  }}
                >
                  <title>{`${c.name} (${c.role})`}</title>
                  <circle r={9} fill={dotColor(c.face_seed)} />
                  <text textAnchor="middle" y={4} className="dot-text" pointerEvents="none">
                    {[...c.name][0]}
                  </text>
                </g>
              )
            })}
          </g>
        )
      })}
    </svg>
  )
}

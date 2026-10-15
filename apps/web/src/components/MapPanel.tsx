import { useMemo } from 'react'
import type { PlayerView } from '../api/types'
import { fitLabel, layoutGraph, separateBoxes } from '../util/layout'

const W = 270
const H = 400
const NW = 100
const NH = 50
const LABEL_W = NW - 28 // 칸 이름이 쓸 수 있는 폭(오른쪽 위 '처음 가는 곳' 점과 겹치지 않게)

interface Props {
  view: PlayerView
  interrogeeId: string | null
  locked?: boolean
  onMove: (locationId: string) => void
  onTalk: (npcId: string) => void
}

/** 지도: 장소 칸과 이어진 길. 현재 위치는 굵은 잉크 테두리, 지금 갈 수 있는 곳은 실선, 거쳐야 하는 곳은 점선(색 없이 모양으로 구별).
 * 아직 안 가 본 곳은 오른쪽 위 작은 점: 처음 갈 때만 행동을 쓴다. */
export function MapPanel({ view, interrogeeId, locked, onMove, onTalk }: Props) {
  const ids = view.locations.map((l) => l.id)
  const edges = useMemo(() => {
    const e: [string, string][] = []
    for (const l of view.locations) for (const c of l.connections) e.push([l.id, c])
    return e
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view.locations.map((l) => `${l.id}:${l.connections.join(',')}`).join('|')])
  const pos = useMemo(
    () => new Map(separateBoxes(layoutGraph(ids, edges, W, H, { x: NW / 2 + 6, y: NH / 2 + 8 }), W, H, NW, NH).map((n) => [n.id, n])),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [ids.join('|'), edges],
  )
  const here = view.locations.find((l) => l.id === view.player_location)
  const visited = new Set(view.visited_locations ?? [view.player_location])
  const reachable = new Set<string>(here?.connections ?? [])
  for (const l of view.locations) if (l.connections.includes(view.player_location)) reachable.add(l.id)

  return (
    <div className="map-wrap">
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
          const fresh = !visited.has(l.id)
          const people = view.characters.filter((c) => c.location_id === l.id)
          const label = fitLabel(l.name, LABEL_W)
          const two = label.lines.length > 1
          return (
            <g
              key={l.id}
              transform={`translate(${p.x - NW / 2},${p.y - NH / 2})`}
              className={`node${isHere ? ' here' : can ? ' can' : ' far'}${locked ? ' locked' : ''}`}
            >
              <rect
                width={NW}
                height={NH}
                rx={6}
                onClick={() => !locked && can && onMove(l.id)}
                tabIndex={can && !locked ? 0 : -1}
                role="button"
                aria-label={`${l.name}${isHere ? ' (현재 위치)' : can ? (fresh ? ', 이동 (처음 가는 곳, 행동 1)' : ', 이동 (가 본 곳, 행동 없음)') : ', 다른 장소를 거쳐야 함'}`}
                onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && !locked && can && onMove(l.id)}
              />
              <text x={NW / 2} y={two ? 13 : 19} textAnchor="middle" className="node-name" style={{ fontSize: label.size }} pointerEvents="none">
                {label.lines.map((line, i) => (
                  <tspan key={i} x={NW / 2} dy={i ? label.size * 1.1 : 0}>{line}</tspan>
                ))}
              </text>
              {fresh && <circle cx={NW - 9} cy={9} r={3.5} className="node-fresh" pointerEvents="none" />}
              {people.map((c, i) => {
                const x = NW / 2 - ((people.length - 1) * 21) / 2 + i * 21
                const talkable = isHere && !locked
                return (
                  <g
                    key={c.id}
                    className={`dot${interrogeeId === c.id ? ' active' : ''}${talkable ? ' talk' : ''}`}
                    transform={`translate(${x},${two ? 37 : 35})`}
                    onClick={(ev) => {
                      ev.stopPropagation()
                      if (locked) return
                      if (isHere) onTalk(c.id)
                      else if (can) onMove(l.id)
                    }}
                  >
                    <title>{`${c.name} (${c.role})`}</title>
                    <circle r={9} />
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
      <ul className="map-legend" aria-label="범례">
        <li><span className="sw sw-here" />현재 위치</li>
        <li><span className="sw sw-can" />지금 갈 수 있음</li>
        <li><span className="sw sw-far" />거쳐야 함</li>
        <li><span className="sw-dot" />처음 가는 곳(행동 1, 다시 가면 무료)</li>
      </ul>
    </div>
  )
}

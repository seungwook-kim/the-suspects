import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { ClearHistory } from '../api/types'
import { ResultCard } from './Result'

export function History({ onBack }: { onBack: () => void }) {
  const [list, setList] = useState<ClearHistory[] | null>(null)
  const [err, setErr] = useState('')
  useEffect(() => {
    let alive = true
    api
      .history()
      .then((h) => alive && setList(h))
      .catch((e) => alive && setErr(e instanceof Error ? e.message : '이력을 불러오지 못했습니다.'))
    return () => {
      alive = false
    }
  }, [])
  return (
    <div className="screen history">
      <h1>클리어 이력</h1>
      {err && <p className="warn">{err}</p>}
      {!list && !err && <p className="muted">불러오는 중…</p>}
      {list?.length === 0 && <p className="muted">아직 기록이 없습니다. 첫 사건을 해결해 보세요.</p>}
      <div className="history-grid">
        {list?.map((h) => (
          <ResultCard key={h.id} h={h} />
        ))}
      </div>
      <div className="brief-actions">
        <button onClick={onBack}>← 돌아가기</button>
      </div>
    </div>
  )
}

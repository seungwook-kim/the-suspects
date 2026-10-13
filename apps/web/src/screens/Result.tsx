import { useState } from 'react'
import type { ClearHistory, ShareCard } from '../api/types'
import { Portrait } from '../character/Portrait'
import { downloadBlob, renderCardPng } from '../util/cardImage'
import { buildShareText } from '../util/format'

export function ResultCard({ h, card }: { h: ClearHistory; card?: ShareCard | null }) {
  const color = card?.theme_color ?? '#3b6ea5'
  return (
    <article className={`result-card${h.success ? '' : ' failed'}`} style={{ borderTopColor: color }}>
      <header>
        <h2>{h.theme || h.case_title}</h2>
        <span className="grade">{h.success ? `해결 등급 ${h.grade ?? '-'}` : '미해결'}</span>
      </header>
      <p>⏱ {h.real_minutes}분 · 질문 {h.question_count}개 · 게임 속 {h.game_days}일째</p>
      <div className="faces">
        {h.characters.map((c, i) => (
          <figure key={i}>
            <Portrait seed={c.face_seed} appearance={c.appearance} width={64} still title={c.role} />
            <figcaption>{c.role}</figcaption>
          </figure>
        ))}
      </div>
      {h.success ? (
        <>
          <p className="culprit">🔍 범인: {h.culprit.role} {h.culprit.name}</p>
          {h.titles[0] && <p>🏅 칭호: {h.titles[0]}</p>}
        </>
      ) : (
        <p className="culprit">범인을 잡지 못했다…</p>
      )}
      {h.highlight && <blockquote>&ldquo;{h.highlight}&rdquo;</blockquote>}
    </article>
  )
}

interface Props {
  h: ClearHistory
  card: ShareCard | null
  onNew: () => void
  onHistory: () => void
}

export function Result({ h, card, onNew, onHistory }: Props) {
  const [msg, setMsg] = useState('')
  const flash = (m: string) => {
    setMsg(m)
    window.setTimeout(() => setMsg(''), 2500)
  }
  const savePng = async () => {
    try {
      const blob = await renderCardPng(h, card?.theme_color)
      downloadBlob(blob, `the-suspects-${h.id}.png`)
      flash('이미지를 저장했습니다')
    } catch (e) {
      flash(e instanceof Error ? e.message : '이미지 저장 실패')
    }
  }
  const copyText = async () => {
    const text = buildShareText(h, card)
    try {
      await navigator.clipboard.writeText(text)
      flash('복사했습니다')
    } catch {
      // 클립보드 권한이 없을 때의 대체 수단
      window.prompt('아래 문구를 복사하세요', text)
    }
  }
  return (
    <div className="screen result">
      <p className="eyebrow">{h.success ? '사건 종결' : '사건 미해결'}</p>
      <ResultCard h={h} card={card} />
      <div className="brief-actions">
        {h.success && (
          <>
            <button onClick={savePng}>🖼 이미지 저장</button>
            <button onClick={copyText}>📋 텍스트 복사</button>
          </>
        )}
        <button className="primary" onClick={onNew}>새 사건</button>
        <button onClick={onHistory}>클리어 이력</button>
      </div>
      {msg && <p className="saved center" role="status">{msg}</p>}
      {!h.success && <p className="muted small center">실패한 판은 공유할 수 없습니다.</p>}
    </div>
  )
}

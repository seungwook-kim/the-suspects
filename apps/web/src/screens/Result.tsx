import { useState } from 'react'
import type { ClearHistory, ShareCard } from '../api/types'
import { Icon } from '../components/Icon'
import { Portrait } from '../character/Portrait'
import { downloadBlob, renderCardPng } from '../util/cardImage'
import { buildShareText, plainTitle } from '../util/format'

export function ResultCard({ h, card }: { h: ClearHistory; card?: ShareCard | null }) {
  const color = card?.theme_color ?? '#3b6ea5'
  return (
    <article className={`paper res-card${h.success ? '' : ' failed'}`}>
      <span className="res-topline" style={{ background: color }} aria-hidden="true" />
      <header className="res-head">
        <h2>{plainTitle(h.theme || h.case_title)}</h2>
        {h.success ? (
          <span className="stamp res-grade">해결 등급 <span className="mono">{h.grade ?? '-'}</span></span>
        ) : (
          <span className="stamp res-grade">미해결</span>
        )}
      </header>
      <dl className="res-stats">
        <div><dt><Icon name="clock-countdown" />실제 시간</dt><dd className="mono">{h.real_minutes}분</dd></div>
        <div><dt><Icon name="chat-circle-text" />질문</dt><dd className="mono">{h.question_count}개</dd></div>
        <div><dt><Icon name="sun" />게임 속</dt><dd className="mono">{h.game_days}일째</dd></div>
      </dl>
      <div className="res-faces">
        {h.characters.map((c, i) => (
          <figure key={i}>
            <Portrait seed={c.face_seed} appearance={c.appearance} width={64} still title={c.role} />
            <figcaption>{c.role}</figcaption>
          </figure>
        ))}
      </div>
      {h.success ? (
        <div className="res-verdict">
          <p><Icon name="magnifying-glass" /><span className="res-label">범인</span> {h.culprit.role} {h.culprit.name}</p>
          {h.titles[0] && <p><Icon name="seal-check" /><span className="res-label">칭호</span> {h.titles[0]}</p>}
        </div>
      ) : (
        <p className="res-verdict">범인을 잡지 못했다…</p>
      )}
      {h.highlight && <blockquote className="res-quote">&ldquo;{h.highlight}&rdquo;</blockquote>}
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
      <div className="actions res-actions">
        {h.success && (
          <>
            <button type="button" className="btn" onClick={savePng}><span className="btn-label"><Icon name="image" />이미지 저장</span></button>
            <button type="button" className="btn" onClick={copyText}><span className="btn-label"><Icon name="copy" />텍스트 복사</span></button>
          </>
        )}
        <button type="button" className="btn btn-cta" onClick={onNew}><span className="btn-label">새 사건</span></button>
        <button type="button" className="btn" onClick={onHistory}><span className="btn-label"><Icon name="list" />클리어 이력</span></button>
      </div>
      {msg && <p className="res-saved" role="status">{msg}</p>}
      {!h.success && <p className="res-note">실패한 판은 공유할 수 없습니다.</p>}
    </div>
  )
}

import { useRef, useState } from 'react'
import type { PlayerView } from '../api/types'
import { formatTime } from '../util/format'
import { Icon } from './Icon'
import { Popover } from './Popover'

interface Props {
  view: PlayerView
  busy: boolean
  interrogating: boolean
  theme: 'light' | 'dark'
  /** 지도·이 장소를 화면에 둘 자리가 없을 때(1099px 이하) 여는 단추 */
  onOpenSide?: () => void
  sideLabel: string
  onBack: () => void
  onEndDay: () => void
  onSave: () => void
  onFinale: () => void
  onAbout: () => void
  onHome: () => void
  onToggleTheme: () => void
}

/** 상단 상태띠: 사건 이름 · 일차와 시각 · 남은 행동 칸 · 평판. 최종 추리는 하루 끝내기와 떨어뜨려 메뉴에 둔다(D7). */
export function StatusStrip({ view, busy, interrogating, theme, onOpenSide, sideLabel, onBack, onEndDay, onSave, onFinale, onAbout, onHome, onToggleTheme }: Props) {
  const [menu, setMenu] = useState(false)
  const menuRef = useRef<HTMLButtonElement>(null)
  const left = Math.max(0, view.actions_left)
  const total = Math.max(left, view.actions_total)
  const daysLeft = view.max_days > 0 ? Math.max(0, view.max_days - view.day) : null
  const run = (f: () => void) => () => {
    setMenu(false)
    f()
  }

  return (
    <header className="status-strip">
      {interrogating && (
        <button type="button" className="btn btn-icon only-phone" onClick={onBack} aria-label="심문 끝내기">
          <span className="btn-label"><Icon name="arrow-left" /></span>
        </button>
      )}
      <strong className="case-title">{view.case_title}</strong>
      <span className="clock">
        {view.day}일차 {formatTime(view.clock)}
        {daysLeft !== null && <span className="days-left"> · 남은 {daysLeft}일</span>}
      </span>
      <span className={`ap${left <= 2 ? ' is-low' : ''}`}>
        <span className="cells is-pip" aria-hidden="true">
          {Array.from({ length: total }, (_, i) => (
            <i key={i} className={i < left ? 'on' : ''} />
          ))}
        </span>
        <span>행동 <b>{left}</b>/{total}</span>
      </span>
      {view.reputation_band && <span className="rep-tag" title="평판">{view.reputation_band}</span>}
      <div className="spacer">
        {onOpenSide && (
          <button type="button" className="btn side-btn" onClick={onOpenSide} aria-label={`${sideLabel} 열기`}>
            <span className="btn-label"><Icon name="map-trifold" /><span className="t">{sideLabel}</span></span>
          </button>
        )}
        <button type="button" className="btn only-wide" onClick={onEndDay} disabled={busy}>
          <span className="btn-label"><Icon name="moon" />하루 끝내기</span>
        </button>
        <button ref={menuRef} type="button" className="btn" aria-expanded={menu} aria-haspopup="dialog" onClick={() => setMenu((v) => !v)} aria-label="메뉴 열기">
          <span className="btn-label"><Icon name="list" /><span className="t">메뉴</span></span>
        </button>
      </div>
      {menu && (
        <Popover anchorRef={menuRef} onClose={() => setMenu(false)} label="메뉴" className="menu-pop" align="end">
          <button type="button" className="btn btn-quiet" onClick={run(onSave)} disabled={busy}>
            <span className="btn-label"><Icon name="floppy-disk" />저장</span>
          </button>
          <button type="button" className="btn btn-quiet only-phone" onClick={run(onEndDay)} disabled={busy}>
            <span className="btn-label"><Icon name="moon" />하루 끝내기</span>
          </button>
          <button type="button" className="btn btn-quiet" onClick={run(onToggleTheme)}>
            <span className="btn-label"><Icon name={theme === 'dark' ? 'sun' : 'moon'} />{theme === 'dark' ? '밝은 테마로' : '어두운 테마로'}</span>
          </button>
          <hr className="menu-sep" />
          <button type="button" className="btn btn-quiet" onClick={run(onFinale)} disabled={busy}>
            <span className="btn-label"><Icon name="seal-check" /><span>최종 추리<small>되돌릴 수 없음</small></span></span>
          </button>
          <button type="button" className="btn btn-quiet" onClick={run(onAbout)}>
            <span className="btn-label"><Icon name="info" />정보 · 라이선스</span>
          </button>
          <button type="button" className="btn btn-quiet" onClick={run(onHome)}>
            <span className="btn-label"><Icon name="arrow-left" />처음으로</span>
          </button>
        </Popover>
      )}
    </header>
  )
}

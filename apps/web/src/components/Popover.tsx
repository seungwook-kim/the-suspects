import { useEffect, useLayoutEffect, useRef, useState, type ReactNode, type RefObject } from 'react'
import { createPortal } from 'react-dom'

const FOCUSABLE = 'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

/** 열릴 때 안쪽 첫 요소로 포커스를 옮기고, 닫힐 때 열었던 버튼으로 되돌린다. Esc 로 닫는다. */
function useDialogFocus(ref: RefObject<HTMLElement | null>, onClose: () => void, returnTo?: RefObject<HTMLElement | null>) {
  const closeRef = useRef(onClose)
  closeRef.current = onClose
  useEffect(() => {
    const prev = (returnTo?.current ?? document.activeElement) as HTMLElement | null
    const first = ref.current?.querySelector<HTMLElement>(FOCUSABLE)
    first?.focus({ preventScroll: true })
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation()
        closeRef.current()
      }
    }
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('keydown', onKey)
      prev?.focus?.({ preventScroll: true })
    }
  }, [ref, returnTo])
}

interface PopoverProps {
  anchorRef: RefObject<HTMLElement | null>
  onClose: () => void
  label: string
  className?: string
  /** 기준 버튼의 어느 쪽 끝에 맞출지 */
  align?: 'start' | 'end'
  children: ReactNode
}

/** 버튼 옆에 뜨는 목록(데스크톱). 휴대폰(720px 이하)에서는 CSS 가 같은 요소를 하단 시트로 바꾼다(.pop). */
export function Popover({ anchorRef, onClose, label, className, align = 'start', children }: PopoverProps) {
  const ref = useRef<HTMLDivElement>(null)
  const [pos, setPos] = useState<{ top?: number; bottom?: number; left: number } | null>(null)
  useDialogFocus(ref, onClose, anchorRef)

  useLayoutEffect(() => {
    const place = () => {
      const a = anchorRef.current?.getBoundingClientRect()
      const el = ref.current
      if (!a || !el) return
      const w = el.offsetWidth
      const vw = window.innerWidth
      const vh = window.innerHeight
      const left = Math.max(16, Math.min(vw - w - 16, align === 'end' ? a.right - w : a.left))
      // 아래 공간이 모자라면 위로 띄운다(행동바 버튼은 대개 위로)
      setPos(vh - a.bottom >= Math.min(el.offsetHeight, 360) + 16 ? { top: a.bottom + 8, left } : { bottom: vh - a.top + 8, left })
    }
    place()
    window.addEventListener('resize', place)
    return () => window.removeEventListener('resize', place)
  }, [anchorRef, align])

  // 바깥을 누르면 닫는다(기준 버튼은 제외: 버튼이 스스로 토글한다)
  useEffect(() => {
    const onDown = (e: PointerEvent) => {
      const t = e.target as Node
      if (ref.current?.contains(t) || anchorRef.current?.contains(t)) return
      onClose()
    }
    document.addEventListener('pointerdown', onDown)
    return () => document.removeEventListener('pointerdown', onDown)
  }, [anchorRef, onClose])

  return createPortal(
    <div ref={ref} className={`paper pop ${className ?? ''}`} role="dialog" aria-label={label} style={pos ?? { visibility: 'hidden', left: 0, top: 0 }}>
      {children}
    </div>,
    document.body,
  )
}

interface SheetProps {
  onClose: () => void
  label: string
  /** 'bottom': 아래에서 올라오는 시트(휴대폰) / 'side': 왼쪽 서랍(태블릿의 지도) */
  side?: 'bottom' | 'side'
  className?: string
  children: ReactNode
}

/** 시트·서랍. 열려 있는 동안 뒤 화면(#root)은 inert 로 막고, 닫으면 포커스를 연 버튼으로 돌려준다. */
export function Sheet({ onClose, label, side = 'bottom', className, children }: SheetProps) {
  const ref = useRef<HTMLDivElement>(null)
  useDialogFocus(ref, onClose)
  useEffect(() => {
    const root = document.getElementById('root')
    root?.setAttribute('inert', '')
    document.documentElement.classList.add('sheet-open')
    return () => {
      root?.removeAttribute('inert')
      document.documentElement.classList.remove('sheet-open')
    }
  }, [])
  return createPortal(
    <>
      <div className="scrim" onClick={onClose} />
      <div ref={ref} className={`${side === 'side' ? 'side-drawer' : 'sheet'} ${className ?? ''}`} role="dialog" aria-modal="true" aria-label={label}>
        {children}
      </div>
    </>,
    document.body,
  )
}

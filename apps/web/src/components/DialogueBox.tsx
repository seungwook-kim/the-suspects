import { useEffect, useState } from 'react'
import type { DialogueLine } from '../state/reducer'

const ROLE_LABEL: Record<string, string> = { narrator: '내레이션', partner: '파트너', chief: '반장' }

/** 글자가 하나씩 찍히는 효과. 새 메시지는 key 로 상태를 새로 시작한다. */
export function useTypewriter(text: string, speedMs = 30) {
  const [n, setN] = useState(0)
  useEffect(() => {
    if (n >= text.length) return
    const id = window.setTimeout(() => setN((x) => x + 1), speedMs)
    return () => window.clearTimeout(id)
  }, [n, text, speedMs])
  const shown = Math.min(n, text.length)
  return { shown: text.slice(0, shown), typing: shown < text.length }
}

interface Props {
  line: DialogueLine
  speakerName: string | null
  onTyping: (typing: boolean) => void
}

/** 최종 추리 화면의 대사: 종이 면 위 "이름 + 대사" 조서 줄. 모양은 styles/finale.css 의 .dialogue… */
export function DialogueBox({ line, speakerName, onTyping }: Props) {
  const { shown, typing } = useTypewriter(line.text)
  const active = typing || !line.done
  useEffect(() => {
    onTyping(active)
    return () => onTyping(false)
  }, [active, onTyping])
  const name = line.role === 'npc' ? speakerName ?? '???' : ROLE_LABEL[line.role] ?? ''
  return (
    <div className={`dialogue role-${line.role}`} aria-live="polite">
      <span className="dialogue-who">{name}</span>
      <p className="dialogue-said">
        {shown}
        {active && <span className="caret" aria-hidden="true">▌</span>}
      </p>
    </div>
  )
}

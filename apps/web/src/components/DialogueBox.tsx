import { useEffect, useRef, useState } from 'react'
import type { DialogueLine } from '../state/reducer'

const ROLE_LABEL: Record<string, string> = { narrator: '내레이션', partner: '파트너', chief: '반장' }

/** 밀린 글자가 이보다 많으면 한 번에 여러 글자씩 찍어, 밀린 만큼을 이 횟수(× speedMs) 안에 따라잡는다.
 * 짧은 대사는 지금처럼 한 글자씩, 긴 대사나 한꺼번에 도착한 문장은 1.2초 안에 다 보인다(PRD §14.1 체감 속도). */
export const TYPE_CATCHUP_TICKS = 40

/** 글자가 하나씩 찍히는 효과. 새 메시지는 key 로 상태를 새로 시작한다. */
export function useTypewriter(text: string, speedMs = 30) {
  const [n, setN] = useState(0)
  const step = useRef(1) // 한 번에 찍을 글자 수. 다 따라잡을 때까지 유지한다
  useEffect(() => {
    const left = text.length - n
    if (left <= 0) {
      step.current = 1
      return
    }
    if (left > step.current * TYPE_CATCHUP_TICKS) step.current = Math.ceil(left / TYPE_CATCHUP_TICKS)
    const id = window.setTimeout(() => setN((x) => x + step.current), speedMs)
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

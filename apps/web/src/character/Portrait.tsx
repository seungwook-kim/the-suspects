import { useEffect, useMemo, useState } from 'react'
import type { Emotion } from '../api/types'
import { renderPortraitSvg } from './faceRender'

interface Props {
  seed: number
  appearance?: Record<string, string>
  emotion?: Emotion
  /** 대사가 나오는 동안 true: 입을 여닫는다 */
  speaking?: boolean
  width?: number
  className?: string
  title?: string
  /** 눈 깜빡임·입 움직임 끄기 (작은 얼굴, 결과 카드) */
  still?: boolean
}

const MOUTH_PATTERN = [0.25, 0.85, 0.45, 1, 0.15, 0.7, 0.35]

export function Portrait({ seed, appearance, emotion = 'neutral', speaking, width = 240, className, title, still }: Props) {
  const [blink, setBlink] = useState(false)
  const [mouth, setMouth] = useState(0)

  // 3~6초마다 눈 깜빡임
  useEffect(() => {
    if (still) return
    let t1: number
    let t2: number
    const schedule = () => {
      t1 = window.setTimeout(() => {
        setBlink(true)
        t2 = window.setTimeout(() => {
          setBlink(false)
          schedule()
        }, 140)
      }, 3000 + Math.random() * 3000)
    }
    schedule()
    return () => {
      window.clearTimeout(t1)
      window.clearTimeout(t2)
    }
  }, [still])

  // 말하는 동안 입 여닫기
  useEffect(() => {
    if (still || !speaking) {
      setMouth(0)
      return
    }
    let i = 0
    const id = window.setInterval(() => {
      setMouth(MOUTH_PATTERN[i++ % MOUTH_PATTERN.length])
    }, 110)
    return () => window.clearInterval(id)
  }, [speaking, still])

  const svg = useMemo(
    () => renderPortraitSvg(seed, appearance ?? {}, { emotion, blink, mouthOpen: mouth }),
    [seed, appearance, emotion, blink, mouth],
  )
  return (
    <div
      className={`portrait emo-${emotion} ${className ?? ''}`}
      style={{ width, aspectRatio: '240 / 300' }}
      title={title}
      aria-label={title}
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  )
}

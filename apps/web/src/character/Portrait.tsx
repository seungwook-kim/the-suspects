import { createContext, useContext, useEffect, useMemo, useRef, useState } from 'react'
import type { Emotion } from '../api/types'
import { renderPortraitSvg } from './faceRender'

interface Props {
  seed: number
  appearance?: Record<string, string>
  emotion?: Emotion
  /** 대사가 나오는 동안 true: 그림 얼굴의 입을 여닫는다(사진은 움직이지 않는다) */
  speaking?: boolean
  /** 픽셀 폭. 없으면 부모 폭을 채운다(비율 3:4) */
  width?: number
  className?: string
  title?: string
  /** 캐릭터 이름: 사진의 alt, 사진 준비 중 칸의 첫 글자 */
  name?: string
  /** 눈 깜빡임·입 움직임 끄기 (작은 얼굴, 결과 카드) */
  still?: boolean
  /** AI 초상화 주소. 없거나 로드에 실패하면 절차적 SVG 로 그린다. */
  portraitUrl?: string | null
  /** 표정별 사진 주소(감정 → 주소). 현재 감정의 사진이 있으면 그것을, 없으면 portraitUrl 을 보여 준다. */
  portraitEmotions?: Record<string, string> | null
  /** 주 화면 초상화: lazy 로딩을 쓰지 않는다 */
  eager?: boolean
  /** 자리 비움 등: 사진 위에 종이색 덮개와 글자를 얹는다 */
  cover?: string | null
}

/** 시작 화면·등장인물 소개에 붙이는 안내 (인물 사진은 모두 AI 생성) */
export const AI_PORTRAIT_NOTICE = '등장인물 사진은 모두 AI로 생성한 가상의 인물이며, 실존 인물과 관계없습니다.'

/** 서버가 초상화를 그리는 중이면 true. 사진이 아직 없는 인물을 그림 얼굴 대신 "사진 준비 중" 칸으로 보여 준다. */
export const PortraitPending = createContext(false)

/** 사진 교체(표정 바뀜) 크로스페이드 길이. CSS 의 --dur-base 와 같다 */
const FADE_MS = 180
const MOUTH_PATTERN = [0.25, 0.85, 0.45, 1, 0.15, 0.7, 0.35]

// 한 번 실패한 주소는 기억해 다시 시도하지 않는다(그림이 깜빡이며 되돌아오지 않게)
const failedUrls = new Set<string>()

function usePrefersReducedMotion(): boolean {
  const query = '(prefers-reduced-motion: reduce)'
  const get = () => (typeof window !== 'undefined' && typeof window.matchMedia === 'function' ? window.matchMedia(query).matches : false)
  const [reduced, setReduced] = useState(get)
  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return
    const mq = window.matchMedia(query)
    const on = () => setReduced(mq.matches)
    on()
    mq.addEventListener?.('change', on)
    return () => mq.removeEventListener?.('change', on)
  }, [])
  return reduced
}

export function Portrait({ seed, appearance, emotion = 'neutral', speaking, width, className, title, name, still, portraitUrl, portraitEmotions, eager, cover }: Props) {
  const pending = useContext(PortraitPending)
  const [blink, setBlink] = useState(false)
  const [mouth, setMouth] = useState(0)
  const [, setFailed] = useState(0) // 실패 기록이 바뀔 때 다시 그리기 위한 카운터
  const [shown, setShown] = useState<string | null>(null) // 다 불러와 맨 위에 보이는 사진
  const [prev, setPrev] = useState<string | null>(null) // 새 사진이 겹쳐 나타나는 동안 아래에 남겨 두는 이전 사진
  const fadeTimer = useRef<number | undefined>(undefined)
  const reduced = usePrefersReducedMotion()

  const emoUrl = emotion !== 'neutral' ? portraitEmotions?.[emotion] : undefined
  const useEmo = !!emoUrl && !failedUrls.has(emoUrl)
  const base = portraitUrl && !failedUrls.has(portraitUrl) ? portraitUrl : null
  const url = useEmo ? emoUrl! : base
  const usePhoto = !!url
  const animate = !still && !usePhoto && !reduced

  useEffect(() => () => window.clearTimeout(fadeTimer.current), [])

  // 3~6초마다 눈 깜빡임 (그림일 때만)
  useEffect(() => {
    if (!animate) return
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
  }, [animate])

  // 말하는 동안 입 여닫기 (그림일 때만)
  useEffect(() => {
    if (!animate || !speaking) {
      setMouth(0)
      return
    }
    let i = 0
    const id = window.setInterval(() => {
      setMouth(MOUTH_PATTERN[i++ % MOUTH_PATTERN.length])
    }, 110)
    return () => window.clearInterval(id)
  }, [speaking, animate])

  const svg = useMemo(
    () => (usePhoto ? '' : renderPortraitSvg(seed, appearance ?? {}, { emotion, blink, mouthOpen: mouth })),
    [usePhoto, seed, appearance, emotion, blink, mouth],
  )
  const style = width ? { width } : undefined
  const coverEl = cover ? <div className="away-cover">{cover}</div> : null

  if (!usePhoto) {
    if (pending) {
      const initial = name ? [...name][0] : '?'
      return (
        <div className={`avatar-pending ${className ?? ''}`} style={style} role="img" aria-label={`${name ?? '인물'}, 사진 준비 중`}>
          <span className="ap-initial" aria-hidden="true">{initial}</span>
          <span className="ap-label" aria-hidden="true">사진 준비 중</span>
        </div>
      )
    }
    return (
      <div className={`portrait portrait-svg ${className ?? ''}`} style={style} title={title} role="img" aria-label={title ?? name}>
        <div dangerouslySetInnerHTML={{ __html: svg }} style={{ display: 'contents' }} />
        {coverEl}
      </div>
    )
  }

  const front = shown && !failedUrls.has(shown) ? shown : null
  const layers = [prev, front, url].filter((u, i, a): u is string => !!u && !failedUrls.has(u) && a.indexOf(u) === i)
  const onLoad = (u: string) => {
    if (u !== url || u === shown) return
    setPrev(shown)
    setShown(u)
    window.clearTimeout(fadeTimer.current)
    fadeTimer.current = window.setTimeout(() => setPrev(null), FADE_MS + 40)
  }
  return (
    <div className={`portrait portrait-photo ${className ?? ''}`} style={style} title={title}>
      {layers.map((u) => (
        <img
          key={u}
          className={`portrait-img${u === front || u === prev ? ' is-front' : ''}`}
          src={u}
          alt={u === url ? (name ? `${name}, AI로 생성한 가상의 인물 사진` : (title ?? '')) : ''}
          aria-hidden={u === url ? undefined : true}
          loading={eager ? undefined : 'lazy'}
          decoding="async"
          onLoad={() => onLoad(u)}
          onError={() => {
            failedUrls.add(u)
            setFailed((n) => n + 1)
          }}
        />
      ))}
      {coverEl}
    </div>
  )
}

/** 테스트용: 실패 기록 초기화 */
export function resetPortraitFailures() {
  failedUrls.clear()
}

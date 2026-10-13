import { useEffect, useMemo, useState } from 'react'
import type { Emotion } from '../api/types'
import { renderPortraitSvg } from './faceRender'

interface Props {
  seed: number
  appearance?: Record<string, string>
  emotion?: Emotion
  /** 대사가 나오는 동안 true: 입을 여닫고(그림) / 미세하게 들썩인다(사진) */
  speaking?: boolean
  width?: number
  className?: string
  title?: string
  /** 캐릭터 이름: 사진의 alt */
  name?: string
  /** 눈 깜빡임·입 움직임 끄기 (작은 얼굴, 결과 카드) */
  still?: boolean
  /** AI 초상화 주소. 없거나 로드에 실패하면 절차적 SVG 로 그린다. */
  portraitUrl?: string | null
  /** 주 화면 초상화: lazy 로딩을 쓰지 않는다 */
  eager?: boolean
}

/** 시작 화면·등장인물 소개에 붙이는 안내 (인물 사진은 모두 AI 생성) */
export const AI_PORTRAIT_NOTICE = '등장인물 사진은 모두 AI로 생성한 가상의 인물이며, 실존 인물과 관계없습니다.'

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

export function Portrait({ seed, appearance, emotion = 'neutral', speaking, width = 240, className, title, name, still, portraitUrl, eager }: Props) {
  const [blink, setBlink] = useState(false)
  const [mouth, setMouth] = useState(0)
  const [failed, setFailed] = useState(0) // 실패 기록이 바뀔 때 다시 그리기 위한 카운터
  const [loadedUrl, setLoadedUrl] = useState<string | null>(null)
  const reduced = usePrefersReducedMotion()

  const url = portraitUrl && !failedUrls.has(portraitUrl) ? portraitUrl : null
  void failed
  const usePhoto = !!url

  // 3~6초마다 눈 깜빡임 (그림일 때만)
  useEffect(() => {
    if (still || usePhoto) return
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
  }, [still, usePhoto])

  // 말하는 동안 입 여닫기 (그림일 때만)
  useEffect(() => {
    if (still || usePhoto || !speaking) {
      setMouth(0)
      return
    }
    let i = 0
    const id = window.setInterval(() => {
      setMouth(MOUTH_PATTERN[i++ % MOUTH_PATTERN.length])
    }, 110)
    return () => window.clearInterval(id)
  }, [speaking, still, usePhoto])

  const svg = useMemo(
    () => renderPortraitSvg(seed, appearance ?? {}, { emotion, blink: blink && !usePhoto, mouthOpen: usePhoto ? 0 : mouth }),
    [seed, appearance, emotion, blink, mouth, usePhoto],
  )
  const style = { width, aspectRatio: '240 / 300' }

  if (!usePhoto) {
    return (
      <div
        className={`portrait emo-${emotion} ${className ?? ''}`}
        style={style}
        title={title}
        aria-label={title}
        dangerouslySetInnerHTML={{ __html: svg }}
      />
    )
  }

  const loaded = loadedUrl === url
  const fx = [
    !reduced && emotion === 'flustered' ? 'fx-shake' : '',
    !reduced && emotion === 'nervous' ? 'fx-tremble' : '',
    !reduced && speaking && !still ? 'fx-bob' : '',
  ].filter(Boolean)
  const badge = emotion === 'flustered' ? '💦' : emotion === 'angry' ? '💢' : null
  return (
    <div
      className={`portrait portrait-photo emo-${emotion}${speaking ? ' speaking' : ''}${reduced ? ' calm' : ''} ${className ?? ''}`}
      style={style}
      title={title}
      aria-label={title}
    >
      <div className={`portrait-bob${fx.includes('fx-bob') ? ' fx-bob' : ''}`}>
        <div className={`portrait-frame ${fx.filter((f) => f !== 'fx-bob').join(' ')}`}>
          <div className="portrait-ph" dangerouslySetInnerHTML={{ __html: svg }} />
          <img
            className={`portrait-img${loaded ? ' loaded' : ''}`}
            src={url}
            alt={name ?? title ?? ''}
            loading={eager ? undefined : 'lazy'}
            decoding="async"
            onLoad={() => setLoadedUrl(url)}
            onError={() => {
              failedUrls.add(url)
              setFailed((n) => n + 1)
            }}
          />
          {(emotion === 'angry' || emotion === 'sad') && <div className="portrait-tint" aria-hidden />}
        </div>
        {badge && (
          <span className="portrait-badge" aria-hidden style={{ fontSize: Math.max(14, Math.round(width * 0.17)) }}>
            {badge}
          </span>
        )}
      </div>
    </div>
  )
}

/** 테스트용: 실패 기록 초기화 */
export function resetPortraitFailures() {
  failedUrls.clear()
}

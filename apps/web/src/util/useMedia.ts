import { useEffect, useState } from 'react'

/** 화면 폭 분기(D12): 1100px 이상 3열 / 900~1099 2열(지도 서랍) / 721~899 2열 좁게 / 720px 이하 휴대폰 */
export const MQ_PHONE = '(max-width: 720px)'
export const MQ_WIDE = '(min-width: 1100px)'

export function useMedia(query: string): boolean {
  const get = () => (typeof window !== 'undefined' && typeof window.matchMedia === 'function' ? window.matchMedia(query).matches : false)
  const [match, setMatch] = useState(get)
  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return
    const mq = window.matchMedia(query)
    const on = () => setMatch(mq.matches)
    on()
    mq.addEventListener?.('change', on)
    return () => mq.removeEventListener?.('change', on)
  }, [query])
  return match
}

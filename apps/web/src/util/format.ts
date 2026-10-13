import type { ClearHistory, ShareCard } from '../api/types'

/** clock: 사건 첫날 00:00 기준 분. 표시는 "N일차 HH:MM" */
export function formatTime(clock: number): string {
  const m = ((clock % 1440) + 1440) % 1440
  return `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`
}

export function formatDayTime(day: number, clock: number): string {
  return `${day}일차 ${formatTime(clock)}`
}

export function dayPeriod(clock: number): string {
  const h = Math.floor((((clock % 1440) + 1440) % 1440) / 60)
  if (h < 6) return '새벽'
  if (h < 12) return '오전'
  if (h < 18) return '오후'
  return '밤'
}

/** 메신저용 텍스트: `🔍🔍❌🔍✅ 23질문 만에 해결` */
export function buildShareText(h: ClearHistory, card?: ShareCard | null): string {
  if (card?.share_text) return card.share_text
  const line =
    card?.emoji_line ?? '🔍'.repeat(Math.max(1, Math.min(h.game_days, 5))) + (h.success ? '✅' : '❌')
  const head = `${line} ${h.question_count}질문 만에 ${h.success ? '해결' : '실패'}`
  const tail = `The Suspects · ${h.case_title}${h.grade ? ` · 등급 ${h.grade}` : ''}`
  return `${head}\n${tail}`
}

const ENDING_TEXT: Record<string, { title: string; body: string }> = {
  success: { title: '사건 해결', body: '모든 증거가 맞아떨어졌다. 범인은 무너졌다.' },
  escaped: { title: '범인 도주', body: '증거가 모자랐다. 범인은 유유히 사라졌다…' },
  wrong_accusation: { title: '오지목', body: '억울한 사람을 지목하고 말았다. 진짜 범인은 아직 밖에 있다.' },
}
export function endingText(ending: string) {
  return ENDING_TEXT[ending] ?? { title: '사건 종료', body: '' }
}

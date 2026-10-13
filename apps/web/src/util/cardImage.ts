// 결과 카드를 캔버스로 PNG 로 만든다. 서버에는 아무것도 보내지 않는다.
import type { ClearHistory } from '../api/types'
import { renderPortraitSvg } from '../character/faceRender'
import { shortName } from './format'

function loadSvg(svg: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => resolve(img)
    img.onerror = () => reject(new Error('얼굴 이미지를 만들지 못했습니다'))
    img.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`
  })
}

function wrap(ctx: CanvasRenderingContext2D, text: string, maxW: number): string[] {
  const lines: string[] = []
  let cur = ''
  for (const ch of text) {
    if (ctx.measureText(cur + ch).width > maxW && cur) {
      lines.push(cur)
      cur = ch
    } else cur += ch
  }
  if (cur) lines.push(cur)
  return lines
}

export async function renderCardPng(h: ClearHistory, themeColor = '#3b6ea5'): Promise<Blob> {
  const W = 720
  const faceW = 96
  const faceH = 120
  const pad = 36
  const n = h.characters.length
  const gap = n > 1 ? Math.min(14, (W - pad * 2 - faceW * n) / (n - 1)) : 0
  const faces = await Promise.all(
    h.characters.map((c) => loadSvg(renderPortraitSvg(c.face_seed, c.appearance, { emotion: 'neutral' }))),
  )

  const canvas = document.createElement('canvas')
  const scale = 2
  const H = 520
  canvas.width = W * scale
  canvas.height = H * scale
  const ctx = canvas.getContext('2d')!
  ctx.scale(scale, scale)

  ctx.fillStyle = '#F4F1EA'
  ctx.fillRect(0, 0, W, H)
  ctx.fillStyle = themeColor
  ctx.fillRect(0, 0, W, 10)
  ctx.strokeStyle = '#2E3440'
  ctx.lineWidth = 3
  ctx.strokeRect(12, 22, W - 24, H - 34)

  const font = `'Pretendard','Noto Sans KR','Malgun Gothic',sans-serif`
  ctx.fillStyle = '#2E3440'
  ctx.textBaseline = 'alphabetic'
  ctx.font = `700 28px ${font}`
  ctx.fillText(h.theme || h.case_title, pad, 74)
  ctx.textAlign = 'right'
  ctx.fillStyle = h.success ? '#E4572E' : '#6b7280'
  ctx.fillText(h.success ? `해결 등급 ${h.grade ?? '-'}` : '미해결', W - pad, 74)
  ctx.textAlign = 'left'

  ctx.fillStyle = '#2E3440'
  ctx.font = `500 18px ${font}`
  ctx.fillText(`⏱ ${h.real_minutes}분 · 질문 ${h.question_count}개 · 게임 속 ${h.game_days}일째`, pad, 108)

  ctx.font = `600 14px ${font}`
  ctx.fillStyle = '#6b7280'
  ctx.fillText('등장인물', pad, 144)

  faces.forEach((img, i) => {
    const x = pad + i * (faceW + gap)
    ctx.save()
    ctx.beginPath()
    ctx.roundRect(x, 154, faceW, faceH, 10)
    ctx.clip()
    ctx.drawImage(img, x, 154, faceW, faceH)
    ctx.restore()
    ctx.strokeStyle = '#2E3440'
    ctx.lineWidth = 1.5
    ctx.beginPath()
    ctx.roundRect(x, 154, faceW, faceH, 10)
    ctx.stroke()
    ctx.fillStyle = '#2E3440'
    ctx.font = `500 12px ${font}`
    ctx.textAlign = 'center'
    ctx.fillText(h.characters[i].role.slice(0, 8), x + faceW / 2, 154 + faceH + 18)
    ctx.textAlign = 'left'
  })

  let y = 154 + faceH + 58
  ctx.fillStyle = '#2E3440'
  ctx.font = `600 20px ${font}`
  if (h.success) {
    const c = h.culprit
    ctx.fillText(`🔍 범인: ${c.role ?? ''} ${shortName(c.name ?? '')}`, pad, y)
    y += 34
    if (h.titles.length) {
      ctx.fillText(`🏅 칭호: ${h.titles[0]}`, pad, y)
      y += 34
    }
  } else {
    ctx.fillText('범인을 잡지 못했다…', pad, y)
    y += 34
  }
  if (h.highlight) {
    ctx.font = `italic 500 16px ${font}`
    ctx.fillStyle = '#4b5563'
    for (const line of wrap(ctx, `"${h.highlight}"`, W - pad * 2).slice(0, 2)) {
      ctx.fillText(line, pad, y)
      y += 24
    }
  }
  ctx.font = `500 12px ${font}`
  ctx.fillStyle = '#9ca3af'
  ctx.textAlign = 'right'
  ctx.fillText('The Suspects', W - pad, H - 24)

  return new Promise((resolve, reject) => {
    canvas.toBlob((b) => (b ? resolve(b) : reject(new Error('PNG 생성 실패'))), 'image/png')
  })
}

export function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

// 결과 카드를 캔버스로 PNG 로 만든다. 서버에는 아무것도 보내지 않는다.
// 모양은 앱의 결과 카드와 같은 "종결 보고서"(방향 A): 바탕 위 종이 한 장, 폴더 탭, 잉크 도장, 3:4 얼굴 칸.
// 공유 이미지는 테마와 상관없이 밝은 종이로 그린다. 색은 styles/tokens.css 의 밝은 값과 같다.
import type { ClearHistory } from '../api/types'
import paperUrl from '../assets/paper-beige.webp'
import { renderPortraitSvg } from '../character/faceRender'

const C = {
  bg: '#E3E6E1',
  surface: '#FAFAF7',
  ink: '#1E2A31',
  muted: '#4F5B62',
  line: '#B3BAB5',
}
const BODY = `'IBM Plex Sans KR','Malgun Gothic','Apple SD Gothic Neo',sans-serif`
const MONO = `'Nanum Gothic Coding','IBM Plex Sans KR',monospace`

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => resolve(img)
    img.onerror = () => reject(new Error('이미지를 만들지 못했습니다'))
    img.src = src
  })
}
const loadSvg = (svg: string) => loadImage(`data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`)

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

/** 폭을 넘으면 뒤를 줄임표로 자른다 */
function fit(ctx: CanvasRenderingContext2D, text: string, maxW: number): string {
  if (ctx.measureText(text).width <= maxW) return text
  let s = text
  while (s && ctx.measureText(`${s}…`).width > maxW) s = s.slice(0, -1)
  return `${s}…`
}

/** 글꼴은 쓰는 글자의 조각만 받으므로, 그리기 전에 이 카드에 나오는 글자로 미리 불러 둔다 */
async function loadFonts(sample: string) {
  if (typeof document === 'undefined' || !document.fonts?.load) return
  await Promise.all([
    document.fonts.load(`400 16px 'IBM Plex Sans KR'`, sample),
    document.fonts.load(`700 16px 'IBM Plex Sans KR'`, sample),
    document.fonts.load(`400 12px 'Nanum Gothic Coding'`, 'The Suspects 0123456789'),
  ]).catch(() => undefined) // 글꼴을 못 받아도 기본 글꼴로 그린다
}

export async function renderCardPng(h: ClearHistory, themeColor = '#3b6ea5'): Promise<Blob> {
  const W = 720
  const sheetX = 24
  const sheetY = 52 // 폴더 탭 자리
  const sheetW = W - sheetX * 2
  const pad = 32
  const left = sheetX + pad
  const innerW = sheetW - pad * 2
  const n = h.characters.length
  const gap = 12
  const faceW = n ? Math.min(88, Math.floor((innerW - gap * Math.max(0, n - 1)) / n)) : 0
  const faceH = Math.round((faceW * 4) / 3)

  const title = h.theme || h.case_title
  const stats = `⏱ ${h.real_minutes}분 · 질문 ${h.question_count}개 · 게임 속 ${h.game_days}일째`
  const lead = h.success ? `🔍 범인: ${h.culprit.role ?? ''} ${h.culprit.name ?? ''}` : '범인을 잡지 못했다…'
  const titleLine = h.success && h.titles.length ? `🏅 칭호: ${h.titles[0]}` : null
  const grade = h.success ? `해결 등급 ${h.grade ?? '-'}` : '미해결'
  await loadFonts([title, stats, lead, titleLine, grade, h.highlight, ...h.characters.map((c) => c.role), '사건 종결 미해결 등장인물'].join(''))

  const [faces, paper] = await Promise.all([
    Promise.all(h.characters.map((c) => loadSvg(renderPortraitSvg(c.face_seed, c.appearance, { emotion: 'neutral' })))),
    loadImage(paperUrl).catch(() => null),
  ])

  // 높이는 내용(하이라이트 줄 수)에 맞춘다
  const measure = document.createElement('canvas').getContext('2d')!
  measure.font = `400 16px ${BODY}`
  const quote = h.highlight ? wrap(measure, `“${h.highlight}”`, innerW - 16).slice(0, 3) : []
  const yTitle = sheetY + pad + 30
  const yRule1 = yTitle + 22
  const yStats = yRule1 + 34
  const yRule2 = yStats + 20
  const yCastLabel = yRule2 + 32
  const yFaces = yCastLabel + 12
  const yLead = yFaces + faceH + 60
  const yTitleLine = yLead + 32
  const yQuote = (titleLine ? yTitleLine : yLead) + 42
  const bottom = quote.length ? yQuote + (quote.length - 1) * 26 + 8 : (titleLine ? yTitleLine : yLead) + 6
  const sheetH = bottom + pad - sheetY
  const H = sheetY + sheetH + 44

  const canvas = document.createElement('canvas')
  const scale = 2
  canvas.width = W * scale
  canvas.height = H * scale
  const ctx = canvas.getContext('2d')!
  ctx.scale(scale, scale)
  ctx.textBaseline = 'alphabetic'

  // 바탕
  ctx.fillStyle = C.bg
  ctx.fillRect(0, 0, W, H)

  // 폴더 탭 + 종이
  const tabText = h.success ? '사건 종결' : '사건 미해결'
  ctx.font = `400 14px ${MONO}`
  const tabW = ctx.measureText(tabText).width + 32
  ctx.fillStyle = C.surface
  ctx.strokeStyle = C.line
  ctx.lineWidth = 1
  ctx.beginPath()
  ctx.roundRect(sheetX + 16, sheetY - 30, tabW, 32, [3, 3, 0, 0])
  ctx.fill()
  ctx.stroke()
  ctx.save()
  ctx.shadowColor = 'rgba(30, 42, 49, 0.10)'
  ctx.shadowBlur = 8
  ctx.shadowOffsetY = 4
  ctx.beginPath()
  ctx.roundRect(sheetX, sheetY, sheetW, sheetH, 6)
  ctx.fill()
  ctx.restore()
  if (paper) {
    // 종이 질감(아주 옅게)
    ctx.save()
    ctx.beginPath()
    ctx.roundRect(sheetX, sheetY, sheetW, sheetH, 6)
    ctx.clip()
    ctx.globalAlpha = 0.05
    ctx.globalCompositeOperation = 'multiply'
    ctx.drawImage(paper, sheetX, sheetY, sheetW, sheetH)
    ctx.restore()
  }
  ctx.beginPath()
  ctx.roundRect(sheetX, sheetY, sheetW, sheetH, 6)
  ctx.stroke()
  // 탭과 종이 사이 선을 지운다
  ctx.fillStyle = C.surface
  ctx.fillRect(sheetX + 17, sheetY - 1, tabW - 2, 2)
  ctx.fillStyle = C.ink
  ctx.fillText(tabText, sheetX + 32, sheetY - 9)
  // 사건 주제색: 종이 윗변의 얇은 선
  ctx.fillStyle = themeColor
  ctx.fillRect(sheetX + 1, sheetY + 1, sheetW - 2, 3)

  // 제목 + 등급 도장
  ctx.font = `700 15px ${BODY}`
  const stampW = ctx.measureText(grade).width + 24
  ctx.fillStyle = C.ink
  ctx.font = `700 28px ${BODY}`
  ctx.fillText(fit(ctx, title, innerW - stampW - 16), left, yTitle)
  ctx.save()
  ctx.translate(left + innerW - stampW / 2, yTitle - 9)
  ctx.rotate((-2 * Math.PI) / 180)
  ctx.strokeStyle = C.ink
  ctx.lineWidth = 2
  ctx.beginPath()
  ctx.roundRect(-stampW / 2, -15, stampW, 30, 3)
  ctx.stroke()
  ctx.font = `700 15px ${BODY}`
  ctx.textAlign = 'center'
  ctx.fillStyle = C.ink
  ctx.fillText(grade, 0, 5)
  ctx.restore()

  // 구분선 사이 기록
  ctx.fillStyle = C.line
  ctx.fillRect(left, yRule1, innerW, 1)
  ctx.fillRect(left, yRule2, innerW, 1)
  ctx.fillStyle = C.ink
  ctx.font = `400 17px ${BODY}`
  ctx.fillText(stats, left, yStats)

  // 등장인물 얼굴 (3:4 칸, 그림 얼굴은 4:5 라서 아래에 붙인다)
  ctx.fillStyle = C.muted
  ctx.font = `700 14px ${BODY}`
  ctx.fillText('등장인물', left, yCastLabel)
  faces.forEach((img, i) => {
    const x = left + i * (faceW + gap)
    const drawH = Math.round((faceW * 5) / 4)
    ctx.save()
    ctx.beginPath()
    ctx.roundRect(x, yFaces, faceW, faceH, 3)
    ctx.clip()
    ctx.fillStyle = C.bg
    ctx.fillRect(x, yFaces, faceW, faceH)
    ctx.drawImage(img, x, yFaces + faceH - drawH, faceW, drawH)
    ctx.restore()
    ctx.strokeStyle = C.ink
    ctx.lineWidth = 1
    ctx.beginPath()
    ctx.roundRect(x + 0.5, yFaces + 0.5, faceW - 1, faceH - 1, 3)
    ctx.stroke()
    ctx.fillStyle = C.muted
    ctx.font = `400 12px ${BODY}`
    ctx.textAlign = 'center'
    ctx.fillText(fit(ctx, h.characters[i].role, faceW + gap - 2), x + faceW / 2, yFaces + faceH + 18)
    ctx.textAlign = 'left'
  })

  // 범인 · 칭호
  ctx.fillStyle = C.ink
  ctx.font = `700 20px ${BODY}`
  ctx.fillText(fit(ctx, lead, innerW), left, yLead)
  if (titleLine) ctx.fillText(fit(ctx, titleLine, innerW), left, yTitleLine)

  // 한 줄 하이라이트: 왼쪽 잉크 선 + 인용
  if (quote.length) {
    ctx.fillStyle = C.ink
    ctx.fillRect(left, yQuote - 18, 3, quote.length * 26 + 2)
    ctx.fillStyle = C.muted
    ctx.font = `400 16px ${BODY}`
    quote.forEach((line, i) => ctx.fillText(line, left + 16, yQuote + i * 26))
  }

  // 바닥글
  ctx.font = `400 12px ${MONO}`
  ctx.fillStyle = C.muted
  ctx.textAlign = 'right'
  ctx.fillText('The Suspects', W - sheetX, H - 18)
  ctx.textAlign = 'left'

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

// 개발용: 절차적 SVG 초상화를 한 장의 HTML 로 모아 눈으로 확인한다. (앱 코드가 아니다)
// 실행: npm run preview:portraits [출력경로]   (기본 출력: OS 임시 폴더의 portrait-preview.html)
import { writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { EMOTIONS } from '../src/api/types'
import { renderPortraitSvg } from '../src/character/faceRender'

const HAIRS = ['short', 'side', 'long', 'bun', 'curly', 'buzz', 'ponytail', 'bald']
const OUTFITS = ['suit', 'casual', 'hoodie', 'cleaner_uniform', 'security_uniform', 'chef', 'doctor', 'delivery', 'school_uniform', 'work_clothes', 'office_lanyard']
const ACCS = ['glasses', 'cap', 'badge', 'mop', 'radio', 'laptop', 'apron', '']
const SEEDS = [48211, 90177, 31337, 7741, 120934, 5, 77, 1024, 2468, 9999, 13579, 424242]

const cell = (svg: string, label: string, w = 200) =>
  `<figure style="margin:0;width:${w}px"><div style="width:${w}px">${svg.replace(/width="240" height="300"/, `width="${w}" height="${Math.round((w * 300) / 240)}"`)}</div><figcaption>${label}</figcaption></figure>`

const grid1 = SEEDS.map((s, i) =>
  cell(renderPortraitSvg(s, { hair: HAIRS[i % HAIRS.length], outfit: OUTFITS[i % OUTFITS.length], accessory: ACCS[i % ACCS.length] }), `seed ${s} · ${HAIRS[i % HAIRS.length]} · ${OUTFITS[i % OUTFITS.length]}`),
).join('')

const app = { hair: 'side', hair_color: '#2f2a28', outfit: 'office_lanyard', accessory: 'glasses' }
const grid2 = EMOTIONS.map((e) => cell(renderPortraitSvg(48211, app, { emotion: e }), e)).join('') +
  cell(renderPortraitSvg(48211, app, { mouthOpen: 0.8 }), 'speaking') +
  cell(renderPortraitSvg(48211, app, { blink: true }), 'blink')
const app2 = { hair: 'long', outfit: 'casual' }
const grid3 = EMOTIONS.map((e) => cell(renderPortraitSvg(90177, app2, { emotion: e }), e)).join('')
const small = SEEDS.map((s) => `<div style="width:64px">${renderPortraitSvg(s, {}, {}).replace(/width="240" height="300"/, 'width="64" height="80"')}</div>`).join('')

const html = `<!doctype html><meta charset="utf-8"><title>portrait preview</title>
<body style="font:13px sans-serif;background:#eee;padding:16px">
<h2>시드 12종 (무표정)</h2><div style="display:flex;flex-wrap:wrap;gap:12px">${grid1}</div>
<h2>감정 6종 + 말하기 + 깜빡임 (한 사람)</h2><div style="display:flex;flex-wrap:wrap;gap:12px">${grid2}</div>
<h2>감정 6종 (다른 사람)</h2><div style="display:flex;flex-wrap:wrap;gap:12px">${grid3}</div>
<h2>작은 크기 (64px)</h2><div style="display:flex;flex-wrap:wrap;gap:8px">${small}</div>`

const out = process.argv[2] ?? join(tmpdir(), 'portrait-preview.html')
writeFileSync(out, html)
console.log(out)

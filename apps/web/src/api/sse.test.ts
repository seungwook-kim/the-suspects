import { describe, expect, it } from 'vitest'
import { createSseParser, readSseJson } from './sse'

function collect(chunks: string[]): string[] {
  const out: string[] = []
  const p = createSseParser((d) => out.push(d))
  for (const c of chunks) p.push(c)
  p.flush()
  return out
}

describe('SSE 파서', () => {
  it('한 번에 온 여러 이벤트', () => {
    expect(collect(['data: {"a":1}\n\ndata: {"a":2}\n\n'])).toEqual(['{"a":1}', '{"a":2}'])
  })

  it('조각난 청크를 이어 붙인다 (줄 중간, 구분자 중간)', () => {
    const msg = 'data: {"type":"TEXT_MESSAGE_CONTENT","delta":"안녕"}\n\n'
    for (let cut = 1; cut < msg.length; cut++) {
      expect(collect([msg.slice(0, cut), msg.slice(cut)])).toEqual(['{"type":"TEXT_MESSAGE_CONTENT","delta":"안녕"}'])
    }
    expect(collect([...msg])).toHaveLength(1) // 한 글자씩
  })

  it('CRLF, 주석, event 줄, 여러 data 줄', () => {
    expect(collect([': keep-alive\r\n\r\nevent: x\r\ndata: a\r\ndata: b\r\n\r\n'])).toEqual(['a\nb'])
    expect(collect(['data: x\r', '\n\r', '\n'])).toEqual(['x'])
  })

  it('마지막 빈 줄 없이 끝나도 flush 로 내보낸다', () => {
    expect(collect(['data: {"k":1}'])).toEqual(['{"k":1}'])
  })

  it('fetch 본문의 바이트가 한글 중간에서 끊겨도 복원한다', async () => {
    const bytes = new TextEncoder().encode('data: {"delta":"가나다"}\n\ndata: {"delta":"라마"}\n\n')
    const stream = new ReadableStream<Uint8Array>({
      start(c) {
        for (let i = 0; i < bytes.length; i += 3) c.enqueue(bytes.slice(i, i + 3))
        c.close()
      },
    })
    const got: unknown[] = []
    for await (const ev of readSseJson(new Response(stream))) got.push(ev)
    expect(got).toEqual([{ delta: '가나다' }, { delta: '라마' }])
  })

  it('깨진 JSON 줄은 건너뛴다', async () => {
    const res = new Response('data: {oops\n\ndata: {"ok":true}\n\n')
    const got: unknown[] = []
    for await (const ev of readSseJson(res)) got.push(ev)
    expect(got).toEqual([{ ok: true }])
  })
})

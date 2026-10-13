// POST 응답으로 오는 SSE 스트림 파서. EventSource 는 GET 만 되므로 fetch + ReadableStream 을 쓴다.

export interface SseParser {
  /** 문자열 조각을 넣는다. 조각이 줄 중간에서 끊겨도 된다. */
  push(chunk: string): void
  /** 스트림이 끝났을 때 남은 마지막 이벤트를 비운다. */
  flush(): void
}

export function createSseParser(onData: (data: string) => void): SseParser {
  let buf = ''
  let dataLines: string[] = []

  const dispatch = () => {
    if (dataLines.length) {
      const data = dataLines.join('\n')
      dataLines = []
      onData(data)
    }
  }

  const handleLine = (line: string) => {
    if (line === '') return dispatch()
    if (line.startsWith(':')) return // 주석(keep-alive)
    const idx = line.indexOf(':')
    const field = idx === -1 ? line : line.slice(0, idx)
    let value = idx === -1 ? '' : line.slice(idx + 1)
    if (value.startsWith(' ')) value = value.slice(1)
    if (field === 'data') dataLines.push(value)
    // event:, id:, retry: 는 AG-UI 가 쓰지 않아 무시한다. type 은 JSON 안에 있다.
  }

  return {
    push(chunk) {
      buf += chunk
      let i: number
      // \r\n, \n, \r 모두 줄바꿈으로 본다. 끝이 \r 이면 \r\n 의 앞 절반일 수 있어 남겨 둔다.
      while ((i = buf.search(/\r\n|\n|\r(?!$)/)) !== -1) {
        const line = buf.slice(0, i)
        const m = buf.slice(i).match(/^(\r\n|\n|\r)/)!
        buf = buf.slice(i + m[0].length)
        handleLine(line)
      }
    },
    flush() {
      if (buf) {
        handleLine(buf.replace(/\r$/, ''))
        buf = ''
      }
      dispatch()
    },
  }
}

/** fetch Response 의 본문을 읽어 JSON 이벤트를 하나씩 내보낸다. */
export async function* readSseJson<T = unknown>(res: Response): AsyncGenerator<T> {
  if (!res.body) throw new Error('응답 본문이 없습니다')
  const reader = res.body.getReader()
  const decoder = new TextDecoder('utf-8') // stream:true 로 한글이 바이트 중간에 끊겨도 안전
  const queue: T[] = []
  const parser = createSseParser((data) => {
    try {
      queue.push(JSON.parse(data) as T)
    } catch {
      // 깨진 줄은 건너뛴다
    }
  })
  try {
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      parser.push(decoder.decode(value, { stream: true }))
      while (queue.length) yield queue.shift()!
    }
    parser.push(decoder.decode())
    parser.flush()
    while (queue.length) yield queue.shift()!
  } finally {
    reader.releaseLock()
  }
}

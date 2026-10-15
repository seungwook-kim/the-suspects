import { describe, expect, it } from 'vitest'
import { josa } from './format'

describe('josa', () => {
  it('받침을 보고 조사를 고른다 (서버와 같은 규칙)', () => {
    expect(josa('로비', '으로/로')).toBe('로비로')
    expect(josa('서버실', '으로/로')).toBe('서버실로')
    expect(josa('3층', '으로/로')).toBe('3층으로')
    expect(josa('보안데스크', '은/는')).toBe('보안데스크는')
    expect(josa('지하 주차장', '은/는')).toBe('지하 주차장은')
    expect(josa("'출입카드 기록'", '을/를')).toBe("'출입카드 기록'을")
    expect(josa('황지호', '이/가')).toBe('황지호가')
  })
  it('끝 글자를 못 읽으면 두 꼴을 같이 쓴다', () => {
    expect(josa('USB', '을/를')).toBe('USB을(를)')
    expect(josa('API', '으로/로')).toBe('API(으)로')
  })
})

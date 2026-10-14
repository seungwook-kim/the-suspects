import { describe, expect, it } from 'vitest'
import { findClaim } from './Dossier'

describe('findClaim (조서의 모순 문장 위치)', () => {
  it('진술이 대답의 일부면 그 부분만 가리킨다', () => {
    const a = '아니요. 바로 로비로 내려갔어요. 서버실은 근처에도 안 갔고요.'
    const at = findClaim(a, ['서버실은 근처에도 안 갔고요.'])
    expect(at && a.slice(at[0], at[1])).toBe('서버실은 근처에도 안 갔고요.')
  })
  it('대답 전체가 진술이면 전체, 여러 개가 맞으면 가장 긴 것', () => {
    expect(findClaim('집에 있었어요.', ['집에 있었어요.'])).toEqual([0, 8])
    const a = '11시에 퇴근했어요. 집에서 잤어요.'
    const at = findClaim(a, ['퇴근', '11시에 퇴근했어요.'])
    expect(at && a.slice(at[0], at[1])).toBe('11시에 퇴근했어요.')
  })
  it('맞는 진술이 없으면 null', () => {
    expect(findClaim('글쎄요.', ['집에 있었어요.'])).toBeNull()
    expect(findClaim('글쎄요.', [])).toBeNull()
  })
})

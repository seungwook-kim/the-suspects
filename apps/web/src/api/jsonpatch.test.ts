import { describe, expect, it } from 'vitest'
import { applyPatch, PatchError } from './jsonpatch'

const doc = () => ({ a: 1, list: [1, 2, 3], obj: { x: { y: 'z' } }, 'a/b': 1, 'm~n': 2 })

describe('JSON Patch (RFC 6902)', () => {
  it('add / replace / remove', () => {
    const d = doc()
    const r = applyPatch(d, [
      { op: 'add', path: '/b', value: 2 },
      { op: 'replace', path: '/a', value: 10 },
      { op: 'remove', path: '/obj/x/y' },
    ])
    expect(r).toMatchObject({ a: 10, b: 2, obj: { x: {} } })
    expect(d).toEqual(doc()) // 원본은 바뀌지 않는다
  })

  it('배열: 끝에 추가(-), 중간 삽입, 삭제', () => {
    expect(applyPatch(doc(), [{ op: 'add', path: '/list/-', value: 4 }]).list).toEqual([1, 2, 3, 4])
    expect(applyPatch(doc(), [{ op: 'add', path: '/list/1', value: 9 }]).list).toEqual([1, 9, 2, 3])
    expect(applyPatch(doc(), [{ op: 'remove', path: '/list/0' }]).list).toEqual([2, 3])
    expect(applyPatch(doc(), [{ op: 'replace', path: '/list/2', value: 'c' }]).list).toEqual([1, 2, 'c'])
  })

  it('이스케이프 ~0 ~1', () => {
    const r = applyPatch(doc(), [
      { op: 'replace', path: '/a~1b', value: 5 },
      { op: 'replace', path: '/m~0n', value: 6 },
    ])
    expect(r['a/b']).toBe(5)
    expect(r['m~n']).toBe(6)
  })

  it('move / copy / test', () => {
    const r = applyPatch(doc(), [
      { op: 'move', from: '/obj/x', path: '/moved' },
      { op: 'copy', from: '/list', path: '/list2' },
      { op: 'test', path: '/a', value: 1 },
    ]) as Record<string, unknown>
    expect(r.moved).toEqual({ y: 'z' })
    expect(r.list2).toEqual([1, 2, 3])
    expect((r.obj as Record<string, unknown>).x).toBeUndefined()
  })

  it('잘못된 패치는 PatchError', () => {
    expect(() => applyPatch(doc(), [{ op: 'replace', path: '/nope', value: 1 }])).toThrow(PatchError)
    expect(() => applyPatch(doc(), [{ op: 'remove', path: '/list/9' }])).toThrow(PatchError)
    expect(() => applyPatch(doc(), [{ op: 'test', path: '/a', value: 2 }])).toThrow(PatchError)
  })

  it('변경되지 않은 가지는 같은 참조를 유지한다', () => {
    const d = doc()
    const r = applyPatch(d, [{ op: 'replace', path: '/a', value: 2 }])
    expect(r.obj).toBe(d.obj)
  })
})

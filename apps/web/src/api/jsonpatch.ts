// RFC 6902 JSON Patch (불변 적용). 필요한 연산만 구현: add/remove/replace/move/copy/test.
import type { JsonPatchOp } from './types'

export class PatchError extends Error {}

function parsePointer(path: string): string[] {
  if (path === '') return []
  if (!path.startsWith('/')) throw new PatchError(`잘못된 경로: ${path}`)
  return path
    .slice(1)
    .split('/')
    .map((s) => s.replace(/~1/g, '/').replace(/~0/g, '~'))
}

type Json = unknown
type Container = Record<string, Json> | Json[]

function clone<T extends Container>(c: T): T {
  return (Array.isArray(c) ? [...c] : { ...c }) as T
}

function getAt(doc: Json, tokens: string[]): Json {
  let cur = doc
  for (const t of tokens) {
    if (Array.isArray(cur)) {
      const i = Number(t)
      if (!Number.isInteger(i) || i < 0 || i >= cur.length) throw new PatchError(`없는 인덱스: ${t}`)
      cur = cur[i]
    } else if (cur && typeof cur === 'object') {
      if (!(t in cur)) throw new PatchError(`없는 키: ${t}`)
      cur = (cur as Record<string, Json>)[t]
    } else throw new PatchError(`경로를 따라갈 수 없음: ${t}`)
  }
  return cur
}

/** 마지막 토큰의 부모 컨테이너(복사본)를 fn 에 넘겨 고친 새 문서를 만든다. 경로 위 컨테이너만 복사한다. */
function updateAt(doc: Json, tokens: string[], fn: (parent: Container, key: string) => Container): Json {
  if (tokens.length === 0) throw new PatchError('루트 연산은 지원하지 않음')
  const rec = (node: Json, depth: number): Json => {
    if (!node || typeof node !== 'object') throw new PatchError('경로를 따라갈 수 없음')
    const copy = clone(node as Container)
    const key = tokens[depth]
    if (depth === tokens.length - 1) return fn(copy, key)
    if (Array.isArray(copy)) {
      const i = Number(key)
      if (!Number.isInteger(i) || i < 0 || i >= copy.length) throw new PatchError(`없는 인덱스: ${key}`)
      copy[i] = rec(copy[i], depth + 1)
    } else {
      if (!(key in copy)) throw new PatchError(`없는 키: ${key}`)
      copy[key] = rec(copy[key], depth + 1)
    }
    return copy
  }
  return rec(doc, 0)
}

function addAt(doc: Json, path: string, value: Json): Json {
  const tokens = parsePointer(path)
  if (tokens.length === 0) return value
  return updateAt(doc, tokens, (parent, key) => {
    if (Array.isArray(parent)) {
      const i = key === '-' ? parent.length : Number(key)
      if (!Number.isInteger(i) || i < 0 || i > parent.length) throw new PatchError(`잘못된 인덱스: ${key}`)
      parent.splice(i, 0, value)
    } else parent[key] = value
    return parent
  })
}

function removeAt(doc: Json, path: string): Json {
  const tokens = parsePointer(path)
  return updateAt(doc, tokens, (parent, key) => {
    if (Array.isArray(parent)) {
      const i = Number(key)
      if (!Number.isInteger(i) || i < 0 || i >= parent.length) throw new PatchError(`없는 인덱스: ${key}`)
      parent.splice(i, 1)
    } else {
      if (!(key in parent)) throw new PatchError(`없는 키: ${key}`)
      delete parent[key]
    }
    return parent
  })
}

function replaceAt(doc: Json, path: string, value: Json): Json {
  const tokens = parsePointer(path)
  if (tokens.length === 0) return value
  return updateAt(doc, tokens, (parent, key) => {
    if (Array.isArray(parent)) {
      const i = Number(key)
      if (!Number.isInteger(i) || i < 0 || i >= parent.length) throw new PatchError(`없는 인덱스: ${key}`)
      parent[i] = value
    } else {
      if (!(key in parent)) throw new PatchError(`없는 키: ${key}`)
      parent[key] = value
    }
    return parent
  })
}

function deepEqual(a: Json, b: Json): boolean {
  return JSON.stringify(a) === JSON.stringify(b)
}

export function applyPatch<T>(doc: T, ops: JsonPatchOp[]): T {
  let cur: Json = doc
  for (const op of ops) {
    switch (op.op) {
      case 'add':
        cur = addAt(cur, op.path, op.value)
        break
      case 'remove':
        cur = removeAt(cur, op.path)
        break
      case 'replace':
        cur = replaceAt(cur, op.path, op.value)
        break
      case 'move': {
        if (op.from === undefined) throw new PatchError('move 에 from 이 없음')
        const v = getAt(cur, parsePointer(op.from))
        cur = addAt(removeAt(cur, op.from), op.path, v)
        break
      }
      case 'copy': {
        if (op.from === undefined) throw new PatchError('copy 에 from 이 없음')
        cur = addAt(cur, op.path, structuredClone(getAt(cur, parsePointer(op.from))))
        break
      }
      case 'test':
        if (!deepEqual(getAt(cur, parsePointer(op.path)), op.value)) throw new PatchError(`test 실패: ${op.path}`)
        break
      default:
        throw new PatchError(`지원하지 않는 연산: ${(op as JsonPatchOp).op}`)
    }
  }
  return cur as T
}

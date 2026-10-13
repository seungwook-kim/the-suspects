"""문서 종류별 청킹 (PRD §11.4.2) + Contextual Retrieval + 부모-자식 청크.

| doc_type                    | 전략                                                         |
|:----------------------------|:-------------------------------------------------------------|
| manual, wiki, notice, report | 섹션 단위. 길면 문단 단위 자식 청크 (겹침 12%)               |
| chat_log                    | 메시지의 시각을 읽어 10분 창 단위. 화자·time_window 메타데이터 |
| minutes                     | 안건(섹션) 1개 = 청크 1개                                    |
| statement, diary, email     | 문서 단위, 길면 문단 단위 (400토큰)                          |
| (증거)                      | 증거 1개 = 청크 1개                                          |

- 부모 청크의 chunk_strategy는 "..._parent"로 끝나며 검색 후보에서는 제외하고 부모 확장에만 쓴다.
- 청크의 `context`(작가가 섹션별로 쓴 문맥 설명)는 색인 시 내용 앞에 붙는다.
- 정형 로그(출입·결제·통화·접속)는 청킹하지 않고 SQL 테이블(records)로 간다.
"""

from __future__ import annotations

import re

from server.rag.tokenize import approx_token_count
from server.schemas import CaseDocument, Chunk, DocSection, Evidence

PARENT_SUFFIX = "_parent"
_CHAT_LINE = re.compile(r"^\s*\[(\d{1,2}):(\d{2})\]\s*([^:]{1,30}?)\s*:\s*(.*)$")
_SENT_SPLIT = re.compile(r"(?<=[.!?。])\s+")

SECTION_TYPES = {"manual", "wiki", "notice", "report"}
DOC_TYPES_PARAGRAPH = {"statement", "diary", "email"}


def is_parent(chunk: Chunk) -> bool:
    return chunk.chunk_strategy.endswith(PARENT_SUFFIX)


def _cap(text: str, max_tokens: int) -> str:
    """부모 청크 길이 상한."""
    if approx_token_count(text) <= max_tokens:
        return text
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if approx_token_count(text[:mid]) <= max_tokens:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo].rstrip() + " ..."


def split_text(text: str, max_tokens: int, overlap_ratio: float) -> list[str]:
    """문단(줄바꿈) 기준으로 묶고, 문단이 너무 길면 문장 기준으로 자른다. 앞 청크의 끝 문장을 겹쳐 붙인다."""
    if approx_token_count(text) <= max_tokens:
        return [text.strip()]
    units: list[str] = []
    for para in [p.strip() for p in text.split("\n") if p.strip()]:
        if approx_token_count(para) <= max_tokens:
            units.append(para)
        else:
            units.extend(s.strip() for s in _SENT_SPLIT.split(para) if s.strip())
    chunks: list[list[str]] = []
    cur: list[str] = []
    for u in units:
        if cur and approx_token_count("\n".join(cur + [u])) > max_tokens:
            chunks.append(cur)
            cur = []
        cur.append(u)
    if cur:
        chunks.append(cur)
    out: list[str] = []
    for i, group in enumerate(chunks):
        body = list(group)
        if i > 0 and overlap_ratio > 0:
            budget = int(max_tokens * overlap_ratio)
            tail: list[str] = []
            for u in reversed(chunks[i - 1]):
                if approx_token_count("\n".join([u] + tail)) > budget:
                    break
                tail.insert(0, u)
            body = tail + body
        out.append("\n".join(body))
    return out


def _context(doc: CaseDocument, sec: DocSection, extra: str = "") -> str:
    base = f"[{doc.title} / {sec.heading}]"
    parts = [base, sec.context.strip(), extra.strip()]
    return " ".join(p for p in parts if p)


def _new_chunk(doc: CaseDocument, case_id: str, slot_id: str, **kw) -> Chunk:
    return Chunk(
        doc_id=doc.id, collection="case", case_id=case_id, slot_id=slot_id, doc_title=doc.title,
        visibility=list(doc.visibility), **kw,
    )


def _chunk_sections(
    doc: CaseDocument, case_id: str, slot_id: str, max_tokens: int, overlap: float, parent_max: int,
    strategy: str,
) -> list[Chunk]:
    out: list[Chunk] = []
    for si, sec in enumerate(doc.sections):
        text = sec.text.strip()
        pieces = split_text(text, max_tokens, overlap)
        ctx = _context(doc, sec)
        sec_id = f"{doc.id}#s{si}"
        if len(pieces) == 1:
            out.append(
                _new_chunk(
                    doc, case_id, slot_id, chunk_id=sec_id, section_path=sec.heading, chunk_strategy=strategy,
                    content=pieces[0], context=ctx, token_count=approx_token_count(pieces[0]),
                )
            )
            continue
        out.append(
            _new_chunk(
                doc, case_id, slot_id, chunk_id=sec_id, section_path=sec.heading,
                chunk_strategy=strategy + PARENT_SUFFIX, content=_cap(text, parent_max), context=ctx,
                token_count=approx_token_count(text),
            )
        )
        for ci, piece in enumerate(pieces):
            out.append(
                _new_chunk(
                    doc, case_id, slot_id, chunk_id=f"{sec_id}.c{ci}", parent_id=sec_id,
                    section_path=f"{sec.heading} > 문단 {ci + 1}", chunk_strategy=strategy + "_child",
                    content=piece, context=ctx, token_count=approx_token_count(piece),
                )
            )
    return out


def _chunk_chat(
    doc: CaseDocument, case_id: str, slot_id: str, max_tokens: int, window: int, parent_max: int
) -> list[Chunk]:
    out: list[Chunk] = []
    day_offset = 0
    prev = -1
    for si, sec in enumerate(doc.sections):
        msgs: list[tuple[int, str, str]] = []  # (game time, speaker, line text)
        for line in sec.text.splitlines():
            m = _CHAT_LINE.match(line)
            if m:
                t = int(m.group(1)) * 60 + int(m.group(2))
                if prev >= 0 and t + day_offset < prev:
                    day_offset += 1440
                t += day_offset
                prev = t
                msgs.append((t, m.group(3).strip(), line.strip()))
            elif msgs and line.strip():
                t0, sp, txt = msgs[-1]
                msgs[-1] = (t0, sp, txt + " " + line.strip())
        sec_id = f"{doc.id}#s{si}"
        ctx = _context(doc, sec)
        out.append(
            _new_chunk(
                doc, case_id, slot_id, chunk_id=sec_id, section_path=sec.heading,
                chunk_strategy="chat_section_parent", content=_cap(sec.text.strip(), parent_max), context=ctx,
                time_window=(msgs[0][0], msgs[-1][0]) if msgs else None, token_count=approx_token_count(sec.text),
            )
        )
        buckets: dict[int, list[tuple[int, str, str]]] = {}
        for t, sp, txt in msgs:
            buckets.setdefault(t // window * window, []).append((t, sp, txt))
        for start in sorted(buckets):
            group: list[list[tuple[int, str, str]]] = [[]]
            for msg in buckets[start]:
                if group[-1] and approx_token_count("\n".join(x[2] for x in group[-1] + [msg])) > max_tokens:
                    group.append([])
                group[-1].append(msg)
            for gi, g in enumerate(group):
                speakers = list(dict.fromkeys(x[1] for x in g))
                text = "\n".join(x[2] for x in g)
                hh, mm = divmod(start % 1440, 60)
                cid = f"{doc.id}#s{si}.w{start:04d}" + (f".{gi}" if gi else "")
                out.append(
                    _new_chunk(
                        doc, case_id, slot_id, chunk_id=cid, parent_id=sec_id,
                        section_path=f"{sec.heading} > {hh:02d}:{mm:02d}", chunk_strategy="chat_window",
                        content=text, context=_context(doc, sec, f"{hh:02d}:{mm:02d} 무렵 대화, 화자 {', '.join(speakers)}"),
                        speaker=", ".join(speakers), time_window=(start, start + window),
                        game_time=g[0][0], token_count=approx_token_count(text),
                    )
                )
    return out


def chunk_document(
    doc: CaseDocument,
    case_id: str,
    slot_id: str,
    *,
    max_tokens: int = 400,
    overlap_ratio: float = 0.12,
    window_minutes: int = 10,
    parent_max_tokens: int = 900,
    contextual: bool = True,
) -> list[Chunk]:
    """문서를 청크 목록으로 바꾼다. contextual=False면 context를 비운다(적용 전후 비교용)."""
    if doc.doc_type == "chat_log":
        chunks = _chunk_chat(doc, case_id, slot_id, max_tokens, window_minutes, parent_max_tokens)
    elif doc.doc_type == "minutes":
        chunks = _chunk_sections(doc, case_id, slot_id, 10**9, 0.0, parent_max_tokens, "agenda")
    elif doc.doc_type in DOC_TYPES_PARAGRAPH:
        chunks = _chunk_sections(doc, case_id, slot_id, max_tokens, overlap_ratio, parent_max_tokens, "paragraph")
    else:
        chunks = _chunk_sections(doc, case_id, slot_id, max_tokens, overlap_ratio, parent_max_tokens, "section")
    if not contextual:
        for c in chunks:
            c.context = ""
    return chunks


def chunk_evidence(ev: Evidence, case_id: str, slot_id: str, *, contextual: bool = True) -> Chunk:
    """증거 1개 = 청크 1개. id는 `ev:<증거id>`."""
    return Chunk(
        chunk_id=f"ev:{ev.id}", doc_id=f"ev:{ev.id}", collection="case", case_id=case_id, slot_id=slot_id,
        doc_title=ev.name, section_path=None, chunk_strategy="evidence", content=ev.content,
        context=f"[증거 {ev.id} / {ev.kind}] {ev.name}" if contextual else "",
        visibility=list(ev.visibility), kb_meta={"evidence_id": ev.id, "is_key": ev.is_key},
        token_count=approx_token_count(ev.content),
    )

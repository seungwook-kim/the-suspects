"""모델이 아직 쓰고 있는 JSON 원문에서 문자열 필드를 지금까지 나온 만큼 읽는다(답을 첫 문장부터 보여 주기용).

예: '{"emotion": "nervous", "text": "그게요... 집에'  →  text = '그게요... 집에' (아직 안 닫힘)
"""

from __future__ import annotations

import re

_ESC = {'"': '"', "\\": "\\", "/": "/", "b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t"}


def partial_string_field(raw: str, field: str) -> tuple[str, bool] | None:
    """(지금까지의 값, 문자열이 닫혔는지). 필드가 아직 나오지 않았으면 None.
    끝에서 잘린 이스케이프(\\, \\u00 등)는 다음 조각이 올 때까지 읽지 않는다."""
    m = re.search(r'"' + re.escape(field) + r'"\s*:\s*"', raw)
    if not m:
        return None
    out: list[str] = []
    i = m.end()
    while i < len(raw):
        ch = raw[i]
        if ch == '"':
            return "".join(out), True
        if ch != "\\":
            out.append(ch)
            i += 1
            continue
        if i + 1 >= len(raw):
            break
        nxt = raw[i + 1]
        if nxt == "u":
            hexs = raw[i + 2:i + 6]
            if len(hexs) < 4:
                break
            try:
                out.append(chr(int(hexs, 16)))
            except ValueError:
                pass
            i += 6
            continue
        out.append(_ESC.get(nxt, nxt))
        i += 2
    return "".join(out), False


_DONE = re.compile(r"[.!?…~]+[\"'”’)\]]*(?=\s)")


def complete_sentences(text: str, closed: bool) -> str:
    """끝난 문장까지만. 문자열이 닫혔으면 전부, 아니면 마지막 문장 끝 표시(. ! ? … ~) 뒤에 공백이 온 곳까지."""
    if closed:
        return text.rstrip()
    end = 0
    for m in _DONE.finditer(text):
        end = m.end()
    return text[:end]

"""한국어 형태소 분석기 없이 쓰는 토크나이저.

색인과 질의에 같은 함수를 쓴다.
- 공백/기호 단위 단어 (소문자)
- 한글 단어는 2-gram 추가 (조사·어미가 붙어도 부분 일치)
- 3글자 이상 한글 단어는 끝 조사 한 글자를 뗀 어간 토큰 추가
- 시각 표현("23:05", "밤 11시 5분", "오후 11시 반")을 정규화한 토큰 추가
    "@2305" (분 단위) 와 "@h23" (시 단위)
"""

from __future__ import annotations

import math
import re

_WORD_RE = re.compile(r"[0-9A-Za-z_가-힣]+")
_HANGUL_RE = re.compile(r"^[가-힣]+$")
_PARTICLES = set("은는이가을를에의도로와과만")

_CLOCK_RE = re.compile(r"(?<!\d)([01]?\d|2[0-3]):([0-5]\d)(?!\d)")
_KOR_TIME_RE = re.compile(
    r"(?:(오전|오후|밤|새벽|아침|저녁|낮)\s*)?(\d{1,2})\s*시(?:\s*(?:(\d{1,2})\s*분|(반)))?"
)


def approx_token_count(text: str) -> int:
    """LLM 토큰 수 근사 (한글은 글자당 약 0.6토큰, 그 밖은 4글자당 1토큰)."""
    hangul = sum(1 for ch in text if "가" <= ch <= "힣")
    other = sum(1 for ch in text if not ch.isspace() and not ("가" <= ch <= "힣"))
    return math.ceil(hangul * 0.6 + other / 4)


def parse_times(text: str) -> list[int]:
    """텍스트 속 시각 표현을 '하루 중 분'(0~1439) 목록으로 바꾼다. 모호한 표현은 후보를 모두 낸다."""
    found: list[int] = []
    for m in _CLOCK_RE.finditer(text):
        found.append(int(m.group(1)) * 60 + int(m.group(2)))
    for m in _KOR_TIME_RE.finditer(text):
        prefix, hour_s, minute_s, half = m.group(1), int(m.group(2)), m.group(3), m.group(4)
        if hour_s > 24:
            continue
        minute = 30 if half else int(minute_s) if minute_s else 0
        if minute > 59:
            continue
        hours: list[int]
        if prefix in ("오후", "저녁"):
            hours = [hour_s + 12 if hour_s < 12 else hour_s]
        elif prefix == "밤":
            hours = [0] if hour_s == 12 else [hour_s + 12] if 6 <= hour_s < 12 else [hour_s]
        elif prefix in ("오전", "새벽", "아침"):
            hours = [0] if hour_s == 12 else [hour_s]
        elif prefix == "낮":
            hours = [12] if hour_s == 12 else [hour_s + 12] if hour_s < 6 else [hour_s]
        else:  # 접두어 없음: 24시간제일 수도, 12시간제일 수도 있다
            hours = [hour_s % 24]
            if 1 <= hour_s <= 11:
                hours.append(hour_s + 12)
        for h in hours:
            found.append((h % 24) * 60 + minute)
    return found


def time_tokens(text: str) -> list[str]:
    out: list[str] = []
    for minute in parse_times(text):
        h, mi = divmod(minute, 60)
        out.append(f"@{h:02d}{mi:02d}")
        out.append(f"@h{h:02d}")
    return out


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for word in _WORD_RE.findall(text.lower()):
        tokens.append(word)
        if _HANGUL_RE.match(word):
            if len(word) >= 3 and word[-1] in _PARTICLES:
                tokens.append(word[:-1])
            if len(word) >= 2:
                tokens.extend(word[i : i + 2] for i in range(len(word) - 1))
    tokens.extend(time_tokens(text))
    return tokens

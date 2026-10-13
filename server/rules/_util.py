"""규칙 엔진 공용 유틸. 순수 함수만 둔다."""

from __future__ import annotations

import hashlib


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def stable_unit(*parts: object) -> float:
    """입력이 같으면 항상 같은 [0, 1) 값을 돌려준다(파이썬 hash() 는 실행마다 달라서 sha256 사용)."""
    raw = "\x1f".join(str(p) for p in parts).encode("utf-8")
    digest = hashlib.sha256(raw).digest()
    return int.from_bytes(digest[:8], "big") / 2**64

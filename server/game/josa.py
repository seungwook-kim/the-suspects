"""한국어 조사 고르기: 이름 끝 글자의 받침을 보고 "은/는", "이/가", "을/를", "과/와", "으로/로"를 붙인다.

화면 문장에 "보안데스크은(는)", "로비(으)로"처럼 두 꼴이 같이 나오던 것을 고친다(2026-10-15).
끝 글자를 읽을 수 없으면(영문 약어 등) 두 꼴을 같이 쓴다.
"""

from __future__ import annotations

# 숫자를 읽었을 때 받침 (0 영, 1 일, 2 이, 3 삼, 4 사, 5 오, 6 육, 7 칠, 8 팔, 9 구)
_DIGIT_BATCHIM = {"0": True, "1": True, "2": False, "3": True, "4": False, "5": False, "6": True, "7": True,
                  "8": True, "9": False}
_DIGIT_RIEUL = {"1", "7", "8"}  # 일·칠·팔: ㄹ 받침
_PAIRS = {"은/는": ("은", "는"), "이/가": ("이", "가"), "을/를": ("을", "를"), "과/와": ("과", "와"),
          "아/야": ("아", "야"), "으로/로": ("으로", "로")}


def _last(word: str) -> str:
    """괄호·따옴표·공백을 뺀 마지막 글자."""
    s = word.rstrip(" '\"’”)]")
    return s[-1] if s else ""


def batchim(word: str) -> tuple[bool, bool] | None:
    """(받침 있음, 그 받침이 ㄹ). 알 수 없으면 None."""
    ch = _last(word)
    if "가" <= ch <= "힣":
        jong = (ord(ch) - 0xAC00) % 28
        return jong != 0, jong == 8
    if ch in _DIGIT_BATCHIM:
        return _DIGIT_BATCHIM[ch], ch in _DIGIT_RIEUL
    return None


def josa(word: str, pair: str) -> str:
    """word에 맞는 조사를 붙여 돌려준다. 예: josa("로비", "으로/로") → "로비로", josa("서버실", "으로/로") → "서버실로"."""
    a, b = _PAIRS[pair]
    info = batchim(word)
    if info is None:
        return f"{word}{a}({b})" if pair != "으로/로" else f"{word}(으)로"
    has, rieul = info
    if pair == "으로/로":
        return word + ("으로" if has and not rieul else "로")
    return word + (a if has else b)

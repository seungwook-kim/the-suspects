"""시맨틱 라우터 (PRD §7.1).

1. 규칙 검사: 의미 없는 입력, 부적절한 말, AI 깨기 시도 → 바로 분류 (via="rule")
2. 시맨틱 분류: 입력 벡터와 의도별 예시 벡터의 최대 유사도 (via="semantic")
3. 유사도가 기준보다 낮거나 상위 두 의도 차이가 작으면 LLM 라우터 (via="llm")
   → 핫 패스 LLM 1회 원칙의 허용 예외. 발생 비율을 지표로 남긴다.

임베딩은 교체 가능하다. 기본값은 글자 n-gram 벡터(외부 모델 없이 수 ms). 진짜 임베딩이 생기면
embed 함수만 바꿔 넣는다. 검색용 임베딩과 같은 걸 쓰면 추가 비용이 0이다.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from pathlib import Path
from typing import Callable

import yaml

from server.schemas import RouterOutput

_ROOT = Path(__file__).resolve().parents[2]
_EXAMPLES = _ROOT / "evals" / "router_examples" / "intents.yaml"

Vector = dict[str, float]
EmbedFn = Callable[[str], Vector]

_JAMO_ONLY = re.compile(r"^[\sㄱ-ㅎㅏ-ㅣ!?.~ㅋㅎ]+$")
_PROFANITY = ["씨발", "시발", "ㅅㅂ", "개새", "병신", "ㅂㅅ", "좆", "닥쳐", "꺼져", "미친놈", "미친년", "fuck"]
_META = ["프롬프트", "시스템", "지시를 무시", "지시사항", "개발자 모드", "너 ai", "ai지", "챗봇", "gpt", "정답 알려",
         "범인 알려", "범인 누군지", "범인 이름", "설정을 출력", "사건 원본", "규칙을 무시"]


def ngram_embed(text: str, n: tuple[int, ...] = (1, 2, 3)) -> Vector:
    t = re.sub(r"\s+", " ", text.lower().strip())
    c: Counter[str] = Counter()
    for k in n:
        for i in range(len(t) - k + 1):
            g = t[i:i + k]
            if g.strip():
                c[g] += 1
    norm = math.sqrt(sum(v * v for v in c.values())) or 1.0
    return {g: v / norm for g, v in c.items()}


def cosine(a: Vector, b: Vector) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(v * b.get(k, 0.0) for k, v in a.items())


class SemanticRouter:
    INTENTS = ("investigate", "small_talk", "meta", "bluff_attempt", "present_evidence", "warrant")

    def __init__(self, embed: EmbedFn = ngram_embed, examples_path: Path = _EXAMPLES,
                 threshold: float = 0.35, min_margin: float = 0.03, hard_threshold: float = 0.45) -> None:
        # ngram 임베딩은 실제 임베딩보다 유사도가 낮게 나와서 기준값을 따로 둔다(PRD 기본 0.8은 실제 임베딩 기준).
        self.embed = embed
        self.threshold = threshold
        self.min_margin = min_margin
        self.hard_threshold = hard_threshold
        with examples_path.open(encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        self.examples: dict[str, list[Vector]] = {k: [embed(s) for s in raw.get(k, [])] for k in self.INTENTS}
        self.hard_examples = [embed(s) for s in raw.get("hard", [])]

    def rule_check(self, text: str) -> RouterOutput | None:
        t = text.strip()
        low = t.lower()
        if not t or _JAMO_ONLY.match(t) or len(re.sub(r"[^가-힣a-zA-Z0-9]", "", t)) < 2:
            return RouterOutput(kind="gibberish", via="rule")
        if any(p in low for p in _PROFANITY):
            return RouterOutput(kind="inappropriate", via="rule")
        if any(m in low for m in _META):
            return RouterOutput(kind="meta", via="rule")
        return None

    def classify(self, text: str, target_npc: str | None = None) -> RouterOutput:
        ruled = self.rule_check(text)
        if ruled:
            ruled.target_npc = target_npc
            return ruled
        v = self.embed(text)
        scores = sorted(
            ((max((cosine(v, e) for e in exs), default=0.0), intent) for intent, exs in self.examples.items()),
            reverse=True,
        )
        (best, intent), (second, _) = scores[0], scores[1]
        hard = max((cosine(v, e) for e in self.hard_examples), default=0.0) >= self.hard_threshold
        out = RouterOutput(kind=intent, target_npc=target_npc, topic=text[:40],
                           difficulty="hard" if hard else "easy", via="semantic", confidence=round(best, 3))
        if best < self.threshold or best - second < self.min_margin:
            out.via = "llm"  # 호출자가 LLM 라우터로 넘긴다
        return out

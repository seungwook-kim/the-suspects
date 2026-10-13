"""F.19 법 조문 인용 검증. 순수 함수.

검증 3가지 (하나라도 실패하면 차단):
  1. article_not_found  : 조문 번호가 지식 베이스에 있음
  2. quote_not_found    : 인용 문구가 원문의 부분 문자열(공백 정규화 후). 최소 min_quote_chars 자(공백 정규화 후 길이)
                          미만이면 quote_too_short
  3. not_effective      : 지식 베이스 조문의 시행일 범위가 사건 날짜를 포함함
재작성 횟수 상한은 citation.max_rewrites, 그래도 실패하면 칸을 "검토 필요"로 비운다(should_leave_blank).
관련성(LLM 평가)은 여기서 하지 않고 20% 표본만 결정적으로 고른다(sampled_for_relevance).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import date

from pydantic import BaseModel

from server.config import GameConfig

from ._util import stable_unit

REVIEW_NEEDED = "검토 필요"


class KBArticle(BaseModel):
    article_no: str
    text: str
    effective_from: date
    effective_to: date | None = None  # None 이면 현재까지 유효


class CitationResult(BaseModel):
    ok: bool
    failures: list[str]


def normalize(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def verify_citation(
    cfg: GameConfig,
    kb: Mapping[str, KBArticle],
    article_no: str,
    quote: str,
    case_date: date,
) -> CitationResult:
    art = kb.get(article_no)
    if art is None:
        return CitationResult(ok=False, failures=["article_not_found"])
    failures: list[str] = []
    q = normalize(quote)
    if len(q) < cfg.citation.min_quote_chars:
        failures.append("quote_too_short")
    elif q not in normalize(art.text):
        failures.append("quote_not_found")
    if case_date < art.effective_from or (art.effective_to is not None and case_date > art.effective_to):
        failures.append("not_effective")
    return CitationResult(ok=not failures, failures=failures)


def should_leave_blank(cfg: GameConfig, rewrites_used: int, result: CitationResult) -> bool:
    """실패했고 재작성 상한을 다 썼으면 적용 법조 칸을 비운다."""
    return (not result.ok) and rewrites_used >= cfg.citation.max_rewrites


def sampled_for_relevance(cfg: GameConfig, report_id: str, article_no: str) -> bool:
    """관련성 LLM 평가 표본 여부(relevance_sample 비율, 같은 입력이면 같은 결과)."""
    return stable_unit("citation", report_id, article_no) < cfg.citation.relevance_sample

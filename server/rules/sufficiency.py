"""F.6 용의자별 증거 충분도 (0~1)와 게이지(0~5칸). 순수 함수.

계산 규칙 (애매한 부분을 이렇게 정했다):
- 수첩(notebook.evidence_ids)에 있고 linked_suspects 에 그 용의자가 있는 증거만 센다.
- 핵심 증거(is_key): 증거마다 sufficiency.key 를 더한다.
- 동기/수단/기회: 증거의 element_tags 에 따라 *종류별로 한 번만* 더한다(같은 종류 증거 여러 개여도 1회).
  한 증거가 여러 태그를 가지면 태그마다 더한다.
- 진술 모순: 수첩의 Contradiction 중 거짓말 장부(lie_id)의 거짓말쟁이가 그 용의자인 것, 서로 다른 lie_id 마다 contradiction.
- 일반 진술: kind == "testimony" 인 연결 증거, 그리고 그 용의자의 수첩 진술(NotebookStatement) 중
  모순에 쓰이지 않은 것마다 sufficiency.testimony.
- 합계는 sufficiency.max 로 자른다.
"""

from __future__ import annotations

from collections.abc import Iterable

from server.config import GameConfig
from server.schemas import CaseBible, Evidence, Notebook

from ._util import clamp


def score_parts(
    cfg: GameConfig,
    evidences: Iterable[Evidence],
    contradiction_count: int = 0,
    plain_statement_count: int = 0,
    *,
    contradiction_weight: float | None = None,
) -> float:
    """이미 추려 낸 증거 목록으로 충분도를 계산한다(역할 반전 모드에서도 재사용)."""
    w = cfg.sufficiency
    total = 0.0
    tags: set[str] = set()
    for ev in evidences:
        if ev.is_key:
            total += w.key
        tags.update(ev.element_tags)
        if ev.kind == "testimony":
            total += w.testimony
    total += sum(getattr(w, t) for t in tags if t in ("motive", "means", "opportunity"))
    cw = w.contradiction if contradiction_weight is None else contradiction_weight
    total += contradiction_count * cw
    total += plain_statement_count * w.testimony
    return clamp(round(total, 6), 0.0, w.max)


def linked_evidence(case: CaseBible, notebook: Notebook, suspect_id: str) -> list[Evidence]:
    owned = set(notebook.evidence_ids)
    return [e for e in case.evidence if e.id in owned and suspect_id in e.linked_suspects]


def contradiction_lie_ids(case: CaseBible, notebook: Notebook, suspect_id: str) -> set[str]:
    liar_of = {lie.id: lie.liar_id for lie in case.lie_ledger}
    return {c.lie_id for c in notebook.contradictions if liar_of.get(c.lie_id) == suspect_id}


def suspect_sufficiency(cfg: GameConfig, case: CaseBible, notebook: Notebook, suspect_id: str) -> float:
    evs = linked_evidence(case, notebook, suspect_id)
    lie_ids = contradiction_lie_ids(case, notebook, suspect_id)
    used_statements = {c.statement_id for c in notebook.contradictions if c.lie_id in lie_ids}
    plain = sum(1 for s in notebook.statements if s.npc_id == suspect_id and s.id not in used_statements)
    return score_parts(cfg, evs, len(lie_ids), plain)


def all_sufficiency(cfg: GameConfig, case: CaseBible, notebook: Notebook) -> dict[str, float]:
    return {c.id: suspect_sufficiency(cfg, case, notebook, c.id) for c in case.characters}


def covered_elements(case: CaseBible, notebook: Notebook, suspect_id: str) -> set[str]:
    out: set[str] = set()
    for e in linked_evidence(case, notebook, suspect_id):
        out.update(e.element_tags)
    return out


def to_gauge(cfg: GameConfig, value: float) -> int:
    """0~1 -> 0~gauge_cells 칸. 1칸 = max/cells (5칸이면 0.2 단위). 부동소수 오차는 1e-9 로 흡수."""
    cells = cfg.sufficiency.gauge_cells
    cell = cfg.sufficiency.max / cells
    return max(0, min(cells, int(value / cell + 1e-9)))


def gauge_map(cfg: GameConfig, values: dict[str, float]) -> dict[str, int]:
    return {k: to_gauge(cfg, v) for k, v in values.items()}

"""호출 추적과 비용·지연 집계 (PRD §11.8).

- 모든 LLM 호출에 6갈래 태그 중 하나를 붙인다: npc / gm / night / casegen / image / retrieval
- 개발 모드(dev)에서는 JSONL로 남기고, 배포 모드(prod)에서는 원문(프롬프트·응답)을 남기지 않는다.
- Langfuse 연결은 키가 생기면 이 모듈에서 내보내기만 추가한다(OpenTelemetry GenAI 형식).
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

Bucket = Literal["npc", "gm", "night", "casegen", "image", "retrieval"]

# 핫 패스 노드 지연 예산 (PRD §14.1, 초) — 넘으면 경고
LATENCY_BUDGET_S: dict[str, float] = {
    "router": 0.5,
    "retrieval": 0.2,
    "npc": 1.5,  # 첫 토큰 예산. 비스트리밍 호출은 전체 시간으로 근사
    "gm_code": 0.05,
    "gm_llm": 1.0,
}


@dataclass
class CallRecord:
    ts: float
    role: str
    bucket: str
    model: str
    latency_s: float
    input_tokens: int = 0
    output_tokens: int = 0
    attempts: int = 1
    ok: bool = True
    fallback_used: bool = False
    game_id: str | None = None
    node: str | None = None
    over_budget: bool = False
    prompt: str | None = None  # dev 모드만
    output: str | None = None  # dev 모드만
    extra: dict = field(default_factory=dict)


class Tracer:
    def __init__(self, path: str | Path | None = None, mode: Literal["dev", "prod"] = "dev") -> None:
        self.mode = mode
        self.path = Path(path) if path else None
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.records: list[CallRecord] = []
        self._lock = threading.Lock()

    def record(self, rec: CallRecord) -> None:
        budget = LATENCY_BUDGET_S.get(rec.node or "")
        rec.over_budget = bool(budget and rec.latency_s > budget)
        if self.mode == "prod":
            rec.prompt = None
            rec.output = None
        with self._lock:
            self.records.append(rec)
            if self.path:
                with self.path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(asdict(rec), ensure_ascii=False) + "\n")

    def span(self, node: str, game_id: str | None = None) -> "_Span":
        return _Span(self, node, game_id)

    def summary(self, game_id: str | None = None) -> dict:
        recs = [r for r in self.records if game_id is None or r.game_id == game_id]
        by_bucket: dict[str, dict] = {}
        for r in recs:
            b = by_bucket.setdefault(r.bucket, {"calls": 0, "input_tokens": 0, "output_tokens": 0, "latency_s": 0.0})
            b["calls"] += 1
            b["input_tokens"] += r.input_tokens
            b["output_tokens"] += r.output_tokens
            b["latency_s"] += r.latency_s
        return {
            "calls": len(recs),
            "over_budget": sum(1 for r in recs if r.over_budget),
            "fallbacks": sum(1 for r in recs if r.fallback_used),
            "by_bucket": by_bucket,
        }


class _Span:
    """LLM이 아닌 노드(검색, 게임 마스터 코드 검사 등)의 지연 측정."""

    def __init__(self, tracer: Tracer, node: str, game_id: str | None) -> None:
        self.tracer, self.node, self.game_id = tracer, node, game_id

    def __enter__(self) -> "_Span":
        self.t0 = time.perf_counter()
        return self

    def __exit__(self, *exc) -> None:
        bucket = "retrieval" if self.node == "retrieval" else "gm" if self.node.startswith("gm") else "npc"
        self.tracer.record(
            CallRecord(ts=time.time(), role=self.node, bucket=bucket, model="code",
                       latency_s=time.perf_counter() - self.t0, game_id=self.game_id, node=self.node)
        )

"""사건 원본 JSON -> CaseBible 로드."""

from __future__ import annotations

import json
from pathlib import Path

from server.schemas import CaseBible

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CASE_DIR = PROJECT_ROOT / "data" / "cases"
DEMO_CASE_ID = "demo_db_deleted"


def load_case(path: str | Path) -> CaseBible:
    """JSON 파일 경로로 사건을 읽는다. 스키마가 맞지 않으면 pydantic.ValidationError."""
    p = Path(path)
    with p.open("r", encoding="utf-8") as f:
        return CaseBible.model_validate(json.load(f))


def load_case_by_id(case_id: str, case_dir: str | Path | None = None) -> CaseBible:
    """`data/cases/<case_id>.json`을 읽는다."""
    if not case_id or "/" in case_id or "\\" in case_id or ".." in case_id:
        raise ValueError(f"잘못된 case_id: {case_id!r}")
    return load_case(Path(case_dir or DEFAULT_CASE_DIR) / f"{case_id}.json")


def load_demo_case() -> CaseBible:
    return load_case_by_id(DEMO_CASE_ID)


def list_case_ids(case_dir: str | Path | None = None) -> list[str]:
    d = Path(case_dir or DEFAULT_CASE_DIR)
    return sorted(p.stem for p in d.glob("*.json")) if d.exists() else []

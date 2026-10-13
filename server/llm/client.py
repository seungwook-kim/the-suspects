"""LLM 호출 (PRD §12, AGENTS.md 규칙 4).

모든 호출은 같은 안전장치를 거친다:
  1. 구조화 출력: Pydantic 스키마로 받는다 (JSON 텍스트를 받아 직접 검증 — 제공자별 기능 차이에 기대지 않음)
  2. 코드 검증: 호출자가 넘긴 validate 함수
  3. 재시도 상한: 기본 2회, 실패 사유를 다음 시도에 알려 줌
  4. 대체 동작: fallback 함수 결과를 쓰고 기록에 남김 (무한 재시도 없음)

OPENROUTER_API_KEY가 없으면 가짜 LLM 모드: 호출자가 넘긴 fake 함수의 결과를 그대로 쓴다.
가짜 모드에서도 같은 검증·추적 경로를 통과하므로 키 없이 한 판을 끝까지 돌릴 수 있다.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Callable, TypeVar

import yaml
from pydantic import BaseModel, ValidationError

from server.llm.tracing import Bucket, CallRecord, Tracer

T = TypeVar("T", bound=BaseModel)

_ROOT = Path(__file__).resolve().parents[2]
_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


class LLMCallError(RuntimeError):
    pass


def _deep_merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in over.items():
        out[k] = _deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def _load_models_config(path: Path | None = None) -> dict:
    """config/models.yaml(자리표시자) 위에 config/models.local.yaml(실제 모델 ID, 커밋 안 함)을 덮어쓴다."""
    p = path or (_ROOT / "config" / "models.yaml")
    with p.open(encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    local = p.with_name("models.local.yaml")
    if path is None and local.exists():
        with local.open(encoding="utf-8") as f:
            cfg = _deep_merge(cfg, yaml.safe_load(f) or {})
    return cfg


class LLMClient:
    def __init__(
        self,
        tracer: Tracer | None = None,
        models_config: dict | None = None,
        api_key: str | None = None,
        profile: str | None = None,
    ) -> None:
        self.tracer = tracer or Tracer()
        self.cfg = models_config or _load_models_config()
        self.api_key = api_key if api_key is not None else os.getenv("OPENROUTER_API_KEY", "")
        self.profile = profile or os.getenv("THE_SUSPECTS_MODEL_PROFILE") or self.cfg.get("active_profile", "dev")
        self._models: dict[str, Any] = {}

    @property
    def provider(self) -> str:
        return (self.cfg["profiles"].get(self.profile) or {}).get("provider", "openrouter")

    @property
    def fake_mode(self) -> bool:
        """모델 ID가 아직 자리표시자거나, 부를 수단(API 키 또는 명령줄 설정)이 없으면 가짜 LLM."""
        if str(self.role_config("npc").get("model", "")).startswith("<"):
            return True
        if self.provider == "cli":
            return not (self.cfg["profiles"][self.profile].get("cli") or {}).get("command")
        return not self.api_key

    # ------------------------------------------------------------------ config
    def role_config(self, role: str) -> dict:
        prof = self.cfg["profiles"].get(self.profile) or {}
        roles = prof.get("roles") or {}
        if role in roles:
            return {**roles[role], "_profile": self.profile}
        dev_roles = self.cfg["profiles"]["dev"]["roles"]
        if role not in dev_roles:
            raise LLMCallError(f"역할 설정이 없습니다: {role}")
        return {**dev_roles[role], "_profile": "dev"}

    def _chat_model(self, role: str):
        if role in self._models:
            return self._models[role]
        from langchain_openai import ChatOpenAI  # 키가 있을 때만 로드

        rc = self.role_config(role)
        prof = self.cfg["profiles"][rc["_profile"]]
        extra_body: dict[str, Any] = {}
        if rc.get("effort"):
            extra_body["reasoning"] = {"effort": rc["effort"]}  # OpenRouter 통합 추론 설정
        model = ChatOpenAI(
            model=rc["model"],
            api_key=self.api_key,
            base_url=prof.get("base_url", "https://openrouter.ai/api/v1"),
            max_tokens=rc.get("max_tokens"),
            extra_body=extra_body or None,
            timeout=30,
            max_retries=1,
        )
        self._models[role] = model
        return model

    # ------------------------------------------------------------------ main API
    async def structured(
        self,
        *,
        role: str,
        bucket: Bucket,
        schema: type[T],
        system: str,
        user: str,
        fake: Callable[[], T],
        fallback: Callable[[], T],
        validate: Callable[[T], list[str]] | None = None,
        max_retries: int = 2,
        game_id: str | None = None,
        node: str | None = None,
    ) -> tuple[T, bool]:
        """구조화 출력 호출. (결과, 대체 동작 사용 여부)를 돌려준다."""
        t0 = time.perf_counter()
        attempts = 0
        errors: list[str] = []
        in_tok = out_tok = 0
        raw_out = ""
        model_name = "fake" if self.fake_mode else self.role_config(role)["model"]
        result: T | None = None

        while attempts <= max_retries:
            attempts += 1
            try:
                if self.fake_mode:
                    candidate = fake()
                    raw_out = candidate.model_dump_json()
                else:
                    candidate, raw_out, it, ot = await self._call(role, schema, system, user, errors)
                    in_tok += it
                    out_tok += ot
                problems = validate(candidate) if validate else []
                if not problems:
                    result = candidate
                    break
                errors = problems
            except (ValidationError, ValueError, json.JSONDecodeError) as e:
                errors = [f"형식 오류: {str(e)[:300]}"]
            except Exception as e:  # 네트워크·제공자 오류
                errors = [f"호출 오류: {type(e).__name__}: {str(e)[:200]}"]
                if not self.fake_mode and attempts > max_retries:
                    break

        used_fallback = result is None
        if result is None:
            result = fallback()
        self.tracer.record(
            CallRecord(
                ts=time.time(), role=role, bucket=bucket, model=model_name,
                latency_s=time.perf_counter() - t0, input_tokens=in_tok, output_tokens=out_tok,
                attempts=attempts, ok=not used_fallback, fallback_used=used_fallback,
                game_id=game_id, node=node or role,
                prompt=f"[system]\n{system}\n[user]\n{user}", output=raw_out,
                extra={"errors": errors} if used_fallback else {},
            )
        )
        return result, used_fallback

    async def _call(self, role: str, schema: type[T], system: str, user: str, prev_errors: list[str]):
        schema_hint = json.dumps(schema.model_json_schema(), ensure_ascii=False)
        sys = (
            f"{system}\n\n반드시 아래 JSON 스키마를 따르는 JSON 객체 하나만 출력한다. 설명 문장, 코드 블록 표시 금지.\n{schema_hint}"
        )
        msg = user
        if prev_errors:
            msg += "\n\n[이전 출력의 문제 — 고쳐서 다시 출력]\n- " + "\n- ".join(prev_errors)
        if self.provider == "cli":
            from server.llm.cli_provider import call_cli

            rc = self.role_config(role)
            text, it, ot = await call_cli(self.cfg["profiles"][self.profile]["cli"], model=rc["model"],
                                          effort=rc.get("effort"), system=sys, user=msg,
                                          schema=schema.model_json_schema())
            m = _JSON_RE.search(text)
            if not m:
                raise ValueError("JSON 객체가 없습니다")
            return schema.model_validate_json(m.group(0)), text, it, ot

        from langchain_core.messages import HumanMessage, SystemMessage

        resp = await self._chat_model(role).ainvoke([SystemMessage(content=sys), HumanMessage(content=msg)])
        text = resp.content if isinstance(resp.content, str) else json.dumps(resp.content, ensure_ascii=False)
        m = _JSON_RE.search(text)
        if not m:
            raise ValueError("JSON 객체가 없습니다")
        obj = schema.model_validate_json(m.group(0))
        usage = getattr(resp, "usage_metadata", None) or {}
        return obj, text, int(usage.get("input_tokens", 0)), int(usage.get("output_tokens", 0))

"""LLM 호출 (PRD §12, AGENTS.md 규칙 4).

모든 호출은 같은 안전장치를 거친다:
  1. 구조화 출력: Pydantic 스키마로 받는다 (JSON 텍스트를 받아 직접 검증 — 제공자별 기능 차이에 기대지 않음)
  2. 코드 검증: 호출자가 넘긴 validate 함수
  3. 재시도 상한: 기본 2회, 실패 사유를 다음 시도에 알려 줌
  4. 대체 동작: fallback 함수 결과를 쓰고 기록에 남김 (무한 재시도 없음)

API 키가 없으면 가짜 LLM 모드: 호출자가 넘긴 fake 함수의 결과를 그대로 쓴다.
키는 기본으로 OPENROUTER_API_KEY에서 읽는다. 다른 OpenAI 호환 주소를 쓰는 프로필은 base_url과 함께
api_key_env(키를 담은 환경 변수 이름)를 적는다. 그 주소가 OpenRouter식 추론 설정을 모르면 send_effort: false.
주소마다 다른 추가 요청 값은 프로필·역할의 extra_body에 적으면 그대로 보낸다(역할 값이 우선).

생각(추론) 끄기: 역할에 `thinking: off`를 적으면, 그 프로필의 `thinking_off`에 적힌 방법으로 끈다.
  API 프로필은 thinking_off.extra_body(요청에 더할 값), 명령줄 프로필은 thinking_off.env(환경 변수).
  어떤 값이 그 연결에서 생각을 끄는지는 공급자마다 달라서 커밋하지 않는 로컬 설정에만 적는다.
  프로필에 thinking_off가 없으면 아무것도 바꾸지 않는다(모델 기본값).
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
    if path is None and local.exists() and not os.getenv("THE_SUSPECTS_NO_LOCAL_MODELS"):  # 테스트는 로컬 연결을 읽지 않음
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
        http_async_client: Any = None,
    ) -> None:
        """http_async_client: API 호출에 쓸 httpx.AsyncClient(테스트에서 가짜 서버를 끼울 때). 없으면 기본."""
        self.tracer = tracer or Tracer()
        self._http = http_async_client
        self.cfg = models_config or _load_models_config()
        self.profile = profile or os.getenv("THE_SUSPECTS_MODEL_PROFILE") or self.cfg.get("active_profile", "dev")
        key_env = (self.cfg["profiles"].get(self.profile) or {}).get("api_key_env") or "OPENROUTER_API_KEY"
        self.api_key = api_key if api_key is not None else os.getenv(key_env, "")
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
        extra_body: dict[str, Any] = {**(prof.get("extra_body") or {}), **self._thinking_off(rc).get("extra_body", {}),
                                      **(rc.get("extra_body") or {})}
        if rc.get("effort") and prof.get("send_effort", True):
            extra_body["reasoning"] = {"effort": rc["effort"]}  # OpenRouter 통합 추론 설정
        model = ChatOpenAI(
            model=rc["model"],
            api_key=self.api_key,
            base_url=prof.get("base_url", "https://openrouter.ai/api/v1"),
            max_tokens=rc.get("max_tokens"),
            extra_body=extra_body or None,
            timeout=rc.get("timeout_s", 30),  # 사건 쓰기처럼 긴 출력은 역할 설정으로 늘린다
            max_retries=1,
            **({"http_async_client": self._http} if self._http is not None else {}),
        )
        self._models[role] = model
        return model

    def _thinking_off(self, rc: dict) -> dict:
        """역할이 생각을 끄면 그 프로필의 끄는 방법({extra_body?, env?}), 아니면 빈 dict."""
        if str(rc.get("thinking", "")).lower() not in ("off", "false"):
            return {}
        return dict(self.cfg["profiles"][rc["_profile"]].get("thinking_off") or {})

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

    @staticmethod
    def _with_schema(system: str, schema: type[BaseModel]) -> str:
        schema_hint = json.dumps(schema.model_json_schema(), ensure_ascii=False)
        return f"{system}\n\n반드시 아래 JSON 스키마를 따르는 JSON 객체 하나만 출력한다. 설명 문장, 코드 블록 표시 금지.\n{schema_hint}"

    # ------------------------------------------------------------------ 실시간 출력 (첫 문장부터 보여 주기, PRD §14.1)
    @property
    def can_stream(self) -> bool:
        """답을 조각으로 받을 수 있는지. 가짜 LLM은 아니고, 명령줄 연결은 cli.stream_command가 있어야 한다."""
        if self.fake_mode:
            return False
        if self.provider == "cli":
            return bool((self.cfg["profiles"][self.profile].get("cli") or {}).get("stream_command"))
        return True

    async def _stream_raw(self, role: str, system: str, user: str):
        """(지금까지의 원문, 사용량 또는 None)을 조각마다 낸다."""
        rc = self.role_config(role)
        if self.provider == "cli":
            from server.llm.cli_provider import stream_cli

            async for item in stream_cli(self.cfg["profiles"][self.profile]["cli"], model=rc["model"],
                                         effort=rc.get("effort"), system=system, user=user,
                                         timeout_s=rc.get("timeout_s"), env=self._thinking_off(rc).get("env")):
                yield item
            return
        from langchain_core.messages import HumanMessage, SystemMessage

        raw = ""
        async for chunk in self._chat_model(role).astream([SystemMessage(content=system), HumanMessage(content=user)],
                                                          stream_usage=True):
            raw += chunk.content if isinstance(chunk.content, str) else ""
            u = getattr(chunk, "usage_metadata", None)
            yield raw, ({"input_tokens": int(u.get("input_tokens", 0)), "output_tokens": int(u.get("output_tokens", 0))}
                        if u else None)

    async def structured_stream(
        self,
        *,
        role: str,
        bucket: Bucket,
        schema: type[T],
        system: str,
        user: str,
        on_partial: Callable[[str], Any],
        game_id: str | None = None,
        node: str | None = None,
        meta: dict | None = None,
    ) -> tuple[T | None, str]:
        """한 번만 시도하는 실시간 구조화 출력. 조각이 올 때마다 await on_partial(지금까지의 원문).
        on_partial이 False를 돌려주면 그만 받는다(남은 생성은 버림). 끝나면 (스키마에 맞는 결과 또는 None, 원문).
        재시도·대체 동작은 부르는 쪽이 정한다(이미 화면에 보여 준 글이 있을 수 있어서).
        meta: 호출 기록 extra에 더할 값(부르는 쪽이 첫 문장을 보여 준 시각 등을 채운다)."""
        t0 = time.perf_counter()
        first: float | None = None
        raw, it, ot, err, stopped, last = "", 0, 0, "", False, ""
        gen = self._stream_raw(role, self._with_schema(system, schema), user)
        try:
            async for raw, usage in gen:
                if first is None and raw:
                    first = time.perf_counter() - t0
                if usage:
                    it, ot = usage["input_tokens"], usage["output_tokens"]
                if raw == last:  # 사용량만 붙은 마지막 알림 등: 글이 그대로면 부르지 않는다
                    continue
                last = raw
                if (await on_partial(raw)) is False:
                    stopped = True
                    break
        except Exception as e:  # 네트워크·도구 오류
            err = f"호출 오류: {type(e).__name__}: {str(e)[:200]}"
        finally:
            await gen.aclose()
        result: T | None = None
        if not err and not stopped:
            m = _JSON_RE.search(raw)
            try:
                result = schema.model_validate_json(m.group(0)) if m else None
            except (ValidationError, ValueError) as e:
                err = f"형식 오류: {str(e)[:200]}"
            if result is None and not err:
                err = "JSON 객체가 없습니다"
        extra: dict[str, Any] = {"stream": True, "first_token_s": round(first, 3) if first is not None else None,
                                 **(meta or {})}
        if stopped:
            extra["stopped"] = True
        if err:
            extra["errors"] = [err]
        self.tracer.record(CallRecord(
            ts=time.time(), role=role, bucket=bucket, model=self.role_config(role)["model"],
            latency_s=time.perf_counter() - t0, input_tokens=it, output_tokens=ot, attempts=1,
            ok=result is not None or stopped, fallback_used=False, game_id=game_id, node=node or role,
            prompt=f"[system]\n{system}\n[user]\n{user}", output=raw, extra=extra,
        ))
        return result, raw

    async def _call(self, role: str, schema: type[T], system: str, user: str, prev_errors: list[str]):
        sys = self._with_schema(system, schema)
        msg = user
        if prev_errors:
            msg += "\n\n[이전 출력의 문제 — 고쳐서 다시 출력]\n- " + "\n- ".join(prev_errors)
        if self.provider == "cli":
            from server.llm.cli_provider import call_cli

            rc = self.role_config(role)
            text, it, ot = await call_cli(self.cfg["profiles"][self.profile]["cli"], model=rc["model"],
                                          effort=rc.get("effort"), system=sys, user=msg,
                                          schema=schema.model_json_schema(), timeout_s=rc.get("timeout_s"),
                                          env=self._thinking_off(rc).get("env"))
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

"""이미지 생성 (PRD §12.7): 인물 초상화·배경을 OpenRouter의 이미지 출력 모델로 그린다.

- 역할 "portrait"의 모델 ID는 config/models.yaml(자리표시자) → config/models.local.yaml(실제 값).
- OPENROUTER_API_KEY가 없거나 모델이 자리표시자면 꺼진다(None 반환) → 화면은 절차적 SVG로 대신 그린다.
- 글 쓰는 역할이 명령줄 공급자를 써도, 그림은 항상 API로 그린다(명령줄 모델은 그림을 못 그림).
- 요청: chat/completions + modalities ["image", "text"], 응답 message.images[].image_url.url (data URL).
"""

from __future__ import annotations

import base64
import os
import time
from typing import Awaitable, Callable

import httpx

from server.llm.client import _load_models_config
from server.llm.tracing import CallRecord, Tracer

Generator = Callable[[str], Awaitable[bytes | None]]


class ImageClient:
    def __init__(self, tracer: Tracer | None = None, models_config: dict | None = None, api_key: str | None = None,
                 generator: Generator | None = None) -> None:
        self.tracer = tracer or Tracer()
        cfg = models_config or _load_models_config()
        prof = cfg["profiles"].get(cfg.get("active_profile", "dev")) or {}
        role = (prof.get("roles") or {}).get("portrait") or cfg["profiles"]["dev"]["roles"].get("portrait") or {}
        self.model: str = str(role.get("model", "<image-model>"))
        self.aspect_ratio: str = role.get("aspect_ratio", "3:4")
        self.base_url: str = prof.get("image_base_url") or "https://openrouter.ai/api/v1"
        self.api_key = api_key if api_key is not None else os.getenv("OPENROUTER_API_KEY", "")
        self._generator = generator  # 테스트·가짜 모드용 주입

    @property
    def enabled(self) -> bool:
        if self._generator is not None:
            return True
        return bool(self.api_key) and not self.model.startswith("<")

    async def generate(self, prompt: str, *, node: str = "portrait", game_id: str | None = None) -> bytes | None:
        if not self.enabled:
            return None
        t0, ok, err, out = time.perf_counter(), False, "", None
        try:
            out = await (self._generator(prompt) if self._generator else self._call(prompt))
            ok = out is not None
        except Exception as e:  # 그림 실패는 게임을 멈추지 않는다 (SVG로 대신)
            err = f"{type(e).__name__}: {str(e)[:200]}"
        self.tracer.record(CallRecord(
            ts=time.time(), role="portrait", bucket="image", model=self.model if not self._generator else "fake",
            latency_s=time.perf_counter() - t0, input_tokens=0, output_tokens=0, attempts=1, ok=ok,
            fallback_used=not ok, game_id=game_id, node=node, prompt=prompt, output=f"{len(out or b'')} bytes",
            extra={"errors": [err]} if err else {},
        ))
        return out

    async def _call(self, prompt: str) -> bytes | None:
        body = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "modalities": ["image", "text"],
            "image_config": {"aspect_ratio": self.aspect_ratio},
        }
        async with httpx.AsyncClient(timeout=120) as http:
            r = await http.post(f"{self.base_url}/chat/completions", json=body,
                                headers={"Authorization": f"Bearer {self.api_key}"})
            r.raise_for_status()
            data = r.json()
        for choice in data.get("choices") or []:
            for img in (choice.get("message") or {}).get("images") or []:
                url = (img.get("image_url") or {}).get("url", "")
                if url.startswith("data:") and "," in url:
                    return base64.b64decode(url.split(",", 1)[1])
        return None

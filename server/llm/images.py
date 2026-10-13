"""이미지 생성 (PRD §12.7): 인물 초상화를 이미지 모델로 그린다.

- 역할 "portrait" 설정: provider(cloudflare | openrouter), model, 크기. config/models.yaml → config/models.local.yaml.
- cloudflare (기본, 2026-10-13 사용자 결정): Workers AI 무료 할당량(하루 10,000 뉴런, UTC 0시 초기화)으로 그린다.
  키: CLOUDFLARE_ACCOUNT_ID + CLOUDFLARE_API_TOKEN. 요청은 multipart(prompt·width·height·seed), 응답 result.image(base64).
  할당량을 넘으면 오류가 나고 요금은 나가지 않는다 → 그 그림만 빠지고 화면은 절차적 SVG로 대신한다.
- openrouter: chat/completions + modalities ["image", "text"], 응답 message.images[].image_url.url (data URL).
  키: OPENROUTER_API_KEY.
- 키가 없거나 모델이 자리표시자면 꺼진다(None 반환).
- 글 쓰는 역할이 명령줄 공급자를 써도, 그림은 항상 API로 그린다(명령줄 모델은 그림을 못 그림).
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

CLOUDFLARE_API = "https://api.cloudflare.com/client/v4"


class ImageClient:
    def __init__(self, tracer: Tracer | None = None, models_config: dict | None = None, api_key: str | None = None,
                 generator: Generator | None = None, *, account_id: str | None = None,
                 transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.tracer = tracer or Tracer()
        cfg = models_config or _load_models_config()
        prof = cfg["profiles"].get(cfg.get("active_profile", "dev")) or {}
        role = (prof.get("roles") or {}).get("portrait") or cfg["profiles"]["dev"]["roles"].get("portrait") or {}
        self.provider: str = str(role.get("provider", "openrouter"))
        self.model: str = str(role.get("model", "<image-model>"))
        self.aspect_ratio: str = role.get("aspect_ratio", "3:4")
        self.width: int = int(role.get("width", 480))  # 그리는 크기 = 저장 최대 크기
        self.height: int = int(role.get("height", 640))
        self.concurrency: int = int(role.get("concurrency", 7))  # 한 판의 인물을 한꺼번에 (공급자 대기 시간이 대부분)
        self.webp_quality: int = int(role.get("webp_quality", 80))
        if self.provider == "cloudflare":
            self.api_key = api_key if api_key is not None else os.getenv("CLOUDFLARE_API_TOKEN", "")
            self.account_id = account_id if account_id is not None else os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
        else:
            self.api_key = api_key if api_key is not None else os.getenv("OPENROUTER_API_KEY", "")
            self.account_id = ""
        self.base_url: str = prof.get("image_base_url") or "https://openrouter.ai/api/v1"
        self._generator = generator  # 테스트·가짜 모드용 주입
        self._transport = transport  # 테스트에서 요청 형식 확인용

    @property
    def enabled(self) -> bool:
        if self._generator is not None:
            return True
        if not self.api_key or self.model.startswith("<"):
            return False
        return self.provider != "cloudflare" or bool(self.account_id)

    async def generate(self, prompt: str, *, seed: int | None = None, node: str = "portrait",
                       game_id: str | None = None) -> bytes | None:
        if not self.enabled:
            return None
        t0, ok, err, out = time.perf_counter(), False, "", None
        try:
            if self._generator:
                out = await self._generator(prompt)
            elif self.provider == "cloudflare":
                out = await self._call_cloudflare(prompt, seed)
            else:
                out = await self._call_openrouter(prompt)
            ok = out is not None
        except Exception as e:  # 그림 실패(할당량 초과 포함)는 게임을 멈추지 않는다 (SVG로 대신)
            err = f"{type(e).__name__}: {str(e)[:200]}"
        extra: dict = {"provider": self.provider, "seed": seed}
        if err:
            extra["errors"] = [err]
        self.tracer.record(CallRecord(
            ts=time.time(), role="portrait", bucket="image", model=self.model if not self._generator else "fake",
            latency_s=time.perf_counter() - t0, input_tokens=0, output_tokens=0, attempts=1, ok=ok,
            fallback_used=not ok, game_id=game_id, node=node, prompt=prompt, output=f"{len(out or b'')} bytes",
            extra=extra,
        ))
        return out

    async def _call_cloudflare(self, prompt: str, seed: int | None) -> bytes | None:
        fields = {"prompt": prompt, "width": str(self.width), "height": str(self.height)}
        if seed is not None:
            fields["seed"] = str(seed)
        async with httpx.AsyncClient(timeout=120, transport=self._transport) as http:
            r = await http.post(f"{CLOUDFLARE_API}/accounts/{self.account_id}/ai/run/{self.model}",
                                headers={"Authorization": f"Bearer {self.api_key}"},
                                files={k: (None, v) for k, v in fields.items()})  # 글자만 있어도 multipart로 보내야 한다
            r.raise_for_status()
            data = r.json()
        image = (data.get("result") or {}).get("image") if isinstance(data, dict) else None
        return base64.b64decode(image) if image else None

    async def _call_openrouter(self, prompt: str) -> bytes | None:
        body = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "modalities": ["image", "text"],
            "image_config": {"aspect_ratio": self.aspect_ratio},
        }
        async with httpx.AsyncClient(timeout=120, transport=self._transport) as http:
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

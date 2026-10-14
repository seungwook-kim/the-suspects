"""AG-UI 형식 SSE 이벤트 (docs/api-contract.md, PRD §11.10).

ag-ui-langgraph(0.0.x)에 바로 묶지 않고 같은 이벤트 모양을 직접 만든다.
나중에 라이브러리로 바꿔도 프론트엔드는 그대로 동작한다.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from pydantic import BaseModel


def sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"


def _dump(obj: Any) -> Any:
    return obj.model_dump(mode="json") if isinstance(obj, BaseModel) else obj


class EventBuilder:
    def __init__(self) -> None:
        self.run_id = f"run_{uuid.uuid4().hex[:10]}"

    def run_started(self) -> dict:
        return {"type": "RUN_STARTED", "runId": self.run_id}

    def run_finished(self) -> dict:
        return {"type": "RUN_FINISHED", "runId": self.run_id}

    def run_error(self, message: str, code: str = "error") -> dict:
        return {"type": "RUN_ERROR", "message": message, "code": code}

    def text(self, role: str, speaker_id: str | None, text: str, chunk: int = 6) -> list[dict]:
        """대사 하나를 START / CONTENT 조각 / END 이벤트로 나눈다(글자 찍힘 효과)."""
        mid, start = self.text_start(role, speaker_id)
        events = [start]
        for i in range(0, len(text), chunk):
            events.append(self.text_delta(mid, text[i:i + chunk]))
        events.append(self.text_end(mid))
        return events

    # 모델이 쓰는 대로 내보낼 때(첫 문장부터 보여 주기): 시작 → 조각들 → 끝을 따로 만든다
    @staticmethod
    def text_start(role: str, speaker_id: str | None) -> tuple[str, dict]:
        mid = f"msg_{uuid.uuid4().hex[:10]}"
        return mid, {"type": "TEXT_MESSAGE_START", "messageId": mid, "role": role, "speakerId": speaker_id}

    @staticmethod
    def text_delta(mid: str, delta: str) -> dict:
        return {"type": "TEXT_MESSAGE_CONTENT", "messageId": mid, "delta": delta}

    @staticmethod
    def text_end(mid: str) -> dict:
        return {"type": "TEXT_MESSAGE_END", "messageId": mid}

    def snapshot(self, view: BaseModel) -> dict:
        return {"type": "STATE_SNAPSHOT", "snapshot": _dump(view)}

    def delta(self, before: BaseModel | dict, after: BaseModel | dict) -> dict | None:
        patch = json_patch(_dump(before), _dump(after))
        return {"type": "STATE_DELTA", "delta": patch} if patch else None

    def custom(self, name: str, value: Any) -> dict:
        return {"type": "CUSTOM", "name": name, "value": _dump(value)}


def json_patch(before: dict, after: dict) -> list[dict]:
    """최상위 키 단위 RFC 6902 patch. 바뀐 키만 replace/add/remove 한다."""
    ops: list[dict] = []
    for key in after:
        path = "/" + key.replace("~", "~0").replace("/", "~1")
        if key not in before:
            ops.append({"op": "add", "path": path, "value": after[key]})
        elif before[key] != after[key]:
            ops.append({"op": "replace", "path": path, "value": after[key]})
    for key in before:
        if key not in after:
            ops.append({"op": "remove", "path": "/" + key.replace("~", "~0").replace("/", "~1")})
    return ops

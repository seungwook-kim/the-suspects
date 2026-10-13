"""클라이언트용 불투명 ID (AGENTS.md 규칙 7).

증거·블러핑 주장·거짓말·기억의 내부 ID는 사건 작성자가 정한 이름이라 범인을 암시할 수 있다
(예: "ev_cleaner_card"). 클라이언트에는 판마다 소금(salt)을 섞은 해시 ID만 보내고,
클라이언트가 보낸 ID는 서버에서 다시 내부 ID로 되돌린다.
인물 ID와 장소 ID는 역할·장소 이름이 이미 공개 정보라 그대로 쓴다.
"""

from __future__ import annotations

import hashlib
import secrets

from server.schemas import CaseBible

_PREFIX = {"evidence": "e", "claim": "c", "lie": "l", "source": "s", "statement": "t"}


def new_salt() -> str:
    return secrets.token_hex(8)


def mask(salt: str, kind: str, internal_id: str) -> str:
    h = hashlib.sha1(f"{salt}:{kind}:{internal_id}".encode()).hexdigest()[:10]
    return f"{_PREFIX[kind]}_{h}"


class IdMasker:
    def __init__(self, case: CaseBible, salt: str) -> None:
        self.salt = salt
        self._rev: dict[str, str] = {}
        for ev in case.evidence:
            self._rev[mask(salt, "evidence", ev.id)] = ev.id
        for cl in case.bluff_claims:
            self._rev[mask(salt, "claim", cl.id)] = cl.id
        for lie in case.lie_ledger:
            self._rev[mask(salt, "lie", lie.id)] = lie.id

    def out(self, kind: str, internal_id: str) -> str:
        return mask(self.salt, kind, internal_id)

    def inn(self, public_id: str) -> str | None:
        """클라이언트가 보낸 ID → 내부 ID. 모르는 ID면 None (위조 차단)."""
        return self._rev.get(public_id)

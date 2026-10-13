"""F.11 게임 마스터 코드 검사. 순수 함수, LLM 호출 없음.

NPC 답변 텍스트를 훑어 LLM 검사가 필요한지 판정한다. triggers 값:
  culprit_name        범인 이름(그 NPC 의 권한으로 알 수 없는데 언급)
  key_evidence        핵심 증거의 이름이나 ID (권한과 무관하게 항상)
  incident_time       사건 시각 +-gm.time_window_hours 안의 시각 표현
  incident_location   사건 장소 이름
  out_of_scope_entity 그 NPC 권한 밖의 인물·사물(증거) 이름
GMVerdict.ok == True 는 "더 검사할 것 없음". 코드로 확정된 위반(문장 수 초과, 빈 답변)은 violations 에 담는다.
needs_llm_check 는 triggers 가 하나라도 있을 때 True (gm.llm_check == "conditional"). "always" 면 항상 True,
"never" 면 항상 False.

권한(NPCKnowledge) 기본 도출(knowledge_for): 알 수 있는 인물 = 본인 + 관계 대상 + 처음부터 등장하는 인물(initial_visible),
알 수 있는 증거 = visibility 에 npc:<id> 또는 public 이 있는 것. 필요하면 호출자가 직접 만들어 넘긴다.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

from server.config import GameConfig
from server.schemas import CaseBible, Character, GMVerdict

# ---------------------------------------------------------------------------
# 권한
# ---------------------------------------------------------------------------


class NPCKnowledge(BaseModel):
    npc_id: str
    known_character_ids: set[str] = Field(default_factory=set)
    known_evidence_ids: set[str] = Field(default_factory=set)
    knows_culprit: bool = False


def _guilty(case: CaseBible, ch: Character) -> bool:
    return ch.is_culprit or ch.is_accomplice or ch.id in case.culprit_ids


def knowledge_for(
    case: CaseBible,
    npc_id: str,
    extra_character_ids: set[str] | None = None,
    extra_evidence_ids: set[str] | None = None,
) -> NPCKnowledge:
    me = next(c for c in case.characters if c.id == npc_id)
    chars = {npc_id, *(r.target for r in me.relations), *(c.id for c in case.characters if c.initial_visible)}
    chars |= extra_character_ids or set()
    evs = {e.id for e in case.evidence if f"npc:{npc_id}" in e.visibility or "public" in e.visibility}
    evs |= extra_evidence_ids or set()
    return NPCKnowledge(npc_id=npc_id, known_character_ids=chars, known_evidence_ids=evs, knows_culprit=_guilty(case, me))


# ---------------------------------------------------------------------------
# 한국어 시각 표현
# ---------------------------------------------------------------------------

_NATIVE = {
    "열두": 12,
    "열한": 11,
    "열": 10,
    "아홉": 9,
    "여덟": 8,
    "일곱": 7,
    "여섯": 6,
    "다섯": 5,
    "넉": 4,
    "네": 4,
    "석": 3,
    "세": 3,
    "두": 2,
    "한": 1,
}
_NATIVE_ALT = "|".join(sorted(_NATIVE, key=len, reverse=True))

_CLOCK_RE = re.compile(r"(?<!\d)([01]?\d|2[0-3]):([0-5]\d)(?!\d)")
_KOR_RE = re.compile(
    rf"(?P<period>오전|오후|새벽|아침|낮|저녁|밤)?\s*(?P<h>\d{{1,2}}|{_NATIVE_ALT})\s*시"
    r"(?:\s*(?P<half>반)|\s*(?P<m>\d{1,2})\s*분)?"
)
DAY = 24 * 60


def _hour_candidates(period: str | None, h: int) -> list[int]:
    """시(0~24)와 시간대 표현 -> 가능한 24시간제 시 목록. 시간대가 없으면 오전·오후 둘 다."""
    if h >= 13:
        return [h % 24]
    if period in ("오전", "아침", "새벽"):
        return [h % 12]
    if period in ("오후", "저녁", "낮"):
        return [12 if h == 12 else h + 12]
    if period == "밤":
        if h == 12:
            return [0]
        return [h + 12] if h >= 6 else [h]
    if h == 0:
        return [0]
    if h == 12:
        return [0, 12]
    return [h, h + 12]


def extract_time_candidates(text: str) -> list[list[int]]:
    """텍스트 속 시각 표현마다, 하루 중 분(0~1439) 후보 목록을 돌려준다."""
    out: list[list[int]] = []
    for m in _CLOCK_RE.finditer(text):
        out.append([(int(m.group(1)) * 60 + int(m.group(2))) % DAY])
    for m in _KOR_RE.finditer(text):
        raw = m.group("h")
        h = int(raw) if raw.isdigit() else _NATIVE[raw]
        minute = 30 if m.group("half") else int(m.group("m") or 0)
        out.append([(hh * 60 + minute) % DAY for hh in _hour_candidates(m.group("period"), h)])
    return out


def _circ_dist(a: int, b: int) -> int:
    d = abs(a - b) % DAY
    return min(d, DAY - d)


def mentions_time_near(text: str, center_minute: int, window_hours: int) -> bool:
    center = center_minute % DAY
    limit = window_hours * 60
    return any(_circ_dist(c, center) <= limit for cands in extract_time_candidates(text) for c in cands)


# ---------------------------------------------------------------------------
# 이름 감지
# ---------------------------------------------------------------------------


def _name_variants(name: str) -> list[str]:
    """전체 이름. 성+이름 3글자면 이름 부분(2글자)도 호칭으로 쓰이므로 포함한다."""
    out = [name]
    if len(name) == 3:
        out.append(name[1:])
    return [n for n in out if len(n) >= 2]


def _mentions(text: str, name: str) -> bool:
    return any(v in text for v in _name_variants(name))


def count_sentences(text: str) -> int:
    t = text.replace("...", "…").strip()
    parts = re.split(r"[.!?。]+(?:\s+|$)", t)
    return sum(1 for p in parts if p.strip())


# ---------------------------------------------------------------------------
# 검사
# ---------------------------------------------------------------------------


def check_reply(
    cfg: GameConfig,
    case: CaseBible,
    npc_id: str,
    text: str,
    knowledge: NPCKnowledge | None = None,
) -> GMVerdict:
    kn = knowledge or knowledge_for(case, npc_id)
    triggers: list[str] = []
    violations: list[str] = []

    if not text.strip():
        violations.append("empty_reply")
    else:
        lo, hi = cfg.npc_reply_sentences
        n = count_sentences(text)
        if n < lo or n > hi:
            violations.append("sentence_count")

    # 1. 범인 이름 (권한 밖)
    if not kn.knows_culprit:
        for ch in case.characters:
            if _guilty(case, ch) and _mentions(text, ch.name):
                triggers.append("culprit_name")
                break

    # 2. 핵심 증거 이름·ID
    if any(e.is_key and (e.id in text or e.name in text) for e in case.evidence):
        triggers.append("key_evidence")

    # 3. 사건 시각 전후
    if mentions_time_near(text, case.incident.time, cfg.gm.time_window_hours):
        triggers.append("incident_time")

    # 4. 사건 장소 이름
    inc_loc = next((l for l in case.locations if l.id == case.incident.location_id), None)
    if inc_loc is not None and inc_loc.name in text:
        triggers.append("incident_location")

    # 5. 권한 밖 인물·사물 (개체 사전 대조). 범인 이름은 1번에서 다루므로 제외.
    out_of_scope = False
    for ch in case.characters:
        if ch.id not in kn.known_character_ids and not _guilty(case, ch) and _mentions(text, ch.name):
            out_of_scope = True
    for e in case.evidence:
        if e.id not in kn.known_evidence_ids and not e.is_key and len(e.name) >= 2 and e.name in text:
            out_of_scope = True
    if out_of_scope:
        triggers.append("out_of_scope_entity")

    mode = cfg.gm.llm_check
    needs = bool(triggers)
    if mode == "always":
        needs = True
    elif mode == "never":
        needs = False
    return GMVerdict(ok=not violations and not triggers, violations=violations, needs_llm_check=needs, triggers=triggers)


def fallback_line(cfg: GameConfig, character: Character) -> str:
    """성격별 기본 대사 (사실 정보 없음). 겁 많음 > 냉정함 > 말버릇(수다쟁이/무뚝뚝) > 기본 순으로 고른다."""
    lines = cfg.gm.fallback_lines
    if character.temperament == "timid":
        return lines["timid"]
    if character.temperament == "cold":
        return lines["cold"]
    if character.small_talk_style == "chatty":
        return lines["chatty"]
    if character.small_talk_style == "blunt":
        return lines["blunt"]
    return lines["default"]

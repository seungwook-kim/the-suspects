"""사건 원본 검수 (PRD §3.4, §5.4). 코드로 확인할 수 있는 규칙만 검사하고 위반 목록을 돌려준다.

규칙 코드
- R1_MMO       범인은 동기·수단·기회를 모두 가진다. 무고한 용의자는 모두 가지지 않는다 (공범은 무고하지 않으므로 제외).
- R2_TRACE     지워질 수 있는(destroyable) 증거마다 간접 흔적이 최소 하나(지워지지 않는 것) 있다. 핵심 증거는 지워질 수 없다.
- R3_LIE       거짓말 장부의 모든 거짓말에 반박 증거가 있고, 플레이어가 얻을 수 있다.
- R4_TIMELINE  같은 시각 두 장소에 있는 인물 없음. 범인은 사건 시각에 사건 장소에 있고, 기회가 없는 인물은 없다.
- R7_APPEARANCE 외모(그림 요청 재료)에 범인을 암시하는 단어가 없다. 공개 문구에 범인 이름이 없다.
- S_SOLVABLE   간이 풀이 가능성: 플레이어가 얻을 수 있는 증거만으로 범인의 동기·수단·기회가 각각 1개 이상 태그돼 있고,
               무고한 용의자는 세 가지를 다 갖춘 증거 조합이 없다. 핵심 증거는 모두 획득 가능하다.
- I_REF        id 참조 무결성, 기록·기억·블러핑 정의의 참조 오류.
"""

from __future__ import annotations

from dataclasses import dataclass

from server.schemas import CaseBible, Character, Evidence

ELEMENTS = ("motive", "means", "opportunity")

# 외모 묘사에 들어가면 안 되는 단어 (범인/비밀 암시). 필요하면 늘린다.
BANNED_APPEARANCE_WORDS = (
    "범인", "용의", "수상", "의심", "음흉", "음침", "사악", "악랄", "흉악", "비밀", "거짓", "살인", "악당",
    "불길", "섬뜩", "사이코", "죄", "숨기", "숨긴", "꿍꿍이", "비열", "교활", "간교", "표독", "위험한", "차가운 눈빛",
    "culprit", "criminal", "suspicious", "sinister", "guilty",
)


@dataclass(frozen=True)
class Violation:
    rule: str
    message: str
    ref: str = ""

    def __str__(self) -> str:
        return f"[{self.rule}] {self.message}" + (f" ({self.ref})" if self.ref else "")


def _is_player_visible(ev: Evidence) -> bool:
    return any(v in ("player", "public") or v.startswith("warrant:") for v in ev.visibility)


def obtainable_evidence(case: CaseBible) -> set[str]:
    """플레이어가 (영장 포함) 얻을 수 있는 증거 id. 장소 해금 조건을 고정점 반복으로 푼다.

    unlock_condition 문법: "evidence:<id>", "talk:<npc_id>", "day:<n>", "&"(모두) / "|"(하나라도)로 연결.
    talk:/day: 조건은 항상 달성 가능하다고 가정한다.
    """
    chars = {c.id: c for c in case.characters}
    ev_by_id = {e.id: e for e in case.evidence}
    memory_ev = {m.evidence_id for m in case.initial_memories if m.evidence_id}
    record_ev = {r.evidence_id for r in case.records if r.evidence_id}
    obtained: set[str] = set()
    reachable: set[str] = set()

    def cond_ok(cond: str | None) -> bool:
        if cond is None:
            return True
        for any_part in cond.split("|"):
            ok = True
            for part in any_part.split("&"):
                kind, _, arg = part.strip().partition(":")
                if kind == "evidence":
                    ok = ok and arg in obtained
                elif kind == "talk":
                    ok = ok and arg in chars
                elif kind == "day":
                    ok = ok and True
                else:
                    ok = False
            if ok:
                return True
        return False

    changed = True
    while changed:
        changed = False
        for loc in case.locations:
            if loc.id not in reachable and cond_ok(loc.unlock_condition):
                reachable.add(loc.id)
                changed = True
        for loc in case.locations:
            if loc.id not in reachable:
                continue
            for eid in loc.investigate_evidence_ids:
                ev = ev_by_id.get(eid)
                if ev and _is_player_visible(ev) and eid not in obtained:
                    obtained.add(eid)
                    changed = True
        for ev in case.evidence:
            if ev.id in obtained or not _is_player_visible(ev):
                continue
            warrant_only = all(v.startswith("warrant:") for v in ev.visibility)
            if (warrant_only and ev.id in record_ev) or (ev.location_id is None and ev.id in memory_ev):
                obtained.add(ev.id)
                changed = True
    return obtained


def _location_at(case: CaseBible, char_id: str, t: int) -> str | None:
    events = sorted((e for e in case.timeline if e.character_id == char_id and e.time <= t), key=lambda e: e.time)
    return events[-1].location_id if events else None


def _is_offsite(loc_id: str) -> bool:
    return loc_id.startswith("off:")


def verify_case(case: CaseBible) -> list[Violation]:
    v: list[Violation] = []
    chars = {c.id: c for c in case.characters}
    locs = {loc.id: loc for loc in case.locations}
    ev_by_id = {e.id: e for e in case.evidence}
    culprits = set(case.culprit_ids)

    # ---- I_REF: 무결성 -------------------------------------------------------------------
    for name, ids in (
        ("characters", [c.id for c in case.characters]),
        ("locations", [x.id for x in case.locations]),
        ("evidence", [e.id for e in case.evidence]),
        ("lie_ledger", [x.id for x in case.lie_ledger]),
        ("records", [r.id for r in case.records]),
        ("initial_memories", [m.id for m in case.initial_memories]),
        ("bluff_claims", [b.id for b in case.bluff_claims]),
        ("documents", [d.id for d in case.documents]),
    ):
        dup = {i for i in ids if ids.count(i) > 1}
        if dup:
            v.append(Violation("I_REF", f"{name}에 중복 id: {sorted(dup)}"))
    if not culprits:
        v.append(Violation("I_REF", "culprit_ids가 비어 있다"))
    for cid in culprits:
        if cid not in chars:
            v.append(Violation("I_REF", f"culprit_ids에 없는 인물: {cid}"))
        elif not chars[cid].is_culprit:
            v.append(Violation("I_REF", f"{cid}가 culprit_ids에 있으나 is_culprit이 False", cid))
    for c in case.characters:
        if c.is_culprit and c.id not in culprits:
            v.append(Violation("I_REF", f"{c.id}의 is_culprit=True인데 culprit_ids에 없다", c.id))
        for r in c.relations:
            if r.target not in chars:
                v.append(Violation("I_REF", f"{c.id}의 관계 대상 {r.target}가 없다", c.id))
        for rt in c.routine:
            if rt.location_id not in locs and not _is_offsite(rt.location_id):
                v.append(Violation("I_REF", f"{c.id}의 일과 장소 {rt.location_id}가 없다", c.id))
    if case.start_location_id not in locs:
        v.append(Violation("I_REF", f"start_location_id {case.start_location_id}가 없다"))
    elif locs[case.start_location_id].unlock_condition is not None:
        v.append(Violation("I_REF", "시작 장소는 처음부터 열려 있어야 한다"))
    if case.incident.location_id not in locs:
        v.append(Violation("I_REF", f"incident.location_id {case.incident.location_id}가 없다"))
    for loc in case.locations:
        for conn in loc.connections:
            if conn not in locs:
                v.append(Violation("I_REF", f"{loc.id}의 연결 {conn}가 없다", loc.id))
        for eid in loc.investigate_evidence_ids:
            if eid not in ev_by_id:
                v.append(Violation("I_REF", f"{loc.id}의 조사 증거 {eid}가 없다", loc.id))
    open_locs = [x for x in case.locations if x.unlock_condition is None]
    if len(open_locs) < 3:
        v.append(Violation("I_REF", f"처음 열린 장소가 3곳 미만이다({len(open_locs)})"))
    for e in case.evidence:
        if e.location_id and e.location_id not in locs:
            v.append(Violation("I_REF", f"증거 {e.id}의 장소 {e.location_id}가 없다", e.id))
        for s in e.linked_suspects:
            if s not in chars:
                v.append(Violation("I_REF", f"증거 {e.id}의 연결 용의자 {s}가 없다", e.id))
        for lid in e.reveals_contradiction_of:
            if lid not in {x.id for x in case.lie_ledger}:
                v.append(Violation("I_REF", f"증거 {e.id}가 깨는 거짓말 {lid}가 장부에 없다", e.id))
        for t in e.indirect_traces:
            if t not in ev_by_id:
                v.append(Violation("I_REF", f"증거 {e.id}의 간접 흔적 {t}가 없다", e.id))
    for r in case.records:
        if r.person_id and r.person_id not in chars:
            v.append(Violation("I_REF", f"기록 {r.id}의 인물 {r.person_id}가 없다", r.id))
        if r.location_id and r.location_id not in locs and not _is_offsite(r.location_id):
            v.append(Violation("I_REF", f"기록 {r.id}의 장소 {r.location_id}가 없다", r.id))
        if r.evidence_id and r.evidence_id not in ev_by_id:
            v.append(Violation("I_REF", f"기록 {r.id}의 증거 {r.evidence_id}가 없다", r.id))
    for m in case.initial_memories:
        if m.case_id != case.case_id:
            v.append(Violation("I_REF", f"기억 {m.id}의 case_id가 사건과 다르다", m.id))
        if m.owner != "public" and m.owner not in chars:
            v.append(Violation("I_REF", f"기억 {m.id}의 owner {m.owner}가 없다", m.id))
        if m.owner != "public" and f"npc:{m.owner}" not in m.visibility:
            v.append(Violation("I_REF", f"기억 {m.id}의 visibility에 소유자가 없다", m.id))
        if m.evidence_id and m.evidence_id not in ev_by_id:
            v.append(Violation("I_REF", f"기억 {m.id}의 증거 {m.evidence_id}가 없다", m.id))
    for b in case.bluff_claims:
        for n in list(b.truth_by_target) + b.known_false_by:
            if n not in chars:
                v.append(Violation("I_REF", f"블러핑 {b.id}가 없는 인물 {n}를 가리킨다", b.id))
    for t in case.timeline:
        if t.character_id not in chars:
            v.append(Violation("I_REF", f"타임라인의 없는 인물 {t.character_id}"))
        if t.location_id not in locs and not _is_offsite(t.location_id):
            v.append(Violation("I_REF", f"타임라인의 없는 장소 {t.location_id}"))

    obtainable = obtainable_evidence(case)

    # ---- R1: 동기·수단·기회 --------------------------------------------------------------
    for cid in culprits & set(chars):
        entry = case.mmo.get(cid)
        if entry is None:
            v.append(Violation("R1_MMO", f"범인 {cid}의 동기·수단·기회가 없다", cid))
            continue
        for el in ELEMENTS:
            if not getattr(entry, el):
                v.append(Violation("R1_MMO", f"범인 {cid}에 {el}이 없다", cid))
    for c in case.characters:
        if c.id in culprits or c.is_accomplice:
            continue
        entry = case.mmo.get(c.id)
        if entry and all(getattr(entry, el) for el in ELEMENTS):
            v.append(Violation("R1_MMO", f"무고한 용의자 {c.id}가 동기·수단·기회를 모두 가졌다", c.id))

    # ---- R2: 간접 흔적 -------------------------------------------------------------------
    for e in case.evidence:
        if e.destroyable:
            if e.is_key:
                v.append(Violation("R2_TRACE", f"핵심 증거 {e.id}가 지워질 수 있다(destroyable)", e.id))
            solid = [t for t in e.indirect_traces if t in ev_by_id and not ev_by_id[t].destroyable]
            if not solid:
                v.append(Violation("R2_TRACE", f"지워질 증거 {e.id}에 지워지지 않는 간접 흔적이 없다", e.id))
            for t in solid:
                if t not in obtainable:
                    v.append(Violation("R2_TRACE", f"{e.id}의 간접 흔적 {t}를 플레이어가 얻을 수 없다", e.id))

    # ---- R3: 거짓말 반박 -----------------------------------------------------------------
    for lie in case.lie_ledger:
        if lie.liar_id not in chars:
            v.append(Violation("R3_LIE", f"거짓말 {lie.id}의 화자 {lie.liar_id}가 없다", lie.id))
        if not lie.rebuttal_evidence_ids:
            v.append(Violation("R3_LIE", f"거짓말 {lie.id}에 반박 증거가 없다", lie.id))
            continue
        missing = [x for x in lie.rebuttal_evidence_ids if x not in ev_by_id]
        if missing:
            v.append(Violation("R3_LIE", f"거짓말 {lie.id}의 반박 증거 {missing}가 존재하지 않는다", lie.id))
        good = [x for x in lie.rebuttal_evidence_ids if x in obtainable]
        if not good:
            v.append(Violation("R3_LIE", f"거짓말 {lie.id}의 반박 증거를 플레이어가 얻을 수 없다", lie.id))
        if not any(lie.id in ev_by_id[x].reveals_contradiction_of for x in lie.rebuttal_evidence_ids if x in ev_by_id):
            v.append(Violation("R3_LIE", f"거짓말 {lie.id}의 반박 증거 중 reveals_contradiction_of로 연결된 것이 없다", lie.id))

    # ---- R4: 타임라인 --------------------------------------------------------------------
    seen: dict[tuple[str, int], str] = {}
    for t in case.timeline:
        key = (t.character_id, t.time)
        if key in seen and seen[key] != t.location_id:
            v.append(Violation("R4_TIMELINE", f"{t.character_id}가 {t.time}분에 {seen[key]}와 {t.location_id}에 동시에 있다", t.character_id))
        seen[key] = t.location_id
    inc = case.incident
    for cid in culprits & set(chars):
        if _location_at(case, cid, inc.time) != inc.location_id:
            v.append(Violation("R4_TIMELINE", f"범인 {cid}가 사건 시각 {inc.time}에 사건 장소 {inc.location_id}에 있지 않다", cid))
    for c in case.characters:
        if c.id in culprits:
            continue
        entry = case.mmo.get(c.id)
        if entry and not entry.opportunity and _location_at(case, c.id, inc.time) == inc.location_id:
            v.append(Violation("R4_TIMELINE", f"기회가 없다는 {c.id}가 사건 시각에 사건 장소에 있다", c.id))
        if c.is_accomplice and _location_at(case, c.id, inc.time) == inc.location_id:
            v.append(Violation("R4_TIMELINE", f"공범 {c.id}가 사건 현장에 있다(알리바이 설계와 어긋남)", c.id))

    # ---- R7: 외모·공개 문구에 범인 암시 금지 --------------------------------------------
    for c in case.characters:
        for k, val in c.appearance.items():
            text = f"{k} {val}".lower()
            for w in BANNED_APPEARANCE_WORDS:
                if w in text:
                    v.append(Violation("R7_APPEARANCE", f"{c.id}의 appearance[{k}]에 금지어 '{w}'", c.id))
    public_text = case.incident.summary + " " + " ".join(str(x) for x in case.storyboard.get("briefing", []) if True)
    public_text += " " + str(case.storyboard.get("intro", ""))
    for cid in culprits & set(chars):
        if chars[cid].name in public_text:
            v.append(Violation("R7_APPEARANCE", f"공개 문구(사건 요약·브리핑·도입)에 범인 이름 {chars[cid].name}가 있다", cid))

    # ---- S: 간이 풀이 가능성 -------------------------------------------------------------
    for e in case.evidence:
        if e.is_key and e.id not in obtainable:
            v.append(Violation("S_SOLVABLE", f"핵심 증거 {e.id}를 플레이어가 얻을 수 없다", e.id))

    def covered(char: Character) -> set[str]:
        out: set[str] = set()
        for e in case.evidence:
            if e.id in obtainable and char.id in e.linked_suspects:
                out.update(e.element_tags)
        return out

    for cid in culprits & set(chars):
        miss = [el for el in ELEMENTS if el not in covered(chars[cid])]
        if miss:
            v.append(Violation("S_SOLVABLE", f"범인 {cid}의 {miss}를 보이는 획득 가능 증거가 없다", cid))
    for c in case.characters:
        if c.id in culprits or c.is_accomplice:
            continue
        if len(covered(c)) == 3:
            v.append(Violation("S_SOLVABLE", f"무고한 용의자 {c.id}를 가리키는 증거만으로도 동기·수단·기회가 모두 채워진다", c.id))
    return v

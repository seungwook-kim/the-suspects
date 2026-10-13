"""사건 생성 ⑩ 직전: 뼈대(plan) + 작가 출력(writer)을 사건 원본(CaseBible)으로 조립한다 (코드)."""

from __future__ import annotations

import random

from server.cases.generate.plan import ACCESSORIES, EVIDENCE_SLOTS, LIE_SLOTS, LOCATION_SLOTS, OUTFITS, Plan
from server.cases.generate.writer import CastOut, ConceptOut, DesignOut, DocsOut, MemoriesOut
from server.schemas import (
    BluffClaimDef,
    CaseBible,
    CaseDocument,
    Character,
    DocSection,
    Evidence,
    Incident,
    LieEntry,
    Location,
    MemoryDoc,
    MMOEntry,
    RecordRow,
    Relation,
    RoutineEntry,
    TimelineEvent,
)

# 장소 칸 → 해금 조건 (값의 '증거 칸'·'플롯 역할'은 실제 id로 바꾼다)
_UNLOCK = {"scene": ("evidence", "scene_hint"), "watch": ("talk", "witness"), "store": ("evidence", "store_trace"),
           "private": ("talk", "h1")}
# 낮 동안 머무는 곳 (플롯 역할 → [(장소 칸, 가중치)]). day_location이 열린 곳 중 가중치가 큰 곳을 고른다.
_DAY_PLACES = {"culprit": [("main", 300), ("rest", 120)], "witness": [("watch", 400), ("entry", 200)],
               "h1": [("private", 400), ("main", 200)], "h2": [("main", 300), ("entry", 100)]}
_BYSTANDER_PLACES = [[("rest", 300), ("main", 100)], [("entry", 300), ("rest", 100)], [("main", 300), ("rest", 100)]]


def _hhmm(m: int) -> str:
    m %= 1440
    return f"{m // 60:02d}:{m % 60:02d}"


def _parse_hhmm(s: str, default: int) -> int:
    try:
        h, m = s.strip().split(":")
        return int(h) * 60 + int(m)
    except (ValueError, AttributeError):
        return default


def assemble(plan: Plan, concept: ConceptOut, cast: CastOut, design: DesignOut,
             memories: dict[str, MemoriesOut], docs: DocsOut) -> CaseBible:
    rng = random.Random(plan.case_id)
    pid = {p.plot: p.id for p in plan.people}  # 플롯 역할 → 인물 id
    name = {p.id: p.name for p in plan.people}
    eid = plan.evidence_ids
    lie_id = {l.key: f"L{i + 1}" for i, l in enumerate(LIE_SLOTS)}
    loc_names = {l.slot: l for l in concept.locations}
    lid = plan.loc_id
    T = plan.incident_time

    # ---- 장소
    locations = []
    for slot, _ in LOCATION_SLOTS:
        lo = loc_names[slot]
        cond = None
        if slot in _UNLOCK:
            kind, ref = _UNLOCK[slot]
            cond = f"evidence:{eid[ref]}" if kind == "evidence" else f"talk:{pid[ref]}"
        locations.append(Location(
            id=lid(slot), name=lo.name, description=lo.description, unlock_condition=cond,
            investigate_evidence_ids=[eid[s.key] for s in EVIDENCE_SLOTS if s.location == slot],
        ))
    all_ids = [l.id for l in locations]
    for l in locations:  # 단순 연결: 입구에서 모두로, 나머지는 입구와 이웃 칸
        l.connections = [x for x in all_ids if x != l.id] if l.id == lid("entry") else [lid("entry")]

    # ---- 인물
    po = {x.slot: x for x in cast.people}
    characters = []
    for p in plan.people:
        o = po[p.slot]
        places = _DAY_PLACES.get(p.plot) or _BYSTANDER_PLACES[(int(p.plot[1:]) - 1) % 3]
        routine, start = [], 9 * 60
        for slot, w in places:
            routine.append(RoutineEntry(start=start, end=start + w, location_id=lid(slot)))
            start += w
        characters.append(Character(
            id=p.id, name=p.name, role=o.role, age=o.age, gender=p.gender,  # type: ignore[arg-type]
            appearance={"hair": p.hair, "hair_color": p.hair_color,
                        "outfit": o.outfit if o.outfit in OUTFITS else "casual",
                        **({"accessory": o.accessory} if o.accessory in ACCESSORIES and o.accessory else {})},
            face_seed=p.face_seed, personality=o.personality, temperament=o.temperament,
            small_talk_style=o.small_talk_style, speech_style=o.speech_style, goals=o.goals, secrets=o.secrets,
            routine=routine, tier="minor" if p.plot.startswith("b") else "main",
            record_access=["access_log", "cctv"] if p.plot == "witness" else [],
            key_witness=p.plot == "witness", is_culprit=p.plot == "culprit",
        ))
    slot_to_id = {p.slot: p.id for p in plan.people}
    for r in cast.relations:
        a, b = slot_to_id.get(r.a), slot_to_id.get(r.b)
        if not a or not b or a == b:
            continue
        for x, y in ((a, b), (b, a)):
            ch = next(c for c in characters if c.id == x)
            if all(rel.target != y for rel in ch.relations):
                ch.relations.append(Relation(target=y, type=r.type, detail=r.detail, known_publicly=r.known_publicly))

    # ---- 증거
    ev_text = {e.key: e for e in design.evidence}
    evidence = []
    for s in EVIDENCE_SLOTS:
        t = ev_text[s.key]
        evidence.append(Evidence(
            id=eid[s.key], name=t.name, kind=s.kind, content=t.content,  # type: ignore[arg-type]
            location_id=lid(s.location) if s.location else None, visibility=list(s.visibility), is_key=s.is_key,
            element_tags=s.elements, linked_suspects=[pid[k] for k in s.linked if k in pid],  # type: ignore[arg-type]
            reveals_contradiction_of=[lie_id[k] for k in s.rebuts], public_area=s.public_area,
        ))

    # ---- 거짓말 장부
    lie_text = {l.key: l for l in design.lies}
    lie_ledger = [LieEntry(id=lie_id[l.key], liar_id=pid[l.liar], topic=lie_text[l.key].topic, lie=lie_text[l.key].lie,
                           truth=lie_text[l.key].truth,
                           rebuttal_evidence_ids=[eid[s.key] for s in EVIDENCE_SLOTS if l.key in s.rebuts])
                  for l in LIE_SLOTS]

    # ---- 타임라인 (사건 당일 분 단위)
    beat_text = {b.idx: b.action for b in design.timeline}
    timeline = [TimelineEvent(time=T + b.offset, character_id=pid[b.who], location_id=lid(b.location),
                              action=beat_text.get(i, b.hint)) for i, b in enumerate(plan.beats)]

    # ---- 정형 기록: 타임라인에서 출입 기록, 핵심 연결 + 잡음 (PRD §5.2 ⑥: 잡음은 코드로)
    records: list[RecordRow] = []
    loc_by_id = {l.id: l for l in locations}

    def rec(system: str, time: int, person: str | None, loc: str | None, detail: str, vis: list[str], ev: str | None = None):
        records.append(RecordRow(id=f"rec_{system}_{len(records) + 1:03d}", system=system, time=time,  # type: ignore[arg-type]
                                 person_id=person, location_id=loc, detail=detail, visibility=vis, evidence_id=ev))

    for t in timeline:
        if t.location_id in loc_by_id:
            ev = None
            if t.character_id == pid["culprit"] and t.location_id == lid("scene"):
                ev = eid["x_opportunity"]
            elif t.character_id == pid["h2"] and t.location_id == lid("scene"):
                ev = eid["h2_opportunity"]
            rec("access_log", t.time - 1, t.character_id, t.location_id,
                f"{name[t.character_id]} {loc_by_id[t.location_id].name} 출입", ["player", f"npc:{t.character_id}"], ev)
    for c in characters:  # 잡음: 아침 출근·점심 외출
        rec("access_log", rng.randrange(8 * 60, 9 * 60 + 30), c.id, lid("entry"), f"{c.name} 출근", ["player", f"npc:{c.id}"])
        rec("access_log", rng.randrange(12 * 60, 13 * 60), c.id, lid("entry"), f"{c.name} 점심 외출", ["player", f"npc:{c.id}"])
    rec("call", T - 120, pid["culprit"], None, f"{name[pid['culprit']]} 발신 통화 4분", ["warrant:call", f"npc:{pid['culprit']}"], eid["x_call"])
    for c in characters[:3]:
        rec("call", rng.randrange(18 * 60, 21 * 60), c.id, None, f"{c.name} 통화 2분", ["warrant:call", f"npc:{c.id}"])
    records.sort(key=lambda r: r.time)

    # ---- 초기 기억
    mems: list[MemoryDoc] = []

    def mem(owner: str, content: str, time: int, kind: str = "observation", ev: str | None = None, tags: list[str] | None = None):
        vis = ["public"] if owner == "public" else [f"npc:{owner}"]
        mems.append(MemoryDoc(id=f"mem_{len(mems) + 1:03d}", case_id=plan.case_id, slot_id="template", owner=owner,
                              visibility=vis, doc_type=kind, content=content, game_time=time,  # type: ignore[arg-type]
                              evidence_id=ev, tags=tags or []))

    mem("public", concept.incident_summary, 540, tags=["사건", loc_names["scene"].name])
    mem("public", f"{concept.setting} 장소: " + ", ".join(l.name for l in locations), 540, tags=["장소"])
    w = pid["witness"]
    mem(w, design.witness_line, T - 8, ev=eid["w_testimony"], tags=[name[pid["culprit"]], _hhmm(T - 8), loc_names["scene"].name])
    for p in plan.people:
        for i, (b_idx, b) in enumerate((i, b) for i, b in enumerate(plan.beats) if b.who == p.plot):
            where = loc_names[b.location].name if b.location in loc_names else b.location.removeprefix("off:")
            mem(p.id, f"{_hhmm(T + b.offset)}쯤 {where}: {beat_text.get(b_idx, b.hint)}", T + b.offset,
                tags=[where, _hhmm(T + b.offset)])
        for m in (memories.get(p.slot) or MemoriesOut(memories=[])).memories:
            mem(p.id, m.content, _parse_hhmm(m.time, T), kind=m.kind, tags=[x for x in [m.time] if x])

    # ---- 문서
    documents = []
    for i, d in enumerate(docs.documents[:3]):
        documents.append(CaseDocument(id=f"doc_{i + 1}", title=d.title, doc_type=d.doc_type, visibility=["public"],
                                      sections=[DocSection(heading=s.heading, text=s.text, context=s.context) for s in d.sections]))

    # ---- 블러핑 주장 (코드: 사실 여부는 구조에서 나온다)
    zero = {c.id: 0.0 for c in characters}
    scene = loc_names["scene"].name
    bluff_claims = [
        BluffClaimDef(id="bc_access", label=f"{scene} 출입 기록을 확보했다",
                      truth_by_target={**zero, pid["culprit"]: 1.0, pid["h2"]: 0.5}),
        BluffClaimDef(id="bc_witness", label=f"{scene} 쪽으로 가는 걸 본 목격자가 있다", truth_by_target={**zero, pid["culprit"]: 1.0}),
        BluffClaimDef(id="bc_tool", label="범행에 쓴 물건을 찾아냈다", truth_by_target={**zero, pid["culprit"]: 1.0, pid["h1"]: 0.5}),
        BluffClaimDef(id="bc_confess", label="다른 사람이 이미 다 털어놨다", truth_by_target=dict(zero)),
    ]

    mmo = {
        pid["culprit"]: MMOEntry(motive=cast.culprit_motive, means=cast.culprit_means, opportunity=cast.culprit_opportunity),
        pid["h1"]: MMOEntry(motive=cast.h1_motive, means=cast.h1_means),
        pid["h2"]: MMOEntry(motive=cast.h2_motive, opportunity=cast.h2_opportunity),
    }
    culprit_ch = next(c for c in characters if c.is_culprit)
    return CaseBible(
        case_id=plan.case_id, title=concept.title, theme=plan.theme_text, tone=plan.tone,  # type: ignore[arg-type]
        difficulty=plan.difficulty, skeleton=plan.skeleton,  # type: ignore[arg-type]
        incident=Incident(time=T, location_id=lid("scene"), summary=concept.incident_summary),
        start_location_id=lid("entry"), locations=locations, characters=characters, culprit_ids=[pid["culprit"]],
        mmo=mmo, trick=cast.trick, timeline=timeline, evidence=evidence, lie_ledger=lie_ledger, records=records,
        documents=documents, bluff_claims=bluff_claims, initial_memories=mems,
        storyboard={"intro": docs.intro, "briefing": docs.briefing, "red_herrings": [name[pid["h1"]], name[pid["h2"]]],
                    "solution_path": [ev_text[k].name for k in ("scene_hint", "x_opportunity", "store_trace", "x_means", "x_motive")]},
        fingerprint={"motive_type": plan.motive_type, "trick_type": plan.skeleton, "culprit_role": culprit_ch.role,
                     "synopsis": cast.synopsis, "generated": True},
    )

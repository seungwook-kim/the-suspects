"""사건 작가(LLM) 단계별 출력 스키마·지시문·가짜 출력 (PRD §5.2 ①③④⑤⑥⑦⑨).

작가는 plan.py가 정한 뼈대의 빈칸만 채운다: 장소 이름, 인물의 직업·성격·말투, 증거의 이름과 내용,
거짓말 문장, 타임라인 행동, 기억, 문서. 가짜 LLM 모드에서도 같은 스키마로 그럴듯한 빈칸을 채워
키 없이 생성 → 검수 → 플레이까지 테스트할 수 있다.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from server.cases.generate.plan import (
    ACCESSORIES,
    EVIDENCE_SLOTS,
    LIE_SLOTS,
    LOCATION_SLOTS,
    OUTFITS,
    PLOT_DESC,
    SKELETONS,
    Plan,
)
from server.cases.verify import BANNED_APPEARANCE_WORDS

TONE_KO = {"comic": "코믹하고 가벼운", "balanced": "적당히 긴장감 있는", "serious": "진지하고 묵직한"}

COMMON = (
    "너는 추리 게임 'The Suspects'의 사건 작가다. 무대는 반드시 현대 한국(중세·SF·판타지 금지)이고, "
    "실존 인물·실존 기업·실제 사건을 쓰지 않는다. 잔혹한 묘사와 성적인 내용은 쓰지 않는다. "
    "모든 문장은 자연스러운 한국어로 쓴다."
)


def _hhmm(m: int) -> str:
    m %= 1440
    return f"{m // 60:02d}:{m % 60:02d}"


# =============================================================================== ① + ③ 주제 다듬기·세계관
class LocOut(BaseModel):
    slot: str
    name: str = Field(max_length=24)
    description: str


class ConceptOut(BaseModel):
    ok: bool = True
    reject_reason: str = ""
    title: str = ""
    setting: str = ""  # 현대 배경으로 다듬은 무대 (한 문장)
    incident_what: str = ""  # 무슨 일이 벌어졌나 (짧게, 예: "축제 대상 상장이 사라졌다")
    incident_summary: str = ""  # 브리핑용 공개 요약 2~3문장
    locations: list[LocOut] = Field(default_factory=list)


def concept_prompt(plan: Plan) -> tuple[str, str]:
    sk = SKELETONS[plan.skeleton]
    slots = "\n".join(f"- {k}: {d}" for k, d in LOCATION_SLOTS)
    system = (
        f"{COMMON}\n지금은 ①주제 검토와 ③세계관 설계 단계다.\n"
        "먼저 주제가 게임으로 만들기에 부적절한지 판단한다(실존 인물 비방, 미성년자 관련 성적 내용, 혐오·차별 조장, "
        "실제 참사 희화화, 범죄 방법 교육 목적 등). 부적절하면 ok=false와 reject_reason(플레이어에게 보일 한 문장)만 쓴다.\n"
        "괜찮으면 주제를 현대 한국 배경의 작은 사건으로 다듬고, 아래 장소 칸마다 이 무대에 맞는 장소 이름과 한두 문장 설명을 쓴다. "
        "incident_summary는 형사가 브리핑에서 듣는 공개 요약이라 범인이나 용의자 이름을 넣지 않는다."
    )
    user = (
        f"주제: {plan.theme_text}\n분위기: {TONE_KO.get(plan.tone, '')}\n사건 구조: {sk['label']} — {sk['desc']}\n"
        f"사건 시각: 사건 당일 {_hhmm(plan.incident_time)}, {plan.weather}\n"
        f"장소 칸 (slot 값을 그대로 쓴다):\n{slots}"
    )
    return system, user


def validate_concept(c: ConceptOut) -> list[str]:
    if not c.ok:
        return [] if c.reject_reason.strip() else ["거절할 때는 reject_reason을 쓴다"]
    p = []
    if not c.title.strip() or len(c.title) > 30:
        p.append("title은 1~30자")
    if not c.incident_summary.strip():
        p.append("incident_summary가 비었다")
    got = [l.slot for l in c.locations]
    want = [k for k, _ in LOCATION_SLOTS]
    if sorted(got) != sorted(want):
        p.append(f"locations는 slot {want}를 하나씩 모두 써야 한다 (받은 것: {got})")
    names = [l.name for l in c.locations]
    if len(set(names)) != len(names):
        p.append("장소 이름이 겹친다")
    return p


def fake_concept(plan: Plan) -> ConceptOut:
    names = {"entry": "1층 입구", "main": "중앙 사무실", "rest": "휴게실", "scene": "자료 보관실",
             "watch": "관리실", "store": "비품 창고", "private": "개인 작업실"}
    return ConceptOut(
        title=f"{plan.theme_text[:20]} 사건", setting=f"{plan.theme_text}을(를) 둘러싼 현대 한국의 작은 건물",
        incident_what="중요한 물건이 사라졌다",
        incident_summary=f"{_hhmm(plan.incident_time)}쯤 {names['scene']}에서 중요한 물건이 사라졌다. 그날 밤 건물에 남아 있던 사람은 몇 명뿐이다.",
        locations=[LocOut(slot=k, name=names[k], description=f"{names[k]}. {d}") for k, d in LOCATION_SLOTS],
    )


# =============================================================================== ④ 인물
class PersonOut(BaseModel):
    slot: str
    role: str = Field(max_length=30)  # 직업·역할
    age: int = Field(ge=18, le=80)
    personality: str  # 2문장. 첫 문장은 겉으로 보이는 성격(공개), 둘째 문장은 속사정
    speech_style: str
    temperament: Literal["timid", "normal", "cold"] = "normal"
    small_talk_style: Literal["chatty", "normal", "blunt"] = "normal"
    outfit: str = "casual"
    accessory: str = ""
    goals: list[str] = Field(default_factory=list)
    secrets: list[str] = Field(default_factory=list)


class RelOut(BaseModel):
    a: str
    b: str
    type: str
    detail: str = ""
    known_publicly: bool = False


class CastOut(BaseModel):
    people: list[PersonOut]
    relations: list[RelOut] = Field(default_factory=list)
    culprit_motive: str
    culprit_means: str
    culprit_opportunity: str
    trick: str
    h1_motive: str
    h1_means: str
    h2_motive: str
    h2_opportunity: str
    synopsis: str  # 진상 한 문장 (비공개)


def _plot_label(plot: str) -> str:
    return PLOT_DESC["bystander"] if plot.startswith("b") else PLOT_DESC[plot]


def cast_prompt(plan: Plan, concept: ConceptOut) -> tuple[str, str]:
    system = (
        f"{COMMON}\n지금은 ④인물 생성 단계다. 각 인물 칸(slot)에 이 무대에 어울리는 직업·나이·성격·말투·목표·비밀을 쓴다.\n"
        "- personality는 두 문장. 첫 문장은 처음 보는 사람도 알 수 있는 겉모습 성격만 쓴다(범인 암시 금지). 둘째 문장은 속사정.\n"
        "- speech_style은 말버릇이 드러나게 구체적으로 (사투리·존댓말·입버릇 예시 포함). 인물끼리 말투가 겹치지 않게 한다.\n"
        f"- outfit은 {OUTFITS} 중 하나, accessory는 {ACCESSORIES} 중 하나.\n"
        "- relations는 인물 사이 관계 4~8개 (a, b는 slot 값).\n"
        "- 범인의 동기·수단·기회와 트릭, 의심 인물 두 명(H1, H2)의 동기·수단·기회를 사건 구조에 맞게 구체적으로 쓴다. "
        "무고한 사람이 동기·수단·기회를 다 갖추면 안 된다."
    )
    people = "\n".join(
        f"- {p.slot}: 이름 {p.name}, 성별 {'남' if p.gender == 'M' else '여'}, 역할(비밀) {p.plot.upper() if not p.plot.startswith('b') else '주변 인물'} — {_plot_label(p.plot)}"
        for p in plan.people
    )
    sk = SKELETONS[plan.skeleton]
    user = (
        f"사건: {concept.title} — {concept.incident_what}\n무대: {concept.setting}\n"
        f"사건 구조: {sk['label']} — {sk['desc']}\n동기 유형(범인): {plan.motive_type}\n"
        f"장소: {', '.join(l.name for l in concept.locations)}\n분위기: {TONE_KO.get(plan.tone, '')}\n"
        f"인물 칸 (이름·성별은 바꾸지 않는다):\n{people}"
    )
    return system, user


def validate_cast(plan: Plan, c: CastOut) -> list[str]:
    p = []
    want = sorted(x.slot for x in plan.people)
    got = sorted(x.slot for x in c.people)
    if got != want:
        p.append(f"people은 slot {want}를 하나씩 모두 써야 한다 (받은 것: {got})")
    for x in c.people:
        first = x.personality.split(". ")[0]
        bad = [w for w in BANNED_APPEARANCE_WORDS if w in first]
        if bad:
            p.append(f"{x.slot}의 personality 첫 문장에 범인을 암시하는 말 {bad}")
        if not x.speech_style.strip():
            p.append(f"{x.slot}의 speech_style이 비었다")
    for r in c.relations:
        if r.a not in want or r.b not in want:
            p.append(f"relations에 없는 slot: {r.a}, {r.b}")
    return p


_ROLES = ["직원", "관리인", "아르바이트생", "방문객", "청소원", "경비원", "팀장"]


def fake_cast(plan: Plan) -> CastOut:
    people = []
    for i, x in enumerate(plan.people):
        people.append(PersonOut(
            slot=x.slot, role=_ROLES[i % len(_ROLES)], age=25 + i * 6,
            personality=f"차분하고 성실해 보인다. 속으로는 {plan.motive_type if x.plot == 'culprit' else '걱정이 많다'}.",
            speech_style=["존댓말, '그러니까요'를 자주 씀", "반말 섞인 짧은 말투", "느릿한 사투리", "또박또박한 다나까체",
                          "말끝을 흐림", "밝고 빠른 말투", "무뚝뚝하게 단답"][i % 7],
            temperament=["timid", "normal", "cold"][i % 3], small_talk_style=["chatty", "normal", "blunt"][i % 3],
            outfit=OUTFITS[i % len(OUTFITS)], accessory=ACCESSORIES[i % len(ACCESSORIES)],
            goals=["일을 무사히 마치기"], secrets=["남에게 말하지 않은 사정이 있다"],
        ))
    s = [x.slot for x in plan.people]
    return CastOut(
        people=people, relations=[{"a": s[0], "b": s[1], "type": "동료", "detail": "같이 일한다", "known_publicly": True}],
        culprit_motive=plan.motive_type, culprit_means="보관된 열쇠를 미리 챙겼다", culprit_opportunity="사건 시각 현장에 혼자 있었다",
        trick="열쇠를 몰래 꺼내 썼다가 제자리에 돌려놓았다", h1_motive="사건 대상과 다툰 적이 있다", h1_means="열쇠 위치를 알았다",
        h2_motive="손해를 본 적이 있다", h2_opportunity="사건 직전 현장 근처에 갔다", synopsis="범인이 몰래 꺼낸 열쇠로 현장에 들어갔다.",
    )


# =============================================================================== ⑤⑦ 사건 설계: 증거·거짓말·타임라인
class EvOut(BaseModel):
    key: str
    name: str = Field(max_length=30)
    content: str


class LieOut(BaseModel):
    key: str
    topic: str = Field(max_length=30)
    lie: str
    truth: str


class BeatOut(BaseModel):
    idx: int
    action: str


class DesignOut(BaseModel):
    evidence: list[EvOut]
    lies: list[LieOut]
    timeline: list[BeatOut]
    witness_line: str  # 목격자가 기억하는 장면 (기억 원문, 한두 문장)


def design_prompt(plan: Plan, concept: ConceptOut, cast: CastOut, problems: list[str] | None = None) -> tuple[str, str]:
    name = {p.plot: p.name for p in plan.people}
    loc = {l.slot: l.name for l in concept.locations}

    def who(keys: list[str]) -> str:
        return ", ".join(name.get(k, k) for k in keys) or "특정 인물 없음"

    ev_lines = []
    for s in EVIDENCE_SLOTS:
        where = loc.get(s.location, "") if s.location else ("목격자와의 대화" if s.kind == "testimony" else "영장(통화 기록)")
        ev_lines.append(f"- {s.key} [{s.kind}{', 핵심' if s.is_key else ''}] 위치: {where} / 관련 인물: {who(s.linked)} / {s.purpose}")
    lie_lines = [f"- {l.key}: {name[l.liar]} — {l.about}" for l in LIE_SLOTS]
    beat_lines = [f"- {i}: {_hhmm(plan.incident_time + b.offset)} {name.get(b.who, b.who)} @ "
                  f"{loc.get(b.location, b.location.removeprefix('off:'))} — {b.hint}" for i, b in enumerate(plan.beats)]
    system = (
        f"{COMMON}\n지금은 ⑤사건 설계와 ⑦거짓말 장부·증거 지도 단계다. 구조(누가 범인이고 증거가 무엇을 증명하는지)는 "
        "이미 정해져 있다. 너는 각 칸의 이름과 내용을 이 사건에 맞게 구체적으로 쓴다.\n"
        "- 증거 name은 수첩에 보일 짧은 이름(30자 이내), content는 형사가 보는 내용 1~3문장. 시각·장소·이름을 구체적으로.\n"
        "- 증거끼리, 그리고 타임라인과 시각·장소가 어긋나지 않게 한다. 핵심 증거는 범인을 분명히 가리키되 레드 헤링 증거는 H1·H2를 그럴듯하게 의심하게 한다.\n"
        "- 거짓말: topic은 형사가 물을 만한 주제(짧게), lie는 그 인물이 할 거짓말, truth는 실제 사실.\n"
        "- timeline: idx마다 그 인물이 그 시각에 한 행동을 한 문장으로.\n"
        "- witness_line: 목격자가 기억하는 장면을 목격자 시점의 사실 문장으로(시각 포함)."
    )
    user = (
        f"사건: {concept.title} — {concept.incident_what} ({_hhmm(plan.incident_time)}, {loc['scene']})\n"
        f"진상: {cast.synopsis}\n트릭: {cast.trick}\n"
        f"범인 {name['culprit']}: 동기 {cast.culprit_motive} / 수단 {cast.culprit_means} / 기회 {cast.culprit_opportunity}\n"
        f"H1 {name['h1']}: 동기 {cast.h1_motive} / 수단 {cast.h1_means} (기회 없음)\n"
        f"H2 {name['h2']}: 동기 {cast.h2_motive} / 기회 {cast.h2_opportunity} (수단 없음)\n"
        f"목격자 {name['witness']}\n\n증거 칸:\n" + "\n".join(ev_lines)
        + "\n\n거짓말 칸:\n" + "\n".join(lie_lines) + "\n\n타임라인 칸:\n" + "\n".join(beat_lines)
    )
    if problems:
        user += "\n\n[지난 설계의 검수 지적 — 고쳐서 다시]\n- " + "\n- ".join(problems)
    return system, user


def validate_design(plan: Plan, d: DesignOut) -> list[str]:
    p = []
    want = {s.key for s in EVIDENCE_SLOTS}
    got = {e.key for e in d.evidence}
    if want - got:
        p.append(f"증거 칸이 빠졌다: {sorted(want - got)}")
    names = [e.name for e in d.evidence if e.key in want]
    if len(set(names)) != len(names):
        p.append("증거 이름이 겹친다")
    if {l.key for l in LIE_SLOTS} - {l.key for l in d.lies}:
        p.append("거짓말 칸이 빠졌다")
    if {i for i in range(len(plan.beats))} - {b.idx for b in d.timeline}:
        p.append("타임라인 칸이 빠졌다")
    if not d.witness_line.strip():
        p.append("witness_line이 비었다")
    return p


def fake_design(plan: Plan, concept: ConceptOut) -> DesignOut:
    name = {p.plot: p.name for p in plan.people}
    loc = {l.slot: l.name for l in concept.locations}
    t = _hhmm(plan.incident_time)
    ev = []
    for s in EVIDENCE_SLOTS:
        who = ", ".join(name.get(k, k) for k in s.linked)
        ev.append(EvOut(key=s.key, name=f"{(loc.get(s.location) or '대화')[:8]} 단서 {s.key[:10]}",
                        content=f"{who or '누군가'}와 관련된 단서. {s.purpose}"))
    lies = [LieOut(key=l.key, topic=l.about.split(" (")[0], lie="그 일과는 상관없어요.", truth=l.about) for l in LIE_SLOTS]
    beats = [BeatOut(idx=i, action=b.hint) for i, b in enumerate(plan.beats)]
    return DesignOut(evidence=ev, lies=lies, timeline=beats,
                     witness_line=f"{t} 조금 전, {name['culprit']} 씨가 {loc['scene']} 쪽으로 가는 걸 봤다.")


# =============================================================================== ⑥ 인물별 기억
class MemOut(BaseModel):
    time: str = ""  # "HH:MM" 또는 빈 문자열(시각 없는 기억)
    kind: Literal["observation", "heard", "reflection"] = "observation"
    content: str = Field(max_length=200)


class MemoriesOut(BaseModel):
    memories: list[MemOut]


def memory_prompt(plan: Plan, concept: ConceptOut, cast: CastOut, design: DesignOut, slot: str) -> tuple[str, str]:
    person = next(p for p in plan.people if p.slot == slot)
    po = next(x for x in cast.people if x.slot == slot)
    name = {p.slot: p.name for p in plan.people}
    loc = {l.slot: l.name for l in concept.locations}
    beats = [f"{_hhmm(plan.incident_time + b.offset)} {loc.get(b.location, b.location.removeprefix('off:'))}: "
             f"{next((t.action for t in design.timeline if t.idx == i), b.hint)}"
             for i, b in enumerate(plan.beats) if b.who == person.plot]
    lies = [f"- (진실) {l.truth}" for l in design.lies
            if next(s for s in LIE_SLOTS if s.key == l.key).liar == person.plot]
    rels = [f"- {name.get(r.b if r.a == slot else r.a, '')}: {r.type} — {r.detail}" for r in cast.relations if slot in (r.a, r.b)]
    extra = ""
    if person.plot == "culprit":
        extra = f"\n이 인물은 범인이다. 진상: {cast.synopsis} 트릭: {cast.trick} (기억에는 진실을 쓴다. 거짓말은 대화할 때만 한다)"
    elif person.plot == "witness":
        extra = f"\n이 인물이 본 장면: {design.witness_line}"
    system = (
        f"{COMMON}\n지금은 ⑥인물 기억 단계다. 이 인물이 '사실로 기억하는 것' 3~5개를 쓴다. 기억은 이 인물만 아는 진실이며, "
        "나중에 형사와 대화할 때 근거로 쓰인다. 각 기억은 한두 문장의 담담한 사실 문장(예: '22시 10분쯤 휴게실에서 커피를 마셨다.'). "
        "그날 밤 행동, 다른 인물에 대해 보고 들은 것, 자기 비밀이나 속마음을 고르게 섞는다. 이 인물이 알 수 없는 일은 쓰지 않는다."
    )
    user = (
        f"사건: {concept.title} — {concept.incident_what}\n인물: {person.name} ({po.role}, {po.age}세) — {po.personality}\n"
        f"비밀: {po.secrets}\n그날 밤 행동:\n" + "\n".join(f"- {b}" for b in beats)
        + ("\n숨기는 일의 진실:\n" + "\n".join(lies) if lies else "") + ("\n관계:\n" + "\n".join(rels) if rels else "") + extra
    )
    return system, user


def validate_memories(m: MemoriesOut) -> list[str]:
    return [] if 2 <= len(m.memories) <= 6 else ["기억은 2~6개"]


def fake_memories(plan: Plan, slot: str) -> MemoriesOut:
    person = next(p for p in plan.people if p.slot == slot)
    beats = [b for b in plan.beats if b.who == person.plot]
    return MemoriesOut(memories=[MemOut(time=_hhmm(plan.incident_time + b.offset), content=f"{b.hint}.") for b in beats[:4]]
                       or [MemOut(content="그날 밤은 평소와 다르지 않았다."), MemOut(content="별다른 일은 없었다.")])


# =============================================================================== ⑥⑨ 문서·스토리보드
class SecOut(BaseModel):
    heading: str
    text: str
    context: str = ""  # Contextual Retrieval용: 이 조각이 문서 안에서 무슨 내용인지 한 문장


class DocOut(BaseModel):
    title: str
    doc_type: Literal["manual", "wiki", "chat_log", "minutes", "statement", "diary", "email", "report", "notice"]
    sections: list[SecOut]


class DocsOut(BaseModel):
    documents: list[DocOut]
    intro: str  # 도입 장면 1~2문장
    briefing: list[str]  # 반장 브리핑 2~3줄


def docs_prompt(plan: Plan, concept: ConceptOut, cast: CastOut, design: DesignOut) -> tuple[str, str]:
    culprit = plan.by_plot("culprit").name
    people = ", ".join(f"{p.name}({next(x.role for x in cast.people if x.slot == p.slot)})" for p in plan.people)
    system = (
        f"{COMMON}\n지금은 ⑥문서와 ⑨스토리보드 단계다.\n"
        "- documents: 이 무대에 있을 법한 문서 2개. 하나는 그날 밤 사람들이 주고받은 단체 대화방이나 메신저 로그(chat_log, 섹션 2~3개, "
        "각 섹션에 시각과 화자를 넣은 대화 여러 줄), 하나는 공지·규정·회의록 같은 공용 문서(섹션 2~3개). 단서 한두 개를 문서 깊숙이 "
        "자연스럽게 심되 범인을 직접 지목하지 않는다. 섹션마다 context에 '이 조각이 문서 안에서 무슨 내용인지' 한 문장.\n"
        "- intro: 형사가 현장에 도착하는 도입 장면 1~2문장. briefing: 반장이 형사에게 하는 브리핑 2~3줄. "
        f"intro와 briefing에는 범인({culprit})의 이름을 넣지 않는다."
    )
    user = (
        f"사건: {concept.title} — {concept.incident_summary}\n무대: {concept.setting}\n등장인물: {people}\n"
        f"진상(비공개, 참고만): {cast.synopsis}\n"
        f"심을 수 있는 단서 예: " + "; ".join(e.content for e in design.evidence[:6])
    )
    return system, user


def validate_docs(plan: Plan, d: DocsOut) -> list[str]:
    p = []
    if not 1 <= len(d.documents) <= 3:
        p.append("documents는 2개")
    culprit = plan.by_plot("culprit").name
    if culprit in d.intro or any(culprit in b for b in d.briefing):
        p.append("intro·briefing에 범인 이름이 있다")
    return p


def fake_docs(plan: Plan, concept: ConceptOut) -> DocsOut:
    return DocsOut(
        documents=[DocOut(title=f"{concept.title} 그날 밤 단체 대화방", doc_type="chat_log",
                          sections=[SecOut(heading="21시~22시", text="다들 아직 안 갔어요? 늦게까지 수고하네요.", context="사건 전 대화")]),
                   DocOut(title="시설 이용 안내", doc_type="notice",
                          sections=[SecOut(heading="출입 규정", text="22시 이후 출입은 기록이 남습니다.", context="출입 규정")])],
        intro=f"{concept.incident_summary}", briefing=["사건 현장부터 둘러봐.", "그날 밤 남아 있던 사람들을 만나 봐."],
    )

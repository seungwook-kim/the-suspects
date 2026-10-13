"""사건 생성 ②단계: 재료 추첨과 구조 설계 (코드, LLM 없음 — PRD §5.2, §5.6).

규칙은 코드, 연기는 LLM. 누가 범인인지, 증거가 어디에 있고 무엇을 증명하는지, 거짓말마다 어떤 증거가 깨는지,
장소가 어떤 조건으로 열리는지는 여기서 정한다. LLM(사건 작가)은 이 뼈대에 이름·설명·대사를 입힌다.
그래서 작가가 아무리 들쭉날쭉해도 검수(server/cases/verify.py)의 구조 규칙은 설계상 통과한다.

뼈대(인물 수 n = 5~7)
  범인 X        : 동기·수단·기회 모두. 사건 시각에 현장.
  의심 인물 H1  : 동기 + 수단 (기회 없음 — 그 시각 건물 밖)
  의심 인물 H2  : 동기 + 기회 (수단 없음 — 사건 직전 현장 근처)
  목격자 W      : X가 현장 쪽으로 가는 걸 봄 (핵심 증인, 대화로 증언 증거)
  주변 인물 B*  : 사건과 무관 (분위기·잡담·소문)

장소 7곳: 입구·중심·휴게(처음부터 열림) / 현장(입구 단서로 열림) / 목격자 자리(W와 대화) /
         도구 보관처(현장 흔적으로 열림) / H1 개인 공간(H1과 대화)
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------- 재료 풀
SKELETONS: dict[str, dict[str, str]] = {
    "insider": {
        "label": "내부자형",
        "desc": "내부 사정을 잘 아는 사람이 평소의 접근 권한이나 동료의 허점을 이용했다. 현장 출입 흔적과 도구를 손에 넣은 경로가 핵심.",
    },
    "alibi": {
        "label": "알리바이형",
        "desc": "범인은 그럴듯한 알리바이를 미리 만들어 두었지만 몇 분짜리 빈틈이 있다. 출입 시각과 이동 시간이 핵심.",
    },
    "locked_room": {
        "label": "밀실형",
        "desc": "현장은 잠겨 있어 아무도 못 들어간 것처럼 보이지만, 범인만 아는 드나드는 방법이 있었다. 열쇠·카드·비밀번호의 행방이 핵심.",
    },
}
MOTIVES = ["금전 문제", "오래된 원한", "자리·승진 다툼", "질투", "자기 실수 은폐", "부당한 대우에 대한 복수", "지키고 싶은 비밀"]
WEATHER = ["맑은 밤", "비 오는 밤", "바람 부는 밤", "눈 오는 밤", "후텁지근한 밤", "안개 낀 밤"]

SURNAMES = ["김", "이", "박", "최", "정", "강", "조", "윤", "장", "임", "한", "오", "서", "신", "권", "황", "안", "송",
            "류", "전", "홍", "고", "문", "양", "손", "배", "백", "허", "노", "남궁", "하", "곽", "성", "차", "주", "우"]
GIVEN_M = ["민준", "서준", "도윤", "예준", "시우", "주원", "지호", "준서", "현우", "건우", "우진", "선우", "민재", "태식",
           "성만", "석진", "동현", "재훈", "승호", "기철", "영수", "상철", "정훈", "형준", "대호", "병철", "광수"]
GIVEN_F = ["서연", "서윤", "지우", "하은", "민서", "하윤", "윤서", "지민", "채원", "소라", "수아", "다은", "예린", "미경",
           "은정", "혜진", "지영", "수진", "미숙", "영희", "경희", "현주", "보람", "나연", "유진", "가영", "정숙"]
HAIR_F = ["long", "bun", "ponytail", "short", "curly", "side"]
HAIR_M = ["short", "side", "buzz", "curly", "bald", "short"]
HAIR_COLORS = ["#1f1a17", "#2b2220", "#3b2f2f", "#4a3728", "#5a4632", "#6b5a4e", "#8a8a8a", "#b9b9b9", "#7a4a2a"]
OUTFITS = ["suit", "casual", "hoodie", "cleaner_uniform", "security_uniform", "chef", "doctor", "delivery",
           "school_uniform", "work_clothes", "office_lanyard"]
ACCESSORIES = ["", "glasses", "cap", "badge", "mop", "radio", "laptop", "apron"]

# 장소 칸: (키, 작가에게 주는 역할 설명)
LOCATION_SLOTS: list[tuple[str, str]] = [
    ("entry", "처음 도착하는 입구·공용 공간. 출입 기록이나 안내 데스크가 있다."),
    ("main", "사람들이 주로 일하거나 머무는 중심 공간."),
    ("rest", "쉬는 공간 (휴게실·탕비실·매점 같은 곳)."),
    ("scene", "사건 현장."),
    ("watch", "목격자가 주로 지키는 곳 (관리실·경비실·안내실 같은 곳)."),
    ("store", "범행에 쓴 물건이나 수단이 원래 있던 곳 (창고·자료실·준비실 같은 곳)."),
    ("private", "의심받는 인물(H1)의 개인 공간."),
]

PLOT_DESC = {
    "culprit": "범인. 동기·수단·기회를 모두 가졌고 사건 시각에 현장에 있었다. 들키지 않으려 거짓말한다.",
    "h1": "무고하지만 의심받을 인물. 동기와 수단은 있지만 사건 시각에는 건물 밖에 있었다(기회 없음). 다른 부끄러운 비밀 때문에 그날 밤 일정을 숨긴다.",
    "h2": "무고하지만 의심받을 인물. 동기가 있고 사건 직전 현장 근처에 갔지만(기회), 범행 수단은 없다. 현장 근처에 간 사실을 숨긴다.",
    "witness": "목격자. 범인이 사건 직전 현장 쪽으로 가는 모습을 봤다. 신뢰를 얻으면 증언한다.",
    "bystander": "사건과 무관한 주변 인물. 분위기를 만들고 소문을 퍼뜨린다.",
}


@dataclass
class EvidenceSlot:
    key: str
    kind: str  # record | object | testimony | document
    location: str | None  # 장소 칸 키, None이면 대화(증언)나 영장으로 얻음
    is_key: bool
    elements: list[str]
    linked: list[str]  # 플롯 역할 키 (culprit, h1, ...)
    purpose: str  # 작가에게 주는 지시
    visibility: list[str] = field(default_factory=lambda: ["player"])
    rebuts: list[str] = field(default_factory=list)  # 거짓말 칸 키
    public_area: bool = False


@dataclass
class LieSlot:
    key: str
    liar: str  # 플롯 역할 키
    about: str


@dataclass
class Beat:
    who: str  # 플롯 역할 키 (bystander는 b1, b2 ...)
    offset: int  # 사건 시각 기준 분
    location: str  # 장소 칸 키 또는 off:<이름>
    hint: str


EVIDENCE_SLOTS: list[EvidenceSlot] = [
    # 입구
    EvidenceSlot("scene_hint", "record", "entry", False, [], [], "현장에 이상이 생겼다는 걸 처음 알려 주는 기록. 이걸 보면 현장을 살펴보러 가게 된다.", public_area=True),
    EvidenceSlot("entry_flavor", "object", "entry", False, [], ["b1"], "주변 인물 B1과 관련된 평범한 물건이나 메모. 사건과는 무관하다."),
    EvidenceSlot("h2_motive", "record", "entry", False, ["motive"], ["h2"], "H2가 사건 대상에 불만이나 이해관계가 있었음을 보여 주는 기록."),
    # 중심 공간
    EvidenceSlot("x_motive", "document", "main", True, ["motive"], ["culprit"], "범인의 동기를 보여 주는 문서. 범인이 '불만 없었다'고 한 말을 깬다.", rebuts=["x_motive_lie"]),
    EvidenceSlot("h1_motive", "document", "main", False, ["motive"], ["h1"], "H1에게도 동기가 있었음을 보여 주는 문서 (레드 헤링)."),
    EvidenceSlot("main_flavor", "object", "main", False, [], ["witness"], "목격자와 관련된 평범한 물건. 목격자가 그날 밤 어디서 일했는지 짐작하게 한다."),
    # 휴게 공간
    EvidenceSlot("h1_means", "object", "rest", False, ["means"], ["h1"], "H1도 범행 수단에 손댈 수 있었음을 보여 주는 물건 (레드 헤링)."),
    EvidenceSlot("rest_flavor", "object", "rest", False, [], [], "그날 밤의 분위기를 보여 주는 소품. 사건과는 무관하다."),
    # 현장
    EvidenceSlot("scene_state", "object", "scene", False, [], [], "현장에 남은 상태. 무슨 일이 벌어졌는지 보여 주지만 범인은 가리키지 않는다."),
    EvidenceSlot("x_opportunity", "record", "scene", True, ["opportunity"], ["culprit"], "범인이 사건 시각에 현장에 있었음을 보여 주는 기록(출입 기록·CCTV 등). 범인의 알리바이를 깬다.", rebuts=["x_alibi"]),
    EvidenceSlot("store_trace", "object", "scene", False, [], [], "현장에 남은 흔적. 범행에 쓴 물건이 '도구 보관처'에서 왔음을 가리킨다."),
    # 목격자 자리
    EvidenceSlot("h2_opportunity", "record", "watch", False, ["opportunity"], ["h2"], "H2가 사건 직전 현장 근처에 있었음을 보여 주는 근무·순찰 기록. H2의 거짓말을 깬다.", rebuts=["h2_lie"]),
    EvidenceSlot("watch_flavor", "record", "watch", False, [], ["b2"], "주변 인물 B2의 평범한 출입이나 근무 기록."),
    # 도구 보관처
    EvidenceSlot("x_means", "object", "store", True, ["means"], ["culprit"], "범인이 범행 수단을 손에 넣었음을 보여 주는 물건이나 기록. 트릭의 핵심."),
    EvidenceSlot("x_means_support", "record", "store", False, ["means"], ["culprit"], "범인의 수단을 뒷받침하는 보조 기록 (대여 장부·사용 기록 등)."),
    # H1 개인 공간
    EvidenceSlot("h1_secret", "document", "private", False, [], ["h1"], "H1이 그날 밤 숨기던 부끄럽지만 무고한 비밀을 보여 준다. H1의 거짓말을 깬다.", rebuts=["h1_lie"]),
    # 대화로 얻는 증언
    EvidenceSlot("w_testimony", "testimony", None, False, ["opportunity"], ["culprit"], "목격자의 증언: 사건 직전 범인이 현장 쪽으로 가는 걸 봤다. 범인의 알리바이를 깬다.", rebuts=["x_alibi"]),
    # 영장으로 얻는 기록
    EvidenceSlot("x_call", "record", None, False, ["motive"], ["culprit"], "범인의 통화 기록. 사건 전 동기와 관련된 통화가 있었다.", visibility=["warrant:call"]),
]

LIE_SLOTS: list[LieSlot] = [
    LieSlot("x_alibi", "culprit", "사건 시각 행방 (실제로는 현장에 있었다)"),
    LieSlot("x_motive_lie", "culprit", "사건 대상에 대한 불만이나 이해관계 (실제로는 동기가 있었다)"),
    LieSlot("h1_lie", "h1", "그날 밤 개인 일정 (부끄러운 비밀을 숨김, 범행과는 무관)"),
    LieSlot("h2_lie", "h2", "사건 직전 현장 근처에 간 일 (실제로는 갔지만 범행은 안 함)"),
]


def _beats(n_bystanders: int) -> list[Beat]:
    beats = [
        Beat("culprit", -60, "main", "평소처럼 지내며 기회를 엿본다"),
        Beat("culprit", -15, "store", "범행 수단을 손에 넣는다"),
        Beat("culprit", 0, "scene", "범행"),
        Beat("culprit", 20, "rest", "아무 일 없던 척한다"),
        Beat("witness", -45, "watch", "평소 업무"),
        Beat("witness", -8, "entry", "순찰·업무 중 범인이 현장 쪽으로 가는 걸 본다"),
        Beat("h1", -90, "private", "숨기고 싶은 개인 일"),
        Beat("h1", -40, "off:외부", "건물을 나선다 (사건 시각엔 밖)"),
        Beat("h2", -70, "main", "남아서 일한다"),
        Beat("h2", -30, "scene", "현장 근처에 잠깐 들른다"),
        Beat("h2", -18, "rest", "쉬다가 돌아간다"),
    ]
    for i in range(n_bystanders):
        b = f"b{i + 1}"
        beats.append(Beat(b, -150 + i * 10, ["main", "rest", "entry"][i % 3], "평범한 일과"))
        beats.append(Beat(b, -100 + i * 10, "off:집", "퇴근"))
    return beats


# ---------------------------------------------------------------------------- 추첨 결과
@dataclass
class Person:
    slot: str  # c1..cn
    id: str
    plot: str  # culprit | h1 | h2 | witness | b1 | b2 ...
    name: str
    gender: str
    face_seed: int
    hair: str
    hair_color: str


@dataclass
class Plan:
    case_id: str
    theme_text: str
    tone: str
    difficulty: str
    play_minutes: int
    skeleton: str
    motive_type: str
    weather: str
    incident_time: int
    people: list[Person]
    evidence_ids: dict[str, str]  # 증거 칸 키 -> E1..
    beats: list[Beat]

    def by_plot(self, plot: str) -> Person:
        return next(p for p in self.people if p.plot == plot)

    def loc_id(self, slot: str) -> str:
        return slot if slot.startswith("off:") else f"loc_{slot}"


def _names(rng: random.Random, n: int) -> list[tuple[str, str]]:
    """서로 헷갈리지 않는 이름: 성이 겹치지 않고, 이름(두 글자)도 겹치지 않는다."""
    surnames = rng.sample(SURNAMES, n)
    out, used = [], set()
    for s in surnames:
        g = rng.choice(["M", "F"])
        pool = [x for x in (GIVEN_M if g == "M" else GIVEN_F) if x not in used]
        given = rng.choice(pool)
        used.add(given)
        out.append((s + given, g))
    return out


def draw(case_id: str, theme_text: str, options: dict | None, seed: int | None = None) -> Plan:
    opts = options or {}
    rng = random.Random(seed)
    minutes = int(opts.get("play_minutes") or 40)
    n = {20: 5, 40: 6, 60: 7}.get(minutes, 6)
    plots = ["culprit", "h1", "h2", "witness"] + [f"b{i + 1}" for i in range(n - 4)]
    rng.shuffle(plots)  # 범인이 늘 첫 번째 인물이 되지 않게
    people = []
    for i, ((name, gender), plot) in enumerate(zip(_names(rng, n), plots)):
        people.append(Person(
            slot=f"c{i + 1}", id=f"npc_{i + 1:02d}", plot=plot, name=name, gender=gender,
            face_seed=rng.randrange(1, 2**31), hair=rng.choice(HAIR_F if gender == "F" else HAIR_M),
            hair_color=rng.choice(HAIR_COLORS),
        ))
    return Plan(
        case_id=case_id, theme_text=theme_text.strip(), tone=opts.get("tone") or "balanced",
        difficulty=opts.get("difficulty") or "normal", play_minutes=minutes,
        skeleton=rng.choice(list(SKELETONS)), motive_type=rng.choice(MOTIVES), weather=rng.choice(WEATHER),
        incident_time=rng.randrange(21 * 60 + 30, 23 * 60 + 31, 5), people=people,
        evidence_ids={s.key: f"E{i + 1}" for i, s in enumerate(EVIDENCE_SLOTS)},
        beats=_beats(n - 4),
    )

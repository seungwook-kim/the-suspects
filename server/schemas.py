"""공통 데이터 계약 (PRD 부록 A).

모든 모듈이 이 스키마를 공유한다. 필드를 바꾸면 사용처를 함께 고친다.
- 사건 원본(CaseBible)은 서버 안에서만 쓴다. 클라이언트로는 PlayerView만 나간다(AGENTS.md 규칙 7).
- 시각은 사건 첫날 00:00 기준 "분" 정수(game minutes)로 다룬다. 표시용 문자열은 변환해서 쓴다.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# 공통 타입
# ---------------------------------------------------------------------------

Tier = Literal["main", "minor"]
Temperament = Literal["timid", "normal", "cold"]  # 블러핑 성격 취약성 V (부록 F.5)
SmallTalkStyle = Literal["chatty", "normal", "blunt"]  # 잡담 신뢰도 증감 (부록 F.3)
Emotion = Literal["neutral", "nervous", "flustered", "angry", "sad", "happy"]
ElementTag = Literal["motive", "means", "opportunity"]
RecordSystem = Literal["access_log", "cctv", "messenger", "bank", "call", "server_log", "delivery"]
MemoryType = Literal["record", "observation", "heard", "said", "reflection", "rumor", "summary"]
MemorySource = Literal["direct", "heard", "guess"]

# visibility 값 규칙
#   "player"            : 플레이어가 조사·심문으로 얻을 수 있음
#   "npc:<id>"          : 해당 NPC가 알고 있음
#   "public"            : 모두 앎 (공용 게시판 등)
#   "warrant:<system>"  : 해당 기록 시스템 영장이 있어야 플레이어가 열람


# ---------------------------------------------------------------------------
# 사건 원본 (서버 전용)
# ---------------------------------------------------------------------------


class Location(BaseModel):
    id: str
    name: str
    description: str
    connections: list[str] = Field(default_factory=list)
    unlock_condition: str | None = None  # None이면 처음부터 열림. 예: "evidence:E3", "day:2", "talk:npc_cleaner"
    background_ref: str | None = None
    overlays_allowed: list[str] = Field(default_factory=list)
    investigate_evidence_ids: list[str] = Field(default_factory=list)  # 이 장소를 조사하면 얻는 증거


class RoutineEntry(BaseModel):
    start: int  # game minutes
    end: int
    location_id: str


class Relation(BaseModel):
    target: str
    type: str  # "동료", "빚", "원한", "연애" ...
    detail: str = ""
    known_publicly: bool = False


class Character(BaseModel):
    id: str
    name: str
    role: str
    age: int
    gender: Literal["M", "F", "X"] = "X"
    appearance: dict[str, str] = Field(default_factory=dict)  # 그림용: hair, outfit, accessory ... 범인 정보 금지
    face_seed: int
    personality: str
    temperament: Temperament = "normal"
    small_talk_style: SmallTalkStyle = "normal"
    speech_style: str  # 말투 규칙 (예: "부산 사투리, 반말 섞음, 말끝에 '마'")
    goals: list[str] = Field(default_factory=list)
    secrets: list[str] = Field(default_factory=list)
    routine: list[RoutineEntry] = Field(default_factory=list)
    relations: list[Relation] = Field(default_factory=list)
    tier: Tier = "main"
    record_access: list[RecordSystem] = Field(default_factory=list)
    initial_visible: bool = True  # 처음부터 등장하는지 (점진적 등장)
    reveal_condition: str | None = None  # 처음엔 숨겨진 인물이 드러나는 조건
    key_witness: bool = False  # 신뢰도가 낮아도 핵심 사실 하나는 말함 (부록 F.3)
    is_culprit: bool = False  # 서버 내부 전용
    is_accomplice: bool = False  # 서버 내부 전용


class MMOEntry(BaseModel):
    """동기·수단·기회 (PRD §3.4)."""

    motive: str | None = None
    means: str | None = None
    opportunity: str | None = None


class TimelineEvent(BaseModel):
    time: int  # game minutes
    character_id: str
    location_id: str
    action: str


class Evidence(BaseModel):
    id: str
    name: str
    kind: Literal["record", "object", "testimony", "document"]
    content: str
    location_id: str | None = None
    visibility: list[str] = Field(default_factory=lambda: ["player"])
    is_key: bool = False
    element_tags: list[ElementTag] = Field(default_factory=list)  # 최종 추리·충분도용
    linked_suspects: list[str] = Field(default_factory=list)
    reveals_contradiction_of: list[str] = Field(default_factory=list)  # 이 증거가 깨는 거짓말(LieEntry id)
    indirect_traces: list[str] = Field(default_factory=list)  # 지워질 경우 남는 간접 흔적 증거 id
    destroyable: bool = False
    public_area: bool = False  # 공용 구역 CCTV 등 영장 없이 볼 수 있는 기록 (부록 F.7)


class LieEntry(BaseModel):
    id: str
    liar_id: str
    topic: str
    lie: str
    truth: str
    rebuttal_evidence_ids: list[str] = Field(min_length=1)


class RecordRow(BaseModel):
    """정형 기록 (SQL 도구로 조회, PRD §11.4)."""

    id: str
    system: RecordSystem
    time: int  # game minutes
    person_id: str | None = None
    location_id: str | None = None
    detail: str
    visibility: list[str] = Field(default_factory=lambda: ["player"])
    evidence_id: str | None = None  # 이 기록이 증거로 연결되면


class DocSection(BaseModel):
    heading: str
    text: str
    context: str = ""  # Contextual Retrieval용 문맥 설명 (작가가 생성 시 함께 작성)


class CaseDocument(BaseModel):
    """긴 서술형 문서 (청킹 대상, PRD §11.4.2)."""

    id: str
    title: str
    doc_type: Literal["manual", "wiki", "chat_log", "minutes", "statement", "diary", "email", "report", "notice"]
    sections: list[DocSection]
    visibility: list[str] = Field(default_factory=lambda: ["player"])


class BluffClaimDef(BaseModel):
    """블러핑 주장 종류 (버튼으로 고름, PRD §8.5)."""

    id: str
    label: str  # "공범이 자백했다"
    truth_by_target: dict[str, float] = Field(default_factory=dict)  # npc_id -> P (1 / 0.5 / 0)
    known_false_by: list[str] = Field(default_factory=list)  # 거짓임을 아는 NPC (즉시 실패)


class Incident(BaseModel):
    time: int
    location_id: str
    summary: str  # 플레이어에게 브리핑되는 공개 요약


class CaseBible(BaseModel):
    case_id: str
    title: str
    theme: str
    tone: Literal["comic", "balanced", "serious"] = "balanced"
    difficulty: Literal["easy", "normal", "hard"] = "normal"
    skeleton: str  # 사용한 뼈대 스킬
    incident: Incident
    start_location_id: str
    locations: list[Location]
    characters: list[Character]
    culprit_ids: list[str]
    mmo: dict[str, MMOEntry] = Field(default_factory=dict)  # character_id -> 동기·수단·기회
    trick: str
    timeline: list[TimelineEvent] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    lie_ledger: list[LieEntry] = Field(default_factory=list)
    records: list[RecordRow] = Field(default_factory=list)
    documents: list[CaseDocument] = Field(default_factory=list)
    bluff_claims: list[BluffClaimDef] = Field(default_factory=list)
    initial_memories: list["MemoryDoc"] = Field(default_factory=list)  # NPC 초기 기억
    storyboard: dict = Field(default_factory=dict)
    fingerprint: dict = Field(default_factory=dict)  # motive_type, trick_type, culprit_role, synopsis


# ---------------------------------------------------------------------------
# RAG
# ---------------------------------------------------------------------------


class MemoryDoc(BaseModel):
    id: str
    case_id: str
    slot_id: str
    owner: str  # npc id 또는 "public"
    visibility: list[str]
    doc_type: MemoryType
    content: str
    game_time: int
    confidence: float = Field(default=0.9, ge=0.0, le=1.0)
    source: MemorySource = "direct"
    source_npc: str | None = None
    contaminated_by: list[str] = Field(default_factory=list)
    is_first_testimony: bool = False
    is_key_evidence: bool = False
    evidence_id: str | None = None
    tags: list[str] = Field(default_factory=list)  # 인물·장소·시각 키워드 (키워드 검색 보조)


class Chunk(BaseModel):
    chunk_id: str
    doc_id: str
    parent_id: str | None = None
    collection: Literal["case", "kb_job", "kb_law"]
    case_id: str | None = None
    slot_id: str | None = None
    doc_title: str
    section_path: str | None = None
    chunk_strategy: str
    content: str
    context: str = ""
    visibility: list[str] = Field(default_factory=lambda: ["player"])
    speaker: str | None = None
    time_window: tuple[int, int] | None = None
    game_time: int | None = None
    kb_meta: dict | None = None
    token_count: int = 0


class RetrievalHit(BaseModel):
    id: str  # memory id 또는 chunk id
    kind: Literal["memory", "chunk", "record"]
    content: str
    score: float
    meta: dict = Field(default_factory=dict)


class RetrievalGold(BaseModel):
    question: str
    relevant_ids: list[str]
    asker_scope: str  # "player" 또는 "npc:<id>"
    source: Literal["auto_case", "kb_reviewed"] = "auto_case"


# ---------------------------------------------------------------------------
# 진행 상태 (서버)
# ---------------------------------------------------------------------------


class NPCState(BaseModel):
    npc_id: str
    location_id: str
    trust: int = 50
    alertness: int = 30  # 범인 경계 수준 (범인·공범만 의미 있음)
    emotion: Emotion = "neutral"
    promoted: bool = False
    visible: bool = True  # 플레이어에게 드러났는지
    bluff_failures: int = 0
    turned_away_until: int | None = None  # 이 행동 번호까지 대화 거부
    apologized_day: int | None = None
    visits_today: int = 0


class NotebookStatement(BaseModel):
    id: str
    npc_id: str
    content: str
    game_time: int
    memory_id: str | None = None
    source_ids: list[str] = Field(default_factory=list)  # 출처 (PRD §11.4.5)


class Contradiction(BaseModel):
    id: str
    statement_id: str
    evidence_id: str
    lie_id: str
    note: str = ""


class Notebook(BaseModel):
    evidence_ids: list[str] = Field(default_factory=list)
    statements: list[NotebookStatement] = Field(default_factory=list)
    contradictions: list[Contradiction] = Field(default_factory=list)
    relations_known: list[dict] = Field(default_factory=list)
    board_links: list[dict] = Field(default_factory=list)
    sufficiency: dict[str, float] = Field(default_factory=dict)


class Warrant(BaseModel):
    system: RecordSystem
    target_id: str
    from_time: int
    to_time: int


class GameState(BaseModel):
    game_id: str
    slot_id: str
    case_id: str
    player_ids: list[str] = Field(default_factory=lambda: ["player"])
    day: int = 1
    phase: Literal["briefing", "day", "night", "finale", "ended"] = "briefing"
    action_no: int = 0  # 누적 행동 번호
    actions_left: int = 12
    clock: int = 9 * 60  # game minutes
    player_location: str
    unlocked_locations: list[str] = Field(default_factory=list)
    npc_states: dict[str, NPCState] = Field(default_factory=dict)
    reputation: int = 0
    reputation_gain_today: int = 0
    had_negative_today: bool = False
    notebook: Notebook = Field(default_factory=Notebook)
    offtopic_streak: int = 0
    bluff_failures_today: int = 0
    warrants: list[Warrant] = Field(default_factory=list)
    conversation_summary: str = ""
    director_state: dict = Field(default_factory=dict)
    used_events: list[str] = Field(default_factory=list)
    hints_used: int = 0
    question_count: int = 0
    finale_wrong: int = 0
    confrontations_used: int = 0
    stakeouts_used: int = 0
    ending: Literal["none", "success", "escaped", "wrong_accusation"] = "none"
    started_at: datetime = Field(default_factory=datetime.now)
    difficulty: Literal["easy", "normal", "hard"] = "normal"
    max_days: int = 3
    finale: dict | None = None  # 최종 추리 쇼 진행 상태 (server.rules.finale 상태를 dump)
    speculative: dict = Field(default_factory=dict)  # 추측 생성 적중률 기록
    feed: list["FeedItem"] = Field(default_factory=list)  # 단톡방·사내 메신저 피드
    events_log: list[dict] = Field(default_factory=list)  # 진실 리플레이용 행동 기록 (서버 전용)
    id_salt: str = ""  # 클라이언트용 불투명 ID 생성 소금 (서버 전용)


# ---------------------------------------------------------------------------
# 에이전트 입출력
# ---------------------------------------------------------------------------


class RouterOutput(BaseModel):
    kind: Literal[
        "investigate", "small_talk", "meta", "inappropriate", "gibberish", "bluff_attempt", "present_evidence", "warrant"
    ]
    target_npc: str | None = None
    topic: str | None = None
    difficulty: Literal["easy", "hard"] = "easy"
    evidence_ids: list[str] = Field(default_factory=list)
    via: Literal["semantic", "llm", "chip", "rule"] = "semantic"
    confidence: float = 1.0


class NPCReply(BaseModel):
    """NPC 답변 LLM 구조화 출력."""

    text: str  # 1~3문장
    emotion: Emotion = "neutral"
    used_ids: list[str] = Field(default_factory=list)  # 근거로 쓴 기억/청크 id


class BluffAction(BaseModel):
    target_npc: str
    claim_id: str
    claim_subject: str | None = None
    basis_evidence_ids: list[str] = Field(default_factory=list)


class BluffResult(BaseModel):
    outcome: Literal["shaken", "rebutted", "confession", "instant_fail"]
    score: float
    factors: dict[str, float] = Field(default_factory=dict)  # E, P, V, R, F
    contaminates_witness: bool = False
    leaked_hint_id: str | None = None


class Rumor(BaseModel):
    content: str
    origin_npc: str
    told_by: str
    told_to: str
    distortion_level: int = Field(default=0, ge=0, le=3)
    distorted_fields: list[str] = Field(default_factory=list)
    game_time: int
    about_player: bool = False


class NPCAction(BaseModel):
    npc_id: str
    action: Literal[
        "move", "talk", "contact", "hide_evidence", "keep_routine", "rest", "tip_off", "deal_offer",
        "threat_message", "anonymous_tip",
    ]
    target: str | None = None
    reason: str = ""


class GMVerdict(BaseModel):
    ok: bool
    violations: list[str] = Field(default_factory=list)
    needs_llm_check: bool = False
    triggers: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 클리어 이력 (사건 삭제 후에도 남는 유일한 데이터)
# ---------------------------------------------------------------------------


class ClearHistory(BaseModel):
    id: str
    player_id: str
    case_title: str
    theme: str
    cleared_at: datetime
    success: bool
    real_minutes: int
    game_days: int
    question_count: int
    grade: Literal["S", "A", "B", "C"] | None = None
    titles: list[str] = Field(default_factory=list)
    reputation: int = 0
    culprit: dict = Field(default_factory=dict)  # {name, role}
    characters: list[dict] = Field(default_factory=list)  # [{name, role, face_seed, appearance}]
    highlight: str = ""  # 게임 기록 기반 한 줄 (플레이어 문장 금지)
    fingerprint: dict = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# 클라이언트로 나가는 플레이어 시점 뷰 (비밀 금지)
# ---------------------------------------------------------------------------


class PublicCharacter(BaseModel):
    id: str
    name: str
    role: str
    age: int
    gender: Literal["M", "F", "X"]
    appearance: dict[str, str]
    face_seed: int
    location_id: str | None  # 플레이어가 위치를 아는 경우만
    emotion: Emotion = "neutral"
    one_liner: str = ""  # 인물 카드 한 줄 특징 (공개 정보)
    portrait_url: str | None = None  # 그 판을 위해 새로 그린 AI 초상화 (없으면 절차적 SVG)


class PublicLocation(BaseModel):
    id: str
    name: str
    description: str
    connections: list[str]
    background_ref: str | None = None
    overlays: list[str] = Field(default_factory=list)


class PublicEvidence(BaseModel):
    id: str
    name: str
    kind: str
    content: str


class Chip(BaseModel):
    id: str
    label: str  # 버튼에 보이는 질문
    target_npc: str
    kind: Literal["ask", "present", "bluff"] = "ask"
    evidence_id: str | None = None


class FeedItem(BaseModel):
    id: str
    channel: str  # "단톡방", "사내 메신저"
    author: str
    text: str
    game_time: int


class PlayerView(BaseModel):
    game_id: str
    case_title: str
    incident_summary: str
    day: int
    phase: str
    clock: int
    actions_left: int
    actions_total: int = 12  # 하루 전체 행동 수 (상태바 "7/12"의 분모)
    max_days: int = 3
    player_location: str
    locations: list[PublicLocation]
    characters: list[PublicCharacter]
    evidence: list[PublicEvidence]
    notebook: Notebook
    sufficiency_gauge: dict[str, int] = Field(default_factory=dict)  # 0~5칸 (정확한 숫자 숨김)
    reputation_band: str = ""  # 칭호 구간 이름만
    chips: list[Chip] = Field(default_factory=list)
    feed: list[FeedItem] = Field(default_factory=list)
    bluff_claims: list[dict] = Field(default_factory=list)  # [{id, label}] 진실 여부는 숨김
    ending: str = "none"


class ShareCard(BaseModel):
    """결과 공유 카드 (PRD §10.3). 클리어 이력으로 만들고, 이미지는 클라이언트가 그린다."""

    emoji_line: str  # 예: "🔍🔍❌🔍✅"
    share_text: str  # 메신저용 한 줄
    theme_color: str  # 카드 배경색 (주제별)


CaseBible.model_rebuild()
GameState.model_rebuild()

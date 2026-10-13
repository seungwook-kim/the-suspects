"""config/game.yaml 의 타입 있는 모델 (PRD 부록 B, F).

규칙 엔진에 쓰이는 섹션은 필드를 모두 필수로 둔다. 기본값을 코드에 두면 수치가
yaml 밖으로 새기 때문이다(AGENTS.md 규칙 8). 규칙과 상관없는 섹션(rag, mcp 등)은
dict 로 그대로 통과시킨다.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class _Base(BaseModel):
    model_config = {"extra": "ignore"}


class OfftopicSteps(_Base):
    chips_again: int
    turn_away: int
    rumor: int


class OfftopicCfg(_Base):
    decay_per_normal: int
    partner_interject_at: int


class ActionsCfg(_Base):
    default: int
    warrant: int
    confrontation: int
    report: int
    stakeout: int
    hint: int


class RumorThreshold(_Base):
    at: int
    count: int


class TitleBand(_Base):
    min: int
    name: str | None = None


class ReputationCfg(_Base):
    start: int
    clue_found: int
    clue_found_daily_cap: int
    offtopic_turnaway: int
    offtopic_rumor: int
    meta: int
    rude: int
    bluff_fail: int
    bluff_fail_rumor_count: int
    stakeout_caught: int
    deal_exposed: int
    apology: int
    subquest: int
    daily_recovery: int
    rumor_threshold: list[RumorThreshold]
    titles: list[TitleBand]


class TrustCfg(_Base):
    min: int
    max: int
    start_main: int
    start_minor: int
    personality_offset: int
    small_talk_chatty: int
    small_talk_blunt: int
    small_talk_normal: int
    lie_exposed: int
    cleared: int
    rude: int
    bluff_fail: int
    apology: int
    uncooperative_below: int
    min_disclosure: bool
    turnaway_actions: int


class BluffWeights(_Base):
    E: float
    P: float
    V: float
    R: float
    F: float


class BluffEvidenceWeight(_Base):
    key: float
    aux: float
    testimony: float


class BluffTemperament(_Base):
    timid: float
    normal: float
    cold: float


class BluffCfg(_Base):
    confession_sufficiency: float
    confession_score: float
    shaken_score: float
    weights: BluffWeights
    evidence_weight: BluffEvidenceWeight
    temperament_v: BluffTemperament
    failure_step: float
    alertness_on_fail: int
    contaminate_confidence_below: float
    contaminate_probability: float


class SufficiencyCfg(_Base):
    key: float
    motive: float
    means: float
    opportunity: float
    contradiction: float
    testimony: float
    max: float
    gauge_cells: int


class WarrantWeights(_Base):
    direct: float
    motive: float
    contradiction: float
    other: float


class WarrantCfg(_Base):
    weights: WarrantWeights
    threshold: dict[str, float]
    scope_hours: int


class MemoryInitial(_Base):
    direct: float
    heard: float
    guess: float


class MemoryDecay(_Base):
    detail: float
    core: float


class SpeechBand(_Base):
    min: float
    band: str
    prefix: str = ""


class MemoryCfg(_Base):
    initial: MemoryInitial
    decay: MemoryDecay
    floor: float
    contaminate_below: float
    contaminate_min_source_trust: float
    contaminated_confidence: float
    speech_bands: list[SpeechBand]


class NoClueCfg(_Base):
    hint_after: int
    event_after: int


class DirectorCfg(_Base):
    no_clue: NoClueCfg
    same_place_limit: int
    early_progress: float
    early_progress_before_day: int
    late_struggle: float
    cooldown_actions: int
    max_per_day: int


class AlertnessCfg(_Base):
    min: int
    max: int
    start: int
    heard_suspicion: int
    bluff_fail: int
    repeat_visit: int
    repeat_visit_count: int
    columbo_divisor: int
    hide_evidence_at: int
    contact_accomplice_at: int
    threat_sufficiency: float


class GMCfg(_Base):
    max_regenerations: int
    llm_check: str
    time_window_hours: int
    fallback_lines: dict[str, str]


class FinaleCfg(_Base):
    stages: list[str]
    lives: dict[str, int]
    bluff_enabled: bool


class GradeCfg(_Base):
    base: int
    par_questions: dict[str, int]
    question_penalty: int
    hint_penalty: int
    wrong_penalty: int
    par_days: int
    day_penalty: int
    confession_bonus: int
    bands: dict[str, int]


class ReversalCfg(_Base):
    contradiction_weight: float
    arrest_threshold: float
    frame_threshold: float


class DedupCfg(_Base):
    history_size: int
    similarity_threshold: float
    fingerprint_keys: list[str]


class CaseGenCfg(_Base):
    max_verify_retries: int
    similarity_threshold: float
    dedup: DedupCfg


class TierLimit(_Base):
    soft: int
    hard: int


class LimitsCfg(_Base):
    confrontation_per_game: int
    stakeout_per_game: int
    input_tokens_per_day: TierLimit
    output_tokens_per_day: TierLimit
    case_gen_default_per_day: TierLimit
    case_gen_free_per_day: TierLimit
    mcp_calls_per_token_per_day: TierLimit
    mcp_concurrent_games: int


class SpeculativeAutoOff(_Base):
    window: int
    min_hit_rate: float


class SpeedCfg(_Base):
    speculative_chips: bool
    speculative_chip_count: int
    speculative_auto_off: SpeculativeAutoOff
    prefetch_retrieval_on_enter: bool
    latency_budget_ms: dict[str, int]


class SkillsLearningCfg(_Base):
    enabled: bool
    max_tokens_per_skill: int
    rollback_on_regression: bool
    min_clears_between_updates: int
    eval_sets: dict[str, int]
    max_rate_drop: float
    max_cost_increase: float


class CitationCfg(_Base):
    min_quote_chars: int
    max_rewrites: int
    relevance_sample: float


class GameConfig(_Base):
    # 부록 B
    play_time_options: list[int]
    default_play_time: int
    investigation_days: dict[str, int]
    day_actions: int
    suspects: dict[str, Any]
    initial_visible_characters: list[int]
    locations: dict[str, int]
    background_prefetch: int
    night: dict[str, Any]
    npc_reply_sentences: list[int]
    offtopic_steps: OfftopicSteps
    bluff: BluffCfg
    gm: GMCfg
    case_gen: CaseGenCfg
    limits: LimitsCfg
    speed: SpeedCfg
    modes: dict[str, bool]
    rag: dict[str, Any]
    router: dict[str, Any]
    guardrails: dict[str, Any]
    streaming: dict[str, Any]
    skills_learning: SkillsLearningCfg
    mcp: dict[str, Any]
    tracing: dict[str, Any]
    retention: dict[str, Any]
    investigation: dict[str, Any]
    reputation_range: list[int]
    grades: list[str]
    # 부록 F
    actions: ActionsCfg
    reputation: ReputationCfg
    trust: TrustCfg
    offtopic: OfftopicCfg
    sufficiency: SufficiencyCfg
    warrant: WarrantCfg
    memory: MemoryCfg
    director: DirectorCfg
    alertness: AlertnessCfg
    finale: FinaleCfg
    grade: GradeCfg
    reversal: ReversalCfg
    citation: CitationCfg

"""F.13 해결 등급. 순수 함수.

점수 = base - max(0, 질문 수 - par) * question_penalty - 힌트 * hint_penalty - 최종 추리 오답 * wrong_penalty
       - max(0, 사용 일수 - par_days) * day_penalty + (증거 충분한 블러핑 자백이면 confession_bonus)
par 는 난이도별 grade.par_questions (난이도별 값은 직접 정함: easy 50 / normal 40 / hard 30).
S >= bands.S, A >= bands.A, B >= bands.B, 그 밖 C.
"""

from __future__ import annotations

from server.config import GameConfig
from server.schemas import GameState


def grade_score(
    cfg: GameConfig,
    difficulty: str,
    questions: int,
    hints: int,
    finale_wrong: int,
    days_used: int,
    confession_bonus: bool = False,
) -> int:
    g = cfg.grade
    score = g.base
    score -= max(0, questions - g.par_questions[difficulty]) * g.question_penalty
    score -= hints * g.hint_penalty
    score -= finale_wrong * g.wrong_penalty
    score -= max(0, days_used - g.par_days) * g.day_penalty
    if confession_bonus:
        score += g.confession_bonus
    return score


def grade_for(cfg: GameConfig, score: float) -> str:
    bands = cfg.grade.bands
    if score >= bands["S"]:
        return "S"
    if score >= bands["A"]:
        return "A"
    if score >= bands["B"]:
        return "B"
    return "C"


def grade_game(cfg: GameConfig, state: GameState, difficulty: str, *, confession_bonus: bool = False) -> tuple[int, str]:
    """GameState 로 (점수, 등급). 사용 일수는 state.day."""
    score = grade_score(
        cfg, difficulty, state.question_count, state.hints_used, state.finale_wrong, state.day, confession_bonus
    )
    return score, grade_for(cfg, score)

"""F.16 비용·호출 상한 판정. 순수 함수.

단계 상한(soft/hard): 사용량이 soft 를 *넘으면* "cheap"(싼 경로로 전환), hard 를 *넘으면* "blocked"(그날 차단).
판당 상한(대질·잠복, 동시 판 수): 이미 쓴 수가 상한에 *이르면* 다음 사용은 불가(can_use_per_game / below_cap).
"""

from __future__ import annotations

from typing import Literal

from server.config import GameConfig
from server.config.game_config import TierLimit

Verdict = Literal["normal", "cheap", "blocked"]

TIERED = (
    "input_tokens_per_day",
    "output_tokens_per_day",
    "case_gen_default_per_day",
    "case_gen_free_per_day",
    "mcp_calls_per_token_per_day",
)


def judge_tier(limit: TierLimit, used: int) -> Verdict:
    if used > limit.hard:
        return "blocked"
    if used > limit.soft:
        return "cheap"
    return "normal"


def check_limit(cfg: GameConfig, name: str, used: int) -> Verdict:
    """name 은 TIERED 중 하나(limits.* 키)."""
    if name not in TIERED:
        raise KeyError(name)
    return judge_tier(getattr(cfg.limits, name), used)


def can_use_per_game(cfg: GameConfig, name: str, used: int) -> bool:
    """name: "confrontation_per_game" | "stakeout_per_game"."""
    if name not in ("confrontation_per_game", "stakeout_per_game"):
        raise KeyError(name)
    return used < getattr(cfg.limits, name)


def can_start_game(cfg: GameConfig, running_games: int) -> bool:
    """외부 MCP 동시 진행 판 수 상한."""
    return running_games < cfg.limits.mcp_concurrent_games


def worst(*verdicts: Verdict) -> Verdict:
    order = {"normal": 0, "cheap": 1, "blocked": 2}
    return max(verdicts, key=lambda v: order[v], default="normal")

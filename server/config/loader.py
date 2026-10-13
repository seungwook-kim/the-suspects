"""설정 로더.

- load_game_config(path=None, overrides=None) -> GameConfig
- game_config_from_dict(data) -> GameConfig   (테스트에서 dict 로 직접 생성)
- get_game_config() -> GameConfig             (프로세스 캐시. 테스트는 위 두 함수 사용)
- load_models_config(path=None) -> dict       (config/models.yaml 읽기 전용)
"""

from __future__ import annotations

import copy
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from .game_config import GameConfig

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GAME_PATH = PROJECT_ROOT / "config" / "game.yaml"
DEFAULT_MODELS_PATH = PROJECT_ROOT / "config" / "models.yaml"


def _read_yaml(path: str | os.PathLike) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"설정 파일 최상위는 매핑이어야 한다: {path}")
    return data


def deep_merge(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    """base 를 복사한 뒤 overrides 를 재귀적으로 덮어쓴다(리스트는 통째로 교체)."""
    out = copy.deepcopy(base)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def game_config_from_dict(data: dict[str, Any]) -> GameConfig:
    return GameConfig.model_validate(data)


def load_game_config(
    path: str | os.PathLike | None = None,
    overrides: dict[str, Any] | None = None,
) -> GameConfig:
    """game.yaml 을 읽는다. 경로 우선순위: 인자 > 환경 변수 GAME_CONFIG_PATH > 기본 경로.

    overrides 가 있으면 yaml 위에 깊은 병합한다(테스트용: {"bluff": {"shaken_score": 0.4}}).
    """
    p = Path(path or os.environ.get("GAME_CONFIG_PATH") or DEFAULT_GAME_PATH)
    data = _read_yaml(p)
    if overrides:
        data = deep_merge(data, overrides)
    return game_config_from_dict(data)


@lru_cache(maxsize=1)
def get_game_config() -> GameConfig:
    return load_game_config()


def load_models_config(path: str | os.PathLike | None = None) -> dict[str, Any]:
    """config/models.yaml 을 dict 로 읽는다(읽기 전용)."""
    return _read_yaml(path or DEFAULT_MODELS_PATH)

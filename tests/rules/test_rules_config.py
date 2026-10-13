import pytest
import yaml

from server.config import (
    GameConfig,
    deep_merge,
    game_config_from_dict,
    get_game_config,
    load_game_config,
    load_models_config,
)
from server.config.loader import DEFAULT_GAME_PATH


def test_load_default(cfg):
    assert isinstance(cfg, GameConfig)
    assert cfg.day_actions == 12
    assert cfg.investigation_days == {"easy": 4, "normal": 3, "hard": 2}
    assert cfg.actions.warrant == 2 and cfg.actions.confrontation == 3
    assert cfg.bluff.weights.E == 0.45
    assert cfg.reputation.titles[0].name == "믿음직한 형사"
    assert cfg.warrant.threshold["bank"] == 0.6
    assert cfg.offtopic_steps.rumor == 6
    assert cfg.case_gen.dedup.similarity_threshold == cfg.case_gen.similarity_threshold == 0.85


def test_bluff_weights_sum_to_one(cfg):
    w = cfg.bluff.weights
    assert w.E + w.P + w.V + w.R + w.F == pytest.approx(1.0)


def test_from_dict_and_overrides():
    raw = yaml.safe_load(DEFAULT_GAME_PATH.read_text(encoding="utf-8"))
    c1 = game_config_from_dict(raw)
    assert c1.day_actions == 12
    raw2 = deep_merge(raw, {"bluff": {"shaken_score": 0.4}, "day_actions": 8})
    assert raw["bluff"]["shaken_score"] == 0.5  # 원본 불변
    c2 = game_config_from_dict(raw2)
    assert c2.bluff.shaken_score == 0.4 and c2.bluff.weights.E == 0.45 and c2.day_actions == 8
    c3 = load_game_config(overrides={"actions": {"warrant": 5}})
    assert c3.actions.warrant == 5 and c3.actions.default == 1


def test_load_from_path(tmp_path):
    p = tmp_path / "g.yaml"
    p.write_text(DEFAULT_GAME_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    assert load_game_config(p).day_actions == 12


def test_missing_key_fails(tmp_path):
    raw = yaml.safe_load(DEFAULT_GAME_PATH.read_text(encoding="utf-8"))
    del raw["actions"]
    with pytest.raises(Exception):
        game_config_from_dict(raw)


def test_get_game_config_cached():
    assert get_game_config() is get_game_config()


def test_models_config():
    m = load_models_config()
    assert "profiles" in m and "active_profile" in m

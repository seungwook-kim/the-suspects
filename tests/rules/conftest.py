"""규칙 엔진 테스트 공용 픽스처. 사건 원본은 여기서 직접 만든다(data/cases 에 의존하지 않음)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from server.config import GameConfig, load_game_config  # noqa: E402
from server.schemas import (  # noqa: E402
    BluffClaimDef,
    CaseBible,
    Character,
    Evidence,
    GameState,
    Incident,
    LieEntry,
    Location,
    NPCState,
    Relation,
)

# 사건: 23:00(첫날 1380분)에 경리팀 사무실에서 일어남.
INCIDENT_TIME = 23 * 60


@pytest.fixture(scope="session")
def cfg() -> GameConfig:
    return load_game_config()


def _char(id_, name, **kw) -> Character:
    base = dict(
        id=id_, name=name, role="직원", age=30, face_seed=1, personality="평범", speech_style="존댓말",
    )
    base.update(kw)
    return Character(**base)


@pytest.fixture()
def case() -> CaseBible:
    chars = [
        _char("a", "김철수", is_culprit=True, temperament="cold", small_talk_style="blunt",
              relations=[Relation(target="b", type="동료")]),
        _char("b", "이영희", temperament="timid", small_talk_style="chatty", key_witness=True,
              relations=[Relation(target="a", type="동료")]),
        _char("c", "박민수", tier="minor", relations=[]),
        _char("d", "정수진", initial_visible=False, relations=[]),
    ]
    ev = [
        Evidence(id="E1", name="출입 기록지", kind="record", content="x", location_id="loc_office", is_key=True,
                 element_tags=["opportunity"], linked_suspects=["a"], reveals_contradiction_of=["L1"]),
        Evidence(id="E2", name="차용증", kind="document", content="x", element_tags=["motive"], linked_suspects=["a"],
                 visibility=["player", "npc:b"]),
        Evidence(id="E3", name="경비원 진술", kind="testimony", content="x", linked_suspects=["a"]),
        Evidence(id="E4", name="약병", kind="object", content="x", element_tags=["means"], linked_suspects=["a"]),
        Evidence(id="E5", name="복도 영상", kind="record", content="x", is_key=True,
                 element_tags=["opportunity"], linked_suspects=["c"]),
    ]
    claims = [
        BluffClaimDef(id="accomplice_confessed", label="공범이 자백했다",
                      truth_by_target={"a": 1.0, "b": 0.0, "c": 0.0}, known_false_by=["c"]),
        BluffClaimDef(id="false_claim", label="거짓 주장", truth_by_target={}),
        BluffClaimDef(id="half_claim", label="세부가 틀린 주장", truth_by_target={"a": 0.5}),
    ]
    return CaseBible(
        case_id="case_test",
        title="테스트 사건",
        theme="사무실",
        skeleton="locked_room",
        incident=Incident(time=INCIDENT_TIME, location_id="loc_office", summary="요약"),
        start_location_id="loc_lobby",
        locations=[
            Location(id="loc_lobby", name="로비", description="x", connections=["loc_office"]),
            Location(id="loc_office", name="경리팀 사무실", description="x", connections=["loc_lobby"]),
        ],
        characters=chars,
        culprit_ids=["a"],
        trick="t",
        evidence=ev,
        lie_ledger=[LieEntry(id="L1", liar_id="a", topic="알리바이", lie="집에 있었다", truth="사무실에 있었다",
                             rebuttal_evidence_ids=["E1"])],
        bluff_claims=claims,
    )


@pytest.fixture()
def state(case) -> GameState:
    return GameState(
        game_id="g1", slot_id="s1", case_id=case.case_id, player_location="loc_lobby",
        npc_states={c.id: NPCState(npc_id=c.id, location_id="loc_lobby") for c in case.characters},
    )


@pytest.fixture()
def with_evidence(state):
    def _make(*ids, **kw):
        nb = state.notebook.model_copy(update={"evidence_ids": list(ids)})
        return state.model_copy(update={"notebook": nb, **kw})

    return _make

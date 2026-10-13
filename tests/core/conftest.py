import pytest

from server.schemas import (
    BluffClaimDef,
    CaseBible,
    Character,
    Evidence,
    GameState,
    Incident,
    LieEntry,
    Location,
    MMOEntry,
    NPCState,
)


@pytest.fixture
def mini_case() -> CaseBible:
    return CaseBible(
        case_id="case_test",
        title="테스트 사건",
        theme="테스트",
        skeleton="insider",
        incident=Incident(time=23 * 60, location_id="loc_server", summary="운영 DB가 사라졌다"),
        start_location_id="loc_office",
        locations=[
            Location(id="loc_office", name="사무실", description="개발팀 사무실", connections=["loc_server", "loc_roof"]),
            Location(id="loc_server", name="서버실", description="서버실", connections=["loc_office"]),
            Location(id="loc_roof", name="옥상", description="옥상", connections=["loc_office"], unlock_condition="day:2"),
        ],
        characters=[
            Character(id="npc_cleaner", name="박정수", role="야간 청소원", age=58, face_seed=101,
                      personality="말수가 적다", speech_style="존댓말, 짧게", secrets=["예전에 개발자였다"],
                      goals=["들키지 않기"], is_culprit=True, appearance={"outfit": "cleaner_uniform"}),
            Character(id="npc_dba", name="이수진", role="DBA", age=34, face_seed=202,
                      personality="꼼꼼하다", speech_style="반말 섞음", secrets=["백업을 안 돌렸다"]),
        ],
        culprit_ids=["npc_cleaner"],
        mmo={"npc_cleaner": MMOEntry(motive="해고 원한", means="관리자 계정", opportunity="야간 근무")},
        trick="출입카드를 빌림",
        evidence=[
            Evidence(id="ev_cleaner_card_secret", name="출입카드 기록", kind="record", content="23:05 서버실 출입",
                     is_key=True, element_tags=["opportunity"], linked_suspects=["npc_cleaner"]),
        ],
        lie_ledger=[
            LieEntry(id="lie_cleaner_alibi", liar_id="npc_cleaner", topic="알리바이", lie="11시엔 1층에 있었다",
                     truth="서버실에 있었다", rebuttal_evidence_ids=["ev_cleaner_card_secret"]),
        ],
        bluff_claims=[BluffClaimDef(id="claim_cleaner_cctv", label="CCTV에 찍혔다", truth_by_target={"npc_cleaner": 1.0})],
    )


@pytest.fixture
def mini_state() -> GameState:
    return GameState(
        game_id="g1",
        slot_id="slot_live",
        case_id="case_test",
        player_location="loc_office",
        unlocked_locations=["loc_office", "loc_server"],
        npc_states={
            "npc_cleaner": NPCState(npc_id="npc_cleaner", location_id="loc_server", alertness=55),
            "npc_dba": NPCState(npc_id="npc_dba", location_id="loc_office", trust=62),
        },
        id_salt="testsalt",
    )

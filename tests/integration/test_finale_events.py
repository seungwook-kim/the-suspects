"""최종 추리 이벤트 계약: 화면은 finale.stage를 "다음에 밝힐 단계"로 읽는다 (2026-10-15 실제 서버에서 증거 칸이 안 열리던 버그)."""

from server.game.masking import IdMasker
from server.game.service import GameService


async def collect(gen):
    return [e async for e in gen]


def finale_events(evs):
    return [e["value"] for e in evs if e.get("name") == "finale"]


def setup(tmp_path):
    svc = GameService(tmp_path, in_memory=True)
    case = svc.cases["demo_db_deleted"]
    game_id, _ = svc.new_game("demo_db_deleted", {"difficulty": "normal"})
    st = svc.store.load_live(game_id)
    st.notebook.evidence_ids = [e.id for e in case.evidence]  # 모든 증거를 가진 상태(계약 확인용)
    svc.store.save_live(st)
    return svc, case, game_id, IdMasker(case, st.id_salt)


async def test_guilty_accusation_opens_next_stage_and_success(tmp_path):
    svc, case, game_id, masker = setup(tmp_path)
    culprit = case.culprit_ids[0]
    stages = svc.cfg.finale.stages
    f = finale_events(await collect(svc.finale(game_id, {"type": "start", "accused_id": culprit})))[-1]
    assert f["accused_id"] == culprit and f["stage"] == stages[0] and not f["pending"] and f["filled"] == []
    for i, stage in enumerate(stages):
        ev = next(e for e in case.evidence if stage in e.element_tags and culprit in e.linked_suspects)
        evs = await collect(svc.finale(game_id, {"type": "present", "stage": stage, "evidence_id": masker.out("evidence", ev.id)}))
        if i < len(stages) - 1:
            f = finale_events(evs)[-1]
            assert f["stage"] == stages[i + 1] and f["filled"] == list(stages[:i + 1]) and f["last"]["result"] == "correct"
        else:
            assert any(e.get("name") == "ending" and e["value"]["ending"] == "success" for e in evs)


async def test_innocent_accusation_pending_then_retract_or_confirm(tmp_path):
    svc, case, game_id, _ = setup(tmp_path)
    innocent = next(c.id for c in case.characters if c.id not in case.culprit_ids)
    f = finale_events(await collect(svc.finale(game_id, {"type": "start", "accused_id": innocent})))[-1]
    assert f["pending"] and f["accused_id"] == innocent
    f = finale_events(await collect(svc.finale(game_id, {"type": "retract"})))[-1]
    assert f["accused_id"] is None and f["stage"] is None  # 화면은 지목 화면으로 돌아간다
    await collect(svc.finale(game_id, {"type": "start", "accused_id": innocent}))
    evs = await collect(svc.finale(game_id, {"type": "confirm"}))
    assert any(e.get("name") == "ending" and e["value"]["ending"] == "wrong_accusation" for e in evs)


async def test_finale_changes_accused_expression(tmp_path):
    """최종 추리 장면에서 지목된 사람의 표정이 바뀐다(지목: 긴장, 맞는 증거: 당황, 해결: 슬픔)."""
    svc, case, game_id, masker = setup(tmp_path)
    culprit = case.culprit_ids[0]

    def emotions(evs):
        return [e["value"]["emotion"] for e in evs if e.get("name") == "emotion" and e["value"]["npcId"] == culprit]

    assert emotions(await collect(svc.finale(game_id, {"type": "start", "accused_id": culprit}))) == ["nervous"]
    seen = []
    for stage in svc.cfg.finale.stages:
        ev = next(e for e in case.evidence if stage in e.element_tags and culprit in e.linked_suspects)
        seen += emotions(await collect(svc.finale(game_id, {"type": "present", "stage": stage,
                                                            "evidence_id": masker.out("evidence", ev.id)})))
    assert seen[:-1] == ["flustered"] * (len(seen) - 1) and seen[-1] == "sad"
    assert svc.store.load_live(game_id).npc_states[culprit].emotion == "sad"


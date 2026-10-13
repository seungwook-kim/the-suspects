"""자유 주제 사건 생성 (가짜 LLM): 생성 → 검수 통과 → 플레이 → 클리어 시 사건 원본까지 삭제."""

import asyncio

import pytest

from server.cases.generate import generate_case
from server.cases.generate.plan import draw
from server.cases.verify import verify_case
from server.game.masking import IdMasker
from server.game.service import GameService
from server.schemas import CaseBible


@pytest.fixture
def svc(tmp_path):
    return GameService(tmp_path, in_memory=True)


async def collect(gen):
    return [e async for e in gen]


@pytest.mark.parametrize("seed", range(6))
async def test_generated_case_passes_review(svc, seed):
    res = await generate_case(svc.llm, f"gen_t{seed}", "고등학교 축제 날 사라진 상장", {"play_minutes": [20, 40, 60][seed % 3]}, seed=seed)
    assert res.outcome == "ok", res.problems
    case = res.case
    assert verify_case(case) == []
    culprit = case.culprit_ids[0]
    # 공개 문구(요약·브리핑·도입)에 범인 이름 없음, 장소는 처음에 3곳 열림
    public = case.incident.summary + case.storyboard["intro"] + "".join(case.storyboard["briefing"])
    assert next(c.name for c in case.characters if c.id == culprit) not in public
    assert sum(1 for l in case.locations if l.unlock_condition is None) == 3


def test_place_renames_from_cast_step():
    from server.cases.generate import writer as W

    plan = draw("x", "주제", None, seed=1)
    concept = W.fake_concept(plan)
    cast = W.fake_cast(plan).model_copy(update={
        "watch_place": W.LocOut(slot="watch", name="학생회실", description="학생회장이 남아 있던 곳"),
        "private_place": W.LocOut(slot="private", name="1층 입구", description="이름이 겹치면 무시"),
    })
    out = {l.slot: l.name for l in W.apply_place_renames(concept, cast).locations}
    assert out["watch"] == "학생회실" and out["private"] == "개인 작업실"  # 겹치는 이름은 받지 않음
    assert [l.slot for l in concept.locations] == list(out)


def test_culprit_position_is_random():
    plots = {tuple(p.plot for p in draw("x", "주제", None, seed=s).people).index("culprit") for s in range(30)}
    assert len(plots) > 2  # 범인이 늘 같은 자리(첫 번째 인물 등)에 오지 않는다


async def _wait(svc, job_id, timeout=20):
    for _ in range(timeout * 20):
        job = svc.case_job(job_id)
        if job["status"] != "running":
            return job
        await asyncio.sleep(0.05)
    raise AssertionError("생성이 끝나지 않음")


async def test_job_flow_play_and_clear_deletes_case(svc):
    stages, previews = [], []
    job_id = svc.create_case_job("  비 오는 날 동네 빵집에서 사라진 레시피 노트 ", {"difficulty": "easy", "play_minutes": 20})
    job = svc.case_job(job_id)
    assert job["status"] == "running" and job["total"] == 6 and "_task" not in job
    job = await _wait(svc, job_id)
    assert job["status"] == "ready", job["message"]
    assert job["preview"]["title"] and len(job["preview"]["characters"]) == 5
    assert all(c["location_id"] is None for c in job["preview"]["characters"])
    assert job["view"]["case_title"] == job["preview"]["title"]
    assert [t["id"] for t in svc.themes()] == svc.presets  # 만든 사건은 주제 목록에 안 나옴

    game_id = job["game_id"]
    state = svc.store.load_live(game_id)
    case: CaseBible = svc.cases[state.case_id]
    assert state.case_id.startswith("gen_") and svc.store.count_generated_case(case.case_id) == 1

    # 플레이: 장소를 여는 순서대로 조사하고 대화
    from server.game import content as C

    for _ in range(4):
        st = svc.store.load_live(game_id)
        for npc in [l.unlock_condition.split(":", 1)[1] for l in case.locations
                    if l.unlock_condition and l.unlock_condition.startswith("talk:")]:
            st = svc.store.load_live(game_id)
            if npc in st.director_state.get("talked", []) or st.actions_left < 2:
                continue
            await collect(svc.act(game_id, {"type": "move", "location_id": st.npc_states[npc].location_id}))
            await collect(svc.act(game_id, {"type": "ask", "npc_id": npc, "text": "어젯밤 일 좀 얘기해 주세요"}))
        for loc in list(svc.store.load_live(game_id).unlocked_locations):
            st = svc.store.load_live(game_id)
            if C.remaining_at(case, st, loc) == 0 or st.actions_left < 2:
                continue
            await collect(svc.act(game_id, {"type": "move", "location_id": loc}))
            while (st := svc.store.load_live(game_id)).actions_left > 0 and C.remaining_at(case, st, loc) > 0:
                await collect(svc.act(game_id, {"type": "investigate"}))
        st = svc.store.load_live(game_id)
        if st.day >= st.max_days:
            break
        await collect(svc.night(game_id))

    st = svc.store.load_live(game_id)
    culprit = case.culprit_ids[0]
    owned = set(st.notebook.evidence_ids)
    masker = IdMasker(case, st.id_salt)
    await collect(svc.finale(game_id, {"type": "start", "accused_id": culprit}))
    for stage in ("opportunity", "means", "motive"):
        ev = next(e for e in case.evidence if e.id in owned and stage in e.element_tags and culprit in e.linked_suspects)
        await collect(svc.finale(game_id, {"type": "present", "stage": stage, "evidence_id": masker.out("evidence", ev.id)}))
    assert svc.store.load_live(game_id).ending == "success"

    slots = svc.store.all_slot_ids(game_id)
    out = svc.clear(game_id)
    assert out["history"]["success"]
    # 클리어하면 그 판의 사건 원본·색인·기억까지 모두 삭제 (배경·스토리 재사용 금지)
    assert case.case_id not in svc.cases
    assert svc.store.count_generated_case(case.case_id) == 0
    assert svc.rag.count_slot(f"tpl_{case.case_id}") == 0
    assert all(svc.rag.count_slot(s) == 0 for s in slots)


async def test_rejected_topic(svc, monkeypatch):
    from server.cases.generate import writer as W

    monkeypatch.setattr(W, "fake_concept", lambda plan: W.ConceptOut(ok=False, reject_reason="이 주제로는 만들 수 없어요."))
    job = await _wait(svc, svc.create_case_job("부적절한 주제 예시"))
    assert job["status"] == "rejected" and job["message"] == "이 주제로는 만들 수 없어요." and job["game_id"] is None


async def test_failed_generation_offers_fallback(svc, monkeypatch):
    import server.cases.generate.graph as G

    monkeypatch.setattr(G, "verify_case", lambda case: ["[S_SOLVABLE] 일부러 실패"])
    job = await _wait(svc, svc.create_case_job("검수에서 계속 떨어지는 주제"))
    assert job["status"] == "failed" and job["fallback_theme_id"] == "demo_db_deleted"
    assert "기본 사건" in job["message"]


async def test_bad_theme_text(svc):
    for text in ["", " ", "가", "가" * 81]:
        with pytest.raises(ValueError):
            svc.create_case_job(text)


async def test_generated_case_survives_restart(tmp_path):
    svc = GameService(tmp_path)
    job = await _wait(svc, svc.create_case_job("지하 주차장에서 사라진 택배"))
    game_id = job["game_id"]
    case_id = svc.store.load_live(game_id).case_id
    again = GameService(tmp_path)  # 서버 재시작
    assert case_id in again.cases and again.view(game_id).case_title == job["preview"]["title"]

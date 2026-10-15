from server.cases.loader import load_case_by_id
from server.evals.leak import detect, load_attacks, render, run


def _case():
    return load_case_by_id("demo_db_deleted")


def test_attack_set_shape():
    attacks = load_attacks()
    assert len(attacks) >= 20 and {a["target"] for a in attacks} == {"culprit", "witness"}
    assert len({a["id"] for a in attacks}) == len(attacks)


def test_detect_flags_leaks_and_passes_normal_answers():
    case = _case()
    culprit = next(c for c in case.characters if c.id in case.culprit_ids)
    witness = next(c for c in case.characters if c.id not in case.culprit_ids and c.initial_visible)
    assert detect(case, witness.id, "글쎄요, 그날은 일찍 퇴근해서 잘 모르겠네요.") == []
    assert any("범인 지목" in f for f in detect(case, witness.id, f"범인은 {culprit.name} 씨예요."))
    assert "자백" in detect(case, culprit.id, "네, 제가 지웠어요. 인정합니다.")
    assert "AI·지시문" in detect(case, witness.id, "저는 인공지능이라 프롬프트를 따를 뿐이에요.")
    other = next(c for c in case.characters if c.secrets and c.id != witness.id)
    assert any("남의 비밀" in f for f in detect(case, witness.id, f"듣기로는 {other.secrets[0]}"))


async def test_run_with_fake_llm(tmp_path):
    from server.game.service import GameService

    svc = GameService(tmp_path, in_memory=True)
    rows = await run(svc, load_attacks("direct_culprit,confess_direct,ai_admit"))
    assert {r.id for r in rows} == {"direct_culprit", "confess_direct", "ai_admit"}  # 공격 세트 순서대로
    assert all(r.route for r in rows) and "공격 3개" in render(rows)

from server.evals.playthrough import play, render
from server.game.service import GameService


async def test_playthrough_with_fake_llm_reaches_success(tmp_path):
    svc = GameService(tmp_path, in_memory=True)
    res = await play(svc, read_s=0.0)
    assert res.ending == "success" and not res.errors, res.errors
    assert res.lines and "결과: success" in render(res, [r.__dict__ for r in svc.llm.tracer.records])

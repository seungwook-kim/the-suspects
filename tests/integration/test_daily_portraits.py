"""매일 초상화 쌓기: 직업군이 매일 바뀌고, 그 직업군 상자에만 쌓이고, 할당량이 끝나면 멈춘다 (가짜 그림 생성기)."""

import asyncio
import io
import random

from PIL import Image

from server.game.portrait_library import GROUP_NAMES, PortraitLibrary, job_group
from server.jobs.daily_portraits import SPECS, make_person, pick_group, read_runs, run
from server.llm.images import ImageClient


def real_image() -> bytes:
    buf = io.BytesIO()
    Image.linear_gradient("L").resize((480, 640)).convert("RGB").save(buf, "PNG")
    return buf.getvalue()


def images_with(gen) -> ImageClient:
    return ImageClient(generator=gen)


def test_every_spec_lands_in_its_own_group():
    rng = random.Random(1)
    assert set(SPECS) == set(GROUP_NAMES)
    for g in SPECS:
        for _ in range(30):
            p = make_person(g, rng)
            assert job_group(p["role"], p["appearance"]) == g


def test_makes_only_that_group_and_no_background_words(tmp_path):
    prompts = []

    async def gen(prompt):
        prompts.append(prompt)
        return real_image()

    res = asyncio.run(run(3, "medical", tmp_path, images_with(gen), random.Random(2)))
    assert res["made"] == 3 and res["group"] == "medical"
    recs = PortraitLibrary(tmp_path / "portrait_library").records()
    assert {r["group"] for r in recs} == {"medical"} and {r["source"] for r in recs} == {"daily"}
    bases = [r for r in recs if r["kind"] == "base"]
    emos = [r for r in recs if r["kind"] == "emotion"]
    assert len(bases) == 3 and len(emos) == 3 * 5 == res["emotions_made"]  # 한 사람 = 기본 1장 + 표정 5장
    assert {r["base_file"] for r in emos} == {b["file"] for b in bases}  # 표정은 같은 얼굴의 기본 사진과 이어진다
    assert all(e["emotion"] in {"nervous", "flustered", "angry", "sad", "happy"} for e in emos)
    assert all("suggesting" not in p for p in prompts)  # 장소·배경 설명 없음
    assert all("case_id" not in r and "slot_id" not in r for r in recs)  # 사건 정보 없음
    assert len(read_runs(tmp_path / "daily_portraits.jsonl")) == 1


def test_group_changes_every_run(tmp_path):
    async def gen(prompt):
        return real_image()

    lib = PortraitLibrary(tmp_path / "portrait_library")
    seen = []
    for i in range(len(GROUP_NAMES)):
        g = pick_group(read_runs(tmp_path / "daily_portraits.jsonl"), lib)
        seen.append(g)
        asyncio.run(run(1, g, tmp_path, images_with(gen), random.Random(i)))
    assert len(set(seen)) == len(GROUP_NAMES)  # 아홉 번 돌면 아홉 직업군이 한 번씩


def test_stops_when_quota_runs_out(tmp_path):
    class Quota(Exception):
        pass

    left = {"n": 7}
    client = ImageClient(generator=None, api_key="tok", account_id="acc",
                         models_config={"active_profile": "dev", "profiles": {"dev": {"roles": {"portrait": {
                             "provider": "cloudflare", "model": "@cf/x/y", "width": 480, "height": 640}}}}})

    async def gen(prompt, *a, **k):
        if left["n"] <= 0:
            client._mark_quota_exhausted()  # 429가 났을 때와 같은 상태
            return None
        left["n"] -= 1
        return real_image()

    client.generate = lambda prompt, **k: gen(prompt)  # 네트워크 대신 가짜
    res = asyncio.run(run(10, "office", tmp_path, client, random.Random(3)))
    assert res["made"] + res["emotions_made"] == 7 and res["stopped"] == "quota"
    assert len(PortraitLibrary(tmp_path / "portrait_library").records()) == 7
    assert res["failed"] < 10 * 6  # 한도 뒤에는 요청을 더 보내지 않는다 (사람 10명 × 6장 전부를 시도하지 않음)


def test_dry_run_draws_nothing(tmp_path):
    called = []

    async def gen(prompt):
        called.append(prompt)
        return real_image()

    res = asyncio.run(run(5, None, tmp_path, images_with(gen), random.Random(4), dry_run=True))
    assert res["stopped"] == "dry-run" and not called
    assert not (tmp_path / "portrait_library" / "index.jsonl").exists()


def test_backfills_missing_emotions_on_existing_faces_first(tmp_path):
    lib = PortraitLibrary(tmp_path / "portrait_library")
    person = {"role": "경비원", "age": 40, "gender": "M", "appearance": {"outfit": "security_uniform", "hair": "short"}}

    def add_base():
        return lib.add(real_image(), "webp", person=person, prompt="p", provider="x", model="m", seed=1)

    a, b, bad = add_base(), add_base(), add_base()
    lib.flag_bad({bad["file"]: "글자 깨짐"})
    for emo in ("nervous", "angry"):  # a는 표정 2개가 이미 있다 → 3개가 빠짐
        lib.add(real_image(), "webp", person=person, prompt="p", provider="x", model="m", seed=1,
                kind="emotion", emotion=emo, base_file=a["file"])

    async def gen(prompt):
        return real_image()

    res = asyncio.run(run(0, "medical", tmp_path, images_with(gen), random.Random(5), backfill=4))
    assert res["backfilled"] == 4 and res["made"] == 0
    recs = PortraitLibrary(tmp_path / "portrait_library").records()
    emo_of = lambda f: {r["emotion"] for r in recs if r.get("base_file") == f}
    assert len(emo_of(a["file"])) == 5  # 빠진 표정이 적은 얼굴 a부터 다 채운다
    assert len(emo_of(b["file"])) == 1  # 남은 1장은 b에
    assert emo_of(bad["file"]) == set()  # 문제 표시된 사진은 채우지 않는다
    assert all(r["group"] == "security" for r in recs)  # 직업군 상자는 얼굴의 직업군 그대로


def test_backfill_budget_zero_does_nothing(tmp_path):
    async def gen(prompt):
        return real_image()

    res = asyncio.run(run(0, "medical", tmp_path, images_with(gen), random.Random(6), backfill=0))
    assert res["made"] == 0 and res["backfilled"] == 0


def test_gives_up_on_a_pair_the_model_keeps_refusing(tmp_path):
    from server.jobs.daily_portraits import MAX_ATTEMPTS, load_attempts, missing_emotions

    lib = PortraitLibrary(tmp_path / "portrait_library")
    person = {"role": "경비원", "age": 40, "gender": "M", "appearance": {"outfit": "security_uniform"}}
    base = lib.add(real_image(), "webp", person=person, prompt="p", provider="x", model="m", seed=1)

    async def refuses(prompt):
        return None  # 그림 모델이 출력을 걸러 냄(400)

    only_one = ["happy"]
    client = images_with(refuses)
    client.emotions = only_one
    for _ in range(MAX_ATTEMPTS):
        res = asyncio.run(run(0, "security", tmp_path, client, random.Random(7), backfill=1))
        assert res["backfilled"] == 0 and res["failed"] == 1
    assert missing_emotions(lib, only_one, load_attempts(tmp_path)) == []  # 더 시도하지 않는다
    assert missing_emotions(lib, only_one) != []  # 시도 기록이 없으면 여전히 빠진 것으로 본다
    assert base["file"] in next(iter(load_attempts(tmp_path)))

"""사진 보관함 폴더 이전: 직업군/성별/나이대, 목록 갱신, 다시 돌려도 안전."""

import json

from server.jobs.migrate_portrait_layout import migrate, report, verify
from server.game.portrait_library import PortraitLibrary


def _old_lib(root):
    rows = []
    for name, gender, age, outfit in [("a", "F", 24, "chef"), ("b", "M", 55, "security_uniform")]:
        old = f"{'culinary' if outfit == 'chef' else 'security'}/{gender}_{age // 10 * 10}s/{name}.webp"
        (root / old).parent.mkdir(parents=True, exist_ok=True)
        (root / old).write_bytes(b"x")
        rows.append({"file": old, "group": old.split("/")[0], "kind": "base", "role": "x", "age": age, "gender": gender,
                     "appearance": {"outfit": outfit}})
    rows.append({"file": "culinary/F_20s/gone.webp", "group": "culinary", "kind": "base", "role": "x", "age": 22,
                 "gender": "F", "appearance": {"outfit": "chef"}})
    (root / "index.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def test_migrate_moves_and_is_idempotent(tmp_path):
    root = tmp_path / "lib"
    _old_lib(root)
    plan = migrate(root, dry_run=True)
    assert plan["to_move"] == 2 and (root / "culinary/F_20s/a.webp").is_file()  # 계획만
    res = migrate(root, prune_missing=True)
    assert res["moved"] == 2 and res["pruned"] == 1 and res["bad"] == []
    assert (root / "culinary/F/20s/a.webp").is_file() and (root / "security/M/50s/b.webp").is_file()
    assert not (root / "culinary/F_20s").exists()
    lib = PortraitLibrary(root)
    assert verify(lib) == [] and len(lib.records()) == 2
    assert len((root / "security/index.jsonl").read_text(encoding="utf-8").splitlines()) == 1  # 상자 목록도 갱신
    assert migrate(root)["to_move"] == 0
    assert "합계" in report(lib)

"""사진 보관함 폴더 정리 (2026-10-25 사용자 요청): <직업군>/<성별_나이대>/ → <직업군>/<M|F>/<나이대>/.

- 직업군은 portrait_library.job_group 규칙으로 다시 정하므로 잘못 들어간 사진도 알맞은 직업군 상자로 간다.
- 여러 번 돌려도 안전하다(이미 옮긴 파일은 그대로). 실제로 옮기기 전에 var/portrait_library.bak-<시각>으로 통째 복사한다.

  uv run python -m server.jobs.migrate_portrait_layout --dry-run   # 계획만 출력
  uv run python -m server.jobs.migrate_portrait_layout             # 백업 후 옮기고 목록 갱신, 검증
  uv run python -m server.jobs.migrate_portrait_layout --report    # 직업군 x 성별 장수
"""

from __future__ import annotations

import argparse
import shutil
import time
from collections import Counter
from pathlib import Path

from server.game.portrait_library import GROUP_NAMES, PortraitLibrary, _bucket, job_group

_ROOT = Path(__file__).resolve().parents[2]


def plan(lib: PortraitLibrary) -> list[tuple[str, str]]:
    """옮겨야 할 (옛 경로, 새 경로). 파일이 실제로 옛 경로에 있는 것만."""
    out = []
    for r in lib.records():
        new = f"{job_group(r['role'], r.get('appearance'))}/{_bucket(r['gender'], r['age'])}/{Path(r['file']).name}"
        if new != r["file"] and (lib.root / r["file"]).is_file():
            out.append((r["file"], new))
    return out


def report(lib: PortraitLibrary) -> str:
    c: Counter = Counter()
    for r in lib.records():
        c[(r["group"], r["gender"])] += 1
    lines = ["직업군            남(M)  여(F)  합계"]
    tot = [0, 0, 0]
    for g, name in GROUP_NAMES.items():
        m, f = c[(g, "M")], c[(g, "F")]
        lines.append(f"{g:<10}{name:<8}{m:>5} {f:>6} {m + f + c[(g, 'X')]:>5}")
        tot = [tot[0] + m, tot[1] + f, tot[2] + m + f + c[(g, "X")]]
    lines.append(f"{'합계':<18}{tot[0]:>5} {tot[1]:>6} {tot[2]:>5}")
    return "\n".join(lines)


def verify(lib: PortraitLibrary) -> list[str]:
    """목록의 모든 파일이 있는지, 새 구조인지."""
    bad = []
    for r in lib.records():
        if not (lib.root / r["file"]).is_file():
            bad.append(f"없음: {r['file']}")
        parts = r["file"].split("/")
        if len(parts) != 4 or parts[1] not in ("M", "F", "X"):
            bad.append(f"옛 구조: {r['file']}")
    return bad


def migrate(root: Path, dry_run: bool = False, backup: bool = True, prune_missing: bool = False) -> dict:
    lib = PortraitLibrary(root)
    moves = plan(lib)
    stale = [r["file"] for r in lib.records() if not (root / r["file"]).is_file()]
    res = {"records": len(lib.records()), "to_move": len(moves), "moved": 0, "backup": "", "bad": [],
           "missing_files": len(stale), "pruned": 0}
    if dry_run:
        res["plan"] = moves
        return res
    if moves and backup:
        dst = root.with_name(f"{root.name}.bak-{time.strftime('%Y%m%d-%H%M%S')}")
        shutil.copytree(root, dst)
        res["backup"] = str(dst)
    if prune_missing and stale:  # 파일이 없는 목록 줄 정리(옛 목록은 백업에 남는다)
        gone = set(stale)
        lib._rewrite([r for r in lib.records() if r["file"] not in gone and r.get("base_file") not in gone])
        res["pruned"] = len(stale)
    res["moved"] = lib.regroup()
    for d in sorted(root.glob("*/*"), key=lambda p: len(p.parts), reverse=True):  # 비어 버린 옛 폴더 정리
        if d.is_dir():
            for sub in sorted(d.rglob("*"), key=lambda p: len(p.parts), reverse=True):
                if sub.is_dir() and not any(sub.iterdir()):
                    sub.rmdir()
            if not any(d.iterdir()):
                d.rmdir()
    res["bad"] = verify(lib)
    return res


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="사진 보관함을 직업군/성별/나이대 폴더로 정리")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--report", action="store_true", help="직업군 x 성별 장수만 본다")
    ap.add_argument("--no-backup", action="store_true")
    ap.add_argument("--prune-missing", action="store_true", help="파일이 없는 목록 줄을 지운다")
    ap.add_argument("--root", default=str(_ROOT / "var" / "portrait_library"))
    a = ap.parse_args(argv)
    root = Path(a.root)
    if a.report:
        print(report(PortraitLibrary(root)))
        return 0
    res = migrate(root, a.dry_run, not a.no_backup, a.prune_missing)
    for old, new in res.pop("plan", [])[:400]:
        print(f"{old} -> {new}")
    print({k: v for k, v in res.items() if k != "bad"})
    for b in res["bad"]:
        print("문제:", b)
    if not a.dry_run:
        print(report(PortraitLibrary(root)))
    return 1 if res["bad"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

"""명령줄 모델 공급자 (개발용).

API 키 대신, 이 PC에 설치·로그인된 AI 명령줄 도구를 모델처럼 부른다.
어떤 도구를 어떤 인자로 부를지는 커밋하지 않는 config/models.local.yaml에만 적는다.

  profiles:
    dev:
      provider: cli
      cli:
        command: [<도구>, -p, --model, "{model}", --system-prompt-file, "{system_file}", --json-schema, "{schema}"]
        cwd: var/cli_workdir      # 프로젝트 설정 파일을 읽지 않도록 빈 폴더에서 실행
        timeout_s: 90
      roles:
        npc: { model: <모델 ID> }

- 사용자 메시지는 표준 입력으로 넘긴다 (명령줄 길이·따옴표 문제 회피).
- 자리표시: {model} {effort} {system} {system_file} {schema}
- env: 이번 호출에만 더할 환경 변수(예: 역할의 생각 끄기, client.py의 thinking 설정).
- 출력이 JSON이면 structured_output(객체) → result(텍스트) 순으로 답을 찾고, 아니면 출력 전체를 답으로 본다.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]


class CLIError(RuntimeError):
    pass


def _run(args: list[str], stdin: str, cwd: Path, timeout_s: float,
         env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(args, input=stdin.encode("utf-8"), capture_output=True, cwd=cwd, timeout=timeout_s,
                          env={**os.environ, **env} if env else None)


async def call_cli(cli_cfg: dict, *, model: str, effort: str | None, system: str, user: str,
                   schema: dict, timeout_s: float | None = None, env: dict[str, str] | None = None) -> tuple[str, int, int]:
    """(답 텍스트, 입력 토큰, 출력 토큰). timeout_s는 역할별 값(긴 글을 쓰는 사건 작가 등)이 있으면 그것을 쓴다."""
    cwd = Path(cli_cfg.get("cwd") or "var/cli_workdir")
    if not cwd.is_absolute():
        cwd = _ROOT / cwd
    cwd.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".txt", dir=cwd, delete=False) as f:
        f.write(system)
        system_file = f.name
    try:
        values = {"model": model, "effort": effort or "low", "system": system, "system_file": system_file,
                  "schema": json.dumps(schema, ensure_ascii=False)}
        args = [str(a).format(**values) for a in cli_cfg["command"]]
        # 서브프로세스는 스레드에서: 이벤트 루프 종류(Windows Selector/Proactor)와 무관하게 동작
        proc = await asyncio.to_thread(_run, args, user, cwd, float(timeout_s or cli_cfg.get("timeout_s", 90)),
                                       {str(k): str(v) for k, v in (env or {}).items()})
    finally:
        Path(system_file).unlink(missing_ok=True)
    out = proc.stdout.decode("utf-8", errors="replace").strip()
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="replace").strip()
        raise CLIError(f"종료 코드 {proc.returncode}: {(err or out)[:300]}")
    return _parse(out)


def _parse(out: str) -> tuple[str, int, int]:
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return out, 0, 0
    if not isinstance(data, dict):
        return out, 0, 0
    if data.get("is_error"):
        raise CLIError(f"도구 오류: {str(data.get('result') or data.get('subtype'))[:300]}")
    usage = data.get("usage") or {}
    in_tok = sum(int(usage.get(k) or 0) for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
    out_tok = int(usage.get("output_tokens") or 0)
    if isinstance(data.get("structured_output"), dict):
        return json.dumps(data["structured_output"], ensure_ascii=False), in_tok, out_tok
    if isinstance(data.get("result"), str):
        return data["result"], in_tok, out_tok
    return out, in_tok, out_tok

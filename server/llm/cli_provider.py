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


# ---------------------------------------------------------------------------- 실시간 출력 (첫 문장부터 보여 주기)
# cli.stream_command: 같은 도구를 "실시간 출력(한 줄에 JSON 하나)"으로 부르는 인자. 출력 형식 강제 인자는 빼고
# 지시문의 JSON 안내만으로 받는다(글자 조각이 그대로 흘러나오게). 한 줄의 모양:
#   {"type": "stream_event", "event": {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "…"}}}
#   {"type": "result", "usage": {...}, "is_error": false}
# 없으면 실시간으로 받지 않는다(client.can_stream이 False).

async def stream_cli(cli_cfg: dict, *, model: str, effort: str | None, system: str, user: str,
                     timeout_s: float | None = None, env: dict[str, str] | None = None):
    """(지금까지의 출력 글, 사용량 또는 None)을 조각이 올 때마다 낸다. 마지막에 사용량이 붙은 한 번을 더 낸다.
    받는 쪽이 중간에 그만두면(aclose) 프로그램을 끝낸다."""
    cwd = Path(cli_cfg.get("cwd") or "var/cli_workdir")
    if not cwd.is_absolute():
        cwd = _ROOT / cwd
    cwd.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".txt", dir=cwd, delete=False) as f:
        f.write(system)
        system_file = f.name
    values = {"model": model, "effort": effort or "low", "system": system, "system_file": system_file, "schema": "{}"}
    args = [str(a).format(**values) for a in cli_cfg["stream_command"]]
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    proc = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd,
                            env={**os.environ, **{str(k): str(v) for k, v in (env or {}).items()}} if env else None)

    def pump() -> None:  # 스레드: 한 줄씩 읽어 이벤트 루프로 넘긴다
        try:
            proc.stdin.write(user.encode("utf-8"))
            proc.stdin.close()
            for line in proc.stdout:
                loop.call_soon_threadsafe(queue.put_nowait, line)
        except Exception as e:  # 프로그램이 먼저 끝난 경우 등
            loop.call_soon_threadsafe(queue.put_nowait, e)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    reader = loop.run_in_executor(None, pump)
    text, usage, deadline = "", None, loop.time() + float(timeout_s or cli_cfg.get("timeout_s", 90))
    try:
        while True:
            item = await asyncio.wait_for(queue.get(), timeout=max(0.1, deadline - loop.time()))
            if item is None:
                break
            if isinstance(item, Exception):
                raise CLIError(f"실시간 출력 읽기 실패: {item}")
            try:
                d = json.loads(item)
            except json.JSONDecodeError:
                continue
            if d.get("type") == "stream_event":
                delta = (d.get("event") or {}).get("delta") or {}
                if delta.get("type") == "text_delta" and delta.get("text"):
                    text += delta["text"]
                    yield text, None
            elif d.get("type") == "result":
                if d.get("is_error"):
                    raise CLIError(f"도구 오류: {str(d.get('result') or d.get('subtype'))[:300]}")
                u = d.get("usage") or {}
                usage = {"input_tokens": sum(int(u.get(k) or 0) for k in
                                             ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")),
                         "output_tokens": int(u.get("output_tokens") or 0)}
                if not text and isinstance(d.get("result"), str):
                    text = d["result"]
        if usage is None and proc.wait(timeout=5) != 0:
            raise CLIError(f"종료 코드 {proc.returncode}: {proc.stderr.read().decode('utf-8', 'replace')[:300]}")
        yield text, usage or {"input_tokens": 0, "output_tokens": 0}
    finally:
        if proc.poll() is None:
            proc.kill()  # 받는 쪽이 그만뒀거나 시간 초과: 남은 생성은 버린다(읽는 스레드는 출력이 닫히면 끝난다)
        del reader
        Path(system_file).unlink(missing_ok=True)

from __future__ import annotations

import asyncio
import json
import os
import signal
import time
from pathlib import Path


_POLL_INTERVAL = 10


async def run(prompt: str, work_dir: Path, *,
              model: str, max_turns: str, budget: str = "1.00",
              log_file: Path | None = None,
              capture_output: bool = False,
              timeout: int | None = None,
              idle_timeout: int | None = None) -> dict:
    output_format = "json" if capture_output else "stream-json"
    cmd = [
        "claude", "--print",
        "--no-session-persistence",
        "--max-budget-usd", budget,
        "--max-turns", max_turns,
        "--model", model,
        "-p", "-",
        "--output-format", output_format,
    ]
    if not capture_output:
        cmd.append("--verbose")

    if capture_output:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=work_dir,
            start_new_session=True,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=prompt.encode()),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            _kill_process_group(proc.pid)
            await proc.wait()
            return {"returncode": -1, "error": f"timed out after {timeout}s", "stdout": "", "stderr": ""}

        stdout_str = stdout.decode() if stdout else ""
        try:
            result = json.loads(stdout_str)
        except (json.JSONDecodeError, ValueError):
            result = {"result": stdout_str}

        return {
            "returncode": proc.returncode,
            "result": result.get("result", ""),
            "stdout": stdout_str,
            "stderr": stderr.decode() if stderr else "",
            **{k: v for k, v in result.items() if k != "result"},
        }
    else:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        log_fh = open(log_file, "w")
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=log_fh,
            stderr=asyncio.subprocess.STDOUT,
            cwd=work_dir,
            start_new_session=True,
        )
        proc.stdin.write(prompt.encode())
        await proc.stdin.drain()
        proc.stdin.close()

        try:
            await _wait_with_idle_check(proc, log_fh, timeout, idle_timeout)
        except asyncio.TimeoutError:
            _kill_process_group(proc.pid)
            await proc.wait()
            log_fh.close()
            return {"returncode": -1, "error": "timed out", "log_file": str(log_file)}
        finally:
            log_fh.close()

        result = _parse_log(log_file)
        result["returncode"] = proc.returncode
        result["log_file"] = str(log_file)
        return result


async def _wait_with_idle_check(proc, log_fh, timeout, idle_timeout):
    if not idle_timeout:
        await asyncio.wait_for(proc.wait(), timeout=timeout)
        return

    now = time.monotonic()
    deadline = now + timeout if timeout else None
    idle_deadline = now + idle_timeout
    last_size = 0

    while proc.returncode is None:
        await asyncio.sleep(_POLL_INTERVAL)
        now = time.monotonic()

        if deadline and now >= deadline:
            raise asyncio.TimeoutError()

        cur_size = os.fstat(log_fh.fileno()).st_size
        if cur_size != last_size:
            last_size = cur_size
            idle_deadline = now + idle_timeout
        elif now >= idle_deadline:
            raise asyncio.TimeoutError()

        try:
            proc._transport.get_pid()
        except (ProcessLookupError, AttributeError):
            break
        if proc.returncode is not None:
            break


def _kill_process_group(pid: int):
    try:
        os.killpg(pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        return
    time.sleep(2)
    try:
        os.killpg(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def _parse_log(log_file: Path) -> dict:
    try:
        content = log_file.read_text()
    except FileNotFoundError:
        return {"result": "", "error": "log file not found"}

    lines = content.strip().splitlines()
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
            if "result" in data:
                return data
        except (json.JSONDecodeError, ValueError):
            continue

    return {"result": "\n".join(lines[-20:]) if lines else ""}


def setup_settings(work_dir: Path, *, phase: str = "",
                   log_dir: Path | None = None,
                   extra_write_paths: list[str] | None = None,
                   allowed_tools: list[str] | None = None,
                   denied_tools: list[str] | None = None):
    from loki2.core.state import PHASE_DENIED_TOOLS

    settings: dict = {}

    # Sandbox filesystem
    if log_dir or extra_write_paths:
        fs: dict = {}
        write_paths: list[str] = []
        if log_dir:
            write_paths.append("/" + str(log_dir))
        for p in (extra_write_paths or []):
            write_paths.append("/" + str(p) + "/")
        if write_paths:
            fs["allowWrite"] = write_paths
            settings["sandbox"] = {"filesystem": fs}

    # Permissions
    allow = allowed_tools or ["mcp__linear-server__*"]
    deny = denied_tools if denied_tools is not None else PHASE_DENIED_TOOLS.get(phase, [])
    settings["permissions"] = {"allow": allow, "deny": deny}

    claude_dir = work_dir / ".claude"
    claude_dir.mkdir(exist_ok=True)
    settings_file = claude_dir / "settings.local.json"
    settings_file.write_text(json.dumps(settings, indent=2))

    local_md = claude_dir / "CLAUDE.local.md"
    local_md.write_text(
        "# Loki Autonomous Agent\n\n"
        "You are running as an autonomous agent. "
        "Do not wait for user input.\n\n"
        "## Git operations\n\n"
        "Always commit and push without asking for confirmation. "
        "Code review happens on the PR, not here. "
        "Never end your turn with questions like \"コミットしますか？\" or \"Should I commit?\". "
        "Just do it.\n\n"
        "## Running tests\n\n"
        "Always run tests in non-interactive mode. "
        "Never use watch mode or commands that wait for interactive input.\n\n"
        "- vitest: use `npx vitest run` (not `npx vitest`)\n"
        "- jest: use `npx jest` (already non-interactive by default)\n"
        "- general: pass `--watch=false` or `--watchAll=false` if needed\n"
    )

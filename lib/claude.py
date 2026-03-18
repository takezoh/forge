import json
import os
import signal
import subprocess
import time
from pathlib import Path

from config import FORGE_ROOT, load_config
from config.constants import PHASE_DENIED_TOOLS
from lib.git import detect_default_branch, diff_stat
from lib.linear import fetch_issue_detail, fetch_sub_issues

_current_process: subprocess.Popen | None = None

_CODE_EDITING_PHASES = {"implementing", "review"}


def get_current_process() -> subprocess.Popen | None:
    return _current_process


def setup_settings(work_dir: Path, *, phase: str = "",
                   log_dir: Path | None = None,
                   extra_write_paths: list[str] | None = None):
    user_config = load_config()
    settings = user_config.get("claude", {})

    sandbox_settings = settings.get("sandbox")
    if sandbox_settings:
        sandbox_settings.setdefault("filesystem", {})
        fs = sandbox_settings["filesystem"]
        if log_dir is not None:
            fs.setdefault("allowWrite", [])
            path_str = "/" + str(log_dir)
            if path_str not in fs["allowWrite"]:
                fs["allowWrite"].append(path_str)

        if extra_write_paths:
            fs.setdefault("allowWrite", [])
            for p in extra_write_paths:
                path_str = "/" + str(p) + "/"
                if path_str not in fs["allowWrite"]:
                    fs["allowWrite"].append(path_str)

    cfg = load_config()
    allow = ["mcp__linear-server__*"]
    deny = []

    if phase:
        phase_allow = cfg.get("allowed_tools", {}).get(phase)
        if not phase_allow and phase in _CODE_EDITING_PHASES:
            phase_allow = cfg.get("allowed_tools", {}).get("code_editing")
        if phase_allow:
            allow = phase_allow + ["mcp__linear-server__*"]
        deny = PHASE_DENIED_TOOLS.get(phase, [])

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
        "Just do it.\n"
    )


_POLL_INTERVAL = 10


def _wait_with_idle_check(proc, cmd, log_fh, timeout, idle_timeout):
    if not idle_timeout:
        proc.wait(timeout=timeout)
        return

    now = time.monotonic()
    deadline = now + timeout if timeout else None
    idle_deadline = now + idle_timeout
    last_size = 0

    while proc.poll() is None:
        time.sleep(_POLL_INTERVAL)
        now = time.monotonic()

        if deadline and now >= deadline:
            raise subprocess.TimeoutExpired(cmd, timeout)

        cur_size = os.fstat(log_fh.fileno()).st_size
        if cur_size != last_size:
            last_size = cur_size
            idle_deadline = now + idle_timeout
        elif now >= idle_deadline:
            raise subprocess.TimeoutExpired(cmd, idle_timeout)


def run(prompt: str, work_dir: Path, *,
        model: str, max_turns: str, budget: str = "1.00",
        phase: str = "",
        log_file: Path | None = None,
        capture_output: bool = False,
        allow_write: list[str] | None = None,
        timeout: int | None = None,
        idle_timeout: int | None = None):
    global _current_process

    setup_settings(work_dir, phase=phase,
                   log_dir=log_file.parent if log_file else None,
                   extra_write_paths=allow_write)

    cmd = [
        "claude", "--print",
        "--no-session-persistence",
        "--max-budget-usd", budget,
        "--max-turns", max_turns,
        "--model", model,
        "-p", "-",
        "--output-format", "json",
    ]

    if capture_output:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True,
            cwd=work_dir,
            start_new_session=True,
        )
        _current_process = proc
        try:
            stdout, stderr = proc.communicate(input=prompt, timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
            raise
        finally:
            _current_process = None
        return subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)
    else:
        with open(log_file, "w") as log:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=log, stderr=subprocess.STDOUT,
                text=True,
                cwd=work_dir,
                start_new_session=True,
            )
            _current_process = proc
            try:
                proc.stdin.write(prompt)
                proc.stdin.close()
                _wait_with_idle_check(proc, cmd, log, timeout, idle_timeout)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
                raise
            finally:
                _current_process = None
        return subprocess.CompletedProcess(cmd, proc.returncode)


def generate_pr_body(parent_id: str, parent_identifier: str, repo_path: str,
                     sub_issues: list[dict], env: dict,
                     work_dir: str | None = None) -> tuple[str, str]:
    prompt_file = FORGE_ROOT / "prompts" / "pr.md"
    prompt = prompt_file.read_text()

    parent_detail = fetch_issue_detail(parent_id)
    prompt = prompt.replace("{{PARENT_ISSUE_DETAIL}}", json.dumps(parent_detail, indent=2, ensure_ascii=False))

    parent_data = fetch_sub_issues(parent_id)
    prompt = prompt.replace("{{PLAN_DOCUMENTS}}", json.dumps(parent_data.get("documents", []), indent=2, ensure_ascii=False))

    sub_summary = []
    for s in sub_issues:
        sub_summary.append(f"- {s['identifier']}: {s['title']} ({s.get('state', '')})")
    prompt = prompt.replace("{{SUB_ISSUES}}", "\n".join(sub_summary))

    default_branch = detect_default_branch(repo_path)
    prompt = prompt.replace("{{DIFF_STAT}}", diff_stat(repo_path, default_branch, parent_identifier))

    ret = run(prompt, Path(work_dir or repo_path),
              model=env.get("FORGE_MODEL_PR", env["FORGE_MODEL"]),
              max_turns="1", capture_output=True)
    if ret.returncode != 0:
        return parent_detail.get("title", parent_identifier), f"Parent issue: {parent_identifier}\n\nAll sub-issues completed."

    try:
        data = json.loads(ret.stdout)
        output = data.get("result", ret.stdout.strip())
    except json.JSONDecodeError:
        output = ret.stdout.strip()
    title = parent_detail.get("title", parent_identifier)
    body = output

    if "TITLE:" in output and "---" in output:
        parts = output.split("---", 1)
        for line in parts[0].splitlines():
            if line.startswith("TITLE:"):
                title = line.removeprefix("TITLE:").strip()
                break
        body = parts[1].strip()
        if body.startswith("```"):
            body = body.split("\n", 1)[1] if "\n" in body else body
        if body.endswith("```"):
            body = body.rsplit("\n", 1)[0] if "\n" in body else body

    return title, body

import sys
from pathlib import Path

from config import load_env
from lib.claude import generate_pr_body
from lib.git import detect_default_branch, pr_create, worktree_add, worktree_remove
from lib.linear import update_issue_state
from config.constants import STATE_IN_REVIEW
from forge.orchestrator import log

import json


def create_parent_pr(parent_identifier: str, parent_title: str, repo_path: str,
                     parent_id: str, sub_issues: list[dict]):
    env = load_env()
    lock_dir = Path(env["FORGE_LOCK_DIR"])
    pr_lock = lock_dir / f"pr-{parent_identifier}.lock"

    parent_worktree = Path(env["FORGE_WORKTREE_DIR"]) / Path(repo_path).name / parent_identifier
    if not parent_worktree.exists():
        parent_worktree.parent.mkdir(parents=True, exist_ok=True)
        worktree_add(repo_path, str(parent_worktree), parent_identifier)

    log(f"  Generating PR description for {parent_identifier}...")
    title, body = generate_pr_body(parent_id, parent_identifier, repo_path,
                                   sub_issues, env,
                                   work_dir=str(parent_worktree))

    default_branch = detect_default_branch(repo_path)
    ret = pr_create(repo_path, f"{parent_identifier}: {title}", body,
                    parent_identifier, default_branch)
    if ret.returncode == 0:
        log(f"  Created PR for {parent_identifier}")
    else:
        log(f"  Failed to create PR for {parent_identifier}: {ret.stderr}")
        pr_lock.unlink(missing_ok=True)
        return

    try:
        update_issue_state(parent_id, STATE_IN_REVIEW)
    except Exception as e:
        log(f"  Error updating state for {parent_identifier}: {e}")

    if parent_worktree.exists():
        worktree_remove(repo_path, str(parent_worktree))


if __name__ == "__main__":
    parent_identifier = sys.argv[1]
    parent_title = sys.argv[2]
    repo_path = sys.argv[3]
    parent_id = sys.argv[4]
    sub_issues = json.loads(sys.argv[5])
    create_parent_pr(parent_identifier, parent_title, repo_path, parent_id, sub_issues)

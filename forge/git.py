import json
import subprocess


def detect_default_branch(repo_path: str) -> str:
    ret = subprocess.run(
        ["git", "-C", repo_path, "symbolic-ref", "refs/remotes/origin/HEAD"],
        capture_output=True, text=True,
    )
    if ret.returncode != 0:
        subprocess.run(
            ["git", "-C", repo_path, "remote", "set-head", "origin", "--auto"],
            capture_output=True,
        )
        ret = subprocess.run(
            ["git", "-C", repo_path, "symbolic-ref", "refs/remotes/origin/HEAD"],
            capture_output=True, text=True,
        )
    if ret.returncode == 0:
        return ret.stdout.strip().split("/")[-1]
    return "main"


def branch_exists(repo_path: str, branch: str) -> bool:
    ret = subprocess.run(
        ["git", "-C", repo_path, "rev-parse", "--verify", branch],
        capture_output=True,
    )
    return ret.returncode == 0


def create_branch(repo_path: str, branch: str, base: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", repo_path, "branch", branch, base],
        capture_output=True, text=True,
    )


def worktree_add(repo_path: str, worktree_dir: str, branch: str,
                 new_branch: str | None = None) -> subprocess.CompletedProcess:
    cmd = ["git", "-C", repo_path, "worktree", "add"]
    if new_branch:
        cmd.extend([worktree_dir, "-b", new_branch, branch])
    else:
        cmd.extend([worktree_dir, branch])
    return subprocess.run(cmd, capture_output=True, text=True)


def worktree_remove(repo_path: str, worktree_dir: str):
    subprocess.run(
        ["git", "-C", repo_path, "worktree", "remove", worktree_dir, "--force"],
        capture_output=True,
    )


def merge(worktree_dir: str, branch: str, message: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", worktree_dir, "merge", "--no-ff", branch, "-m", message],
        capture_output=True, text=True,
    )


def merge_abort(worktree_dir: str):
    subprocess.run(["git", "-C", worktree_dir, "merge", "--abort"], capture_output=True)


def push(worktree_dir: str, branch: str):
    subprocess.run(
        ["git", "-C", worktree_dir, "push", "-u", "origin", branch],
        capture_output=True,
    )


def delete_branch(repo_path: str, branch: str):
    subprocess.run(
        ["git", "-C", repo_path, "branch", "-D", branch],
        capture_output=True,
    )


def has_new_commits(work_dir: str, base: str) -> bool:
    ret = subprocess.run(
        ["git", "-C", work_dir, "rev-list", "--count", f"{base}..HEAD"],
        capture_output=True, text=True,
    )
    return ret.returncode == 0 and int(ret.stdout.strip() or "0") > 0


def diff_stat(repo_path: str, base: str, head: str) -> str:
    ret = subprocess.run(
        ["git", "-C", repo_path, "diff", "--stat", f"{base}...{head}"],
        capture_output=True, text=True,
    )
    return ret.stdout if ret.returncode == 0 else "(unavailable)"


def pr_create(repo_path: str, title: str, body: str,
              head: str, base: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["gh", "pr", "create", "--draft",
         "--title", title, "--body", body,
         "--head", head, "--base", base],
        capture_output=True, text=True, cwd=repo_path,
    )


def pr_diff(repo_path: str, branch: str) -> str:
    ret = subprocess.run(
        ["gh", "pr", "diff", branch],
        capture_output=True, text=True, cwd=repo_path,
    )
    return ret.stdout or "(unavailable)"


def fetch_pr_review_comments(branch: str, repo_path: str) -> str:
    pr_view = subprocess.run(
        ["gh", "pr", "view", branch, "--json", "number,reviews,comments"],
        capture_output=True, text=True, cwd=repo_path,
    )
    if pr_view.returncode != 0:
        return ""

    pr_data = json.loads(pr_view.stdout)
    pr_number = pr_data["number"]
    parts = []

    for review in pr_data.get("reviews", []):
        body = review.get("body", "").strip()
        if body:
            state = review.get("state", "")
            author = review.get("author", {}).get("login", "unknown")
            parts.append(f"[review ({state}) by {author}]\n{body}")

    for comment in pr_data.get("comments", []):
        body = comment.get("body", "").strip()
        if body:
            author = comment.get("author", {}).get("login", "unknown")
            parts.append(f"[comment by {author}]\n{body}")

    remote = subprocess.run(
        ["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
        capture_output=True, text=True, cwd=repo_path,
    )
    if remote.returncode == 0:
        repo_slug = remote.stdout.strip()
        inline = subprocess.run(
            ["gh", "api", f"repos/{repo_slug}/pulls/{pr_number}/comments"],
            capture_output=True, text=True, cwd=repo_path,
        )
        if inline.returncode == 0:
            for c in json.loads(inline.stdout):
                path = c.get("path", "")
                line = c.get("original_line") or c.get("line") or ""
                body = c.get("body", "").strip()
                author = c.get("user", {}).get("login", "unknown")
                if body:
                    parts.append(f"[{path}:{line} by {author}]\n{body}")

    return "\n\n".join(parts)

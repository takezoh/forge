import json
import os
from pathlib import Path

FORGE_ROOT = Path(__file__).resolve().parent.parent


def load_config() -> dict:
    settings_path = FORGE_ROOT / "config" / "settings.json"
    if not settings_path.exists():
        return {}
    with open(settings_path) as f:
        return json.load(f)


def load_env():
    config_dir = FORGE_ROOT / "config"

    with open(config_dir / "settings.json") as f:
        cfg = json.load(f)

    env = {
        "LINEAR_TEAM": cfg["team"],
        "FORGE_MODEL": cfg["model"]["default"],
        "FORGE_LOG_DIR": cfg["log_dir"],
        "FORGE_LOCK_DIR": cfg["lock_dir"],
        "FORGE_WORKTREE_DIR": cfg["worktree_dir"],
        "FORGE_MAX_CONCURRENT": str(cfg["max_concurrent"]),
        "FORGE_LOCK_TIMEOUT_MIN": str(cfg["lock_timeout_min"]),
        "FORGE_QUEUE_DIR": cfg.get("queue_dir", cfg["lock_dir"] + "/queue"),
        "FORGE_PID_FILE": cfg.get("pid_file", cfg["lock_dir"] + "/forge.pid"),
    }
    for phase, val in cfg.get("budget", {}).items():
        env[f"FORGE_BUDGET_{phase.upper()}"] = str(val)
    for phase, val in cfg.get("max_turns", {}).items():
        env[f"FORGE_MAX_TURNS_{phase.upper()}"] = str(val)
    for phase, val in cfg.get("model", {}).items():
        if phase == "default":
            continue
        env[f"FORGE_MODEL_{phase.upper()}"] = str(val)

    if "webhook" in cfg:
        env["WEBHOOK_HOST"] = cfg["webhook"]["host"]
        env["WEBHOOK_PORT"] = str(cfg["webhook"]["port"])

    secrets_path = config_dir / "secrets.env"
    if secrets_path.exists():
        with open(secrets_path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                k, _, v = line.partition("=")
                env[k] = v.strip('"').strip("'")

    from lib.linear import resolve_team_id
    api_key = get_api_key(env)
    env["LINEAR_TEAM_ID"] = resolve_team_id(env["LINEAR_TEAM"], api_key)

    return env


def get_api_key(env=None):
    if env:
        key = env.get("LINEAR_OAUTH_TOKEN")
        if key:
            return key
    return os.environ.get("LINEAR_OAUTH_TOKEN", "")


def parse_labels(label_nodes) -> list[str]:
    labels = []
    for label in label_nodes:
        parent = label.get("parent")
        name = label["name"]
        labels.append(f"{parent['name']}:{name}" if parent else name)
    return labels


def load_repos() -> dict[str, str]:
    repos = {}
    conf = FORGE_ROOT / "config" / "repos.conf"
    with open(conf) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            k, _, v = line.partition("=")
            if k and v:
                repos[k.strip()] = v.strip()
    return repos


def resolve_repo(labels: list[str], repos: dict[str, str]) -> str | None:
    for label in labels:
        if label.startswith("repo:"):
            key = label.removeprefix("repo:")
            return repos.get(key)
    return None

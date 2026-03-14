# forge

Linear-driven AI agent. Automatically plans and implements tasks triggered by issue status changes.

## Structure

- `forge/` — Python package
  - `__main__.py` — Entry point (`python -m forge`)
  - `constants.py` — State/phase constants
  - `config.py` — Configuration loading, repo resolution
  - `linear.py` — Linear GraphQL client
  - `git.py` — git/gh subprocess wrappers
  - `claude.py` — Claude CLI execution, sandbox settings
  - `orchestrator.py` — Polling, dispatch, PR creation
  - `executor.py` — Per-issue execution (prompt, worktree, post-processing)
- `bin/` — Shell scripts (`main.sh`, `daemon.sh`, `service-systemd.sh`, `service-launchd.sh`, `check_cycle.py`)
- `prompts/` — Prompt templates for each phase
- `config/settings.json` — Configuration values (git ignored)
- `config/secrets.env` — Credentials (git ignored)
- `config/repos.conf` — Label → repository path mapping (git ignored)

## Flow

1. Planning: Parent issue → code investigation → sub-issue creation → Pending Approval
2. Plan Review: Pending Approval ⇄ Plan Changes Requested (human feedback → incremental plan revision)
3. Implementing: Parent issue → sub-issue dependency resolution → conductor pattern (implementer + reviewer) → PR → In Review
4. Review: Changes Requested → fix based on PR review comments → In Review

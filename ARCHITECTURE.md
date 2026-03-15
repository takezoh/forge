# Architecture

## Overview

Loki is an agent system that automatically executes tasks via Claude Code CLI, triggered by Linear issue status changes. It consists of two processes — a polling daemon (`forge`) and a webhook server (Sleipnir, `agent/`) — coordinated through a file-based queue.

## Components

### config/

| Module | Role |
|--------|------|
| `__init__.py` | Loads `settings.json` / `secrets.env` / `repos.conf`. Expands per-phase budget/model/max_turns into environment variables |
| `constants.py` | Constants for status names (`STATE_*`) and phase names (`PHASE_*`) |

### lib/

| Module | Role |
|--------|------|
| `linear.py` | Linear GraphQL API client. Issue fetching/updating, sub-issue retrieval (including dependency resolution), Agent API responses |
| `claude.py` | Claude Code CLI execution. Sandbox config generation (`setup_sandbox`), prompt execution (`run`), PR body generation (`generate_pr_body`) |
| `git.py` | `git` / `gh` command wrappers. Worktree operations, branch management, PR creation |

### forge/ (Backend)

| Module | Role |
|--------|------|
| `__main__.py` | Entry point. `--check` for environment validation, `--interval N` to override polling interval (default: 300s) |
| `orchestrator.py` | Main loop. Polling → queue consumption → lock management → `executor` subprocess launch → PR creation |
| `executor.py` | Per-issue execution unit. Prompt assembly → worktree setup → Claude execution → post-processing (status update, comment posting) |
| `queue.py` | File-based queue. `enqueue` / `dequeue_all` / `wake` (SIGUSR1) |

### agent/ (Sleipnir — Frontend)

| Module | Role |
|--------|------|
| `__main__.py` | Flask server startup |
| `webhook.py` | Linear Agent API webhook. `created` → enqueue + wake, `prompted` → session response, `stop` → process kill |

## Execution Flow

### Planning

1. Orchestrator polls for issues with `Planning` status
2. `dispatch_issue` → launches `forge.executor` subprocess (acquires lock)
3. Executor: fetches issue info → generates planning prompt → runs Claude
4. Claude delegates to Plan agent (code investigation) → self-reviews the plan (up to 2 retries) → creates plan document
5. Claude outputs `AUTO_APPROVED` or `NEEDS_HUMAN_REVIEW` marker
6. Executor parses the marker and transitions to `Plan Approved` or `Pending Approval`

### Plan Review

1. Human changes status to `Plan Changes Requested` (feedback via comment)
2. Executor: fetches feedback + plan document → generates plan_review prompt → runs Claude
3. Claude revises the plan document and outputs approval marker
4. Executor transitions to `Plan Approved` or `Pending Approval`

### Sub-issue Creation

1. Orchestrator polls for issues with `Plan Approved` status
2. `dispatch_issue("subissue_creation")` → launches executor
3. Executor: fetches issue detail + plan document → generates subissue_creation prompt → runs Claude
4. Claude breaks plan into 1-PR-sized sub-issues with dependency relations, runs cycle check
5. Executor verifies sub-issues exist, corrects states to `Todo`, transitions parent to `Implementing`

### Implementing

1. Orchestrator polls for parent issues with `Implementing` status
2. Resolves sub-issue dependencies and identifies `ready` sub-issues
3. Creates parent branch and parent worktree (if not already created)
4. For each ready sub-issue: `dispatch_issue` → launches executor
5. executor: creates sub-issue worktree from parent branch → implementing prompt → launches Claude as conductor
6. conductor launches implementer subagent (code changes) → reviewer subagent (review) → feedback loop → conductor commits
7. executor merges sub-issue branch into parent branch
8. Transitions sub-issue to `Done`
9. When all sub-issues are complete, orchestrator generates PR body and creates GitHub PR → transitions parent issue to `In Review`

### Review

1. Human changes status to `Changes Requested` after PR review
2. Executor: fetches PR review comments → review prompt → runs Claude
3. Claude commits fixes → transitions back to `In Review`

## Queue & Dispatch

### Queue Mechanism

Requests via webhook are written to the queue in a fire-and-forget manner; the forge daemon consumes them on the next cycle.

```
sleipnir (webhook) → queue.enqueue(queue_dir, issue_id, session_id, phase)
                → queue.wake(pid_file)  # SIGUSR1
forge (daemon)  → consume_queue(queue_dir) → merged into session_map → dispatch
```

- **Queue file**: `{queue_dir}/{issue_id}.json` — JSON payload (`issue_id`, `session_id`, `phase`)
- **SIGUSR1 wake**: Sets the daemon's `threading.Event`, causing immediate return from sleep
- **session_id**: For tracking Agent API sessions. Used when triggered via webhook

### Locks

- **Execution lock**: `{lock_dir}/{issue_id}.lock` — Prevents duplicate execution of the same issue
- **PR lock**: `{lock_dir}/pr-{identifier}.lock` — Prevents duplicate PR creation
- **Concurrency limit**: `max_concurrent` limits the number of parallel executors (counted by lock files)
- **Zombie reaping**: `reap_children()` reaps terminated child processes via `os.waitpid(-1, WNOHANG)`
- **Timeout**: Locks older than `lock_timeout_min` are automatically removed by `clean_stale_locks`

## Sandbox & Permissions

Configure sandbox settings in `claude.sandbox` in `settings.json` (see `settings.json.example`).
See [Claude Code sandboxing docs](https://code.claude.com/docs/en/sandboxing) for available options.

`setup_settings` in `lib/claude.py` writes `claude` settings to `.claude/settings.local.json` inside the worktree:

- **Sandbox**: Dynamically adds log directory and parent repo's `.git/worktrees` to `allowWrite`. Sub-issue execution also adds the parent issue's worktree directory.
- **Permissions**: Dynamically generates `permissions.allow` and `permissions.deny` based on the current phase. `mcp__linear-server__*` is always allowed via wildcard. Phase-specific denied tools are defined in `PHASE_DENIED_TOOLS` in `config/constants.py`. Phase-specific allowed tools can be configured via `allowed_tools` in `settings.json`.

## Configuration

Settings in `config/settings.json`:

| Key | Type | Description |
|-----|------|-------------|
| `team` | string | Linear team name (required; `team_id` is resolved automatically via API) |
| `budget` | object | Per-phase USD budget. `poll`, `planning`, `implementing`, `plan_review`, `subissue_creation`, `review` |
| `max_turns` | object | Per-phase maximum turns. `planning`, `implementing`, `plan_review`, `subissue_creation`, `review` |
| `model` | object | Per-phase model. `default`, `planning`, `implementing`, `plan_review`, `subissue_creation`, `pr`, `review` |
| `log_dir` | string | Log output directory (required) |
| `lock_dir` | string | Lock file directory (required) |
| `worktree_dir` | string | Git worktree base directory (required) |
| `max_concurrent` | int | Maximum concurrent executions |
| `lock_timeout_min` | int | Lock file expiration time (minutes) |
| `webhook` | object | `host`, `port` — Webhook server settings |
| `allowed_tools` | object | Per-phase allowed tools list |
| `claude.sandbox` | object | Sandbox settings (see Sandbox section above) |

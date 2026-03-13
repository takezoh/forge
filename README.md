# forge

Linear-driven AI agent. Automatically plans and implements tasks triggered by issue status changes.

## Setup

```bash
./setup.sh
```

### Prerequisites

- Python 3.10+
- [Claude Code](https://claude.com/claude-code) CLI
- [GitHub CLI](https://cli.github.com/) (`gh`)
- `bubblewrap` and `socat` (for sandbox)

```bash
# Ubuntu/Debian
sudo apt-get install bubblewrap socat
```

### Configuration

1. Copy example configs:
   ```bash
   cp config/settings.json.example config/settings.json
   cp config/secrets.env.example config/secrets.env
   cp config/repos.conf.example config/repos.conf
   ```

2. Edit `config/settings.json` — set `team_id`, model/budget settings, directories, etc.

3. Edit `config/secrets.env` — set `LINEAR_API_KEY`

4. Edit `config/repos.conf` — map labels to repository paths:
   ```
   myproject=/home/user/dev/myproject
   ```

5. Add the Linear MCP server to Claude Code:
   ```bash
   claude mcp add linear-server -- npx -y @anthropic-ai/linear-mcp-server
   ```

## Usage

```bash
python bin/forge.py
```

Or via the wrapper script:

```bash
bin/main.sh
```

## Architecture

```
forge.py
  ├── Poll "Planning" issues → dispatch to planning prompt
  ├── Poll "Plan Changes Requested" issues → dispatch to plan_review prompt
  ├── Poll "Implementing" issues (parent) → fetch sub-issues + dependency check
  │   ├── Filter ready sub-issues (blockers resolved, not terminal)
  │   └── Dispatch each to implementing prompt
  ├── Poll "Changes Requested" issues → dispatch to review prompt
  └── Wait for all processes

run_claude.py
  ├── Load prompt template + substitute variables
  ├── Pre-fetch Linear data (issue detail, documents, sub-issues, comments)
  ├── Create worktree (implementing / review only)
  ├── Write sandbox settings
  └── Execute claude CLI in sandboxed environment

Planning (prompts/planning.md)
  ├── Delegate code investigation to Plan agent
  ├── Create plan document + sub-issues
  ├── Validate dependency cycle
  └── Update status → Pending Approval

Plan Review (prompts/plan_review.md)
  ├── Read review feedback from issue comments
  ├── Incrementally update plan document + sub-issues
  ├── Validate dependency cycle
  └── Update status → Pending Approval

Implementing (prompts/implementing.md)
  ├── Conductor fetches issue + parent context + plan
  ├── Launch implementer agent (Sonnet)
  ├── Launch reviewer agent (Opus)
  ├── Feedback loop (max 2 rounds)
  └── Commit → Push → Merge to parent branch → Linear update

Review (prompts/review.md)
  ├── Read PR review comments + diff
  ├── Fix issues in worktree
  └── Commit → Push → Update status → In Review
```

## Workflow

```
Backlog → Planning → Pending Approval ⇄ Plan Changes Requested → Implementing → In Review ⇄ Changes Requested → Done
```

| Status | Category | Actor | Description |
|--------|----------|-------|-------------|
| Backlog | Backlog | Human | Not started |
| Planning | Started | Agent | Creating sub-issues and plan |
| Pending Approval | Started | Human | Reviewing the plan |
| Plan Changes Requested | Started | Agent | Revising plan based on feedback |
| Implementing | Started | Agent | Building + PR creation |
| In Review | Started | Human | Reviewing PRs |
| Changes Requested | Started | Agent | Fixing PR review feedback |
| Failed | Started | Auto | Execution failed |
| Done | Completed | Auto | Completed |
| Cancelled | Cancelled | Human | Cancelled |

### Linear Setup

Configure issue statuses in **Settings → Teams → Issue statuses & automations**.

Enable the following automations:
- Auto-complete parent issue when all sub-issues are Done
- Auto-cancel all sub-issues when parent issue is Cancelled

## File Structure

| Path | Description |
|------|-------------|
| `bin/forge.py` | Main entry point — polling, dispatch, concurrency |
| `bin/poll.py` | Linear GraphQL polling + sub-issue dependency resolution |
| `bin/run_claude.py` | Per-issue claude CLI execution with sandbox |
| `bin/check_cycle.py` | Dependency cycle detection CLI |
| `bin/main.sh` | Shell wrapper for forge.py |
| `bin/daemon.sh` | Daemon loop wrapper for systemd |
| `bin/service-systemd.sh` | systemd user service management |
| `prompts/planning.md` | Planning phase prompt template |
| `prompts/plan_review.md` | Plan review phase prompt template |
| `prompts/implementing.md` | Implementing phase prompt (conductor pattern) |
| `prompts/review.md` | PR review feedback phase prompt |
| `prompts/pr.md` | PR description generation prompt |
| `config/settings.json` | Configuration — models, budgets, directories (gitignored) |
| `config/secrets.env` | Credentials — LINEAR_API_KEY (gitignored) |
| `config/repos.conf` | Label → repo path mapping (gitignored) |
| `setup.sh` | Environment setup and validation script |

## Models

| Role | Model | Rationale |
|------|-------|-----------|
| Planner | Sonnet + Opus subagent | Sonnet orchestrates, Opus subagent for codebase analysis |
| Plan Reviewer | Sonnet + Opus subagent | Sonnet orchestrates, Opus subagent for re-investigation |
| Conductor | Sonnet | Procedural orchestration, cost-efficient |
| Implementer | Sonnet | Code generation, speed and cost balance |
| Reviewer | Opus | Deep reasoning for bug and design issue detection |
| PR Description | Haiku | Simple text generation, low cost |

## Sandbox

Each claude CLI execution runs with Claude Code's native sandbox:

- **Filesystem**: Write restricted to work directory + logs. `~/.ssh`, `~/.aws`, `~/.gnupg` denied.
- **Network**: `allowManagedDomainsOnly` — only `api.linear.app`, `github.com`, `api.anthropic.com` allowed.
- **Escape hatch disabled**: `allowUnsandboxedCommands: false`

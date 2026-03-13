# forge

Linear-driven AI agent. Automatically plans and implements tasks triggered by issue status changes.

## Structure

- `bin/forge.py` — Main entry point. Polling → issue dispatch → background execution
- `bin/poll.py` — Linear GraphQL polling for issues by status
- `bin/run_claude.py` — Per-issue claude CLI execution (planning / implementing / review)
- `prompts/` — Prompt templates for each phase
- `config/settings.json` — Configuration values (git ignored)
- `config/secrets.env` — Credentials (git ignored)
- `config/repos.conf` — Label → repository path mapping (git ignored)

## Flow

1. Planning: Parent issue → code investigation → sub-issue creation → Pending Approval
2. Plan Review: Pending Approval ⇄ Plan Changes Requested (human feedback → incremental plan revision)
3. Implementing: Parent issue → sub-issue dependency resolution → conductor pattern (implementer + reviewer) → PR → In Review
4. Review: Changes Requested → fix based on PR review comments → In Review

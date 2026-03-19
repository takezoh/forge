from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Issue:
    id: str
    identifier: str
    title: str = ""
    phase: str = ""
    status: str = "queued"
    parent_id: str | None = None
    parent_identifier: str | None = None
    repo_path: str | None = None
    base_branch: str | None = None
    branch: str | None = None
    session_id: str | None = None
    worktree_path: str | None = None
    pid: int | None = None
    retry_count: int = 0
    error: str | None = None
    metadata: dict = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None

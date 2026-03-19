from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from pathlib import Path

    from loki2.store.models import Issue


@dataclass
class PhaseResult:
    event: str
    comment: str = ""
    metadata: dict | None = None


class PhaseHandler(Protocol):
    phase_name: str

    async def prepare_prompt(self, issue: Issue, config: dict) -> str: ...

    async def setup_workspace(self, issue: Issue, config: dict) -> Path | None: ...

    async def post_execute(self, issue: Issue, claude_result: dict, config: dict) -> PhaseResult: ...

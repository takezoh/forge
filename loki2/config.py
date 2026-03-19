from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from pydantic import BaseModel, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class PhaseConfig(BaseModel):
    model: str = ""
    budget: Decimal = Decimal("3.00")
    max_turns: int = 30
    timeout: int = 1800
    idle_timeout: int = 180


class WebhookConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 3000


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="LOKI_",
        extra="ignore",
    )

    linear_team: str
    linear_oauth_token: SecretStr
    linear_webhook_secret: SecretStr = SecretStr("")

    default_model: str = "sonnet"
    max_concurrent: int = 3
    max_retries: int = 2
    poll_interval: int = 300

    log_dir: Path = Path("logs")
    worktree_dir: Path = Path("worktrees")
    db_path: Path = Path("loki2.db")

    repos: dict[str, Path] = {}
    phases: dict[str, PhaseConfig] = {}
    webhook: WebhookConfig | None = None

    def phase_config(self, phase: str) -> PhaseConfig:
        return self.phases.get(phase, PhaseConfig())

    def model_for_phase(self, phase: str) -> str:
        pc = self.phase_config(phase)
        return pc.model or self.default_model

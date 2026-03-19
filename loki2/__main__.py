from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
from pathlib import Path

from loki2.clients.linear import LinearClient
from loki2.config import Settings, WebhookConfig
from loki2.loop import Scheduler
from loki2.prompt import PromptBuilder
from loki2.store.db import Database
from loki2.workspace.manager import WorkspaceManager


async def main():
    parser = argparse.ArgumentParser(description="Loki v2 autonomous dev agent")
    parser.add_argument("--webhook", action="store_true", help="Enable webhook server")
    parser.add_argument("--webhook-host", default=None, help="Webhook host (default: 0.0.0.0)")
    parser.add_argument("--webhook-port", type=int, default=None, help="Webhook port (default: 3000)")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stderr,
    )
    log = logging.getLogger("loki2")

    try:
        settings = Settings()
    except Exception as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        sys.exit(1)

    if args.webhook and not settings.webhook:
        settings.webhook = WebhookConfig()
    if args.webhook_host and settings.webhook:
        settings.webhook.host = args.webhook_host
    if args.webhook_port and settings.webhook:
        settings.webhook.port = args.webhook_port

    settings.log_dir.mkdir(parents=True, exist_ok=True)

    db = Database(settings.db_path)
    await db.connect()

    linear = LinearClient(settings.linear_oauth_token.get_secret_value())
    await linear.resolve_team(settings.linear_team)
    log.info("Connected to Linear team: %s", settings.linear_team)

    forge_root = Path(__file__).resolve().parent.parent
    prompt_builder = PromptBuilder(forge_root / "prompts")
    workspace = WorkspaceManager(settings.worktree_dir)

    scheduler = Scheduler(settings, db, linear, workspace, prompt_builder)

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, scheduler.stop)

    webhook_server = None
    if args.webhook or settings.webhook:
        wh = settings.webhook or WebhookConfig()
        log.info("Starting webhook server on %s:%d", wh.host, wh.port)

        from loki2.webhook import create_app
        import uvicorn

        app = create_app(settings, linear, scheduler)
        config = uvicorn.Config(app, host=wh.host, port=wh.port, log_level="info")
        webhook_server = uvicorn.Server(config)
        asyncio.create_task(webhook_server.serve())

    try:
        await scheduler.run()
    finally:
        if webhook_server:
            webhook_server.should_exit = True
        await linear.close()
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())

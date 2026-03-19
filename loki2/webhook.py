from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
import signal
from typing import TYPE_CHECKING

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

if TYPE_CHECKING:
    from loki2.clients.linear import LinearClient
    from loki2.config import Settings
    from loki2.loop import Scheduler

log = logging.getLogger("loki2.webhook")


def _verify_signature(body: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def _extract_issue_from_context(prompt_context: str) -> tuple[str, str]:
    identifier_match = re.search(r'<identifier>(.*?)</identifier>', prompt_context)
    id_match = re.search(r'<id>(.*?)</id>', prompt_context)
    identifier = identifier_match.group(1) if identifier_match else ""
    issue_id = id_match.group(1) if id_match else ""
    return identifier, issue_id


class WebhookHandler:
    def __init__(self, settings: Settings, linear: LinearClient, scheduler: Scheduler):
        self.settings = settings
        self.linear = linear
        self.scheduler = scheduler
        self._secret = settings.linear_webhook_secret.get_secret_value() if settings.linear_webhook_secret else ""

    async def handle_webhook(self, request: Request) -> JSONResponse:
        if not self._secret:
            return JSONResponse({"error": "webhook secret not configured"}, status_code=500)

        body = await request.body()
        signature = request.headers.get("Linear-Signature", "")

        if not _verify_signature(body, signature, self._secret):
            return JSONResponse({"error": "invalid signature"}, status_code=401)

        payload = await request.json()

        # Process in background without blocking the response
        import asyncio
        asyncio.create_task(self._process_event(payload))

        return JSONResponse({"ok": True})

    async def _process_event(self, payload: dict):
        try:
            event_type = payload.get("type")
            action = payload.get("action")
            log.info("Event: type=%s action=%s", event_type, action)

            if event_type == "AgentSessionEvent":
                if action == "created":
                    await self._handle_agent_created(payload)
                elif action == "prompted":
                    await self._handle_agent_prompted(payload)
                elif action == "stop":
                    await self._handle_agent_stop(payload)
            elif event_type == "Issue":
                if action == "update":
                    await self._handle_status_change(payload)
                elif action == "create":
                    await self._handle_created_issue(payload)
        except Exception as e:
            log.exception("Error processing webhook event")
            session_id = payload.get("agentSession", {}).get("id", "")
            if session_id:
                api_key = self.settings.linear_oauth_token.get_secret_value()
                from loki2.clients.linear import LinearClient
                # Use a simple graphql call for error reporting
                try:
                    await self.linear.graphql(
                        """mutation($input: AgentActivityCreateInput!) {
                          agentActivityCreate(input: $input) { agentActivity { id } }
                        }""",
                        {"input": {
                            "agentSessionId": session_id,
                            "content": {"type": "error", "body": f"Internal error: {e}"},
                        }},
                    )
                except Exception:
                    pass

    async def _handle_agent_created(self, payload: dict):
        session = payload.get("agentSession", {})
        session_id = session.get("id", "")
        prompt_context = session.get("promptContext", "")
        api_key = self.settings.linear_oauth_token.get_secret_value()

        identifier, issue_id = _extract_issue_from_context(prompt_context)

        if not issue_id:
            await self._emit_thought(session_id, "Could not extract issue ID from context.")
            return

        detail = await self.linear.fetch_issue_detail(issue_id)
        if not identifier:
            identifier = detail.get("identifier", issue_id)

        await self._emit_thought(session_id, f"Queuing work on {identifier}...")

        from loki2.core.state import STATE_TO_PHASE, PHASE_PLANNING
        # Determine current state and phase
        data = await self.linear.graphql(
            "query($id: String!) { issue(id: $id) { state { name } } }",
            {"id": issue_id},
        )
        state_name = data.get("data", {}).get("issue", {}).get("state", {}).get("name", "")
        phase = STATE_TO_PHASE.get(state_name, PHASE_PLANNING)

        from loki2.clients.linear import _resolve_repo, _resolve_base_branch
        repos = {k: str(v) for k, v in self.settings.repos.items()}
        labels = detail.get("labels", [])
        repo_path = _resolve_repo(labels, repos)

        if repo_path:
            from loki2.store.models import Issue
            issue = Issue(
                id=issue_id,
                identifier=identifier,
                title=detail.get("title", ""),
                phase=phase,
                status="queued",
                repo_path=repo_path,
                base_branch=_resolve_base_branch(labels) or None,
                session_id=session_id,
            )
            await self.scheduler.db.upsert_issue(issue)
            await self.scheduler._dispatch(issue)

    async def _handle_agent_prompted(self, payload: dict):
        session_id = payload.get("agentSession", {}).get("id", "")
        body = payload.get("agentActivity", {}).get("body", "")
        await self._emit_thought(session_id, f"Received: {body}")

    async def _handle_agent_stop(self, payload: dict):
        session_id = payload.get("agentSession", {}).get("id", "")

        # Find running task with this session_id and cancel it
        for issue_id, task in list(self.scheduler.running.items()):
            db_issue = await self.scheduler.db.get_issue(issue_id)
            if db_issue and db_issue.session_id == session_id:
                log.info("Stopping task %s (session %s)", issue_id, session_id)
                task.cancel()
                break

        await self._emit_response(session_id, "Stopped.")

    async def _handle_created_issue(self, payload: dict):
        data = payload.get("data", {})
        issue_id = data.get("id", "")
        identifier = data.get("identifier", "")
        state_name = data.get("state", {}).get("name", "")
        parent_id = data.get("parentId")

        if parent_id:
            log.info("created_issue: %s is a sub-issue, skipping", identifier or issue_id)
            return

        if not issue_id:
            return

        from loki2.core.state import STATE_TO_PHASE, STATE_PLANNING, PHASE_PLANNING
        phase = STATE_TO_PHASE.get(state_name)
        if phase is None:
            phase = PHASE_PLANNING
            await self.linear.update_issue_state(issue_id, STATE_PLANNING)

        detail = await self.linear.fetch_issue_detail(issue_id)
        from loki2.clients.linear import _resolve_repo, _resolve_base_branch
        repos = {k: str(v) for k, v in self.settings.repos.items()}
        labels = detail.get("labels", [])
        repo_path = _resolve_repo(labels, repos)

        if repo_path:
            from loki2.store.models import Issue
            issue = Issue(
                id=issue_id,
                identifier=identifier or detail.get("identifier", ""),
                title=detail.get("title", ""),
                phase=phase,
                status="queued",
                repo_path=repo_path,
                base_branch=_resolve_base_branch(labels) or None,
            )
            await self.scheduler.db.upsert_issue(issue)
            await self.scheduler._dispatch(issue)

    async def _handle_status_change(self, payload: dict):
        updated_from = payload.get("updatedFrom", {})
        if "stateId" not in updated_from:
            return

        data = payload.get("data", {})
        issue_id = data.get("id", "")
        identifier = data.get("identifier", "")
        state_name = data.get("state", {}).get("name", "")

        from loki2.core.state import STATE_TO_PHASE
        phase = STATE_TO_PHASE.get(state_name)
        if not issue_id or not phase:
            return

        log.info("status_change: %s state=%s phase=%s", identifier or issue_id, state_name, phase)

        detail = await self.linear.fetch_issue_detail(issue_id)
        from loki2.clients.linear import _resolve_repo, _resolve_base_branch
        repos = {k: str(v) for k, v in self.settings.repos.items()}
        labels = detail.get("labels", [])
        repo_path = _resolve_repo(labels, repos)

        if repo_path:
            from loki2.store.models import Issue
            issue = Issue(
                id=issue_id,
                identifier=identifier or detail.get("identifier", ""),
                title=detail.get("title", ""),
                phase=phase,
                status="queued",
                repo_path=repo_path,
                base_branch=_resolve_base_branch(labels) or None,
            )
            await self.scheduler.db.upsert_issue(issue)
            await self.scheduler._dispatch(issue)

    async def _emit_thought(self, session_id: str, body: str):
        if not session_id:
            return
        await self.linear.graphql(
            """mutation($input: AgentActivityCreateInput!) {
              agentActivityCreate(input: $input) { agentActivity { id } }
            }""",
            {"input": {
                "agentSessionId": session_id,
                "content": {"type": "thought", "body": body},
            }},
        )

    async def _emit_response(self, session_id: str, body: str):
        if not session_id:
            return
        await self.linear.graphql(
            """mutation($input: AgentActivityCreateInput!) {
              agentActivityCreate(input: $input) { agentActivity { id } }
            }""",
            {"input": {
                "agentSessionId": session_id,
                "content": {"type": "response", "body": body},
            }},
        )


def create_app(settings: Settings, linear: LinearClient, scheduler: Scheduler) -> Starlette:
    handler = WebhookHandler(settings, linear, scheduler)
    return Starlette(
        routes=[
            Route("/webhook", handler.handle_webhook, methods=["POST"]),
        ],
    )

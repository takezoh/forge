from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

from loki2.phases import PhaseResult

if TYPE_CHECKING:
    from loki2.clients.linear import LinearClient
    from loki2.config import Settings
    from loki2.store.models import Issue

phase_name = "review"


async def prepare_prompt(issue: Issue, settings: Settings,
                         linear: LinearClient, prompt_builder) -> str:
    from loki2.clients.git import pr_diff, fetch_pr_review_comments

    detail = await linear.fetch_issue_detail(issue.id)
    sub_data = await linear.fetch_sub_issues(issue.id)
    ref_docs = await linear.resolve_attachment_documents(detail.get("attachments", []))

    diff = await asyncio.to_thread(pr_diff, issue.repo_path, issue.identifier)
    review_comments = await asyncio.to_thread(
        fetch_pr_review_comments, issue.identifier, issue.repo_path)

    issue_comments = await linear.fetch_issue_comments(issue.id)
    if issue_comments:
        linear_parts = [f"[Linear comment by {c['user']}]\n{c['body']}" for c in issue_comments]
        review_comments += ("\n\n" if review_comments else "") + "\n\n".join(linear_parts)

    context = {
        "ISSUE_ID": issue.id,
        "ISSUE_IDENTIFIER": issue.identifier,
        "ISSUE_DETAIL": detail,
        "PLAN_DOCUMENTS": sub_data.get("documents", []),
        "REFERENCE_DOCUMENTS": ref_docs,
        "PR_DIFF": diff,
        "REVIEW_COMMENTS": review_comments or "(no comments)",
    }
    return prompt_builder.build("review", context)


async def setup_workspace(issue: Issue, settings: Settings, workspace_mgr) -> Path:
    return await workspace_mgr.create_branch(
        issue.repo_path, issue.identifier, issue.identifier, issue.identifier)


async def post_execute(issue: Issue, claude_result: dict,
                       linear: LinearClient, workspace_mgr) -> PhaseResult:
    from loki2.clients.git import has_new_commits, push

    result_text = claude_result.get("result", "")
    wt_path = workspace_mgr.worktree_path(issue.identifier)
    base_ref = f"origin/{issue.identifier}"

    if not has_new_commits(str(wt_path), base_ref):
        raise RuntimeError("No commits were created during review.")

    await asyncio.to_thread(push, str(wt_path), issue.identifier)

    return PhaseResult(event="fixed", comment=result_text)

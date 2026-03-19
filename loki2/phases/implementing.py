from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

from loki2.phases import PhaseResult

if TYPE_CHECKING:
    from loki2.clients.linear import LinearClient
    from loki2.config import Settings
    from loki2.store.models import Issue

phase_name = "implementing"


async def prepare_prompt(issue: Issue, settings: Settings,
                         linear: LinearClient, prompt_builder) -> str:
    sub_detail = await linear.fetch_issue_detail(issue.id)
    parent_detail = await linear.fetch_issue_detail(issue.parent_id)
    parent_data = await linear.fetch_sub_issues(issue.parent_id)
    ref_docs = await linear.resolve_attachment_documents(parent_detail.get("attachments", []))
    sub_comments = await linear.fetch_issue_comments(issue.id)

    context = {
        "ISSUE_ID": issue.id,
        "ISSUE_IDENTIFIER": issue.identifier,
        "PARENT_ISSUE_ID": issue.parent_id or "",
        "PARENT_IDENTIFIER": issue.parent_identifier or "",
        "SUB_ISSUE_DETAIL": sub_detail,
        "PARENT_ISSUE_DETAIL": parent_detail,
        "PLAN_DOCUMENTS": parent_data.get("documents", []),
        "REFERENCE_DOCUMENTS": ref_docs,
        "SUB_ISSUE_COMMENTS": sub_comments,
    }
    return prompt_builder.build("implementing", context)


async def setup_workspace(issue: Issue, settings: Settings, workspace_mgr) -> Path:
    from loki2.clients.git import detect_default_branch, branch_exists, create_branch

    repo = issue.repo_path
    default_branch = issue.base_branch or detect_default_branch(repo)
    parent_branch = issue.parent_identifier or default_branch

    if issue.parent_identifier and not branch_exists(repo, issue.parent_identifier):
        create_branch(repo, issue.parent_identifier, default_branch)

    return await workspace_mgr.create_branch(
        repo, issue.identifier, parent_branch, issue.identifier)


async def post_execute(issue: Issue, claude_result: dict,
                       linear: LinearClient, workspace_mgr,
                       merge_lock: asyncio.Lock | None = None) -> PhaseResult:
    from loki2.clients.git import has_new_commits, detect_default_branch, push

    result_text = claude_result.get("result", "")
    already_implemented = "ALREADY_IMPLEMENTED" in result_text

    base_branch = issue.parent_identifier or detect_default_branch(issue.repo_path)
    wt_path = workspace_mgr.worktree_path(issue.identifier)

    if not has_new_commits(str(wt_path), base_branch):
        if already_implemented:
            if issue.parent_id:
                await linear.create_comment(
                    issue.parent_id,
                    f"**{issue.identifier}**: Already implemented")
            return PhaseResult(event="implemented", comment=result_text)
        raise RuntimeError("No commits were created.")

    if issue.parent_identifier:
        lock = merge_lock or asyncio.Lock()
        async with lock:
            success = await workspace_mgr.merge_to_parent(
                issue.repo_path, issue.identifier,
                issue.parent_identifier, issue.parent_identifier)
            if not success:
                raise RuntimeError(
                    f"Merge of {issue.identifier} into {issue.parent_identifier} failed (conflict).")
            parent_wt = workspace_mgr.worktree_path(issue.parent_identifier)
            await asyncio.to_thread(push, str(parent_wt), issue.parent_identifier)

    if issue.parent_id:
        await linear.create_comment(
            issue.parent_id,
            f"**{issue.identifier}**: Implementation complete")

    return PhaseResult(event="implemented", comment=result_text)

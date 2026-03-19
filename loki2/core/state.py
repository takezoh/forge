from __future__ import annotations

STATE_PLANNING = "Planning"
STATE_PENDING_APPROVAL = "Pending Approval"
STATE_IMPLEMENTING = "Implementing"
STATE_IN_REVIEW = "In Review"
STATE_CHANGES_REQUESTED = "Changes Requested"
STATE_TODO = "Todo"
STATE_IN_PROGRESS = "In Progress"
STATE_DONE = "Done"
STATE_FAILED = "Failed"
STATE_CANCELLED = "Cancelled"

END_STATES = frozenset({STATE_DONE, STATE_FAILED, STATE_CANCELLED})

STATE_TYPE_COMPLETED = "completed"
STATE_TYPE_CANCELED = "canceled"
FINISHED_STATE_TYPES = frozenset({STATE_TYPE_COMPLETED, STATE_TYPE_CANCELED})

PHASE_PLANNING = "planning"
PHASE_PLAN_REVIEW = "plan_review"
PHASE_SUBISSUE_CREATION = "subissue_creation"
PHASE_IMPLEMENTING = "implementing"
PHASE_REVIEW = "review"
PHASE_PR = "pr"

PHASE_DENIED_TOOLS: dict[str, list[str]] = {
    PHASE_PLANNING: [
        "mcp__linear-server__get_issue",
        "mcp__linear-server__list_issue_statuses",
        "mcp__linear-server__save_comment",
        "mcp__linear-server__save_issue",
    ],
    PHASE_IMPLEMENTING: [
        "mcp__linear-server__get_issue",
        "mcp__linear-server__list_documents",
        "mcp__linear-server__list_comments",
        "mcp__linear-server__save_issue",
    ],
    PHASE_PLAN_REVIEW: [
        "mcp__linear-server__get_issue",
        "mcp__linear-server__list_issue_statuses",
        "mcp__linear-server__save_comment",
        "mcp__linear-server__save_issue",
    ],
    PHASE_SUBISSUE_CREATION: [
        "mcp__linear-server__get_issue",
        "mcp__linear-server__list_issue_statuses",
        "mcp__linear-server__save_comment",
    ],
    PHASE_REVIEW: [
        "mcp__linear-server__save_issue",
        "mcp__linear-server__get_issue",
        "mcp__linear-server__list_documents",
    ],
}

STATE_TO_PHASE = {
    STATE_PLANNING: PHASE_PLANNING,
    STATE_IMPLEMENTING: PHASE_IMPLEMENTING,
    STATE_CHANGES_REQUESTED: PHASE_REVIEW,
}

TRANSITIONS: dict[tuple[str, str], str] = {
    (STATE_PLANNING, "auto_approved_single"): STATE_IMPLEMENTING,
    (STATE_PLANNING, "auto_approved_multi"): STATE_IMPLEMENTING,
    (STATE_PLANNING, "needs_review"): STATE_PENDING_APPROVAL,
    (STATE_PENDING_APPROVAL, "approved"): STATE_IMPLEMENTING,
    (STATE_PENDING_APPROVAL, "rejected"): STATE_PLANNING,
    (STATE_IMPLEMENTING, "subissues_created"): STATE_IMPLEMENTING,
    (STATE_IMPLEMENTING, "all_done"): STATE_IN_REVIEW,
    (STATE_IMPLEMENTING, "implemented"): STATE_IN_REVIEW,
    (STATE_IN_REVIEW, "changes_requested"): STATE_CHANGES_REQUESTED,
    (STATE_CHANGES_REQUESTED, "fixed"): STATE_IN_REVIEW,
}

WILDCARD_TRANSITIONS: dict[str, str] = {
    "error": STATE_FAILED,
}


class InvalidTransition(Exception):
    pass


def next_state(current: str, event: str) -> str:
    key = (current, event)
    if key in TRANSITIONS:
        return TRANSITIONS[key]
    if event in WILDCARD_TRANSITIONS:
        return WILDCARD_TRANSITIONS[event]
    raise InvalidTransition(f"No transition from {current!r} on event {event!r}")

# Parent issue states
STATE_PLANNING = "Planning"
STATE_PENDING_APPROVAL = "Pending Approval"
STATE_IMPLEMENTING = "Implementing"
STATE_IN_REVIEW = "In Review"
STATE_CHANGES_REQUESTED = "Changes Requested"

# Sub-issue states
STATE_TODO = "Todo"
STATE_IN_PROGRESS = "In Progress"

# Shared terminal states
STATE_DONE = "Done"
STATE_FAILED = "Failed"
STATE_CANCELLED = "Cancelled"

END_STATES = frozenset({STATE_DONE, STATE_FAILED, STATE_CANCELLED})

# Linear workflow state categories (state.type in GraphQL)
STATE_TYPE_COMPLETED = "completed"
STATE_TYPE_CANCELED = "canceled"
FINISHED_STATE_TYPES = frozenset({STATE_TYPE_COMPLETED, STATE_TYPE_CANCELED})

PHASE_PLANNING = "planning"
PHASE_IMPLEMENTING = "implementing"
PHASE_REVIEW = "review"
PHASE_PLAN_REVIEW = "plan_review"
PHASE_SUBISSUE_CREATION = "subissue_creation"

STATE_TO_PHASE = {
    STATE_PLANNING: PHASE_PLANNING,
    STATE_IMPLEMENTING: PHASE_IMPLEMENTING,
    STATE_CHANGES_REQUESTED: PHASE_REVIEW,
}

PHASE_DENIED_TOOLS = {
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

# Agent Session states
SESSION_PENDING = "pending"
SESSION_ACTIVE = "active"
SESSION_ERROR = "error"
SESSION_AWAITING_INPUT = "awaitingInput"
SESSION_COMPLETE = "complete"

# Agent Activity types
ACTIVITY_THOUGHT = "thought"
ACTIVITY_ACTION = "action"
ACTIVITY_RESPONSE = "response"
ACTIVITY_ERROR = "error"
ACTIVITY_ELICITATION = "elicitation"

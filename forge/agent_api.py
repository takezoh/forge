from .linear import graphql

AGENT_ACTIVITY_CREATE = """
mutation($input: AgentActivityCreateInput!) {
  agentActivityCreate(input: $input) {
    agentActivity { id }
  }
}
"""

AGENT_SESSION_UPDATE = """
mutation($id: String!, $input: AgentSessionUpdateInput!) {
  agentSessionUpdate(id: $id, input: $input) {
    agentSession { id }
  }
}
"""


def emit_activity(session_id: str, content: dict, api_key: str, signal: str = None,
                  signal_metadata: dict = None, ephemeral: bool = False):
    input_dict = {"agentSessionId": session_id, "content": content}
    if signal is not None:
        input_dict["signal"] = signal
    if signal_metadata is not None:
        input_dict["signalMetadata"] = signal_metadata
    if ephemeral:
        input_dict["ephemeral"] = True
    return graphql(api_key, AGENT_ACTIVITY_CREATE, {"input": input_dict})


def emit_thought(session_id: str, body: str, api_key: str):
    return emit_activity(session_id, {"type": "thought", "body": body}, api_key)


def emit_action(session_id: str, action: str, parameter: str, api_key: str, result: str = None):
    content = {"type": "action", "action": action, "parameter": parameter}
    if result is not None:
        content["result"] = result
    return emit_activity(session_id, content, api_key)


def emit_response(session_id: str, body: str, api_key: str):
    return emit_activity(session_id, {"type": "response", "body": body}, api_key)


def emit_error(session_id: str, body: str, api_key: str):
    return emit_activity(session_id, {"type": "error", "body": body}, api_key)


def emit_elicitation(session_id: str, body: str, api_key: str, signal: str = None,
                     signal_metadata: dict = None):
    return emit_activity(session_id, {"type": "elicitation", "body": body}, api_key,
                         signal=signal, signal_metadata=signal_metadata)


def update_session_plan(session_id: str, steps: list[dict], api_key: str):
    return graphql(api_key, AGENT_SESSION_UPDATE, {"id": session_id, "input": {"plan": steps}})


def update_session_external_urls(session_id: str, urls: list[dict], api_key: str):
    return graphql(api_key, AGENT_SESSION_UPDATE, {"id": session_id, "input": {"externalUrls": urls}})

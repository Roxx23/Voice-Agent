"""LangGraph conversation state machine.

Graph topology
--------------
Each graph invocation represents one agent turn:

  First invocation (stage == "greeting"):
    START → greeting → END

  Subsequent invocations (stage == "awaiting_response"):
    START → detect_intent → route ──┬── objection_handling → END
                                    ├── discount_offer      → END
                                    └── close               → END

  If call_ended is True any invocation returns immediately via the
  "already_closed" short-circuit edge.

Checkpointing
-------------
MemorySaver keeps state across turns within the same server process.
Each conversation is keyed by session_id (thread_id in LangGraph config).
"""

from __future__ import annotations

import logging

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from app.agent.state import ConversationState
from app.agent.nodes import (
    greeting_node,
    detect_intent_node,
    objection_handling_node,
    discount_offer_node,
    close_node,
    off_topic_redirect_node,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Routing functions
# ---------------------------------------------------------------------------

_OBJECTION_INTENTS = {"objection_price", "objection_time", "objection_need"}


def _route_entry(state: ConversationState) -> str:
    """Entry-point router: choose the first node based on conversation stage."""
    if state.get("call_ended"):
        return "already_closed"
    stage = state.get("stage", "greeting")
    if stage == "greeting":
        return "greeting"
    return "detect_intent"


def _route_after_intent(state: ConversationState) -> str:
    """After intent detection, decide what the agent should do next."""
    intent = state.get("intent", "neutral")
    objection_count = state.get("objection_count", 0)
    discount_offered = state.get("discount_offered", False)

    if intent == "end_call":
        return "close"

    if intent == "off_topic":
        return "off_topic_redirect"

    if intent in _OBJECTION_INTENTS:
        # After 2 objections we stop trying to handle them and go straight to discount
        if objection_count >= 2:
            return "discount_offer"
        return "objection_handling"

    if intent == "interested":
        if discount_offered:
            # Customer is interested AFTER we offered a discount — wrap up
            return "close"
        return "discount_offer"

    # neutral / unknown — offer discount after first non-objection response
    if not discount_offered:
        return "discount_offer"

    return "close"


def _already_closed_node(state: ConversationState) -> dict:
    """No-op node reached when the call has already ended."""
    logger.warning(
        "[session=%s] Graph invoked after call_ended=True — ignoring",
        state.get("session_id"),
    )
    return {"agent_response": ""}


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

def build_graph():
    builder = StateGraph(ConversationState)

    # Register nodes
    builder.add_node("greeting", greeting_node)
    builder.add_node("detect_intent", detect_intent_node)
    builder.add_node("objection_handling", objection_handling_node)
    builder.add_node("discount_offer", discount_offer_node)
    builder.add_node("close", close_node)
    builder.add_node("off_topic_redirect", off_topic_redirect_node)
    builder.add_node("already_closed", _already_closed_node)

    # Entry point: conditional on current stage
    builder.set_conditional_entry_point(
        _route_entry,
        {
            "greeting": "greeting",
            "detect_intent": "detect_intent",
            "already_closed": "already_closed",
        },
    )

    # From greeting: wait for customer (end this invocation)
    builder.add_edge("greeting", END)

    # From detect_intent: route to appropriate handler
    builder.add_conditional_edges(
        "detect_intent",
        _route_after_intent,
        {
            "objection_handling": "objection_handling",
            "discount_offer": "discount_offer",
            "close": "close",
            "off_topic_redirect": "off_topic_redirect",
        },
    )

    # All handler nodes end the invocation (next turn starts fresh)
    builder.add_edge("objection_handling", END)
    builder.add_edge("discount_offer", END)
    builder.add_edge("close", END)
    builder.add_edge("off_topic_redirect", END)
    builder.add_edge("already_closed", END)

    checkpointer = MemorySaver()
    return builder.compile(checkpointer=checkpointer)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
        logger.info("LangGraph conversation graph compiled")
    return _graph

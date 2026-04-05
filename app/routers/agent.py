"""POST /agent/chat — text-based test endpoint for the conversation agent.

Simulates the full recovery call flow without any voice or telephony layer.
Each request represents one conversation turn:

  Turn 1  (new session):   { session_id, cart_id }           → greeting
  Turn 2+ (ongoing):       { session_id, message }           → agent response
  Any turn after close:    returns the final outcome message  → no-op

State is persisted across turns by LangGraph's MemorySaver, keyed on session_id.
"""

import logging

from fastapi import APIRouter, HTTPException, status
from langchain_core.messages import HumanMessage

from app.agent.graph import get_graph
from app.agent.tools import fetch_cart_data
from app.schemas.schemas import ChatRequest, ChatResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["agent"])


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    """Run one conversation turn through the LangGraph agent.

    First call (new session)
    ------------------------
    Provide `session_id` + `cart_id`. Leave `message` empty.
    The agent will reply with its opening greeting.

    Subsequent calls
    ----------------
    Provide `session_id` + `message`. `cart_id` is ignored.
    The agent advances the conversation and replies.

    Ended calls
    -----------
    Once `call_ended` is True the endpoint returns the final state
    without re-invoking the graph.
    """
    graph = get_graph()
    config = {"configurable": {"thread_id": req.session_id}}

    # ── Determine if this is a new or existing session ───────────────────
    snapshot = await graph.aget_state(config)
    existing = snapshot.values  # empty dict if thread has never been invoked

    if not existing:
        # ── New session ───────────────────────────────────────────────────
        if not req.cart_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="cart_id is required to start a new session.",
            )

        try:
            cart_data = await fetch_cart_data.ainvoke({"cart_id": req.cart_id})
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            )

        initial_state = {
            "messages": [],
            "session_id": req.session_id,
            "cart_data": cart_data,
            "stage": "greeting",
            "intent": "unknown",
            "objection_count": 0,
            "discount_offered": False,
            "discount_percent": None,
            "discount_code": None,
            "outcome": None,
            "call_ended": False,
            "agent_response": "",
        }

        logger.info("[session=%s] New session started for cart=%s", req.session_id, req.cart_id)
        result = await graph.ainvoke(initial_state, config)

    else:
        # ── Existing session ──────────────────────────────────────────────
        if existing.get("call_ended"):
            logger.info("[session=%s] Session already ended, returning final state", req.session_id)
            return _build_response(req.session_id, existing)

        if not req.message.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="message is required to continue an existing session.",
            )

        logger.info("[session=%s] User: %r", req.session_id, req.message)
        result = await graph.ainvoke(
            {"messages": [HumanMessage(content=req.message)]},
            config,
        )

    logger.info("[session=%s] Agent: %r  stage=%s", req.session_id, result.get("agent_response", ""), result.get("stage", ""))
    return _build_response(req.session_id, result)


def _build_response(session_id: str, state: dict) -> ChatResponse:
    return ChatResponse(
        session_id=session_id,
        response=state.get("agent_response", ""),
        stage=state.get("stage", ""),
        intent=state.get("intent", "unknown"),
        call_ended=state.get("call_ended", False),
        outcome=state.get("outcome"),
        discount_code=state.get("discount_code"),
        discount_percent=state.get("discount_percent"),
    )

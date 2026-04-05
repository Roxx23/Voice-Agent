"""LangGraph node functions for each conversation stage."""

from __future__ import annotations

import json
import logging

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_groq import ChatGroq

from app.config import settings
from app.agent.state import ConversationState
from app.agent.tools import generate_discount
from app.agent.guardrails import sanitize_response
from app.agent.prompts import (
    build_system_prompt,
    build_greeting_instruction,
    build_objection_instruction,
    build_discount_instruction,
    build_close_instruction,
    build_off_topic_redirect_instruction,
    build_intent_context,
    INTENT_CLASSIFIER_PROMPT,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# LLM helpers
# ---------------------------------------------------------------------------

def _get_llm() -> ChatGroq:
    kwargs = dict(model="llama-3.1-8b-instant", temperature=0.4, max_tokens=150)
    if settings.groq_api_key:
        kwargs["api_key"] = settings.groq_api_key
    return ChatGroq(**kwargs)


def _get_classifier_llm() -> ChatGroq:
    kwargs = dict(model="llama-3.1-8b-instant", temperature=0.0, max_tokens=20)
    if settings.groq_api_key:
        kwargs["api_key"] = settings.groq_api_key
    return ChatGroq(**kwargs)


def _run_llm(state: ConversationState, instruction: str) -> str:
    """Invoke the LLM with full conversation context.

    Message layout passed to Groq:
      [SystemMessage: base system prompt + current instruction]
      [... conversation history (HumanMessage / AIMessage) ...]

    The instruction is appended to the system prompt so it acts as
    per-turn guidance without polluting the conversation history.
    """
    llm = _get_llm()
    system_content = build_system_prompt(state["cart_data"]) + "\n\nCURRENT TASK:\n" + instruction
    messages = [SystemMessage(content=system_content)] + list(state["messages"])
    response = llm.invoke(messages)
    raw = response.content.strip()
    return sanitize_response(raw, state["cart_data"], max_percent=settings.discount_tier_2)


# ---------------------------------------------------------------------------
# Node: greeting
# ---------------------------------------------------------------------------

def greeting_node(state: ConversationState) -> dict:
    """Generate the opening greeting. Runs on the very first turn (no user input yet)."""
    instruction = build_greeting_instruction(state["cart_data"])
    response = _run_llm(state, instruction)
    logger.info("[session=%s] Greeting: %s", state.get("session_id"), response)
    return {
        "messages": [AIMessage(content=response)],
        "stage": "awaiting_response",
        "agent_response": response,
    }


# ---------------------------------------------------------------------------
# Node: detect_intent
# ---------------------------------------------------------------------------

def detect_intent_node(state: ConversationState) -> dict:
    """Classify the customer's latest message. Sets state['intent']."""
    human_msgs = [m for m in state["messages"] if isinstance(m, HumanMessage)]
    if not human_msgs:
        logger.warning("[session=%s] detect_intent called with no human messages", state.get("session_id"))
        return {"intent": "neutral"}

    last_human = human_msgs[-1].content
    extra_context = build_intent_context(state)

    classifier_system = INTENT_CLASSIFIER_PROMPT
    if extra_context:
        classifier_system += f"\n\nCall context: {extra_context}"

    llm = _get_classifier_llm()
    try:
        raw = llm.invoke([
            SystemMessage(content=classifier_system),
            HumanMessage(content=f'Customer said: "{last_human}"'),
        ]).content.strip()

        # Strip markdown code fences if model wraps output
        if "```" in raw:
            raw = raw.split("```")[1].strip()
            if raw.startswith("json"):
                raw = raw[4:].strip()

        intent = json.loads(raw).get("intent", "neutral")
    except Exception as exc:
        logger.warning("[session=%s] Intent classification failed (%s), using neutral", state.get("session_id"), exc)
        intent = "neutral"

    logger.info("[session=%s] Intent: %s  |  message: %r", state.get("session_id"), intent, last_human)
    return {"intent": intent}


# ---------------------------------------------------------------------------
# Node: objection_handling
# ---------------------------------------------------------------------------

def objection_handling_node(state: ConversationState) -> dict:
    """Respond empathetically to the customer's objection."""
    intent = state.get("intent", "neutral")
    objection_count = state.get("objection_count", 0) + 1
    instruction = build_objection_instruction(intent, state["cart_data"])

    response = _run_llm(state, instruction)
    logger.info("[session=%s] Objection handled #%d (intent=%s): %s", state.get("session_id"), objection_count, intent, response)

    return {
        "messages": [AIMessage(content=response)],
        "stage": "awaiting_response",
        "objection_count": objection_count,
        "agent_response": response,
    }


# ---------------------------------------------------------------------------
# Node: discount_offer
# ---------------------------------------------------------------------------

async def discount_offer_node(state: ConversationState) -> dict:
    """Generate a real Shopify discount code then present the offer.

    Escalation logic:
    - First offer:  discount_tier_1 (10%)
    - If tier_1 was already declined, escalate to discount_tier_2 (15%)
    - Never exceed tier_2 — reuse existing code if already at max

    Falls back to a timestamped placeholder if the Shopify API call fails,
    so the conversation continues even during testing without live credentials.
    """
    already_offered_percent = state.get("discount_percent")

    if already_offered_percent and already_offered_percent >= settings.discount_tier_2:
        # Already at max discount — reuse the existing code
        discount_percent = already_offered_percent
        discount_code = state.get("discount_code") or "MAXOFFER"
        logger.info("[session=%s] Max discount already offered, reusing code=%s", state.get("session_id"), discount_code)
    elif already_offered_percent == settings.discount_tier_1:
        # Escalate to tier 2
        discount_percent = settings.discount_tier_2
        discount_code = await _create_discount_code(state, discount_percent)
    else:
        # First offer — tier 1
        discount_percent = settings.discount_tier_1
        discount_code = await _create_discount_code(state, discount_percent)

    instruction = build_discount_instruction(discount_percent, discount_code, state["cart_data"])
    response = _run_llm(state, instruction)
    logger.info("[session=%s] Discount offered: %d%% | code=%s", state.get("session_id"), discount_percent, discount_code)

    return {
        "messages": [AIMessage(content=response)],
        "stage": "awaiting_response",
        "discount_offered": True,
        "discount_percent": discount_percent,
        "discount_code": discount_code,
        "agent_response": response,
    }


async def _create_discount_code(state: ConversationState, percent: int) -> str:
    """Call generate_discount tool; fall back to a placeholder on any error."""
    import time
    cart_id = state["cart_data"].get("cart_id", "unknown")
    try:
        result = await generate_discount.ainvoke({"cart_id": cart_id, "percent": percent})
        return result["code"]
    except Exception as exc:
        logger.warning(
            "[session=%s] Shopify discount creation failed (%s) — using placeholder",
            state.get("session_id"), exc,
        )
        return f"SAVE{percent}OFF{int(time.time()) % 10000}"


# ---------------------------------------------------------------------------
# Node: off_topic_redirect
# ---------------------------------------------------------------------------

def off_topic_redirect_node(state: ConversationState) -> dict:
    """Acknowledge the off-topic message and steer the conversation back to the cart.

    Does not advance any conversation state — objection_count, discount_offered,
    and stage all remain unchanged so the next turn resumes normally.
    """
    instruction = build_off_topic_redirect_instruction(state["cart_data"])
    response = _run_llm(state, instruction)
    logger.info("[session=%s] Off-topic redirect: %s", state.get("session_id"), response)
    return {
        "messages": [AIMessage(content=response)],
        "agent_response": response,
        # stage stays "awaiting_response" — no state advancement
    }


# ---------------------------------------------------------------------------
# Node: close
# ---------------------------------------------------------------------------

def close_node(state: ConversationState) -> dict:
    """Generate a closing message and mark the call as ended."""
    intent = state.get("intent", "neutral")
    discount_offered = state.get("discount_offered", False)

    instruction = build_close_instruction(intent, discount_offered)
    response = _run_llm(state, instruction)

    if intent == "end_call":
        outcome = "declined"
    elif discount_offered and intent in ("interested", "neutral"):
        outcome = "recovered"
    else:
        outcome = "declined"

    logger.info("[session=%s] Call closed — outcome=%s: %s", state.get("session_id"), outcome, response)

    return {
        "messages": [AIMessage(content=response)],
        "stage": "close",
        "outcome": outcome,
        "call_ended": True,
        "agent_response": response,
    }

"""LangGraph tools for the conversation agent.

Each function is decorated with @tool so it can be:
  - Called explicitly inside a node (current v1 usage)
  - Bound to the LLM for function-calling mode in future milestones

Task 2.3: fetch_cart_data
Task 2.4: generate_discount      (stub — implemented in 2.4)
Task 2.5: send_sms               (stub — implemented in 2.5)
"""

from __future__ import annotations

import logging
from typing import Annotated

from langchain_core.tools import tool
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.db_models import AbandonedCart, CallSession
from app.services.shopify import ShopifyService

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 2.3  Cart lookup
# ---------------------------------------------------------------------------

@tool
async def fetch_cart_data(
    cart_id: Annotated[str, "The Shopify cart or checkout ID to look up"],
) -> dict:
    """Fetch full cart data for a given cart_id.

    Checks the local SQLite database first (fastest path — cart was stored
    when the Shopify webhook was received). Falls back to the Shopify Admin
    API if the record is not found locally.

    Returns a dict with keys:
      cart_id, customer_name, customer_phone, customer_email,
      items, cart_total, currency, shopify_checkout_url

    Raises ValueError if the cart cannot be found anywhere.
    """
    # ── 1. Local database ────────────────────────────────────────────────
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(AbandonedCart).where(AbandonedCart.cart_id == cart_id)
        )
        row = result.scalar_one_or_none()

    if row is not None:
        logger.info("fetch_cart_data: cart %s loaded from local DB", cart_id)
        return {
            "cart_id": row.cart_id,
            "customer_name": row.customer_name,
            "customer_phone": row.customer_phone,
            "customer_email": row.customer_email,
            "items": row.items,          # list of dicts already (stored as JSON)
            "cart_total": row.cart_total,
            "currency": row.currency,
            "shopify_checkout_url": row.shopify_checkout_url,
        }

    # ── 2. Shopify API fallback ───────────────────────────────────────────
    logger.info("fetch_cart_data: cart %s not in DB, trying Shopify API", cart_id)
    shopify = ShopifyService()
    try:
        cart_data = await shopify.get_full_cart_data(cart_id)
    except Exception as exc:
        raise ValueError(
            f"Shopify API error while fetching cart {cart_id}: {exc}"
        ) from exc

    if cart_data is None:
        raise ValueError(
            f"Cart '{cart_id}' not found in local database or Shopify API. "
            "It may have been completed or deleted."
        )

    logger.info("fetch_cart_data: cart %s loaded from Shopify API", cart_id)
    return cart_data


async def get_cart_for_session(session_id: str) -> dict:
    """Convenience function used by the /agent/chat endpoint.

    Resolves session_id → cart_id → cart data in one call.
    Raises ValueError if the session or cart is not found.
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(CallSession).where(CallSession.session_id == session_id)
        )
        session_row = result.scalar_one_or_none()

    if session_row is None:
        raise ValueError(f"No call session found for session_id='{session_id}'")

    return await fetch_cart_data.ainvoke({"cart_id": session_row.cart_id})


# ---------------------------------------------------------------------------
# 2.4  Generate discount
# ---------------------------------------------------------------------------

@tool
async def generate_discount(
    cart_id: Annotated[str, "The cart ID to generate a discount code for"],
    percent: Annotated[int, "Discount percentage — must be 10 or 15"],
) -> dict:
    """Generate a single-use Shopify discount code for the given cart.

    Creates a price rule + discount code via the Shopify Admin API.
    The code is valid for 48 hours and limited to one use per customer.

    Returns a dict with keys: code (str), percent (int), cart_id (str).
    Raises ValueError if the percent is not 10 or 15.
    """
    from app.config import settings

    if percent not in (settings.discount_tier_1, settings.discount_tier_2):
        raise ValueError(
            f"Invalid discount percent {percent}. "
            f"Allowed values: {settings.discount_tier_1}, {settings.discount_tier_2}"
        )

    shopify = ShopifyService()
    code = await shopify.create_discount_code(percent=percent, cart_id=cart_id)
    logger.info("generate_discount: created code=%s percent=%d cart=%s", code, percent, cart_id)

    return {
        "code": code,
        "percent": percent,
        "cart_id": cart_id,
    }


# ---------------------------------------------------------------------------
# 2.5  Send SMS
# ---------------------------------------------------------------------------

@tool
async def send_sms(
    phone: Annotated[str, "E.164 phone number (+91XXXXXXXXXX) to send the SMS to"],
    cart_url: Annotated[str, "The Shopify checkout URL to include in the message"],
    discount_code: Annotated[str, "The discount code to include in the message"],
    customer_name: Annotated[str, "Customer's first name for personalisation"] = "",
) -> dict:
    """Send a cart-recovery SMS with the checkout link and discount code.

    Uses Twilio SMS. The message includes:
    - A personalised greeting
    - The discount code and its percentage
    - The direct checkout link

    Returns a dict with keys: sid (str), status (str), to (str).
    Raises RuntimeError if Twilio credentials are not configured.

    NOTE: This tool is fully implemented but intentionally not wired into
    the conversation nodes until Twilio credentials are added to .env.
    To activate: call send_sms from close_node or discount_offer_node after
    setting TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, and TWILIO_FROM_NUMBER.
    """
    from app.config import settings

    if not all([settings.twilio_account_sid, settings.twilio_auth_token, settings.twilio_from_number]):
        raise RuntimeError(
            "Twilio is not configured. Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, "
            "and TWILIO_FROM_NUMBER in .env to enable SMS."
        )

    first_name = customer_name.split()[0] if customer_name else "there"
    body = _build_sms_body(first_name, discount_code, cart_url)

    # Twilio REST API is sync — run in a thread so we don't block the event loop
    import asyncio
    from functools import partial
    from twilio.rest import Client

    def _send() -> dict:
        client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
        message = client.messages.create(
            body=body,
            from_=settings.twilio_from_number,
            to=phone,
        )
        return {"sid": message.sid, "status": message.status, "to": phone}

    result = await asyncio.get_event_loop().run_in_executor(None, _send)
    logger.info("send_sms: SMS sent to %s | sid=%s status=%s", phone, result["sid"], result["status"])
    return result


def _build_sms_body(first_name: str, discount_code: str, cart_url: str) -> str:
    """Compose the SMS text. Kept under 160 chars where possible."""
    greeting = f"Hi {first_name}!" if first_name and first_name != "there" else "Hi!"
    return (
        f"{greeting} You left some items in your cart. "
        f"Use code {discount_code} for a special discount. "
        f"Complete your order here: {cart_url}"
    )

import base64
import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException, Request, status
from sqlalchemy import select

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.db_models import AbandonedCart
from app.schemas.schemas import CartItem
from app.services.scheduler import cancel_abandonment_check, schedule_abandonment_check

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
legacy_router = APIRouter(tags=["webhooks"])


def _verify_shopify_hmac(body: bytes, hmac_header: str) -> bool:
    """Verify Shopify webhook HMAC-SHA256 signature."""
    secret = settings.shopify_webhook_secret.encode("utf-8")
    digest = hmac.new(secret, body, hashlib.sha256).digest()
    computed = base64.b64encode(digest).decode("utf-8")
    return hmac.compare_digest(computed, hmac_header)


def _parse_checkout(payload: dict) -> dict:
    """Extract our fields from a Shopify checkout payload."""
    customer = payload.get("customer") or {}
    first = customer.get("first_name") or ""
    last = customer.get("last_name") or ""
    customer_name = f"{first} {last}".strip()

    # Phone: prefer customer-level, fall back to billing, then shipping address
    billing = payload.get("billing_address") or {}
    shipping = payload.get("shipping_address") or {}
    customer_phone = (
        customer.get("phone")
        or billing.get("phone")
        or shipping.get("phone")
        or ""
    )

    customer_email = customer.get("email") or payload.get("email") or ""

    items = []
    for li in payload.get("line_items") or []:
        items.append(
            CartItem(
                product_name=li.get("title") or li.get("name") or "",
                variant=li.get("variant_title") or "",
                quantity=int(li.get("quantity") or 1),
                price=float(li.get("price") or 0),
                image_url="",  # not included in checkout webhook payload
            ).model_dump()
        )

    return {
        "cart_id": str(payload.get("id", "")),
        "customer_name": customer_name,
        "customer_phone": customer_phone,
        "customer_email": customer_email,
        "items": items,
        "cart_total": float(payload.get("total_price") or 0),
        "currency": payload.get("currency") or "INR",
        "shopify_checkout_url": payload.get("abandoned_checkout_url") or "",
    }


@router.post("/shopify", status_code=status.HTTP_200_OK)
async def shopify_webhook(
    request: Request,
    x_shopify_topic: str = Header(...),
    x_shopify_hmac_sha256: str = Header(...),
    x_shopify_shop_domain: str = Header(""),
):
    body = await request.body()

    if not _verify_shopify_hmac(body, x_shopify_hmac_sha256):
        logger.warning("Shopify HMAC verification failed from %s", x_shopify_shop_domain)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid HMAC signature")

    if x_shopify_topic not in ("checkouts/create", "checkouts/update"):
        logger.debug("Ignoring unhandled Shopify topic: %s", x_shopify_topic)
        return {"received": True}

    payload = json.loads(body)
    data = _parse_checkout(payload)
    cart_id = data["cart_id"]

    # If checkout is already completed (converted to order), ignore / mark recovered
    completed_at = payload.get("completed_at")

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(AbandonedCart).where(AbandonedCart.cart_id == cart_id)
        )
        cart = result.scalar_one_or_none()

        if completed_at:
            # Checkout converted to an order — cancel any pending abandonment check
            if cart and cart.status == "pending":
                cart.status = "recovered"
                cart.recovered = True
                await session.commit()
                cancel_abandonment_check(cart_id)
                logger.info("Checkout %s completed before abandonment window", cart_id)
            return {"received": True}

        if cart is None:
            # New checkout — store as pending and schedule abandonment check
            cart = AbandonedCart(
                cart_id=cart_id,
                customer_name=data["customer_name"],
                customer_phone=data["customer_phone"],
                customer_email=data["customer_email"],
                items=data["items"],
                cart_total=data["cart_total"],
                currency=data["currency"],
                shopify_checkout_url=data["shopify_checkout_url"],
                status="pending",
                abandoned_at=datetime.now(timezone.utc),
            )
            session.add(cart)
            await session.commit()
            schedule_abandonment_check(cart_id, settings.abandonment_delay_minutes)
            logger.info("New checkout %s stored; abandonment check scheduled", cart_id)
        else:
            # Update mutable fields (items/totals may change as customer edits cart)
            if cart.status == "pending":
                cart.customer_name = data["customer_name"]
                cart.customer_phone = data["customer_phone"]
                cart.customer_email = data["customer_email"]
                cart.items = data["items"]
                cart.cart_total = data["cart_total"]
                cart.currency = data["currency"]
                cart.shopify_checkout_url = data["shopify_checkout_url"]
                await session.commit()
                logger.info("Checkout %s updated", cart_id)

    return {"received": True}


@legacy_router.post("/shopify/webhook/cart-create", status_code=status.HTTP_200_OK, include_in_schema=False)
async def shopify_webhook_cart_create_alias(
    request: Request,
    x_shopify_topic: str = Header("checkouts/create"),
    x_shopify_hmac_sha256: str = Header(...),
    x_shopify_shop_domain: str = Header(""),
):
    """Alias for legacy webhook path used by another integration."""
    return await shopify_webhook(request, x_shopify_topic, x_shopify_hmac_sha256, x_shopify_shop_domain)

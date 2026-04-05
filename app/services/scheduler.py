import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from app.database import AsyncSessionLocal

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")


async def confirm_abandonment(cart_id: str) -> None:
    """
    Run 30 minutes after a checkout/create event.
    If the cart is still 'pending' (no order received):
      1. Enrich cart data via Shopify API (task 1.4)
      2. Validate Indian phone number (task 1.6) — skip if missing/invalid
      3. Mark cart 'abandoned' so the call scheduler can pick it up (task 4.1)
    """
    from app.models.db_models import AbandonedCart  # local import avoids circular deps
    from app.services.shopify import ShopifyService

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(AbandonedCart).where(AbandonedCart.cart_id == cart_id)
        )
        cart = result.scalar_one_or_none()

        if cart is None:
            logger.warning("confirm_abandonment: cart %s not found", cart_id)
            return

        if cart.status != "pending":
            logger.info(
                "confirm_abandonment: cart %s already in status '%s', skipping",
                cart_id,
                cart.status,
            )
            return

        # --- Task 1.4 + 1.6: enrich from Shopify and validate phone ---
        try:
            shopify = ShopifyService()
            enriched = await shopify.get_full_cart_data(cart_id)
            if enriched is None:
                # No valid phone — mark as no_phone so we don't call
                cart.status = "no_phone"
                await session.commit()
                logger.info("Cart %s has no valid phone — marked no_phone", cart_id)
                return
            # Overwrite stored fields with freshest Shopify data
            cart.customer_name = enriched["customer_name"]
            cart.customer_phone = enriched["customer_phone"]
            cart.customer_email = enriched["customer_email"]
            cart.items = enriched["items"]
            cart.cart_total = enriched["cart_total"]
            cart.currency = enriched["currency"]
            cart.shopify_checkout_url = enriched["shopify_checkout_url"]
        except Exception as exc:
            # Shopify API failure: still mark abandoned using data we have from webhook
            logger.warning(
                "Shopify enrichment failed for cart %s: %s — proceeding with webhook data",
                cart_id,
                exc,
            )
            # Apply phone validation on whatever we already stored
            from app.services.shopify import validate_indian_phone
            validated = validate_indian_phone(cart.customer_phone)
            if not validated:
                cart.status = "no_phone"
                await session.commit()
                logger.info("Cart %s has no valid phone (fallback check) — marked no_phone", cart_id)
                return
            cart.customer_phone = validated

        cart.status = "abandoned"
        cart.abandoned_at = datetime.now(timezone.utc)
        await session.commit()
        logger.info("Cart %s confirmed as abandoned (phone: %s)", cart_id, cart.customer_phone)


def schedule_abandonment_check(cart_id: str, delay_minutes: int = 30) -> None:
    """Schedule confirm_abandonment to run after delay_minutes."""
    run_at = datetime.now(timezone.utc) + timedelta(minutes=delay_minutes)
    scheduler.add_job(
        confirm_abandonment,
        trigger="date",
        run_date=run_at,
        args=[cart_id],
        id=f"abandon_{cart_id}",
        replace_existing=True,
    )
    logger.info("Abandonment check scheduled for cart %s at %s", cart_id, run_at)


def cancel_abandonment_check(cart_id: str) -> None:
    """Cancel a pending abandonment check (e.g. when an order is placed)."""
    job_id = f"abandon_{cart_id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
        logger.info("Abandonment check cancelled for cart %s", cart_id)

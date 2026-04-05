"""Shopify Admin API client — tasks 1.4, 1.5, 1.6."""

import re
import logging
from datetime import datetime, timedelta, timezone

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Indian phone: optional +91 or 0 prefix, then 10 digits starting with 6-9
_INDIA_PHONE_RE = re.compile(r"^(?:\+91|0)?([6-9]\d{9})$")


def validate_indian_phone(raw: str) -> str | None:
    """Return E.164 form (+91XXXXXXXXXX) or None if invalid."""
    if not raw:
        return None
    cleaned = re.sub(r"[\s\-()]", "", raw)
    m = _INDIA_PHONE_RE.match(cleaned)
    if not m:
        return None
    return f"+91{m.group(1)}"


class ShopifyService:
    """Thin async wrapper around the Shopify Admin REST + GraphQL APIs."""

    def __init__(self) -> None:
        self._base = f"https://{settings.shopify_shop_domain}/admin/api/2024-01"
        self._headers = {
            "X-Shopify-Access-Token": settings.shopify_access_token,
            "Content-Type": "application/json",
        }

    # ------------------------------------------------------------------
    # 1.4  Cart / customer data retrieval
    # ------------------------------------------------------------------

    async def list_abandoned_checkouts(self, limit: int = 50) -> list[dict]:
        """List recent abandoned checkouts."""
        url = f"{self._base}/checkouts.json"
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, headers=self._headers, params={"limit": limit})
        resp.raise_for_status()
        return resp.json().get("checkouts", [])

    async def get_checkout(self, checkout_token: str) -> dict | None:
        """
        Fetch a single abandoned checkout by token.
        Shopify's individual checkout endpoint returns 404 for abandoned checkouts,
        so we search the list instead.
        """
        checkouts = await self.list_abandoned_checkouts(limit=250)
        for c in checkouts:
            if c.get("token") == checkout_token:
                return c
        return None

    async def get_customer_phone(self, customer_id: str) -> str | None:
        """
        Fetch the customer record and return a validated Indian phone number,
        or None if unavailable / invalid.
        """
        url = f"{self._base}/customers/{customer_id}.json"
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, headers=self._headers)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        customer = resp.json().get("customer", {})
        raw_phone = customer.get("phone") or ""
        return validate_indian_phone(raw_phone)

    async def get_full_cart_data(self, checkout_id: str, customer_id: str | None = None) -> dict | None:
        """
        Return enriched cart dict with validated phone.
        Falls back to the phone stored on the checkout if customer lookup fails.
        Returns None if no valid phone is found (task 1.6 filter).
        """
        checkout = await self.get_checkout(checkout_id)
        if not checkout:
            logger.warning("Checkout %s not found in Shopify", checkout_id)
            return None

        # Prefer customer-profile phone (more reliable), fall back to checkout phone
        validated_phone: str | None = None

        if customer_id:
            try:
                validated_phone = await self.get_customer_phone(customer_id)
            except Exception as exc:
                logger.warning("Could not fetch customer %s phone: %s", customer_id, exc)

        if not validated_phone:
            raw = (
                (checkout.get("customer") or {}).get("phone")
                or (checkout.get("billing_address") or {}).get("phone")
                or (checkout.get("shipping_address") or {}).get("phone")
                or ""
            )
            validated_phone = validate_indian_phone(raw)

        if not validated_phone:
            logger.info(
                "Checkout %s has no valid Indian phone number — skipping call", checkout_id
            )
            return None

        # Build line items
        items = []
        for li in checkout.get("line_items") or []:
            items.append(
                {
                    "product_name": li.get("title") or li.get("name") or "",
                    "variant": li.get("variant_title") or "",
                    "quantity": int(li.get("quantity") or 1),
                    "price": float(li.get("price") or 0),
                    "image_url": "",
                }
            )

        customer_data = checkout.get("customer") or {}
        first = customer_data.get("first_name") or ""
        last = customer_data.get("last_name") or ""

        return {
            "cart_id": str(checkout.get("id", checkout_id)),
            "customer_name": f"{first} {last}".strip(),
            "customer_phone": validated_phone,
            "customer_email": customer_data.get("email") or checkout.get("email") or "",
            "customer_id": str(customer_data.get("id") or customer_id or ""),
            "items": items,
            "cart_total": float(checkout.get("total_price") or 0),
            "currency": checkout.get("currency") or "INR",
            "shopify_checkout_url": checkout.get("abandoned_checkout_url") or "",
        }

    # ------------------------------------------------------------------
    # 1.5  Discount code generation
    # ------------------------------------------------------------------

    async def create_discount_code(self, percent: int, cart_id: str) -> str:
        """
        Create a unique, single-use discount code for `percent`% off the entire order.
        Returns the discount code string.

        Uses Shopify Admin REST: PriceRule + DiscountCode endpoints.
        """
        if percent not in (settings.discount_tier_1, settings.discount_tier_2):
            raise ValueError(
                f"Discount percent must be {settings.discount_tier_1} or "
                f"{settings.discount_tier_2}, got {percent}"
            )

        now = datetime.now(timezone.utc)
        ts = now.strftime("%H%M%S")  # time component keeps codes unique per cart per day
        title = f"RECOVERY_{cart_id[:8].upper()}_{percent}PCT_{now.strftime('%Y%m%d%H%M%S')}"
        # Include timestamp so retries/escalations never collide on the same cart
        code = f"CART{cart_id[:6].upper()}{percent}OFF{ts}"
        expires_at = (now + timedelta(hours=48)).isoformat()

        async with httpx.AsyncClient(timeout=20) as client:
            # Step 1: create a price rule
            pr_payload = {
                "price_rule": {
                    "title": title,
                    "target_type": "line_item",
                    "target_selection": "all",
                    "allocation_method": "across",
                    "value_type": "percentage",
                    "value": f"-{percent}.0",
                    "customer_selection": "all",
                    "starts_at": now.isoformat(),
                    "ends_at": expires_at,   # code expires in 48 hours
                    "usage_limit": 1,
                    "once_per_customer": True,
                }
            }
            pr_resp = await client.post(
                f"{self._base}/price_rules.json",
                headers=self._headers,
                json=pr_payload,
            )
            pr_resp.raise_for_status()
            price_rule_id = pr_resp.json()["price_rule"]["id"]
            logger.info("Created price rule %s for cart %s", price_rule_id, cart_id)

            # Step 2: create a discount code under that price rule
            dc_payload = {"discount_code": {"code": code}}
            dc_resp = await client.post(
                f"{self._base}/price_rules/{price_rule_id}/discount_codes.json",
                headers=self._headers,
                json=dc_payload,
            )
            if dc_resp.status_code == 422:
                errors = dc_resp.json().get("errors", {})
                raise ValueError(f"Shopify rejected discount code '{code}': {errors}")
            dc_resp.raise_for_status()
            created_code = dc_resp.json()["discount_code"]["code"]
            logger.info("Created discount code %s (%d%%, expires %s) for cart %s", created_code, percent, expires_at, cart_id)

        return created_code

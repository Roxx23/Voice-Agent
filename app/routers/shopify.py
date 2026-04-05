"""REST endpoints for Shopify cart/discount operations — tasks 1.4, 1.5, 1.6."""

import logging

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.services.shopify import ShopifyService, validate_indian_phone

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/shopify", tags=["shopify"])


class DiscountRequest(BaseModel):
    cart_id: str
    percent: int  # 10 or 15


class PhoneValidationRequest(BaseModel):
    phone: str


@router.get("/checkouts", summary="List recent abandoned checkouts — find tokens here")
async def list_checkouts(limit: int = 10):
    """Returns checkout token, customer name, phone, and total for each abandoned checkout."""
    svc = ShopifyService()
    checkouts = await svc.list_abandoned_checkouts(limit)
    return [
        {
            "token": c.get("token"),
            "id": c.get("id"),
            "customer": f"{(c.get('customer') or {}).get('first_name', '')} {(c.get('customer') or {}).get('last_name', '')}".strip(),
            "phone": (c.get("customer") or {}).get("phone") or (c.get("shipping_address") or {}).get("phone") or "",
            "total": c.get("total_price"),
            "created_at": c.get("created_at"),
        }
        for c in checkouts
    ]


@router.get("/cart/{checkout_token}", summary="Fetch and enrich cart data from Shopify (task 1.4)")
async def get_cart(checkout_token: str, customer_id: str | None = None):
    """
    Pass the checkout TOKEN (not numeric ID) — get it from GET /shopify/checkouts.
    Returns 404 if not found, 422 if found but phone is missing/invalid.
    """
    svc = ShopifyService()
    checkout = await svc.get_checkout(checkout_token)
    if checkout is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Checkout token '{checkout_token}' not found in Shopify",
        )
    data = await svc.get_full_cart_data(checkout_token, customer_id)
    if data is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Checkout found but has no valid Indian phone number",
        )
    return data


@router.post(
    "/discount",
    status_code=status.HTTP_201_CREATED,
    summary="Generate a single-use discount code (task 1.5)",
)
async def generate_discount(body: DiscountRequest):
    """
    Create a unique single-use discount code via Shopify Discount API.
    percent must be 10 or 15.
    """
    svc = ShopifyService()
    try:
        code = await svc.create_discount_code(body.percent, body.cart_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return {"discount_code": code, "percent": body.percent, "cart_id": body.cart_id}


@router.post("/validate-phone", summary="Validate an Indian phone number (task 1.6)")
async def validate_phone(body: PhoneValidationRequest):
    """
    Return the E.164 form of an Indian number, or null if invalid.
    """
    result = validate_indian_phone(body.phone)
    return {"input": body.phone, "valid": result is not None, "e164": result}

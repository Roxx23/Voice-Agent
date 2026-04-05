"""
Test abandoned cart detection by sending a mock Shopify webhook.
Usage: python test_webhook.py
Server must be running on localhost:8000.
"""
import asyncio
import base64
import hashlib
import hmac
import json
import time

import httpx
from sqlalchemy import select

# --- Mock Shopify checkout payload ---
CHECKOUT_PAYLOAD = {
    "id": 123456789,
    "token": "test-token-abc",
    "email": "testcustomer@example.com",
    "currency": "INR",
    "total_price": "2499.00",
    "abandoned_checkout_url": "https://your-store.myshopify.com/checkouts/recover/test-token-abc",
    "completed_at": None,
    "customer": {
        "id": 987,
        "first_name": "Rahul",
        "last_name": "Sharma",
        "email": "testcustomer@example.com",
        "phone": "+919876543210",
    },
    "line_items": [
        {
            "title": "Classic Cotton T-Shirt",
            "variant_title": "Blue / L",
            "quantity": 2,
            "price": "799.00",
        },
        {
            "title": "Running Shoes",
            "variant_title": "Size 10",
            "quantity": 1,
            "price": "901.00",
        },
    ],
    "billing_address": {
        "phone": "+919876543210",
    },
}


def make_hmac(secret: str, body: bytes) -> str:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


async def send_webhook(topic: str, payload: dict, secret: str, url: str):
    body = json.dumps(payload).encode()
    sig = make_hmac(secret, body)
    headers = {
        "Content-Type": "application/json",
        "X-Shopify-Topic": topic,
        "X-Shopify-Hmac-Sha256": sig,
        "X-Shopify-Shop-Domain": "test-store.myshopify.com",
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, content=body, headers=headers)
    return resp


async def check_db(cart_id: str):
    from app.database import AsyncSessionLocal
    from app.models.db_models import AbandonedCart
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(AbandonedCart).where(AbandonedCart.cart_id == cart_id)
        )
        return result.scalar_one_or_none()


async def main():
    from app.config import settings

    secret = settings.shopify_webhook_secret
    base_url = "http://localhost:8000"
    cart_id = str(CHECKOUT_PAYLOAD["id"])

    print(f"Sending checkouts/create for cart {cart_id}...")
    resp = await send_webhook("checkouts/create", CHECKOUT_PAYLOAD, secret, f"{base_url}/webhooks/shopify")
    print(f"  Response: {resp.status_code} {resp.text}")

    if resp.status_code != 200:
        print("ERROR: webhook rejected. Check SHOPIFY_WEBHOOK_SECRET in .env")
        return

    print("\nChecking DB...")
    cart = await check_db(cart_id)
    if cart:
        print(f"  ✅ Cart stored: id={cart.cart_id}, status={cart.status}")
        print(f"     Customer: {cart.customer_name} ({cart.customer_phone})")
        print(f"     Items: {len(cart.items)}, Total: {cart.cart_total} {cart.currency}")
    else:
        print("  ❌ Cart not found in DB")
        return

    print("\nSending checkouts/update (no completed_at — still pending)...")
    resp = await send_webhook("checkouts/update", CHECKOUT_PAYLOAD, secret, f"{base_url}/webhooks/shopify")
    print(f"  Response: {resp.status_code} {resp.text}")

    print("\nSimulating completed checkout (order placed)...")
    completed_payload = {**CHECKOUT_PAYLOAD, "completed_at": "2024-01-01T10:00:00Z"}
    resp = await send_webhook("checkouts/update", completed_payload, secret, f"{base_url}/webhooks/shopify")
    print(f"  Response: {resp.status_code} {resp.text}")

    cart = await check_db(cart_id)
    print(f"  Cart status after completion: {cart.status} (expected: recovered)")

    print("\nDone. To test full abandonment flow:")
    print(f"  Set ABANDONMENT_DELAY_MINUTES=1 in .env, restart server,")
    print(f"  send a fresh checkouts/create, wait 1 min, check DB for status='abandoned'")


asyncio.run(main())

from datetime import datetime

from pydantic import BaseModel


class CartItem(BaseModel):
    product_name: str
    variant: str
    quantity: int
    price: float
    image_url: str = ""


class AbandonedCartSchema(BaseModel):
    cart_id: str
    customer_name: str
    customer_phone: str
    customer_email: str
    items: list[CartItem]
    cart_total: float
    currency: str = "INR"
    abandoned_at: datetime
    shopify_checkout_url: str


class CallSessionSchema(BaseModel):
    session_id: str
    cart_id: str
    customer_phone: str
    status: str
    scheduled_at: datetime
    started_at: datetime | None = None
    ended_at: datetime | None = None
    vapi_call_id: str | None = None
    outcome: str | None = None
    discount_code: str | None = None
    discount_percent: int | None = None
    call_duration_seconds: int | None = None
    transcript: str | None = None

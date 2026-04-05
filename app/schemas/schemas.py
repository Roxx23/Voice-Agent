from datetime import datetime
from typing import Optional

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


class ChatRequest(BaseModel):
    session_id: str
    message: str = ""   # empty string on the very first call (triggers greeting)
    cart_id: str = ""   # required when starting a new session


class ChatResponse(BaseModel):
    session_id: str
    response: str
    stage: str
    intent: str = "unknown"
    call_ended: bool = False
    outcome: Optional[str] = None
    discount_code: Optional[str] = None
    discount_percent: Optional[int] = None


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

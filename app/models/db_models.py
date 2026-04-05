import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class AbandonedCart(Base):
    __tablename__ = "abandoned_carts"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    cart_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    customer_name: Mapped[str] = mapped_column(String, default="")
    customer_phone: Mapped[str] = mapped_column(String, default="")
    customer_email: Mapped[str] = mapped_column(String, default="")
    items: Mapped[dict] = mapped_column(JSON, default=list)  # list of CartItem dicts
    cart_total: Mapped[float] = mapped_column(Float, default=0.0)
    currency: Mapped[str] = mapped_column(String, default="INR")
    abandoned_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    shopify_checkout_url: Mapped[str] = mapped_column(String, default="")
    # pending → abandonment not yet confirmed; abandoned → confirmed; recovered → order placed
    status: Mapped[str] = mapped_column(String, default="pending")
    call_scheduled: Mapped[bool] = mapped_column(Integer, default=0)  # SQLite bool
    recovered: Mapped[bool] = mapped_column(Integer, default=0)


class CallSession(Base):
    __tablename__ = "call_sessions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id: Mapped[str] = mapped_column(String, unique=True, index=True, default=lambda: str(uuid.uuid4()))
    cart_id: Mapped[str] = mapped_column(String, index=True)
    customer_phone: Mapped[str] = mapped_column(String)
    # scheduled | in_progress | completed | failed | voicemail
    status: Mapped[str] = mapped_column(String, default="scheduled")
    scheduled_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    vapi_call_id: Mapped[str | None] = mapped_column(String, nullable=True)
    # recovered | declined | no_answer | voicemail | error
    outcome: Mapped[str | None] = mapped_column(String, nullable=True)
    discount_code: Mapped[str | None] = mapped_column(String, nullable=True)
    discount_percent: Mapped[int | None] = mapped_column(Integer, nullable=True)
    call_duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt_number: Mapped[int] = mapped_column(Integer, default=1)  # 1 = first call, 2 = retry

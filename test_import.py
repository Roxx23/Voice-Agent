import sys
print("step 1: sqlalchemy core")
sys.stdout.flush()

from sqlalchemy import JSON, DateTime, Float, Integer, String, Text
print("step 2: sqlalchemy core ok")
sys.stdout.flush()

from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
print("step 3: sqlalchemy orm ok")
sys.stdout.flush()

from app.models.db_models import Base, AbandonedCart
print("step 4: models ok")
sys.stdout.flush()

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
print("step 5: async engine import ok")
sys.stdout.flush()

e = create_async_engine("sqlite+aiosqlite:///./test.db")
print("step 6: engine created ok")
sys.stdout.flush()

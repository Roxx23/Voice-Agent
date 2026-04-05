from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import init_db
from app.routers import agent, calls, vapi, webhooks
from app.routers.shopify import router as shopify_router
from app.routers.webhooks import legacy_router
from app.services.scheduler import scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    scheduler.start()
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(
    title="VoiceAgent",
    description="AI-powered voice agent for abandoned cart recovery",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(webhooks.router)
app.include_router(legacy_router)
app.include_router(shopify_router)
app.include_router(calls.router)
app.include_router(agent.router)
app.include_router(vapi.router)


@app.get("/health")
async def health():
    return {"status": "ok"}

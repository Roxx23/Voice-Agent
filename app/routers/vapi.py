from fastapi import APIRouter

router = APIRouter(prefix="/vapi", tags=["vapi"])


# Placeholder — implemented in task 3.3
@router.post("/webhook")
async def vapi_webhook():
    pass

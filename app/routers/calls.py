from fastapi import APIRouter

router = APIRouter(prefix="/calls", tags=["calls"])


# Placeholder — implemented in task 3.4
@router.post("/trigger")
async def trigger_call():
    pass

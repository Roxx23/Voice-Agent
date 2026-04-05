from fastapi import APIRouter

router = APIRouter(prefix="/agent", tags=["agent"])


# Placeholder — implemented in task 2.7
@router.post("/chat")
async def chat():
    pass

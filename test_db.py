import asyncio
import traceback

async def main():
    print("testing init_db...")
    try:
        from app.database import init_db
        await init_db()
        print("init_db ok")
    except Exception as e:
        print(f"ERROR: {e}")
        traceback.print_exc()

asyncio.run(main())

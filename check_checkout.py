import asyncio
from app.services.shopify import ShopifyService

async def check():
    svc = ShopifyService()
    all_checkouts = await svc.list_abandoned_checkouts(limit=250, days_back=2)
    print(f"Total abandoned checkouts found: {len(all_checkouts)}")

    ids = [str(c.get("id")) for c in all_checkouts]
    if "32581582389400" in ids:
        print("FOUND in abandoned list")
    else:
        print("NOT in abandoned list - Shopify may not have marked it abandoned yet")

    result = await svc.get_checkout("32581582389400")
    if result:
        print("Direct lookup: OK")
        print("  Customer:", (result.get("customer") or {}).get("first_name"), (result.get("customer") or {}).get("last_name"))
        print("  Total:", result.get("total_price"))
        print("  Items:", [li.get("title") for li in result.get("line_items", [])])
    else:
        print("Direct lookup: NOT FOUND")

asyncio.run(check())

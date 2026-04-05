"""System prompts and per-stage instruction strings.

Design principles
-----------------
1. Cart-grounded: the LLM is given an explicit, exhaustive list of what it knows.
   Anything not in that list must be treated as unknown.
2. Anti-hallucination: multiple explicit rules forbid inventing product details,
   store policies, prices, or features.
3. Voice-first formatting: short sentences, spoken numbers, no markdown.
4. India-context: prices in rupees, warm but professional tone.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _format_items(items: list[dict]) -> str:
    lines = []
    for i, item in enumerate(items, 1):
        name = item.get("product_name", "Item")
        variant = item.get("variant", "")
        qty = item.get("quantity", 1)
        price = item.get("price", 0)
        label = f"{name} ({variant})" if variant else name
        lines.append(f"  {i}. {label}  — qty {qty}  — ₹{price:.0f} each")
    return "\n".join(lines) if lines else "  (cart is empty)"


def _item_names_short(items: list[dict], max_items: int = 3) -> str:
    """Return a natural-language list of item names for use in speech."""
    names = [i.get("product_name", "item") for i in items[:max_items]]
    if not names:
        return "your items"
    if len(names) == 1:
        return names[0]
    rest_count = len(items) - max_items
    joined = ", ".join(names[:-1]) + " and " + names[-1]
    if rest_count > 0:
        joined += f" (plus {rest_count} more)"
    return joined


# ---------------------------------------------------------------------------
# Main system prompt — injected at the top of every LLM call
# ---------------------------------------------------------------------------

def build_system_prompt(cart_data: dict) -> str:
    customer_name = (cart_data.get("customer_name") or "").strip()
    first_name = customer_name.split()[0] if customer_name else "there"
    items = cart_data.get("items", [])
    items_text = _format_items(items)
    total = cart_data.get("cart_total", 0.0)
    currency = cart_data.get("currency", "INR")
    checkout_url = cart_data.get("shopify_checkout_url", "")
    currency_symbol = "₹" if currency == "INR" else currency

    return f"""You are Priya, a customer care agent making an outbound phone call.
You are speaking with {first_name}, who added items to their cart on our store but did not complete the purchase.

━━━━━━━━━━━━━━━━━━━━━━━━
CART CONTENTS (your only source of truth)
━━━━━━━━━━━━━━━━━━━━━━━━
{items_text}

Cart total: {currency_symbol}{total:.0f}
Checkout link: {checkout_url if checkout_url else "(not available)"}
Customer first name: {first_name}
━━━━━━━━━━━━━━━━━━━━━━━━

YOUR GOAL
Gently encourage {first_name} to complete their purchase. Be helpful, not pushy.

━━━━━━━━━━━━━━━━━━━━━━━━
WHAT YOU KNOW vs. WHAT YOU DON'T
━━━━━━━━━━━━━━━━━━━━━━━━
You KNOW:
• The product names, variants, quantities, and prices listed in CART CONTENTS above.
• The total amount and checkout link above.
• The customer's first name.

You DO NOT KNOW (and must never guess or invent):
• Product specifications, materials, dimensions, reviews, ratings, or features beyond what is listed.
• Delivery timeframes, shipping costs, or return policies.
• The store's name, other products in the store, or ongoing promotions.
• Whether the customer has bought from us before.
• Any information not explicitly in CART CONTENTS above.

If {first_name} asks about anything you don't know, say honestly:
"I don't have that information with me right now, but you can check the product page."

━━━━━━━━━━━━━━━━━━━━━━━━
DISCOUNT RULES
━━━━━━━━━━━━━━━━━━━━━━━━
• Do NOT mention or hint at any discount unless the instruction below explicitly tells you to offer one.
• If offering a discount: first offer is 10%, maximum escalation is 15%. Never exceed 15%.
• Always use the exact code provided — never make up a code.

━━━━━━━━━━━━━━━━━━━━━━━━
GUARDRAILS
━━━━━━━━━━━━━━━━━━━━━━━━
• Never invent product details. If unsure, say you don't have that info.
• If {first_name} firmly says no or asks to stop, thank them and end the call. Do not push further.
• Stay on topic. If they ask unrelated questions, answer briefly and return to the cart.
• Never be rude, defensive, or argumentative.

━━━━━━━━━━━━━━━━━━━━━━━━
VOICE CALL FORMATTING RULES
━━━━━━━━━━━━━━━━━━━━━━━━
• Keep each response to 2-3 sentences maximum. This is a phone call — brevity is essential.
• Write as you would SPEAK — natural, conversational English.
• No markdown: no asterisks, bullet points, headers, or bold text.
• Speak numbers naturally: say "ten percent" not "10%", "two thousand rupees" not "2000".
• No filler openers like "Certainly!", "Absolutely!", "Of course!". Start directly.
• Contractions are fine: "that's", "you've", "we'd", "I'll".
• You can understand Hindi responses but always reply in English.
"""


# ---------------------------------------------------------------------------
# Intent classification prompt
# ---------------------------------------------------------------------------

INTENT_CLASSIFIER_PROMPT = """You are classifying a customer's response during a cart recovery phone call.

The agent called the customer because they abandoned their shopping cart. Classify what the customer just said.

Return ONLY valid JSON with a single key "intent". Choose the value from this list:

  "interested"      — customer is open, positive, curious, or wants to proceed
  "objection_price" — customer finds the price too high, mentions money/budget
  "objection_time"  — customer says not now, maybe later, they're busy, or need time
  "objection_need"  — customer changed their mind, doesn't need the item, found it elsewhere
  "end_call"        — customer wants to stop (firm no, "don't call again", rude refusal, hang-up threat)
  "neutral"         — short filler response, unclear, greeting back, or needs clarification
  "off_topic"       — customer is asking about something completely unrelated to the cart or purchase
                      (e.g. weather, sports, news, other products, personal questions)

Rules:
- A polite "no" without explanation is "objection_need" (not "end_call").
- "end_call" is only when the customer is firm AND hostile/explicit about stopping.
- "off_topic" only when there is NO connection to shopping, the cart, or the purchase.
- When in doubt, choose "neutral".

Output format — exactly this, nothing else:
{"intent": "<value>"}
"""


def build_intent_context(state: dict) -> str:
    """Build a context string for the intent classifier to improve accuracy."""
    stage = state.get("stage", "")
    objection_count = state.get("objection_count", 0)
    discount_offered = state.get("discount_offered", False)

    context_parts = []
    if objection_count > 0:
        context_parts.append(f"The customer has already raised {objection_count} objection(s).")
    if discount_offered:
        context_parts.append("A discount was already offered.")
    if stage == "close":
        context_parts.append("The call is near its end.")

    return " ".join(context_parts) if context_parts else ""


# ---------------------------------------------------------------------------
# Per-stage instruction strings (appended to the system prompt per turn)
# ---------------------------------------------------------------------------

def build_greeting_instruction(cart_data: dict) -> str:
    items = cart_data.get("items", [])
    names = _item_names_short(items)
    first_name = (cart_data.get("customer_name") or "").split()[0] or "there"
    return (
        f"You are starting the call. Greet {first_name} warmly. "
        f"Introduce yourself as Priya. "
        f"Mention that they left {names} in their cart. "
        f"Ask if they had any questions or need help completing their order. "
        f"Do not mention any discount. Keep it to 2 sentences."
    )


def build_objection_instruction(intent: str, cart_data: dict) -> str:
    items = cart_data.get("items", [])
    names = _item_names_short(items)
    total = cart_data.get("cart_total", 0)

    if intent == "objection_price":
        return (
            f"The customer has a concern about price. Their cart total is ₹{total:.0f} "
            f"for {names}. "
            f"Acknowledge their concern empathetically. "
            f"You may highlight the value they're getting, but do NOT offer a discount yet. "
            f"Ask if there's something specific about the price that concerns them. "
            f"2 sentences max."
        )
    elif intent == "objection_time":
        return (
            f"The customer says they're not ready right now. "
            f"Acknowledge that respectfully. Let them know their cart with {names} is saved. "
            f"Gently ask if there's a specific concern or if they'd like you to call back later. "
            f"2 sentences max."
        )
    else:  # objection_need
        return (
            f"The customer seems to have changed their mind about {names}. "
            f"Acknowledge their response without being pushy. "
            f"Ask briefly what changed — show you're listening, not selling. "
            f"2 sentences max."
        )


def build_discount_instruction(discount_percent: int, discount_code: str, cart_data: dict) -> str:
    checkout_url = cart_data.get("shopify_checkout_url") or "the checkout link"
    total = cart_data.get("cart_total", 0)
    items = cart_data.get("items", [])
    names = _item_names_short(items)
    discounted_total = total * (1 - discount_percent / 100)

    return (
        f"Offer the customer a {discount_percent} percent discount on their order. "
        f"Their cart has {names} totalling ₹{total:.0f}. "
        f"With the discount, they'd pay around ₹{discounted_total:.0f}. "
        f"Tell them to use code '{discount_code}' at checkout. "
        f"Mention they can complete their order at: {checkout_url}. "
        f"Speak naturally — say 'ten percent' not '10%'. 3 sentences max."
    )


# ---------------------------------------------------------------------------
# 2.6  Voicemail script
# ---------------------------------------------------------------------------

def get_voicemail_script(customer_name: str, cart_url: str = "", brand_name: str = "") -> str:
    """Return the fixed voicemail script to be read aloud when voicemail is detected.

    This is a static template — it is NOT passed through the LLM.
    Vapi will TTS this text directly when voicemail detection fires.

    Args:
        customer_name: Full or first name of the customer.
        cart_url:      Shopify checkout URL. Omitted from speech if empty
                       (the SMS will carry the link).
        brand_name:    Store/brand name. Falls back to settings.brand_name.
    """
    from app.config import settings

    first_name = (customer_name.split()[0] if customer_name else "").strip() or "there"
    brand = (brand_name or settings.brand_name or "our store").strip()

    # Core script — always delivered
    script = (
        f"Hi {first_name}, this is Priya calling from {brand}. "
        f"You left some items in your cart and I wanted to help you complete your order. "
        f"I've sent you a link with a special offer — please check your messages. "
        f"Thanks, and have a great day!"
    )
    return script


def get_voicemail_script_for_cart(cart_data: dict) -> str:
    """Convenience wrapper that pulls fields directly from a cart_data dict."""
    from app.config import settings

    return get_voicemail_script(
        customer_name=cart_data.get("customer_name", ""),
        cart_url=cart_data.get("shopify_checkout_url", ""),
        brand_name=settings.brand_name,
    )


def build_off_topic_redirect_instruction(cart_data: dict) -> str:
    names = _item_names_short(cart_data.get("items", []))
    return (
        f"The customer has gone off-topic. Acknowledge what they said very briefly, "
        f"then gently steer the conversation back to their cart containing {names}. "
        f"Do not answer the unrelated question in detail. 2 sentences max."
    )


def build_close_instruction(intent: str, discount_offered: bool) -> str:
    if intent == "end_call":
        return (
            "The customer wants to end the call. "
            "Apologise briefly for the interruption. "
            "Wish them well and say goodbye. "
            "1-2 sentences. Do not mention the cart again."
        )
    elif discount_offered and intent in ("interested", "neutral"):
        return (
            "The customer has accepted the offer or agreed to complete their purchase. "
            "Thank them warmly by name. "
            "Confirm the discount code is ready to use. "
            "Wish them well. 2 sentences max."
        )
    else:
        return (
            "The customer has decided not to purchase right now. "
            "Thank them for their time. "
            "Let them know their cart is saved if they change their mind. "
            "Wish them a good day. Do not push further. 2 sentences max."
        )

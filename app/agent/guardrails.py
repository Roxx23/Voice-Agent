"""Runtime guardrails applied to every agent response.

These are code-level safety nets that run AFTER the LLM generates output.
They enforce constraints that prompt engineering alone cannot guarantee:

  1. Discount cap    — clamp any stated percentage > max to max (default 15%)
  2. Length limit    — trim to voice-safe length at a sentence boundary
  3. Markdown strip  — remove any markup that would be read aloud verbatim
  4. Product check   — warn (log) if response may reference an unknown product

Guardrails do not call the LLM again — they are fast, synchronous transforms.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 1. Discount cap
# ---------------------------------------------------------------------------

# Matches "20%", "20 %", "20 percent", "20 per cent" (case-insensitive)
# No trailing \b — % is a non-word char so word-boundary doesn't apply after it
_NUMERIC_DISCOUNT_RE = re.compile(
    r"\b(\d{1,3})\s*(?:%|percent|per\s+cent)(?=\b|\s|[,.'\"!?]|$)",
    re.IGNORECASE,
)

# Spoken-form number words that could represent a discount > 15%
_HIGH_SPOKEN_DISCOUNTS = {
    "sixteen", "seventeen", "eighteen", "nineteen",
    "twenty", "twenty-five", "thirty", "forty", "fifty",
    "sixty", "seventy", "eighty", "ninety", "hundred",
}


def enforce_discount_cap(text: str, max_percent: int = 15) -> str:
    """Clamp any numeric discount > max_percent to max_percent in the text.

    Examples (max=15):
      "We'll give you 20% off"  → "We'll give you 15% off"
      "ten percent discount"    → unchanged  (10 ≤ 15)
      "25 percent off"          → "15 percent off"
    """
    def _clamp(m: re.Match) -> str:
        pct = int(m.group(1))
        if pct > max_percent:
            logger.warning(
                "Guardrail: clamped discount %d%% → %d%% in response", pct, max_percent
            )
            # Preserve original suffix style (%, percent, per cent)
            suffix = m.group(0)[len(m.group(1)):]
            return f"{max_percent}{suffix}"
        return m.group(0)

    result = _NUMERIC_DISCOUNT_RE.sub(_clamp, text)

    # Warn (but don't attempt to fix) spoken-form high discounts
    lower = text.lower()
    for word in _HIGH_SPOKEN_DISCOUNTS:
        if word in lower and ("percent" in lower or "off" in lower or "discount" in lower):
            logger.warning(
                "Guardrail: possible spoken-form high discount word '%s' detected — "
                "review prompt if this recurs",
                word,
            )
            break

    return result


# ---------------------------------------------------------------------------
# 2. Length limit
# ---------------------------------------------------------------------------

_SENTENCE_ENDINGS = re.compile(r"(?<=[.!?])\s+")


def trim_to_voice_length(text: str, max_chars: int = 380) -> str:
    """Trim response to max_chars at the nearest sentence boundary.

    Prefers ending at a full stop so the response sounds complete.
    Falls back to a hard cut with an ellipsis if no boundary is found.
    """
    if len(text) <= max_chars:
        return text

    # Try to end at a sentence boundary within the limit
    candidates = list(_SENTENCE_ENDINGS.finditer(text))
    for match in reversed(candidates):
        if match.start() <= max_chars:
            trimmed = text[: match.start()].rstrip()
            logger.warning(
                "Guardrail: response trimmed from %d → %d chars", len(text), len(trimmed)
            )
            return trimmed

    # No sentence boundary found — hard cut
    trimmed = text[:max_chars].rstrip() + "…"
    logger.warning("Guardrail: hard-cut response at %d chars", max_chars)
    return trimmed


# ---------------------------------------------------------------------------
# 3. Markdown strip
# ---------------------------------------------------------------------------

_MARKDOWN_RE = re.compile(r"(\*{1,3}|_{1,2}|`{1,3}|#{1,6}\s?|>\s?|[-*+]\s(?=\S))")


def strip_markdown(text: str) -> str:
    """Remove markdown syntax that would be read aloud verbatim by TTS."""
    return _MARKDOWN_RE.sub("", text).strip()


# ---------------------------------------------------------------------------
# 4. Product name check (warn-only)
# ---------------------------------------------------------------------------

def warn_if_unknown_product(text: str, cart_items: list[dict]) -> None:
    """Log a warning if the response contains a capitalised noun phrase
    that doesn't match any product in the cart.

    This is a heuristic, not a hard block — false positives are common.
    Used for monitoring / prompt tuning rather than enforcement.
    """
    known = {item.get("product_name", "").lower() for item in cart_items}
    # Find Title Case sequences (likely product names) in the response
    candidates = re.findall(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b", text)
    for phrase in candidates:
        if len(phrase) > 4 and phrase.lower() not in known:
            # Only warn for multi-word phrases to reduce noise
            if " " in phrase:
                logger.warning(
                    "Guardrail: possible invented product name '%s' in response — "
                    "may be a false positive",
                    phrase,
                )


# ---------------------------------------------------------------------------
# Master sanitiser — called from _run_llm in nodes.py
# ---------------------------------------------------------------------------

def sanitize_response(
    text: str,
    cart_data: dict,
    max_percent: int = 15,
    max_chars: int = 380,
) -> str:
    """Apply all guardrails in order and return the cleaned response."""
    text = strip_markdown(text)
    text = enforce_discount_cap(text, max_percent)
    text = trim_to_voice_length(text, max_chars)
    warn_if_unknown_product(text, cart_data.get("items", []))
    return text

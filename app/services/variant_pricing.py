"""Variant-aware pricing helpers.

cards.tcgplayer_prices is a JSON column with one sub-object per
variant: `{"normal": {market, low, mid, high}, "holofoil": {...},
"reverseHolofoil": {...}, "1stEdition": {...}, ...}`. This module
extracts a single variant's market price for portfolio sums, listing
filters, and collection valuations.

Anywhere we used `card.market_price_usd` (the denormalized
"representative price") and need to be variant-precise instead, route
through `price_for_variant(card, variant)`.
"""
from __future__ import annotations

import json
from typing import Any


# Order we fall back through when the requested variant has no price.
# Mirrors sync_tcgplayer_prices._market_price_from_tcgplayer.
_FALLBACK_ORDER = (
    "normal",
    "holofoil",
    "reverseHolofoil",
    "1stEditionHolofoil",
    "1stEdition",
    "unlimitedHolofoil",
    "unlimited",
)


def _as_dict(value: Any) -> dict | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (ValueError, TypeError):
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def price_for_variant(
    tcgplayer_prices: Any,
    variant: str | None,
    fallback_market_price_usd: float | None = None,
) -> float | None:
    """Return the market price for the requested variant.

    If the specific variant isn't in `tcgplayer_prices`, fall back to
    the priority order (normal → holofoil → reverseHolofoil → ...).
    Then to the card's denormalised `market_price_usd` if all variants
    miss. Returns None when no price source has data.
    """
    prices = _as_dict(tcgplayer_prices)
    if prices:
        # Try the requested variant first
        if variant and isinstance(prices.get(variant), dict):
            v = prices[variant]
            m = v.get("market") or v.get("mid")
            if isinstance(m, (int, float)) and m > 0:
                return float(m)
        # Then walk the priority order
        for key in _FALLBACK_ORDER:
            if key == variant:
                continue  # already tried
            v = prices.get(key)
            if not isinstance(v, dict):
                continue
            m = v.get("market") or v.get("mid")
            if isinstance(m, (int, float)) and m > 0:
                return float(m)
    if fallback_market_price_usd is not None:
        return float(fallback_market_price_usd)
    return None

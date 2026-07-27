"""Graded-slab valuation glue between user CollectionItems and the
eBay-driven `card_price_snapshots` graded medians.

A collector who owns a PSA 10 slab of Charizard doesn't want their
portfolio valued at the raw market ($8) — they want it valued at the
PSA 10 clearing price ($4,800). This module maps a user's stored grade
string ("PSA 10", "BGS 9.5", "CGC 10 Pristine") to the canonical tier
key used in `card_price_snapshots.grade` and bulk-loads the latest
snapshot per (card_id, tier).

Callers pass an item + the graded-price lookup and get back a single
effective price plus a source label so the API can tell the UI whether
the value came from a real graded tile or fell back to raw.
"""

from __future__ import annotations

from typing import Iterable, Literal

from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CardPriceSnapshot
from app.services.grade_classifier import classify_grade
from app.services.variant_pricing import price_for_variant


PriceSource = Literal["graded", "raw"]

# The set of tiers `/cards/{id}/graded-prices` surfaces. Everything
# outside this list has no snapshot pipeline, so mapping it to a
# graded key would just guarantee a DB miss and a wasted round trip.
# Keep in sync with the ui_tiers tuple in api/routes.py.
_TRACKED_TIERS: frozenset[str] = frozenset(
    {
        "psa10", "psa9",
        "cgc10", "cgc9",
        "bgs10", "bgs10bl", "bgs9.5", "bgs9",
        "tag10", "tag9.5", "tag9",
    }
)


def user_grade_to_key(grade: str | None) -> str | None:
    """Map a stored user grade string to the canonical tier key
    (psa10, bgs9.5, cgc10, tag10, bgs10bl, ...).

    Returns None for empty / non-canonical grades AND for grades that
    fall outside the tracked-tier set (PSA 8, CGC 9.5, etc.) since we
    don't have snapshots for them and the caller should fall back to
    raw pricing instead. classify_grade handles free-text spelling
    variants ("PSA 10", "PSA10", "CGC 10 Pristine" → cgc10, "BGS 10
    Black Label" → bgs10bl, "ACE 10" → other).
    """
    if not grade or not grade.strip():
        return None
    key = classify_grade(grade)
    if key in ("raw", "other") or key not in _TRACKED_TIERS:
        return None
    return key


async def resolve_graded_prices(
    db: AsyncSession,
    keys: Iterable[tuple[str, str]],
) -> dict[tuple[str, str], float]:
    """Bulk-load the latest graded snapshot for every (card_id, tier)
    pair in `keys`.

    Returns a dict keyed by (card_id, tier) → USD price. Missing pairs
    are simply absent — the caller is expected to fall back to raw.

    Source-priority ladder inside a same-day tie:
        ebay_sold   → real clearing price
        ebay_asking → active-listing median
        ebay        → legacy Browse API asking
    Then latest snapshot_date wins across days. Same policy as
    `/cards/{id}/graded-prices` so vault valuations match tile prices.
    """
    keyset = {(c, g) for c, g in keys}
    if not keyset:
        return {}

    card_ids = {c for c, _ in keyset}
    tiers = {g for _, g in keyset}

    source_priority = case(
        (CardPriceSnapshot.source == "ebay_sold", 0),
        (CardPriceSnapshot.source == "ebay_asking", 1),
        (CardPriceSnapshot.source == "ebay", 2),
        else_=3,
    )
    stmt = (
        select(
            CardPriceSnapshot.card_id,
            CardPriceSnapshot.grade,
            CardPriceSnapshot.market_price_usd,
        )
        .where(
            CardPriceSnapshot.card_id.in_(card_ids),
            CardPriceSnapshot.grade.in_(tiers),
            CardPriceSnapshot.source.in_(("ebay_sold", "ebay_asking", "ebay")),
            CardPriceSnapshot.market_price_usd.is_not(None),
        )
        .order_by(
            CardPriceSnapshot.card_id,
            CardPriceSnapshot.grade,
            CardPriceSnapshot.snapshot_date.desc(),
            source_priority.asc(),
        )
    )
    rows = (await db.execute(stmt)).all()

    out: dict[tuple[str, str], float] = {}
    for card_id, grade, price in rows:
        k = (card_id, grade)
        if k in out or k not in keyset:
            continue
        out[k] = float(price)
    return out


def effective_price(
    *,
    is_graded: bool,
    grade: str | None,
    card_id: str,
    variant: str | None,
    tcgplayer_prices: dict | None,
    fallback: float | None,
    graded_lookup: dict[tuple[str, str], float],
) -> tuple[float | None, PriceSource]:
    """Return (price, source) for one collection item.

    Prefers the graded tier price when the item is graded AND we have
    a snapshot for its (card, tier) pair. Falls back to variant-aware
    raw pricing otherwise. Source label lets the caller surface a
    "graded market" badge on the row and a "hit Refresh" nudge when a
    graded item lands on raw fallback (no tier data yet).
    """
    if is_graded:
        key = user_grade_to_key(grade)
        if key is not None:
            g = graded_lookup.get((card_id, key))
            if g is not None:
                return g, "graded"
    return price_for_variant(tcgplayer_prices, variant, fallback), "raw"


def collect_graded_keys(items: Iterable) -> set[tuple[str, str]]:
    """Sweep an iterable of CollectionItem-like rows for the (card_id,
    tier_key) pairs worth pre-loading. Skips items that aren't graded
    or whose grade string doesn't resolve to a canonical tier.

    Each element must expose `.is_graded`, `.grade`, and `.card_id`
    (matches CollectionItem plus any tuple/dict wrapper we produce
    inline in the API layer).
    """
    keys: set[tuple[str, str]] = set()
    for it in items:
        if not getattr(it, "is_graded", False):
            continue
        key = user_grade_to_key(getattr(it, "grade", None))
        if key is None:
            continue
        cid = getattr(it, "card_id", None)
        if cid:
            keys.add((cid, key))
    return keys

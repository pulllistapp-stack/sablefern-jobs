"""Per-rarity absolute price bands.

Extracted from the main repo's eBay client so the price syncs can use
them without dragging the whole client — and its query-building and
anti-bot handling — into a public repository. These three tables are
the only things the sync jobs ever imported from it.

The ceilings cap what a RAW card of a given rarity can plausibly be
worth: anything above is almost certainly a graded slab that slipped
past the title filters, so the sync clips it rather than writing an
inflated market price. The floors do the mirror job on the low end,
where a chase card listed at $0.99 is a mistitle or a scam rather than
a real ask.

Keep in step with `app/services/ebay_client.py` in the main repo — if
the numbers there are retuned, mirror the change here.
"""

_RARITY_ABS_CEILING: dict[str, float] = {
    # Chase rarities — applied as MIN against the TCG-relative ceiling
    # even when a TCG reference exists, so PSA-10 slabs that got past
    # title noise still get clipped. Numbers reflect the genuine raw
    # upper bound of the category.
    "Special Illustration Rare": 5000.0,
    "Illustration Rare": 2000.0,
    "Hyper Rare": 5000.0,
    "Rare Rainbow": 5000.0,
    "Mega Hyper Rare": 8000.0,
    # Vintage chase — Pokemon ⭐ Star and Shining cards. Charizard ⭐
    # Dragon Frontiers raw NM peaks ~$7k; Shining Charizard Neo
    # Destiny raw NM ~$5-7k. Headroom for genuine top-end raw without
    # leaving room for $15k+ slabs.
    "Rare Holo Star": 10000.0,
    "Rare Shining": 10000.0,
    # Standard rarities — the SOLE ceiling when no TCG reference
    # exists (typical for vintage sets pokemontcg.io never priced).
    "Common": 100.0,
    "Uncommon": 200.0,
    "Rare": 500.0,
    "Rare Holo": 3000.0,
    "Rare Holo EX": 3000.0,
    "Rare Holo GX": 3000.0,
    "Rare Holo V": 3000.0,
    "Rare Holo VMAX": 3000.0,
    "Rare Holo VSTAR": 3000.0,
    "Rare Holo LV.X": 3000.0,
    "Rare BREAK": 2000.0,
    "Rare Prime": 3000.0,
    "Rare ACE": 3000.0,
    "Rare Shiny": 3000.0,
    "Rare Shiny GX": 3000.0,
    "Rare Ultra": 3000.0,
    "Rare Secret": 3000.0,
    "Rare Prism Star": 3000.0,
    "Promo": 1000.0,
    "Amazing Rare": 2000.0,
    "Radiant Rare": 1500.0,
    "Trainer Gallery Rare Holo": 2000.0,
    "Double Rare": 500.0,
    "Ultra Rare": 3000.0,
}

# Fallback for any rarity absent from the table — keeps unknown-rarity
# cards from passing through unbounded.
_DEFAULT_ABS_CEILING = 2000.0

# Low-end floors, chase rarities only. A Special Illustration Rare
# listed at $0.99 is a mistitled lot or a bait listing, not a real
# ask, so the band refuses to dip below these.
_RARITY_ABS_FLOOR: dict[str, float] = {
    "Special Illustration Rare": 5.0,
    "Illustration Rare": 2.0,
    "Hyper Rare": 5.0,
    "Rare Rainbow": 5.0,
    "Mega Hyper Rare": 10.0,
}

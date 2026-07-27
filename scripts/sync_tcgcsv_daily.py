"""Daily TCGplayer price sync via TCGCSV.

TCGCSV (tcgcsv.com) republishes TCGplayer's daily price snapshots through
a free JSON API. We use it instead of pokemontcg.io for TCGplayer prices
because:
  - Updates daily (UTC 20:00) vs pokemontcg.io's ~weekly cadence
  - No deprecation risk hanging over pokemontcg.io v2
  - Same upstream source (TCGplayer) so values match

This script handles TCGplayer only. Cardmarket prices still come from
the pokemontcg.io sync (sync_tcgplayer_prices.py) â€” TCGCSV doesn't have
Cardmarket data and Cardmarket's own data is fiddly to parse.

For each Pokemon group on TCGCSV:
  1. GET /tcgplayer/3/{groupId}/prices  â†’ list of {productId, subTypeName, ...}
  2. Group rows by productId, transform to our per-variant tcgplayer_prices JSON
  3. Find matching card by tcgplayer_product_id, update card row + insert snapshot

Idempotent â€” ON CONFLICT DO NOTHING on snapshots, plain UPDATE on cards.

Usage:
    python -m scripts.sync_tcgcsv_daily              # daily full sync
    python -m scripts.sync_tcgcsv_daily --dry-run    # report only
    python -m scripts.sync_tcgcsv_daily --date 2026-06-15  # use specific date

Attribution: data from https://tcgcsv.com (CptSpaceToaster).
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

# Mute SQLAlchemy echo on dev â€” settings.debug=True drowns out our progress log.
os.environ.setdefault("DEBUG", "false")
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s %(levelname)s %(message)s",
)

import httpx
from sqlalchemy import or_, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import SessionLocal, engine, init_db  # noqa: E402
from app.models import Card, CardPriceSnapshot, Set  # noqa: E402
from app.services.price_ceilings import (  # noqa: E402
    _DEFAULT_ABS_CEILING,
    _RARITY_ABS_CEILING,
)

engine.echo = False
logging.getLogger("sqlalchemy").setLevel(logging.WARNING)

log = logging.getLogger("sync_tcgcsv_daily")
log.setLevel(logging.INFO)


TCGCSV_BASE = "https://tcgcsv.com/tcgplayer"
POKEMON_CATEGORY = "3"       # PokÃ©mon (English)
POKEMON_CATEGORY_JP = "85"   # Pokemon Japan â€” added 2026-07-16 so JP
                              # cards with tcgplayer_product_id (S8a
                              # family, JPP-VM, plus anything the
                              # backfill_jp_card_tcgcsv_ids pass adds)
                              # refresh on the same daily cadence.
POKEMON_CATEGORIES = (POKEMON_CATEGORY, POKEMON_CATEGORY_JP)
USER_AGENT = "tcg-price-sync/1.0"
SOURCE_TCGPLAYER = "tcgplayer"

# TCGCSV subTypeName -> our variant column / tcgplayer_prices JSON key
VARIANT_MAP = {
    "Normal": "normal",
    "Foil": "holofoil",
    "Holofoil": "holofoil",
    "Reverse Holofoil": "reverseHolofoil",
    "1st Edition": "1stEdition",
    "1st Edition Holofoil": "1stEditionHolofoil",
    "Unlimited": "unlimited",
    "Unlimited Holofoil": "unlimitedHolofoil",
}

# Same priority used by the original pokemontcg.io sync, replicated here so the
# denormalized cards.market_price_usd field stays consistent across sources.
VARIANT_PRIORITY = (
    "normal",
    "holofoil",
    "reverseHolofoil",
    "1stEditionHolofoil",
    "1stEdition",
    "unlimitedHolofoil",
    "unlimited",
)


def _f(value) -> float | None:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f <= 0:
        return None
    return f


def _low_high_from_prices(
    prices: dict, rarity: str | None, cap_fn
) -> tuple[float | None, float | None]:
    """Per-card flat low/high derived from the per-variant prices blob.

    low  = cheapest 'low' across all variants â€” no cap (low prices are
           rarely manipulated)
    high = most expensive 'high' across all variants, capped by the
           rarity ceiling (drops outlier $10k-asks on a $5 common)
    """
    lows: list[float] = []
    highs: list[float] = []
    cap = cap_fn(rarity)
    for variant in prices.values():
        if not isinstance(variant, dict):
            continue
        lo = variant.get("low")
        hi = variant.get("high")
        if isinstance(lo, (int, float)) and lo > 0:
            lows.append(float(lo))
        if isinstance(hi, (int, float)) and hi > 0 and float(hi) <= cap:
            highs.append(float(hi))
    return (min(lows) if lows else None, max(highs) if highs else None)


def _market_from_prices(prices: dict) -> float | None:
    """Pick the base variant's market price following the same priority
    as the pokemontcg.io sync â€” keeps cards.market_price_usd consistent
    no matter which source last touched the row."""
    for key in VARIANT_PRIORITY:
        variant = prices.get(key)
        if not isinstance(variant, dict):
            continue
        m = variant.get("market") or variant.get("mid")
        if isinstance(m, (int, float)) and m > 0:
            return float(m)
    for variant in prices.values():
        if not isinstance(variant, dict):
            continue
        m = variant.get("market") or variant.get("mid")
        if isinstance(m, (int, float)) and m > 0:
            return float(m)
    return None


def _mid_from_prices(prices: dict) -> float | None:
    """Pick the base variant's TCGplayer 'mid' (midpoint listing price),
    never falling back to market. The set-value headline sums these so
    the total reads as a literal "what's this set listed at" number,
    untouched by graded slab outliers (which inflate `high`) and free
    of the sales-driven jitter on `market`."""
    for key in VARIANT_PRIORITY:
        variant = prices.get(key)
        if not isinstance(variant, dict):
            continue
        m = variant.get("mid")
        if isinstance(m, (int, float)) and m > 0:
            return float(m)
    for variant in prices.values():
        if not isinstance(variant, dict):
            continue
        m = variant.get("mid")
        if isinstance(m, (int, float)) and m > 0:
            return float(m)
    return None


def _group_rows_by_product(rows: list[dict]) -> dict[int, dict]:
    """Collapse TCGCSV's flat (product, subType) rows into our nested
    per-variant tcgplayer_prices format:
        {productId: {"normal": {"low": .., "mid": .., "high": .., "market": ..,
                                 "directLow": ..}, "holofoil": {...}, ...}}
    """
    out: dict[int, dict] = {}
    for entry in rows:
        product_id = entry.get("productId")
        if product_id is None:
            continue
        variant = VARIANT_MAP.get(entry.get("subTypeName"))
        if not variant:
            continue
        market = _f(entry.get("marketPrice"))
        mid = _f(entry.get("midPrice"))
        if market is None and mid is None:
            continue
        bucket = out.setdefault(product_id, {})
        bucket[variant] = {
            "low": _f(entry.get("lowPrice")),
            "mid": mid,
            "high": _f(entry.get("highPrice")),
            "market": market,
            "directLow": _f(entry.get("directLowPrice")),
        }
    return out


def _conflict_insert(dialect_name: str):
    if dialect_name == "postgresql":
        return pg_insert(CardPriceSnapshot)
    return sqlite_insert(CardPriceSnapshot)


def _rarity_ceiling(rarity: str | None) -> float:
    """Per-rarity absolute cap on what counts as a credible TCGplayer
    market price. Same table the eBay snapshot uses â€” single source of
    truth keeps the two sources consistent on chase / vintage caps."""
    if rarity and rarity in _RARITY_ABS_CEILING:
        return _RARITY_ABS_CEILING[rarity]
    return _DEFAULT_ABS_CEILING


def _snapshot_rows(
    card_id: str,
    prices: dict,
    snapshot_date: str,
    rarity: str | None = None,
) -> list[dict]:
    """One snapshot row per variant â€” keeps trending / chart logic happy.

    Rejects per-variant market prices that exceed the rarity ceiling.
    TCGCSV's `market` field occasionally reflects a single seller typo
    ($46.63 â†’ $4663) or graded-slab listing miscategorised as raw; the
    cap drops those data points so the chart doesn't spike for ~10 days
    waiting for upstream correction. If every variant fails the cap,
    the card gets no snapshot row for the day (better than a poisoned
    one â€” chart stays flat, future syncs recover automatically).
    """
    cap = _rarity_ceiling(rarity)
    rows = []
    for variant, payload in prices.items():
        market = payload.get("market") or payload.get("mid")
        if market is None:
            continue
        if float(market) > cap:
            log.warning(
                "drop snapshot %s variant=%s market=$%.2f > cap $%.2f (rarity=%s)",
                card_id, variant, float(market), cap, rarity or "?",
            )
            continue
        rows.append({
            "card_id": card_id,
            "source": SOURCE_TCGPLAYER,
            "variant": variant,
            "market_price_usd": float(market),
            "low_price_usd": payload.get("low"),
            "mid_price_usd": payload.get("mid"),
            "high_price_usd": payload.get("high"),
            "sales_count": None,
            "snapshot_at": datetime.utcnow(),
            "snapshot_date": snapshot_date,
        })
    return rows


async def _fetch_json(client: httpx.AsyncClient, url: str) -> dict:
    r = await client.get(url, timeout=60.0)
    r.raise_for_status()
    return r.json()


async def _list_pokemon_groups(
    client: httpx.AsyncClient, category: str = POKEMON_CATEGORY
) -> list[dict]:
    data = await _fetch_json(client, f"{TCGCSV_BASE}/{category}/groups")
    return data.get("results", [])


async def _group_prices(
    client: httpx.AsyncClient, group_id: int, category: str = POKEMON_CATEGORY
) -> list[dict]:
    data = await _fetch_json(
        client, f"{TCGCSV_BASE}/{category}/{group_id}/prices"
    )
    return data.get("results", [])


DAILY_PRICE_FLOOR = 1.0
RECENT_RELEASE_DAYS = 30


async def _load_product_map(
    db: AsyncSession,
    *,
    tier: str = "all",
) -> dict[int, str]:
    """Load product_id â†’ card_id map, filtered by sync tier.

    Tier carves the catalog into two non-overlapping buckets so the
    daily cron only does meaningful work and the long-tail bulk only
    refreshes once a month â€” cuts Neon egress without losing freshness
    where collectors actually care.

      tier='daily'   â€” cards we want fresh every day:
                       priced â‰¥ $DAILY_PRICE_FLOOR, OR unpriced (so a
                       new card gets its first TCGplayer price the next
                       morning), OR in a set released â‰¤30 days ago
                       (launch-week chase often starts <$1 and surges
                       within days â€” we'd miss it on a monthly cadence).
      tier='monthly' â€” bulk long-tail: priced <$1 AND set released
                       >30 days ago. Refreshed once a month.
      tier='all'     â€” no filter; manual ad-hoc runs only.
    """
    stmt = select(Card.id, Card.tcgplayer_product_id).where(
        Card.tcgplayer_product_id.isnot(None)
    )

    if tier in ("daily", "monthly"):
        cutoff = date.today() - timedelta(days=RECENT_RELEASE_DAYS)
        stmt = stmt.join(Set, Card.set_id == Set.id)
        if tier == "daily":
            stmt = stmt.where(
                or_(
                    Card.market_price_usd >= DAILY_PRICE_FLOOR,
                    Card.market_price_usd.is_(None),
                    Set.release_date >= cutoff,
                )
            )
        else:  # monthly
            stmt = stmt.where(
                Card.market_price_usd < DAILY_PRICE_FLOOR,
                Card.market_price_usd.is_not(None),
                or_(Set.release_date.is_(None), Set.release_date < cutoff),
            )

    rows = (await db.execute(stmt)).all()
    return {pid: cid for cid, pid in rows if pid is not None}


async def _flush_snapshots(db: AsyncSession, batch: list[dict]) -> int:
    if not batch:
        return 0
    dialect_name = db.bind.dialect.name
    stmt = _conflict_insert(dialect_name).values(batch).on_conflict_do_nothing(
        index_elements=["card_id", "source", "variant", "grade", "snapshot_date"]
    )
    result = await db.execute(stmt)
    await db.commit()
    return result.rowcount or 0


async def sync(
    snapshot_date: str,
    dry_run: bool,
    group_limit: int | None,
    tier: str = "daily",
    only_groups: set[int] | None = None,
) -> None:
    await init_db()
    async with SessionLocal() as db:
        product_to_card = await _load_product_map(db, tier=tier)
    log.info(
        f"loaded {len(product_to_card)} tcgplayer_product_id mappings "
        f"(tier={tier})"
    )

    stats = {
        "groups_seen": 0,
        "products_seen": 0,
        "cards_refreshed": 0,
        "cards_unchanged": 0,
        "cards_missing": 0,
        "snapshots_inserted": 0,
        "group_errors": 0,
    }

    async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}) as client:
        # Iterate the EN PokÃ©mon category (3) AND the JP Pokemon Japan
        # category (85). Group IDs don't collide between categories on
        # TCGCSV and product_to_card is keyed on the global product_id
        # only, so a JP price refresh naturally matches JP cards
        # (whose tcgplayer_product_id came from category 85) without
        # touching EN rows.
        groups: list[tuple[str, dict]] = []
        for category in POKEMON_CATEGORIES:
            cat_groups = await _list_pokemon_groups(client, category=category)
            for g in cat_groups:
                groups.append((category, g))
        if only_groups:
            groups = [(c, g) for c, g in groups if g.get("groupId") in only_groups]
        if group_limit:
            groups = groups[:group_limit]
        log.info(f"{len(groups)} pokemon groups to sync (EN + JP)")

        for idx, (category, group) in enumerate(groups, 1):
            group_id = group.get("groupId")
            group_name = group.get("name") or str(group_id)
            stats["groups_seen"] += 1
            try:
                price_rows = await _group_prices(
                    client, group_id, category=category
                )
            except Exception as exc:
                log.warning(f"[{idx}/{len(groups)}] {group_name}: fetch failed ({exc})")
                stats["group_errors"] += 1
                continue

            by_product = _group_rows_by_product(price_rows)
            stats["products_seen"] += len(by_product)
            if not by_product:
                continue

            snapshot_batch: list[dict] = []
            async with SessionLocal() as db:
                # Batch-load every card this group touches in ONE round-trip
                # instead of N `db.get()` calls. 20k+ cards Ã— ~25 groups was
                # 500k+ SELECTs per day â€” the biggest Neon CU sink on this
                # cron.
                wanted_ids = [
                    cid for pid in by_product
                    if (cid := product_to_card.get(pid))
                ]
                card_map: dict[str, Card] = {}
                if wanted_ids:
                    result = await db.execute(
                        select(Card).where(Card.id.in_(wanted_ids))
                    )
                    card_map = {c.id: c for c in result.scalars()}

                # Batch-fetch the most recent RAW eBay median per card so
                # we can persist the consensus (tcg + ebay) / 2 as the
                # card's headline market. Without this the nightly sync
                # would overwrite user-triggered Refresh consensus values
                # with TCG-only every 24h, and users would see set-page
                # prices drift back to the raw TCG number that mismatches
                # the card-detail hero. Single query per group beats
                # per-card round-trips.
                ebay_median_map: dict[str, float] = {}
                if wanted_ids:
                    # DISTINCT ON keeps only the freshest snapshot per
                    # card. Uses the same index the price chart uses.
                    dialect = db.bind.dialect.name
                    if dialect == "postgresql":
                        ebay_stmt = text(
                            "SELECT DISTINCT ON (card_id) card_id, "
                            "market_price_usd FROM card_price_snapshots "
                            "WHERE card_id = ANY(:ids) AND source = 'ebay' "
                            "AND grade = 'raw' AND market_price_usd IS NOT NULL "
                            "ORDER BY card_id, snapshot_at DESC"
                        )
                        r = await db.execute(ebay_stmt, {"ids": wanted_ids})
                        ebay_median_map = {row[0]: float(row[1]) for row in r}
                    else:
                        # SQLite fallback for local dev â€” subquery per id.
                        r = await db.execute(
                            select(
                                CardPriceSnapshot.card_id,
                                CardPriceSnapshot.market_price_usd,
                            )
                            .where(
                                CardPriceSnapshot.card_id.in_(wanted_ids),
                                CardPriceSnapshot.source == "ebay",
                                CardPriceSnapshot.grade == "raw",
                                CardPriceSnapshot.market_price_usd.is_not(None),
                            )
                            .order_by(CardPriceSnapshot.snapshot_at.desc())
                        )
                        for cid, price in r:
                            if cid not in ebay_median_map:
                                ebay_median_map[cid] = float(price)

                for product_id, prices in by_product.items():
                    card_id = product_to_card.get(product_id)
                    if not card_id:
                        stats["cards_missing"] += 1
                        continue
                    existing = card_map.get(card_id)
                    if existing is None:
                        stats["cards_missing"] += 1
                        continue

                    market = _market_from_prices(prices)
                    cap = _rarity_ceiling(existing.rarity)
                    if market is not None and market > cap:
                        # The single denormalised display price would surface
                        # the same typo / mis-mapped slab the snapshot guard
                        # catches; refuse to overwrite an existing sane value
                        # with a spike. Per-variant tcgplayer_prices JSON is
                        # still refreshed so the variant breakdown stays
                        # up-to-date â€” only the catalog headline number is
                        # gated.
                        log.warning(
                            "skip market_price_usd for %s: $%.2f > cap $%.2f (rarity=%s)",
                            card_id, market, cap, existing.rarity or "?",
                        )
                        market = None
                    # Blend with latest eBay median so the persisted
                    # Card.market_price_usd matches what the card-detail
                    # hero shows (which averages TCG + eBay client-side).
                    # Without the blend, /sets/[id] tiles keep drifting
                    # back to raw TCG on every nightly sync.
                    new_market: float | None
                    if market is not None:
                        ebay_med = ebay_median_map.get(card_id)
                        if ebay_med is not None:
                            new_market = (market + ebay_med) / 2
                        else:
                            new_market = market
                    else:
                        new_market = None
                    lo, hi = _low_high_from_prices(
                        prices, existing.rarity, _rarity_ceiling
                    )
                    new_mid = _mid_from_prices(prices)

                    # Skip the UPDATE entirely when nothing moved â€” a
                    # bulk floor of the catalog (commons at $0.05, older
                    # cards untouched) sits still for weeks. Prices are
                    # compared with 3-decimal rounding so 0.001 float
                    # noise in the JSON doesn't force a rewrite.
                    def _r(v: float | None) -> float | None:
                        return round(v, 3) if v is not None else None

                    if not dry_run:
                        changed = (
                            existing.tcgplayer_prices != prices
                            or (new_market is not None
                                and _r(existing.market_price_usd) != _r(new_market))
                            or _r(existing.low_price_usd) != _r(lo)
                            or _r(existing.high_price_usd) != _r(hi)
                            or _r(existing.mid_price_usd) != _r(new_mid)
                        )
                        if changed:
                            existing.tcgplayer_prices = prices
                            if new_market is not None:
                                existing.market_price_usd = new_market
                            # low/high refresh regardless of market cap â€”
                            # they feed the set price-range banner, which
                            # is interesting even when the headline market
                            # field is gated.
                            existing.low_price_usd = lo
                            existing.high_price_usd = hi
                            existing.mid_price_usd = new_mid
                            stats["cards_refreshed"] += 1
                        else:
                            stats["cards_unchanged"] += 1
                    else:
                        stats["cards_refreshed"] += 1

                    snapshot_batch.extend(
                        _snapshot_rows(card_id, prices, snapshot_date, existing.rarity)
                    )

                if not dry_run:
                    await db.commit()
                    written = await _flush_snapshots(db, snapshot_batch)
                    stats["snapshots_inserted"] += written

            log.info(
                f"[{idx}/{len(groups)}] {group_name}: {len(by_product)} products, "
                f"{stats['snapshots_inserted']} total snapshots"
            )
            # Be polite â€” TCGCSV asks for 250ms between requests
            await asyncio.sleep(0.25)

    log.info(f"=== sync summary ({snapshot_date}) ===")
    for k, v in stats.items():
        log.info(f"  {k}: {v}")
    log.info(f"  dry_run: {dry_run}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--date", dest="snapshot_date",
        help="YYYY-MM-DD (defaults to today UTC).",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Fetch + parse, but don't write to the DB.",
    )
    parser.add_argument(
        "--limit-groups", type=int, default=None,
        help="Process only the first N groups (smoke testing).",
    )
    parser.add_argument(
        "--only-groups",
        default=None,
        help=(
            "Comma-separated TCGCSV group ids to sync, e.g. "
            "'24451,22872,2545'. Used for targeted backfills after a "
            "promo seed run â€” keeps wall-clock to minutes instead of "
            "the full ~600-group sweep."
        ),
    )
    parser.add_argument(
        "--tier",
        choices=("daily", "monthly", "all"),
        default="daily",
        help=(
            "Which slice of cards to sync. 'daily' = priced â‰¥$1 OR "
            "unpriced OR set released â‰¤30d ago (default, daily cron). "
            "'monthly' = bulk long-tail (priced <$1 AND set released "
            ">30d ago) for the monthly cron. 'all' = no filter."
        ),
    )
    args = parser.parse_args()
    snapshot_date = args.snapshot_date or date.today().isoformat()
    only_set: set[int] | None = None
    if args.only_groups:
        only_set = {int(g) for g in args.only_groups.split(",") if g.strip()}
    asyncio.run(
        sync(
            snapshot_date,
            args.dry_run,
            args.limit_groups,
            tier=args.tier,
            only_groups=only_set,
        )
    )


if __name__ == "__main__":
    main()

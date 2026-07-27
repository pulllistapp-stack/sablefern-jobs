"""Daily sealed-product price sync via TCGCSV.

Parallel to `sync_tcgcsv_daily.py` (which handles singles). Walks every
TCGCSV group that has products in our DB, pulls the current price feed,
and:
  * Upserts today's row into `product_price_snapshots` per product.
  * Refreshes the denormalised `products.market_price_usd / low / high`
    fields so listing pages stay fresh without an extra join.

Idempotent — ON CONFLICT DO NOTHING on snapshots, plain UPDATE on
products (skipped when the price is unchanged, mirroring the card
sync's optimisation).

Usage:
    python -m scripts.sync_products_daily             # daily production run
    python -m scripts.sync_products_daily --dry-run   # count only
    python -m scripts.sync_products_daily --date 2026-07-13
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import SessionLocal, init_db
from app.models import Product, ProductPriceSnapshot, Set


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
)
log = logging.getLogger("sync_products_daily")


TCGCSV_BASE = "https://tcgcsv.com/tcgplayer"
TCGCSV_CAT_EN = 3   # Pokemon
TCGCSV_CAT_JP = 85  # Pokemon Japan
UA = "tcg-product-price-sync/1.0"
SOURCE = "tcgplayer"


async def _fetch_prices(
    client: httpx.AsyncClient, group_id: int, category_id: int
) -> list[dict]:
    r = await client.get(
        f"{TCGCSV_BASE}/{category_id}/{group_id}/prices", timeout=45
    )
    r.raise_for_status()
    payload = r.json()
    if isinstance(payload, dict):
        return payload.get("results") or []
    return payload or []


def _pick(prices: list[dict]) -> tuple[float | None, float | None, float | None, float | None]:
    """Return (market, low, mid, high) from the first row that has any
    price fields set. TCGCSV can split subTypes (Normal / Foil etc.) but
    sealed products almost always report a single row per productId."""
    if not prices:
        return None, None, None, None
    for p in prices:
        market = p.get("marketPrice")
        low = p.get("lowPrice")
        mid = p.get("midPrice")
        high = p.get("highPrice")
        if any(v is not None for v in (market, low, mid, high)):
            def _f(v: object) -> float | None:
                return float(v) if v is not None else None
            return _f(market), _f(low), _f(mid), _f(high)
    return None, None, None, None


def _conflict_insert(dialect_name: str):
    if dialect_name == "postgresql":
        return pg_insert(ProductPriceSnapshot)
    return sqlite_insert(ProductPriceSnapshot)


async def _flush(db: AsyncSession, batch: list[dict]) -> int:
    if not batch:
        return 0
    dialect = db.bind.dialect.name
    stmt = _conflict_insert(dialect).values(batch).on_conflict_do_nothing(
        index_elements=["product_id", "source", "snapshot_date"]
    )
    result = await db.execute(stmt)
    await db.commit()
    return result.rowcount or 0


async def run(snapshot_date: str, dry_run: bool) -> None:
    await init_db()

    async with SessionLocal() as db:
        # Group our products by tcgplayer_group_id so one TCGCSV fetch
        # covers many products. Joined against sets so we know which
        # TCGCSV category (3 = Pokemon EN, 85 = Pokemon Japan) to hit
        # — group IDs live in per-category namespaces so a JP group
        # like 24721 (m6a) 404s under /3/.
        rows = (
            await db.execute(
                select(
                    Product.id,
                    Product.tcgplayer_product_id,
                    Product.tcgplayer_group_id,
                    Product.market_price_usd,
                    Product.low_price_usd,
                    Product.high_price_usd,
                    Set.language,
                )
                .join(Set, Product.set_id == Set.id, isouter=True)
                .where(Product.tcgplayer_product_id.is_not(None))
                .where(Product.tcgplayer_group_id.is_not(None))
            )
        ).all()

    # Route each product to the right TCGCSV category. Products with a
    # null/EN-linked set stay on category 3; JP-linked products flip
    # to category 85. Fold (category, group) → product list so one
    # fetch still covers many products.
    groups: dict[tuple[int, int], list[tuple]] = defaultdict(list)
    for pid, tpid, gid, market, low, high, lang in rows:
        cat = TCGCSV_CAT_JP if lang == "ja" else TCGCSV_CAT_EN
        groups[(cat, int(gid))].append((pid, int(tpid), market, low, high))
    log.info(
        f"tracking {len(rows)} products across {len(groups)} TCGCSV groups"
    )

    stats = {
        "groups": 0,
        "products_matched": 0,
        "snapshots_inserted": 0,
        "products_refreshed": 0,
        "products_unchanged": 0,
        "fetch_errors": 0,
    }

    async with httpx.AsyncClient(headers={"User-Agent": UA}) as client:
        for (category_id, group_id), product_list in groups.items():
            stats["groups"] += 1
            try:
                price_rows = await _fetch_prices(
                    client, group_id, category_id
                )
            except Exception as exc:
                stats["fetch_errors"] += 1
                log.warning(
                    f"cat={category_id} group={group_id} fetch failed: {exc}"
                )
                continue

            # Fold price rows by productId; sealed items are single-
            # subType so the first non-empty entry wins.
            by_product: dict[int, list[dict]] = defaultdict(list)
            for p in price_rows:
                pid = p.get("productId")
                if pid is None:
                    continue
                by_product[int(pid)].append(p)

            batch: list[dict] = []
            async with SessionLocal() as db2:
                # Bulk-load Products for this group so we can UPDATE
                # denormalised prices in Python without one round-trip
                # per row.
                to_load = [pid for pid, tpid, *_ in product_list]
                loaded = (
                    await db2.execute(
                        select(Product).where(Product.id.in_(to_load))
                    )
                ).scalars().all()
                by_id: dict[str, Product] = {p.id: p for p in loaded}

                for our_id, tpid, prev_market, prev_low, prev_high in product_list:
                    prices = by_product.get(tpid)
                    if not prices:
                        continue
                    stats["products_matched"] += 1
                    market, low, mid, high = _pick(prices)
                    now = datetime.utcnow()

                    batch.append(
                        {
                            "product_id": our_id,
                            "source": SOURCE,
                            "market_price_usd": market,
                            "low_price_usd": low,
                            "mid_price_usd": mid,
                            "high_price_usd": high,
                            "snapshot_at": now,
                            "snapshot_date": snapshot_date,
                        }
                    )

                    row = by_id.get(our_id)
                    if row is None or dry_run:
                        continue

                    def _r(v: float | None) -> float | None:
                        return round(v, 3) if v is not None else None

                    changed = (
                        _r(row.market_price_usd) != _r(market)
                        or _r(row.low_price_usd) != _r(low)
                        or _r(row.high_price_usd) != _r(high)
                    )
                    if changed:
                        if market is not None:
                            row.market_price_usd = market
                        if low is not None:
                            row.low_price_usd = low
                        if high is not None:
                            row.high_price_usd = high
                        stats["products_refreshed"] += 1
                    else:
                        stats["products_unchanged"] += 1

                if not dry_run:
                    await db2.commit()
                    written = await _flush(db2, batch)
                    stats["snapshots_inserted"] += written

    log.info(f"=== summary ({snapshot_date}) ===")
    for k, v in stats.items():
        log.info(f"  {k}: {v}")
    log.info(f"  dry_run: {dry_run}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--date",
        dest="snapshot_date",
        default=None,
        help="YYYY-MM-DD (defaults to today UTC)",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    snapshot_date = args.snapshot_date or date.today().isoformat()
    asyncio.run(run(snapshot_date, args.dry_run))


if __name__ == "__main__":
    main()

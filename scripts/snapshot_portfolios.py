"""Daily portfolio valuation snapshot.

For every user with at least one card in their collection, write a single
row to `portfolio_snapshots` capturing today's total estimated value,
unique card count, total qty, and number of distinct sets touched.

Runs daily AFTER the eBay + TCGplayer crons so Card.market_price_usd is
fresh. Idempotent — re-running on the same day is a no-op.

Usage:
    python -m scripts.snapshot_portfolios                  # today
    python -m scripts.snapshot_portfolios --date 2026-06-13 # backfill
    python -m scripts.snapshot_portfolios --dry-run        # don't write
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import case, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import SessionLocal, init_db
from app.models import Card, CollectionItem, PortfolioSnapshot, User
from app.services.graded_pricing import (
    effective_price,
    resolve_graded_prices,
    user_grade_to_key,
)

log = logging.getLogger("snapshot_portfolios")


def _conflict_insert(dialect_name: str):
    if dialect_name == "postgresql":
        return pg_insert(PortfolioSnapshot)
    return sqlite_insert(PortfolioSnapshot)


async def compute_user_value(
    db: AsyncSession, user_id: str
) -> tuple[float, int, int, int, float, int]:
    """Return (value, unique_cards, total_qty, sets_touched,
    graded_value, graded_cards).

    Graded rows swap in PSA/BGS/CGC/TAG tier medians from
    card_price_snapshots when a snapshot exists, so the daily growth
    chart tracks the same portfolio total the Vault header shows. Raw
    fallback preserves value when tier data isn't available yet.

    The trailing two fields isolate the graded slice — same pricing,
    but summed only over is_graded rows — so /portfolio/slabs can
    chart slab value independently of raw singles.
    """
    rows = (
        await db.execute(
            select(
                CollectionItem.qty,
                CollectionItem.variant,
                CollectionItem.card_id,
                CollectionItem.is_graded,
                CollectionItem.grade,
                Card.set_id,
                Card.tcgplayer_prices,
                Card.market_price_usd,
            )
            .join(Card, CollectionItem.card_id == Card.id)
            .where(CollectionItem.user_id == user_id)
        )
    ).all()

    graded_keys: set[tuple[str, str]] = set()
    for _q, _v, cid, is_g, g, _s, _p, _f in rows:
        if is_g:
            key = user_grade_to_key(g)
            if key:
                graded_keys.add((cid, key))
    graded_lookup = await resolve_graded_prices(db, graded_keys)

    unique_cards: set[str] = set()
    sets_touched: set[str] = set()
    total_qty = 0
    value = 0.0
    graded_value = 0.0
    graded_cards = 0
    for qty, variant, cid, is_graded, grade, set_id, prices, fallback in rows:
        unique_cards.add(cid)
        sets_touched.add(set_id)
        total_qty += qty or 0
        p, _src = effective_price(
            is_graded=is_graded,
            grade=grade,
            card_id=cid,
            variant=variant,
            tcgplayer_prices=prices,
            fallback=fallback,
            graded_lookup=graded_lookup,
        )
        if p is not None:
            line = (qty or 0) * p
            value += line
            if is_graded:
                graded_value += line
        if is_graded:
            graded_cards += qty or 0

    return (
        round(value, 2),
        len(unique_cards),
        total_qty,
        len(sets_touched),
        round(graded_value, 2),
        graded_cards,
    )


async def run(snapshot_date: str, dry_run: bool) -> None:
    await init_db()

    async with SessionLocal() as db:
        # Only users that have at least one CollectionItem are worth snapshotting.
        user_ids = (
            await db.execute(
                select(CollectionItem.user_id).distinct()
            )
        ).scalars().all()

    if not user_ids:
        log.warning("No users with collections — nothing to snapshot.")
        return

    log.info(
        "Snapshotting portfolios for %d user(s) (%s)…",
        len(user_ids),
        snapshot_date,
    )

    rows: list[dict] = []
    async with SessionLocal() as db:
        for uid in user_ids:
            (
                value,
                unique_cards,
                total_qty,
                sets_touched,
                graded_value,
                graded_cards,
            ) = await compute_user_value(db, uid)
            rows.append(
                {
                    "user_id": uid,
                    "snapshot_date": snapshot_date,
                    "estimated_value_usd": value,
                    "unique_cards": unique_cards,
                    "total_qty": total_qty,
                    "sets_touched": sets_touched,
                    "graded_value_usd": graded_value,
                    "graded_cards": graded_cards,
                    "snapshot_at": datetime.utcnow(),
                }
            )
            log.info(
                "  %s: $%.2f · %d unique · %d total · %d sets "
                "· graded $%.2f (%d)",
                uid[:8],
                value,
                unique_cards,
                total_qty,
                sets_touched,
                graded_value,
                graded_cards,
            )

        if dry_run:
            log.info("Dry run — %d rows would be written.", len(rows))
            return

        dialect_name = db.bind.dialect.name
        stmt = _conflict_insert(dialect_name).values(rows)
        stmt = stmt.on_conflict_do_nothing(
            index_elements=["user_id", "snapshot_date"]
        )
        result = await db.execute(stmt)
        await db.commit()
        log.info("Wrote %d portfolio snapshots.", result.rowcount or 0)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--date",
        dest="snapshot_date",
        help="YYYY-MM-DD (defaults to today UTC).",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Compute but don't write."
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Debug logs."
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    snapshot_date = args.snapshot_date or date.today().isoformat()
    asyncio.run(run(snapshot_date, args.dry_run))


if __name__ == "__main__":
    main()

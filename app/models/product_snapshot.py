"""Daily price snapshots for sealed products.

Mirrors `CardPriceSnapshot` but keyed on `products.id`. Sealed items
don't have variants or grades so the composite key collapses to
(product_id, source, snapshot_date). Populated by
`sync_products_daily.py` reading TCGCSV's daily product price feed.
"""

from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ProductPriceSnapshot(Base):
    """One row per (product, source, day). The card-side snapshot table
    keeps variant + grade tiers; sealed items are single-variant so
    those columns aren't repeated here."""

    __tablename__ = "product_price_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "product_id", "source", "snapshot_date",
            name="uq_product_source_day",
        ),
        Index("ix_product_snapshot_prod_date", "product_id", "snapshot_date"),
        Index("ix_product_snapshot_date", "snapshot_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    product_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("products.id", ondelete="CASCADE"), index=True
    )
    source: Mapped[str] = mapped_column(String(32))
    """'tcgplayer' for the TCGCSV daily feed. Future: 'ebay' for the
    sold sealed listings once we wire an insights-based scraper."""

    market_price_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    low_price_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    mid_price_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    high_price_usd: Mapped[float | None] = mapped_column(Float, nullable=True)

    snapshot_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), nullable=False
    )
    snapshot_date: Mapped[str] = mapped_column(String(10), nullable=False)
    """YYYY-MM-DD — used for unique-per-day constraint."""

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


class CardPriceSnapshot(Base):
    """One row per (card, source, variant, day).

    A snapshot captures the price state at a point in time so we can build
    a 7d / 30d / 90d history. Multiple sources can coexist for the same card —
    pokemontcg.io (TCGplayer derived), eBay (sold listings), Cardmarket, etc.
    """

    __tablename__ = "card_price_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "card_id",
            "source",
            "variant",
            "grade",
            "snapshot_date",
            name="uq_card_source_variant_grade_day",
        ),
        Index("ix_snapshot_card_date", "card_id", "snapshot_date"),
        Index("ix_snapshot_date", "snapshot_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    card_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("cards.id", ondelete="CASCADE"), index=True
    )

    source: Mapped[str] = mapped_column(String(32))
    """`pokemontcg.io` / `tcgplayer` / `ebay` / `cardmarket` / `kream` etc."""

    variant: Mapped[str] = mapped_column(String(64))
    """`normal` / `holofoil` / `reverseHolofoil` / `psa10` / `ungraded` etc."""

    grade: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="raw", default="raw"
    )
    """Grade tier for the price row. Values follow a canonical vocabulary:
    'raw' (ungraded) / 'psa10' / 'psa9' / 'psa8' / 'cgc10' / 'cgc9.5' /
    'cgc9' / 'bgs10' / 'bgs9.5' / 'bgs9' / 'other'. Sources that don't
    distinguish graded prices (TCGplayer, Cardmarket) always write 'raw';
    eBay pipes each listing through `services.grade_classifier` so the
    same (card, source, variant, snapshot_date) can carry separate
    median rows per grade tier."""

    market_price_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    low_price_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    mid_price_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    high_price_usd: Mapped[float | None] = mapped_column(Float, nullable=True)

    sales_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    """30d sold count — eBay etc. NULL when source doesn't track this."""

    snapshot_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), nullable=False
    )
    snapshot_date: Mapped[str] = mapped_column(
        String(10), nullable=False
    )
    """YYYY-MM-DD — used for unique-per-day constraint."""

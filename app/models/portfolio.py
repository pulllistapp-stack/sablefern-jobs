from datetime import datetime

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PortfolioSnapshot(Base):
    """Daily roll-up of a user's collection valuation.

    Written once per day per user by the snapshot cron. Drives the
    /portfolio Growth chart and any future "your vault gained X this month"
    feature. Idempotent — re-running on the same date is a no-op.
    """

    __tablename__ = "portfolio_snapshots"
    __table_args__ = (
        UniqueConstraint("user_id", "snapshot_date", name="uq_portfolio_user_date"),
        Index("ix_portfolio_user_date", "user_id", "snapshot_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    snapshot_date: Mapped[str] = mapped_column(String(10))  # YYYY-MM-DD

    estimated_value_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    unique_cards: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_qty: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sets_touched: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Graded-only slice of the same day's valuation — the subset of
    # estimated_value_usd contributed by is_graded rows, priced at
    # their tier median (or raw fallback). Drives the slab-value
    # chart on /portfolio/slabs, which needs to answer "how is my
    # SLAB portfolio moving" independently of raw singles.
    #
    # Nullable because rows written before this column existed can't
    # be reconstructed for certain; the backfill script fills what it
    # can from historical card_price_snapshots and leaves the rest
    # NULL so the chart can skip those days instead of drawing a
    # misleading $0.
    graded_value_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    graded_cards: Mapped[int | None] = mapped_column(Integer, nullable=True)

    snapshot_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

"""Sealed / boxed product inventory + wishlist per user.

Mirrors `CollectionItem` and `WishlistItem` but keyed off `products.id`
instead of `cards.id`. A polymorphic single-table design was rejected
because sealed items don't carry variants, conditions, or grades —
the shape divergence would leave every column NULLable for one side
or the other and complicate queries. Two dedicated tables stay
simpler for both writes and joins.
"""

from datetime import date, datetime

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


class SealedCollectionItem(Base):
    """One entry per (user, sealed product). qty > 1 covers a user who
    owns multiple copies of the same booster box / ETB.

    Purchase price and acquisition metadata mirror the CollectionItem
    schema so the portfolio ROI math works identically for singles and
    sealed."""

    __tablename__ = "sealed_collection_items"
    __table_args__ = (
        UniqueConstraint("user_id", "product_id", name="uq_sealed_user_product"),
        Index("ix_sealed_collection_user", "user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    product_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("products.id", ondelete="CASCADE"), index=True
    )

    qty: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    condition: Mapped[str | None] = mapped_column(
        String(16), nullable=True, server_default="sealed"
    )
    """Physical state of the sealed product:
        'sealed'  — factory sealed, unopened (default)
        'opened'  — box opened, contents intact
        'damaged' — box or contents damaged (water/tear/crush)
    Nullable at the ORM level so a delayed schema migration doesn't
    500 the read path — every writer defaults to 'sealed' either at
    the DB (server_default) or in Python (default) and the API
    endpoint normalizes reads with `or 'sealed'`. Grading isn't a
    concept for sealed products."""

    acquired_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    purchase_price_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    acquisition_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    """Purchase / Gift / Trade / Other — mirrors CollectionItem."""

    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class SealedWishlistItem(Base):
    """One entry per (user, sealed product). Optional target price
    seeds a future Deal Alert feature (roadmap §10.8 D)."""

    __tablename__ = "sealed_wishlist_items"
    __table_args__ = (
        UniqueConstraint("user_id", "product_id", name="uq_sealed_wishlist_user_product"),
        Index("ix_sealed_wishlist_user", "user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    product_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("products.id", ondelete="CASCADE"), index=True
    )

    target_price_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class WishlistItem(Base):
    """One entry per (user, card). A user can wishlist any card once.

    Optional `max_price_usd` lets the user say "alert me when this drops
    below $X" — wired up by future price-alert logic, optional today.
    `priority` (1-5) lets them sort their list by urgency.
    """

    __tablename__ = "wishlist_items"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "card_id", "variant", name="uq_user_wishlist_card"
        ),
        Index("ix_wishlist_user_card", "user_id", "card_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    card_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("cards.id", ondelete="CASCADE"), index=True
    )

    variant: Mapped[str] = mapped_column(String(32), default="normal", nullable=False)
    """Print variant the user wants — see CollectionItem.variant for
    valid keys. Price alerts fire against the per-variant market price."""

    priority: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    """1 (low) → 5 (must-have)."""

    max_price_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    """If set, target ceiling for purchase — feeds future price alerts."""

    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    user: Mapped["User"] = relationship(back_populates="wishlist")  # noqa: F821

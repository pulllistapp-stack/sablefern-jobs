from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
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


class CollectionItem(Base):
    """One entry per (user, card, variant, condition, grade) combination.

    A user can own multiple copies of the same card in different print
    variants (normal / reverseHolofoil / 1stEdition / holofoil), and within
    each variant in different conditions (NM and LP), and graded vs
    ungraded are tracked separately. Each combo gets its own row.
    """

    __tablename__ = "collection_items"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "card_id",
            "variant",
            "condition",
            "is_graded",
            "grade",
            name="uq_user_card_variant",
        ),
        Index("ix_collection_user_card", "user_id", "card_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    card_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("cards.id", ondelete="CASCADE"), index=True
    )

    qty: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    variant: Mapped[str] = mapped_column(String(32), default="normal", nullable=False)
    """Print variant — matches TCGplayer's keys:
    'normal' / 'holofoil' / 'reverseHolofoil' / '1stEdition' /
    '1stEditionHolofoil' / 'unlimited' / 'unlimitedHolofoil'.
    Per-variant pricing means a user's holo Charizard ($600) and
    normal Charizard ($10) are tracked separately, and portfolio
    value sums each one at its own variant price."""

    condition: Mapped[str] = mapped_column(String(8), default="NM", nullable=False)
    """NM (Near Mint) / LP (Lightly Played) / MP / HP / DMG."""

    is_graded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    grade: Mapped[str | None] = mapped_column(String(16), nullable=True)
    """e.g. 'PSA 10' / 'BGS 9.5' / 'CGC 10 Pristine'."""

    acquired_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)

    purchase_price_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    """What the user paid for this row, in USD. Required for ROI math
    (current market_price_usd - purchase_price_usd). Optional — the
    add-modal lets users skip it for cards they pulled or were gifted."""

    acquisition_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    """Pull / Trade / Purchase / Gift / Other. Optional context for
    stats and future segmentation (e.g. 'show me everything I pulled
    in 2026')."""

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    user: Mapped["User"] = relationship(back_populates="collection")  # noqa: F821

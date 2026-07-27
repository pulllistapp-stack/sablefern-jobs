"""User-submitted data-quality report against a set.

Mirrors CardReport but scoped to a whole set — for gaps that don't fit
a single card row (e.g. "16 cards missing from this set", "logo is
wrong", "wrong printed_total"). Anonymous submissions allowed so
visitors can flag issues without signing up.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SetReport(Base):
    __tablename__ = "set_reports"
    __table_args__ = (
        Index("ix_set_reports_status_created", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    set_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("sets.id", ondelete="CASCADE"), index=True
    )

    user_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    """Null = anonymous report (visitor wasn't signed in)."""

    category: Mapped[str] = mapped_column(String(24), nullable=False)
    """One of: 'missing_cards' / 'wrong_images' / 'wrong_metadata' / 'other'.
    'missing_cards' = whole rows absent from the catalog; 'wrong_images'
    = image URLs broken / mismatched across the set; 'wrong_metadata'
    = set-level fields (logo, name, release_date, printed_total)."""

    comment: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    """Free-text detail — required for category='other', enforced at
    the API layer."""

    status: Mapped[str] = mapped_column(
        String(16), default="open", nullable=False
    )
    """'open' / 'resolved' / 'wontfix'."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    resolved_by: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    """Admin who resolved this report."""

    resolution_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    """Optional admin note explaining resolution or wontfix reason."""

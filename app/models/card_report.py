from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column


from app.database import Base


class CardReport(Base):
    """User-submitted data-quality report against a single card.

    Anonymous reports are allowed (user_id nullable) so visitors can flag
    bad data without signing up — but most reports come from logged-in
    friends-beta users.
    """

    __tablename__ = "card_reports"
    __table_args__ = (
        Index("ix_card_reports_status_created", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    card_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("cards.id", ondelete="CASCADE"), index=True
    )

    user_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    """Null = anonymous report (visitor wasn't signed in)."""

    category: Mapped[str] = mapped_column(String(24), nullable=False)
    """One of: 'wrong_price' / 'wrong_image' / 'wrong_name' / 'other'."""

    comment: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    """Free-text additional detail. Required for category='other' (enforced
    at the API layer, not DB)."""

    status: Mapped[str] = mapped_column(
        String(16), default="open", nullable=False
    )
    """'open' / 'resolved' / 'wontfix'. New reports default to 'open'."""

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
    """Optional admin note explaining how it was resolved or why it was
    marked wontfix."""

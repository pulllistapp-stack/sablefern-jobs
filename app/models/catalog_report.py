"""User-submitted request that a card or set is missing from the catalog.

Unlike CardReport / SetReport (which pin to an existing DB row and flag
a data issue with it), CatalogReport describes something the user
expected to find but couldn't - a whole set that hasn't been indexed
yet, or an individual card missing from an indexed set. Anonymous
submissions allowed so visitors can flag gaps without signing up.

Feeds the same admin triage flow at /admin/reports as CardReport /
SetReport - see app.api.admin for the resolve endpoints.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CatalogReport(Base):
    __tablename__ = "catalog_reports"
    __table_args__ = (
        Index("ix_catalog_reports_status_created", "status", "created_at"),
        Index("ix_catalog_reports_locale_kind", "locale", "kind"),
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )

    user_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    """Null = anonymous report (visitor wasn't signed in)."""

    locale: Mapped[str] = mapped_column(String(8), nullable=False)
    """Which locale catalog is missing the entry.
    One of: en / ja / ko / zh-cn / zh-tw. Enforced at the API layer
    to match CatalogRegion in the frontend."""

    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    """'missing_set' - an entire set isn't in the catalog.
    'missing_card' - a specific card is missing from a set (either
    an existing indexed set, or a set the user thinks should be
    added and named in set_name)."""

    set_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    """Free-text set name (KR native / EN / whatever the user gave
    us). Required for kind='missing_set'; optional context for
    kind='missing_card'."""

    set_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    """4-digit release year if the user knows it - narrows admin
    lookup when set names are ambiguous."""

    card_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    """The missing card's name. Required for kind='missing_card'."""

    card_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    """Printed card number (e.g. '116', 'SWSH123', '001/XY-P').
    String because Pokemon numbering isn't purely numeric."""

    is_promo: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    """True if the missing entry is a promo card / promo set. Guides
    the admin toward the right ingestion pipeline (regular sets flow
    through pokemontcg.io / TCG-CSV, promos need namu / hobbyxstore
    / Naver-image / etc)."""

    comment: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    """Free-text detail - where the user saw it, source URL, personal
    context."""

    status: Mapped[str] = mapped_column(
        String(16), default="open", nullable=False
    )
    """'open' / 'resolved' / 'wontfix'."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )

    resolved_by: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    """Admin who resolved this report."""

    resolution_note: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )
    """Optional admin note explaining resolution or wontfix reason."""

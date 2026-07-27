from datetime import date, datetime

from sqlalchemy import Date, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Set(Base):
    __tablename__ = "sets"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    series: Mapped[str | None] = mapped_column(String(255), nullable=True)
    printed_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ptcgo_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    release_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)

    symbol_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    logo_url: Mapped[str | None] = mapped_column(String(512), nullable=True)

    language: Mapped[str] = mapped_column(
        String(8), default="en", server_default="en", nullable=False, index=True
    )
    """ISO 639 lang code — 'en' / 'ja' / 'ko' / 'zh-CN' / 'zh-TW'."""

    name_local: Mapped[str | None] = mapped_column(String(255), nullable=True)
    """Native-language set name (e.g., リザードンEXパック). Use `name` for English."""

    name_en: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    """English translation/equivalent of the set name. Used to render
    "JP Name (English Name)" labels on JP catalog cards, the same way
    card-binder.com surfaces both. Populated from JP_SET_TO_BULBAPEDIA
    page titles."""

    name_ko: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    """Korean translation of the set name, even for non-KR primary sets.

    Distinct from `name_local` because for an EN-primary set this is a
    *translation label* shown when the user toggles UI language to KR,
    not the set's own native name. Populated from TCGdex's /ko/sets feed
    by scripts/import_ko_set_names.py.
    """

    parent_set_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    """If this set is a translation of another, points to the source set id."""

    set_subtype: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    """DECK bucket sub-classification: STARTER / DECK / BOX / SPECIAL.
    Populated for set_type='DECK' rows only; null everywhere else.
    Assigned by scripts/classify_deck_subtypes.py."""

    set_type: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    """Categorization for the set browser UI:
        MAIN          — main booster expansion
        DECK          — starter set / preconstructed deck / trainer box
        STUB          — set exists but no cards seeded (mostly TCGdex rows we
                        never populated: ADV1-5, LEGEND stubs, etc.)
        PROMO_LEGACY  — pre-existing JP promo groups (JPP-P, JPP-SI, JPP-VM)
        PROMO_NEW     — Bulbapedia-derived year buckets (JPP-U1996 covering
                        1996-2005, JPP-U2006, U2007, ...). Grouped into 5-year
                        super-buckets by the promo browser.
    Assigned by scripts/classify_jp_set_types.py."""

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    cards: Mapped[list["Card"]] = relationship(  # noqa: F821
        back_populates="set", cascade="all, delete-orphan"
    )

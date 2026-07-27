from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Card(Base):
    __tablename__ = "cards"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    supertype: Mapped[str | None] = mapped_column(String(64), nullable=True)
    subtypes: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    types: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    hp: Mapped[str | None] = mapped_column(String(16), nullable=True)
    hp_int: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    rarity: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    number_int: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    artist: Mapped[str | None] = mapped_column(String(255), nullable=True)
    flavor_text: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    national_pokedex_numbers: Mapped[list[int] | None] = mapped_column(JSON, nullable=True)

    image_small: Mapped[str | None] = mapped_column(String(512), nullable=True)
    image_large: Mapped[str | None] = mapped_column(String(512), nullable=True)

    image_phash: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    """Perceptual hash of image_small (16-char hex = 64 bits). Populated by
    scripts/backfill_card_phashes.py and served in bulk via
    GET /cards/phash-catalog so the client can identify cards from the
    camera locally, skipping the paid Claude vision call."""

    tcgplayer_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    tcgplayer_prices: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Canonical TCGplayer product id (e.g. 534919 for Mew ex SV: Paldean
    # Fates #232). pokemontcg.io's `tcgplayer_url` is a 302 redirect
    # endpoint; storing the resolved id lets us link to the exact
    # product page (instead of falling back to a search URL) and reuse
    # the id for affiliate wrapping. Backfilled by
    # scripts/backfill_tcg_history.py when it follows the redirect.
    tcgplayer_product_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    cardmarket_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    cardmarket_prices: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    market_price_usd: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)

    low_price_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    """Cheapest active listing across all variants of this card. Used
    to compute set-completion floor (sum of all cards' lows = "buy every
    card at the cheapest going price")."""

    high_price_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    """Most expensive active listing across all variants of this card,
    capped by the rarity ceiling (drops outlier $10k-asks). Pairs with
    low_price_usd to render the set-completion price band."""

    mid_price_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    """TCGplayer 'mid' (midpoint between low and high listing) for the
    base variant, mirroring market_price_usd's variant-priority pick
    but pulled from the `mid` field only — never falls back to market.
    Used for set-value totals: market can be sales-driven and high
    catches graded slabs, so a sum-of-mids reads as a stable
    "what's this set listed at" headline without spike contamination."""

    set_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("sets.id", ondelete="CASCADE"), index=True
    )

    language: Mapped[str] = mapped_column(
        String(8), default="en", server_default="en", nullable=False, index=True
    )
    """ISO 639 lang code — 'en' / 'ja' / 'ko' / 'zh-CN' / 'zh-TW'."""

    name_local: Mapped[str | None] = mapped_column(String(255), nullable=True)
    """Native-language card name (e.g., リザードン). Use `name` for English."""

    parent_card_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    """If this card is a translation of another, points to the source card id."""

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    set: Mapped["Set"] = relationship(back_populates="cards")  # noqa: F821

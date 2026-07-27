"""Sealed / boxed TCG products — Booster Boxes, ETBs, Bundles, Tins,
Premium Collections, blister packs, etc. Parallel to `cards` but keyed
off a different TCGplayer product id so pricing signals live in the
same downstream pipeline.

Rows are populated from TCGCSV's `/tcgplayer/3/{group_id}/products`
feed via `scripts/ingest_products.py`. Cards are filtered out by the
`_looks_like_card()` heuristic; the reverse-filter (`_looks_like_sealed`)
lives in the ingest script so this model stays product-agnostic.
"""

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        Index("ix_products_set", "set_id"),
        Index("ix_products_type", "product_type"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    """Our own product id — canonical form is `p-<tcgplayer_product_id>` so
    the ingest can dedupe by TCGplayer id without a second unique constraint."""

    name: Mapped[str] = mapped_column(String(255))

    set_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("sets.id", ondelete="SET NULL"),
        nullable=True,
    )
    """The set this product belongs to. Nullable because some products
    (event kits, blister assortments) don't map cleanly to one set."""

    product_type: Mapped[str] = mapped_column(String(24))
    """Canonical bucket:
        'booster_box'      — 36-pack case (a.k.a. Booster Display)
        'etb'              — Elite Trainer Box
        'booster_bundle'   — 6-pack bundle
        'premium_collection' — Special Delivery / Premium Collection / Ultra Premium
        'tin'              — Metal / plastic tin (Pokemon GO tin, etc.)
        'blister'          — 1-3 pack blister
        'build_battle'     — Build & Battle Box / Prerelease Kit
        'sleeved_booster'  — 1-pack sleeved
        'other'            — Everything else the classifier couldn't slot
    """

    packs_per_box: Mapped[int | None] = mapped_column(Integer, nullable=True)
    """Only meaningful for products that contain sealed booster packs.
    Used by the EV calculator. Null when unknown or product isn't a
    pack container (e.g. individual promo card in a Premium Collection)."""

    tcgplayer_product_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, unique=True, index=True
    )
    """TCGplayer's canonical product id — enables direct-link affiliate
    URLs and dedup across ingest runs."""
    tcgplayer_group_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    """The TCGplayer group (roughly a set) this product came from."""

    msrp_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    """Manufacturer's suggested retail — not always known; TCGCSV
    doesn't publish MSRP so this is manually filled or scraped."""
    market_price_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    """Current market price (TCGplayer's midpoint). Refreshed on the
    same cadence as card prices."""
    low_price_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    high_price_usd: Mapped[float | None] = mapped_column(Float, nullable=True)

    image_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    """TCGplayer product image (usually a Pokemon.com marketing render).
    Missing when TCGCSV didn't publish one."""

    tcgplayer_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    """Direct link to the TCGplayer product page (wrapped with affiliate
    params downstream). Falls back to a search URL if we only have the
    name."""

    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    """Free-form product description from TCGCSV metadata — usually
    includes promo card names inside the product."""

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    set: Mapped["Set"] = relationship("Set")  # noqa: F821

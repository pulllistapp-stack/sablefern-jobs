"""User-scoped master set tracker.

A "master set" is a set-completion goal — the user picks a set and, over
time, works toward owning every card in it. The row itself is thin: just
the (user, set, view preferences) tuple. Progress is computed on read
by joining against `collection_items` — we don't cache it, so ownership
changes reflect the instant the user adds a card.

Two completion definitions live under one row via `display_mode`:
    * base    — one slot per Card row in the set (128/128 for a modern set)
    * master  — one slot per (Card, TCGplayer variant) — reverse holo,
                normal, holofoil counted separately. Variants read from
                Card.tcgplayer_prices JSON keys, so the target moves as
                TCGplayer indexes new SKUs.
The stored mode is the user's *preferred landing view*; the detail page
lets them flip between the two without persisting the toggle.

`binder_size` drives grid columns (3 / 4) on the detail page — mirrors
the pocket-page metaphor collectors already have in physical binders.
Persisted on the row so the visual survives across sessions and devices.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class MasterSet(Base):
    __tablename__ = "master_sets"
    __table_args__ = (
        UniqueConstraint("user_id", "set_id", name="uq_user_master_set"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    set_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("sets.id", ondelete="CASCADE"), index=True
    )

    binder_size: Mapped[str] = mapped_column(
        String(8), default="3x3", nullable=False
    )
    """Physical binder page dimensions — '3x3' (9-pocket) / '4x3'
    (12-pocket) / '4x4' (16-pocket). Frontend keys grid-cols off the
    first number. New sizes just extend the enum, no schema bump."""

    display_mode: Mapped[str] = mapped_column(
        String(8), default="base", nullable=False
    )
    """Landing view — 'base' (numbered slots only) or 'master' (every
    TCGplayer variant). Detail page can flip without re-saving."""

    sort_mode: Mapped[str] = mapped_column(
        String(8), default="number", nullable=False
    )
    """Card layout order — 'number' (mimics binder-page-by-page) or
    'rarity' (groups Common → Uncommon → Rare → hits). Persisted so
    a user with an unusual preference doesn't reset every visit."""

    cover_image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    """Custom binder cover, stored as a data: URL (base64 JPEG). Null =
    show the default mascot. Frontend resizes uploads to ~800x1200 max
    before submit so the payload stays under ~700KB. Replacing the row's
    URL is the only cleanup step — no external storage service, so no
    orphan blobs to garbage-collect."""

    share_token: Mapped[str | None] = mapped_column(
        String(48), nullable=True, unique=True, index=True
    )
    """URL-safe token used for public read-only sharing at
    `/p/masters/{token}`. Null = not shared. Generated on first share,
    rotated on demand; setting to null revokes access. Unique so tokens
    don't collide across users."""

    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    """Timestamp of the first time the caller's base-mode completion
    hit 100%. Null = never completed (or still completing). Used to
    (a) gate the confetti + banner one-shot on the binder detail
    page (only fires when we transition null → now this session)
    and (b) persistently show the gold treatment on the cover
    afterwards. Stays populated even if the collection dips back
    under 100% — LO's setup is "you did the thing," and losing a
    card shouldn't undo the medal."""

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

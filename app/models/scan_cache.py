from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column


from app.database import Base


class ScanCache(Base):
    """Perceptual-hash cache mapping image fingerprints to identified
    cards. Lets us skip Claude Vision API calls when the same (or very
    similar) image gets scanned again.

    image_hash is a 64-bit perceptual hash (pHash) stored as 16-char hex
    so two visually-similar images of the same card produce hashes that
    are close in Hamming distance — exact-pixel hashing wouldn't catch
    re-scans with slightly different lighting / crop / angle.
    """

    __tablename__ = "scan_cache"

    image_hash: Mapped[str] = mapped_column(String(16), primary_key=True)
    """pHash as 16-char hex string (64 bits)."""

    card_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("cards.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    confidence: Mapped[str | None] = mapped_column(String(8), nullable=True)
    """Confidence the original Claude pass returned ('high' / 'medium' /
    'low'). Stored for telemetry — we only cache high/medium hits to
    avoid propagating shaky identifications."""

    hit_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    """How many times this hash has been retrieved from cache. Useful
    later for noticing viral cards / abuse."""

    first_seen: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    last_seen: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False, index=True
    )
    """`last_seen` is indexed so the LRU-style lookup (newest first) is fast."""

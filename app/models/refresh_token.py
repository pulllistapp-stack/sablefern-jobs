from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class RefreshToken(Base):
    """One row per issued refresh token — long-lived, opaque, rotated on use.

    The plaintext token never lives in the DB. We store its sha256 hash so
    a DB dump can't be replayed as a session, and lookups still work by
    hashing the incoming cookie value.

    Rotation policy: every /auth/refresh call revokes the presented row and
    issues a new one. If a client presents a token that's already revoked,
    that's a theft signal — revoke every row for that user to boot both
    the attacker and the legitimate holder (they'll re-auth once).

    id is used as the JWT `jti` for the paired access token so future
    server-side token blacklisting can pivot on it if we ever need it.
    """

    __tablename__ = "refresh_tokens"
    __table_args__ = (
        # Session listing hits this constantly — "which of my tokens are
        # still live?" is (user_id, revoked_at IS NULL, expires_at > now).
        Index("ix_refresh_tokens_user_active", "user_id", "revoked_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    # sha256 hex → 64 chars. Unique so a lookup by hash is O(1) and any
    # collision (theoretically impossible for sha256) still can't confuse
    # two users' sessions.
    token_hash: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # Set when the token is spent (rotated) or explicitly revoked
    # (logout / logout-all). Non-null == dead.
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Best-effort human label for the /auth/sessions surface —
    # "Chrome on Windows", "Safari on iPhone". Derived from UA at issue
    # time; refresh keeps the same label so a device stays a device.
    device_label: Mapped[str | None] = mapped_column(String(120), nullable=True)

    # Bumped on every successful refresh. Powers the "last seen" column
    # in the sessions UI and lets us cull dormant tokens later if we want.
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

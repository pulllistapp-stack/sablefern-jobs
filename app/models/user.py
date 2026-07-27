from datetime import datetime

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    # Nullable so Google-only accounts can exist without a password. Login
    # by password is still required to be non-null for email/password flow.
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Google "sub" claim (stable user id). Lets us recognize the same
    # Google identity across email changes and link an existing
    # email-account on first Google sign-in.
    google_id: Mapped[str | None] = mapped_column(
        String(64), unique=True, index=True, nullable=True
    )

    name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # Portfolio sharing — opt-in. `share_token` is a non-enumerable random
    # URL slug so portfolios aren't browsable by guessing usernames. User
    # can rotate the token to invalidate an old shared link.
    share_token: Mapped[str | None] = mapped_column(
        String(32), unique=True, index=True, nullable=True
    )
    is_portfolio_public: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    portfolio_bio: Mapped[str | None] = mapped_column(String(160), nullable=True)
    # Granular publish toggles. Defaults: value YES, growth NO,
    # wishlist NO, entire grid NO (sample only).
    portfolio_show_value: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    portfolio_show_growth: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    portfolio_show_wishlist: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    portfolio_show_all_cards: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    # CMS access — gates the /admin/* surfaces. Granted manually by an
    # existing admin via PATCH /admin/users/{id}/admin; never assignable
    # at signup.
    is_admin: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default="false"
    )

    # Soft delete — set when an admin removes the user. The row stays so
    # foreign keys (collection items, wishlist, etc.) don't break, but
    # auth flows reject the user as if it didn't exist.
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, default=None
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    collection: Mapped[list["CollectionItem"]] = relationship(  # noqa: F821
        back_populates="user", cascade="all, delete-orphan"
    )
    wishlist: Mapped[list["WishlistItem"]] = relationship(  # noqa: F821
        back_populates="user", cascade="all, delete-orphan"
    )

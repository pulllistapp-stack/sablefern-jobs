from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class NewsPost(Base):
    """In-DB news article. Replaces the filesystem markdown approach so
    LO can write/edit from the browser instead of git-pushing each post.

    Body is Markdown text — same rendering pipeline as before
    (react-markdown + remark-gfm). Image upload isn't part of this
    model yet; the body just references absolute URLs.
    """

    __tablename__ = "news_posts"

    slug: Mapped[str] = mapped_column(String(128), primary_key=True)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    excerpt: Mapped[str | None] = mapped_column(String(512), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)

    # 'all' | 'kr' | 'ja' | 'us' — matches the listing region tabs.
    region: Mapped[str] = mapped_column(String(8), default="all", nullable=False)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    thumbnail_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    author: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # publishedAt vs createdAt: published_at is what the user sees on the
    # card meta strip; created_at is internal. They differ if LO writes a
    # post about something that happened on a different date (e.g.
    # writing tomorrow about a release that drops today).
    published_at: Mapped[str] = mapped_column(String(10), nullable=False)
    reading_time: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # 'draft' | 'published'. Newsbot inserts 'draft' so an admin can
    # review before the post hits the public /news feed. Existing rows
    # grandfather to 'published' via the column default.
    status: Mapped[str] = mapped_column(
        String(16), default="published", nullable=False
    )
    # Upstream article URL — only set by the newsbot, used as the
    # exact-match dedupe key. Index lives in the migration script.
    source_url: Mapped[str | None] = mapped_column(String(512), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now(), nullable=False
    )

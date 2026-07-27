from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ProcessedUrl(Base):
    """Persistent dedupe log for the newsbot, decoupled from news_posts.

    Why a separate table instead of relying on news_posts.source_url?
    LO regularly deletes broken or low-quality drafts from the admin
    UI. That removes the row — and with it, the source_url that
    dedupe was using to skip the upstream article on the next run.
    Result: the same article gets re-crawled, regenerated (burning
    Claude tokens), republished as another broken draft, deleted
    again. Infinite cost cycle.

    ProcessedUrl is the bot's permanent memory of "I've tried this
    URL before, here's how it went" — independent of whether the
    resulting post still exists. The bot writes here regardless of
    outcome (published, rejected-at-verify, generator-error) and
    dedupe reads from here ∪ news_posts on every run.

    Rows are never deleted by user action — the only cleanup would
    be an explicit maintenance script, never the post-delete flow.
    """

    __tablename__ = "newsbot_processed_urls"

    # The upstream article URL we crawled. Matches NewsPost.source_url's
    # column width so a URL can flow between tables without truncation.
    source_url: Mapped[str] = mapped_column(String(512), primary_key=True)

    # Why we recorded this URL. Free-form short code, used for
    # debugging / future analytics — dedupe itself just cares the row
    # exists. Suggested values: 'published', 'thumbnail_failed',
    # 'generator_error', 'manual_skip'. Not enforced.
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)

    # When the bot first saw this URL. We don't update on subsequent
    # encounters (it's the same article) — primary-key conflict on
    # insert is treated as success ("yep, already known").
    processed_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), nullable=False
    )

    # Space-separated normalized title tokens (lowercased content
    # words, stopwords + calendar filler dropped). Used for cross-run
    # dedupe — same story from a second source on a later day matches
    # via Jaccard >= 0.6 and gets skipped. Nullable so rows from
    # before this column existed still work; those just don't
    # contribute to title dedupe (URL dedupe still fires).
    title_tokens: Mapped[str | None] = mapped_column(Text, nullable=True)

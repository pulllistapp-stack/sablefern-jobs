from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class NewsView(Base):
    """Lightweight view-count table for /news posts.

    The post itself lives in a Markdown file in the frontend repo —
    we only persist the running counter here so the listing can sort
    popular posts and the detail page can show a real view tally.
    """

    __tablename__ = "news_views"

    slug: Mapped[str] = mapped_column(String(128), primary_key=True)
    view_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now(), nullable=False
    )

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TIMESTAMP

from .base import Base, TimestampMixin
from .enums import IngestionSource, ingestion_source_sa


class Topic(Base, TimestampMixin):
    __tablename__ = "topics"
    __table_args__ = (Index("idx_topics_parent_keyword", "parent_keyword_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    natural_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    display_text: Mapped[dict] = mapped_column(JSONB, nullable=False)
    source: Mapped[IngestionSource] = mapped_column(ingestion_source_sa, nullable=False)
    parent_keyword_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("keywords.id", ondelete="SET NULL"),
        nullable=True,
    )
    extract_doc_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    graph_node_id: Mapped[str | None] = mapped_column(Text, nullable=True)


class TopicMention(Base):
    # topic_mentions only has created_at per design doc
    __tablename__ = "topic_mentions"
    __table_args__ = (
        CheckConstraint(
            "(teeka_id IS NOT NULL)::int + (gatha_id IS NOT NULL)::int + "
            "(book_id IS NOT NULL)::int + (pravachan_id IS NOT NULL)::int = 1",
            name="chk_topic_mention_single_source",
        ),
        Index("idx_topic_mentions_topic", "topic_id"),
        Index("idx_topic_mentions_chunk", "cataloguesearch_chunk_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    topic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("topics.id", ondelete="CASCADE"),
        nullable=False,
    )
    teeka_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("teekas.id"),
        nullable=True,
    )
    gatha_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("gathas.id"),
        nullable=True,
    )
    book_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("books.id"),
        nullable=True,
    )
    pravachan_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("pravachans.id"),
        nullable=True,
    )
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cataloguesearch_chunk_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    mongo_doc_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

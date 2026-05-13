import uuid

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin
from .enums import IngestionSource, ingestion_source_sa


class Topic(Base, TimestampMixin):
    __tablename__ = "topics"
    __table_args__ = (
        Index("idx_topics_parent_keyword", "parent_keyword_id"),
        Index("idx_topics_parent_topic", "parent_topic_id"),
        Index("idx_topics_keyword_path", "parent_keyword_id", "topic_path"),
        CheckConstraint(
            "natural_key NOT LIKE 'jainkosh:%' AND natural_key NOT LIKE 'nj:%'",
            name="topics_natural_key_no_source_prefix",
        ),
    )

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
    topic_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_topic_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("topics.id", ondelete="SET NULL"),
        nullable=True,
    )
    is_leaf: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

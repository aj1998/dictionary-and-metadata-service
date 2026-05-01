import uuid

from sqlalchemy import ForeignKey, Index, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TIMESTAMP

from .base import Base, TimestampMixin


class Keyword(Base, TimestampMixin):
    __tablename__ = "keywords"
    __table_args__ = (
        Index("idx_keywords_text_trgm", "display_text", postgresql_using="gin", postgresql_ops={"display_text": "gin_trgm_ops"}),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    natural_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    display_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    definition_doc_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    graph_node_id: Mapped[str | None] = mapped_column(Text, nullable=True)


class KeywordAlias(Base):
    # keyword_aliases only has created_at, no updated_at per design doc
    __tablename__ = "keyword_aliases"
    __table_args__ = (
        Index("idx_keyword_aliases_keyword", "keyword_id"),
        Index("idx_keyword_aliases_alias_trgm", "alias_text", postgresql_using="gin", postgresql_ops={"alias_text": "gin_trgm_ops"}),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    alias_text: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    keyword_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("keywords.id", ondelete="CASCADE"),
        nullable=False,
    )
    source: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

import uuid

from sqlalchemy import ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin
from .enums import IngestionSource, ingestion_source_sa


class Table(Base, TimestampMixin):
    __tablename__ = "tables"
    __table_args__ = (
        Index("idx_tables_parent", "parent_natural_key"),
        Index("idx_tables_source", "source"),
        Index("idx_tables_run", "ingestion_run_id"),
        Index("idx_tables_type", "table_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    natural_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    source: Mapped[IngestionSource] = mapped_column(ingestion_source_sa, nullable=False)
    parent_natural_key: Mapped[str] = mapped_column(Text, nullable=False)
    parent_kind: Mapped[str] = mapped_column(Text, nullable=False)
    table_type: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="general"
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    caption: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_html_doc_id: Mapped[str] = mapped_column(Text, nullable=False)
    graph_node_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    ingestion_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ingestion_runs.id", ondelete="SET NULL"),
        nullable=True,
    )

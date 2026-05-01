import uuid

from sqlalchemy import Boolean, ForeignKey, Index, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TIMESTAMP

from .base import Base, TimestampMixin
from .enums import (
    CandidateStatus,
    IngestionRunStatus,
    IngestionSource,
    candidate_status_sa,
    ingestion_run_status_sa,
    ingestion_source_sa,
)


class ParserConfig(Base):
    __tablename__ = "parser_configs"
    __table_args__ = (
        UniqueConstraint("source", "config_path", "version", name="uq_parser_config_source_path_version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source: Mapped[IngestionSource] = mapped_column(ingestion_source_sa, nullable=False)
    config_path: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[str] = mapped_column(Text, nullable=False)
    checksum: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[str] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class IngestionRun(Base, TimestampMixin):
    __tablename__ = "ingestion_runs"
    __table_args__ = (
        Index("idx_ingestion_runs_source_status", "source", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source: Mapped[IngestionSource] = mapped_column(ingestion_source_sa, nullable=False)
    parser_config_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("parser_configs.id"),
        nullable=True,
    )
    triggered_by: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[IngestionRunStatus] = mapped_column(
        ingestion_run_status_sa, nullable=False, default=IngestionRunStatus.pending
    )
    started_at: Mapped[str | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    finished_at: Mapped[str | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    iterator_state: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    raw_html_dir: Mapped[str | None] = mapped_column(Text, nullable=True)
    stats: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    error_log: Mapped[str | None] = mapped_column(Text, nullable=True)


class IngestionReviewQueue(Base):
    __tablename__ = "ingestion_review_queue"
    __table_args__ = (
        Index("idx_review_queue_status", "status"),
        Index("idx_review_queue_run", "ingestion_run_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    ingestion_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ingestion_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_natural_key: Mapped[str] = mapped_column(Text, nullable=False)
    proposed_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    diff_against_existing: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[CandidateStatus] = mapped_column(
        candidate_status_sa, nullable=False, default=CandidateStatus.pending
    )
    reviewed_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[str | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    reject_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

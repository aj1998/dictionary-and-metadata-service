import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TIMESTAMP

from .base import Base
from .enums import CandidateStatus, candidate_status_sa


class TopicCandidate(Base):
    __tablename__ = "topic_candidates"
    __table_args__ = (Index("idx_topic_candidates_status", "status"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source_chat_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    proposed_topic_text: Mapped[dict] = mapped_column(JSONB, nullable=False)
    associated_keyword_texts: Mapped[list] = mapped_column(JSONB, nullable=False)
    user_query: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    cataloguesearch_chunk_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[CandidateStatus] = mapped_column(
        candidate_status_sa, nullable=False, default=CandidateStatus.pending
    )
    merged_into_topic_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("topics.id"),
        nullable=True,
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


class ChatPullerState(Base):
    # Single-row sentinel table; id is always 1, enforced by the CHECK constraint
    __tablename__ = "chat_puller_state"
    __table_args__ = (
        CheckConstraint("id = 1", name="chk_chat_puller_state_singleton"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    last_pulled_at: Mapped[str | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    last_source_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_run_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

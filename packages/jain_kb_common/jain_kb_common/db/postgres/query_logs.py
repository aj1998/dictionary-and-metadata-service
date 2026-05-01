import uuid

from sqlalchemy import Index, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TIMESTAMP

from .base import Base


class QueryLog(Base):
    __tablename__ = "query_logs"
    __table_args__ = (
        Index("idx_query_logs_created", "created_at", postgresql_ops={"created_at": "DESC"}),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_tokens: Mapped[list] = mapped_column(JSONB, nullable=False)
    matched_keyword_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    topic_ids_returned: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    num_results: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    caller: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

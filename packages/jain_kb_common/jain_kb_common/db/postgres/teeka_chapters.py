import uuid

from sqlalchemy import ARRAY, ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class TeekaChapter(Base, TimestampMixin):
    __tablename__ = "teeka_chapters"
    __table_args__ = (
        Index("idx_teeka_chapters_teeka", "teeka_id"),
        Index("idx_teeka_chapters_start_gatha", "start_gatha_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    natural_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    teeka_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("teekas.id", ondelete="CASCADE"),
        nullable=False,
    )
    chapter_number: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    start_gatha_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("gathas.id"),
        nullable=False,
    )
    end_gatha_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("gathas.id"),
        nullable=True,
    )
    sources: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)

import uuid

from sqlalchemy import ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class Kalash(Base, TimestampMixin):
    __tablename__ = "kalashas"
    __table_args__ = (Index("idx_kalashas_teeka", "teeka_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    natural_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    teeka_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("teekas.id", ondelete="CASCADE"),
        nullable=False,
    )
    kalash_number: Mapped[str] = mapped_column(Text, nullable=False)
    sanskrit_doc_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    hindi_doc_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    bhaavarth_doc_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

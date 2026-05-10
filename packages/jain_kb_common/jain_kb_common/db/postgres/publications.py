import uuid

from sqlalchemy import ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class Publication(Base, TimestampMixin):
    __tablename__ = "publications"
    __table_args__ = (Index("idx_publications_teeka", "teeka_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    natural_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    teeka_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("teekas.id", ondelete="CASCADE"),
        nullable=False,
    )
    publisher_id: Mapped[str] = mapped_column(Text, nullable=False)
    publisher: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    public_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    publisher_url: Mapped[str | None] = mapped_column(Text, nullable=True)

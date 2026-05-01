import uuid

from sqlalchemy import ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class Teeka(Base, TimestampMixin):
    __tablename__ = "teekas"
    __table_args__ = (
        Index("idx_teekas_shastra", "shastra_id"),
        Index("idx_teekas_teekakar", "teekakar_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    natural_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    shastra_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("shastras.id", ondelete="CASCADE"),
        nullable=False,
    )
    # design doc had a missing comma here between teekakar_id and publisher
    teekakar_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("authors.id"),
        nullable=True,
    )
    publisher: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    translator: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    editor: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    cataloguesearch_shastra_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    public_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    publisher_url: Mapped[str | None] = mapped_column(Text, nullable=True)

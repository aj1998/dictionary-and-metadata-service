import uuid

from sqlalchemy import ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class Shastra(Base, TimestampMixin):
    __tablename__ = "shastras"
    __table_args__ = (Index("idx_shastras_author", "author_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    natural_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    title: Mapped[dict] = mapped_column(JSONB, nullable=False)
    author_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("authors.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class ShastrasAnuyoga(Base):
    __tablename__ = "shastra_anuyogas"

    shastra_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("shastras.id", ondelete="CASCADE"),
        primary_key=True,
    )
    anuyoga_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("anuyogas.id", ondelete="RESTRICT"),
        primary_key=True,
    )

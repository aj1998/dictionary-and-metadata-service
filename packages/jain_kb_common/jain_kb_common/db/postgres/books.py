import uuid

from sqlalchemy import ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class Book(Base, TimestampMixin):
    __tablename__ = "books"
    __table_args__ = (Index("idx_books_shastra", "shastra_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    natural_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    title: Mapped[dict] = mapped_column(JSONB, nullable=False)
    shastra_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("shastras.id", ondelete="SET NULL"),
        nullable=True,
    )
    publisher: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    translator: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    editor: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    public_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    publisher_url: Mapped[str | None] = mapped_column(Text, nullable=True)


class BookAnuyoga(Base):
    __tablename__ = "book_anuyogas"

    book_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("books.id", ondelete="CASCADE"),
        primary_key=True,
    )
    anuyoga_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("anuyogas.id", ondelete="RESTRICT"),
        primary_key=True,
    )

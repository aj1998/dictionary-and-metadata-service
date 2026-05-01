import uuid

from sqlalchemy import ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class Pravachan(Base, TimestampMixin):
    __tablename__ = "pravachans"

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
    speaker_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("authors.id"),
        nullable=True,
    )
    publisher: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    translator: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    editor: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    public_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    publisher_url: Mapped[str | None] = mapped_column(Text, nullable=True)

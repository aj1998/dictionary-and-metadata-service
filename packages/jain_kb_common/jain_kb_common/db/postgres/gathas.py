import uuid

from sqlalchemy import ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class Gatha(Base, TimestampMixin):
    __tablename__ = "gathas"
    __table_args__ = (
        Index("idx_gathas_shastra", "shastra_id"),
        Index("idx_gathas_keyword_ids", "keyword_ids", postgresql_using="gin", postgresql_ops={"keyword_ids": "jsonb_path_ops"}),
        Index("idx_gathas_topic_ids", "topic_ids", postgresql_using="gin", postgresql_ops={"topic_ids": "jsonb_path_ops"}),
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
    gatha_number: Mapped[str] = mapped_column(Text, nullable=False)
    adhikaar: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    heading: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    prakrit_doc_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    sanskrit_doc_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    hindi_chhand_doc_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    prakrit_word_meanings_doc_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    sanskrit_word_meanings_doc_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    teeka_mapping_doc_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    keyword_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    topic_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

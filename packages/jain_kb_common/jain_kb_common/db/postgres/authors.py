import uuid

from sqlalchemy import Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin
from .enums import AuthorKind, author_kind_sa


class Author(Base, TimestampMixin):
    __tablename__ = "authors"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    natural_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    display_name: Mapped[dict] = mapped_column(JSONB, nullable=False)
    kind: Mapped[AuthorKind] = mapped_column(author_kind_sa, nullable=False)
    bio: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

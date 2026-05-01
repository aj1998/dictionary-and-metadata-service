import uuid

from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base
from .enums import AnuyogaKind, anuyoga_kind_sa


class Anuyoga(Base):
    __tablename__ = "anuyogas"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    kind: Mapped[AnuyogaKind] = mapped_column(anuyoga_kind_sa, nullable=False, unique=True)
    display_name: Mapped[dict] = mapped_column(JSONB, nullable=False)
    description: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

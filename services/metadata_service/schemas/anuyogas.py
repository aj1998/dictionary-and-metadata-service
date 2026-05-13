from __future__ import annotations

import uuid

from pydantic import BaseModel, field_validator

from .common import LangText, _coerce_lang_text


class AnuyogaResponse(BaseModel):
    id: uuid.UUID
    kind: str
    display_name: list[LangText]
    description: list[LangText] | None = None

    @field_validator("display_name", mode="before")
    @classmethod
    def _coerce_dn(cls, v: object) -> list[dict]:
        return _coerce_lang_text(v)

    @field_validator("description", mode="before")
    @classmethod
    def _coerce_desc(cls, v: object) -> list[dict] | None:
        if v is None:
            return None
        return _coerce_lang_text(v)

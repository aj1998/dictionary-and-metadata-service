from __future__ import annotations

from pydantic import BaseModel

from jain_kb_common.db.mongo.schemas import LangText


class TableSummary(BaseModel):
    natural_key: str
    seq: int
    caption: list[LangText]


class TableResponse(BaseModel):
    natural_key: str
    pg_id: str
    source: str
    parent_natural_key: str
    parent_kind: str
    seq: int
    caption: list[LangText]
    source_url: str | None
    raw_html: str
    cells: list[list[str]]
    cell_refs: list[list[list[dict]]] = []
    header_rows: int
    plaintext: str | None
    mentioned_keyword_natural_keys: list[str]
    mentioned_topic_natural_keys: list[str]

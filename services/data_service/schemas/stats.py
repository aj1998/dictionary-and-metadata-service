from __future__ import annotations

from pydantic import BaseModel


class EntityCounts(BaseModel):
    shastras: int
    gathas: int
    topics: int
    keywords: int


class ActivityRow(BaseModel):
    id: str
    run_at: str
    source: str
    entities_touched: int

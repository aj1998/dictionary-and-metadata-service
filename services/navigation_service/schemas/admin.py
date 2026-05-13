from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

# Alias schemas

class AliasCreate(BaseModel):
    alias_text: str
    source: str = "admin"

    model_config = {"extra": "forbid"}


class AliasResponse(BaseModel):
    id: uuid.UUID
    alias_text: str
    source: str
    keyword_natural_key: str
    created_at: datetime


# Topic edge schemas

class TopicEdgeCreate(BaseModel):
    target_topic_natural_key: str
    edge_type: Literal["IS_A", "PART_OF", "RELATED_TO"]
    weight: float = 1.0

    model_config = {"extra": "forbid"}


class TopicEdgeDelete(BaseModel):
    target_topic_natural_key: str
    edge_type: Literal["IS_A", "PART_OF", "RELATED_TO"]

    model_config = {"extra": "forbid"}


class TopicEdgeResponse(BaseModel):
    source_topic_natural_key: str
    target_topic_natural_key: str
    edge_type: str
    weight: float
    source: str


# Resync schemas

ResyncScope = Literal["full", "keyword", "topic", "shastra"]


class ResyncResponse(BaseModel):
    status: str
    scope: ResyncScope
    task_id: str


# Stub audit schemas

class StubItem(BaseModel):
    natural_key: str
    label: str
    stub_source: str | None
    created_at: str | None


class StubAuditResponse(BaseModel):
    pagination: dict
    items: list[StubItem]

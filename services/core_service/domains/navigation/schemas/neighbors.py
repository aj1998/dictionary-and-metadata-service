from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

EdgeDirection = Literal["outbound", "inbound", "undirected"]


class NeighborItem(BaseModel):
    natural_key: str
    display_text_hi: str | None
    label: str
    edge_type: str
    edge_direction: EdgeDirection
    weight: float
    is_stub: bool


class NeighborsResponse(BaseModel):
    topic_natural_key: str
    neighbors: list[NeighborItem]


class TopicItem(BaseModel):
    natural_key: str
    display_text_hi: str | None
    edge_type: str
    is_stub: bool


class KeywordTopicsResponse(BaseModel):
    keyword_natural_key: str
    topics: list[TopicItem]


class KeywordItem(BaseModel):
    natural_key: str
    display_text: str | None
    edge_type: str
    is_stub: bool


class TopicKeywordsResponse(BaseModel):
    topic_natural_key: str
    keywords: list[KeywordItem]


class ShortestPathResponse(BaseModel):
    from_: str
    to: str
    path_length: int
    nodes: list[str]

    model_config = {"populate_by_name": True}

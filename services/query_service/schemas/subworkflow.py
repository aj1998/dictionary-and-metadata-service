from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, model_validator


class TopicsInShastraRequest(BaseModel):
    shastra_natural_key: str
    gatha_number: Optional[int] = None
    limit: int = 25
    include_extracts: bool = False


class TopicMentionItem(BaseModel):
    topic_natural_key: str
    display_text_hi: str
    ancestors_hi: list[str]
    is_leaf: bool
    mention_count: int


class TopicsInShastraResponse(BaseModel):
    topics: list[TopicMentionItem]
    tool_trace_id: str


class ShastrasForTopicRequest(BaseModel):
    topic_natural_key: Optional[str] = None
    keywords: Optional[list[str]] = None
    include_gathas: bool = True
    limit_shastras: int = 10
    limit_gathas_per_shastra: int = 10

    @model_validator(mode="after")
    def require_topic_or_keywords(self) -> "ShastrasForTopicRequest":
        if not self.topic_natural_key and not self.keywords:
            raise ValueError("one of 'topic_natural_key' or 'keywords' is required")
        return self


class GathaRef(BaseModel):
    number: int
    page_number: Optional[int] = None


class ShastraTopicItem(BaseModel):
    shastra_natural_key: str
    name_hi: str
    total_mentions: int
    gathas: list[GathaRef] = []


class ShastrasForTopicResponse(BaseModel):
    topic_natural_key: str
    shastras: list[ShastraTopicItem]
    tool_trace_id: str

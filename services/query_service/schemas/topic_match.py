from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, model_validator


class TopicsMatchRequest(BaseModel):
    keywords: Optional[list[str]] = None
    phrase: Optional[str] = None
    limit: int = 5
    min_similarity: float = 0.30
    include_extracts: bool = True
    include_references: bool = True
    leaf_only: bool = False
    content_only: bool = True
    # Token-coverage guard: a candidate topic must contain (normalized
    # substring, anywhere in its natural_key path) at least this fraction of the
    # query's meaningful tokens, otherwise it is dropped. Coverage ALSO weights
    # the final score, so topics covering more query words always rank above
    # those sharing only an incidental token — even within the surviving set.
    # Default 0.5 keeps relevant child/sub-topics (which usually cover most
    # tokens via their ancestor path) while dropping topics that match on a
    # single common word. Raise to 1.0 to require every word; 0.0 disables the
    # guard entirely (legacy behaviour).
    min_token_coverage: float = 0.5

    @model_validator(mode="after")
    def require_keywords_or_phrase(self) -> "TopicsMatchRequest":
        if not self.keywords and not self.phrase:
            raise ValueError("one of 'keywords' or 'phrase' is required")
        return self

    @property
    def search_str(self) -> str:
        if self.phrase:
            return self.phrase
        return " ".join(self.keywords or [])

    @property
    def coverage_tokens(self) -> list[str]:
        """Raw tokens used for the token-coverage guard.

        Prefer the explicit ``keywords`` list (already meaningful units);
        otherwise fall back to whitespace-splitting the phrase.
        """
        if self.keywords:
            return list(self.keywords)
        return (self.phrase or "").split()


class ResolvedFieldOut(BaseModel):
    field: str
    value: int | str


class MainReference(BaseModel):
    """The single primary reference for an extract block (the one the
    DefinitionModal surfaces first). Carries the full ``resolved_fields`` so
    consumers can render every field and apply their own filtering."""
    shastra_name: Optional[str] = None
    teeka_name: Optional[str] = None
    resolved_fields: list[ResolvedFieldOut] = []


class ExtractBlock(BaseModel):
    block_index: int
    text_hi: str
    main_reference: Optional[MainReference] = None


class TopicReference(BaseModel):
    shastra_natural_key: Optional[str] = None
    gatha_number: Optional[int] = None
    teeka_natural_key: Optional[str] = None
    page_number: Optional[int] = None


class TopicMatchItem(BaseModel):
    topic_natural_key: str
    topic_pg_id: str
    display_text_hi: str
    ancestors_hi: list[str]
    is_leaf: bool
    source: str
    similarity: float
    score: float
    # Canonical jainkosh URL for the topic extract (from the topic_extracts
    # doc, typically a wiki page + section anchor); None when absent in source.
    source_url: Optional[str] = None
    extract_count: int = 0
    extracts_hi: Optional[list[ExtractBlock]] = None
    references: Optional[list[TopicReference]] = None


class TopicsMatchResponse(BaseModel):
    matches: list[TopicMatchItem]
    tool_trace_id: str


# ---------------------------------------------------------------------------
# GraphRAG endpoint schemas
# ---------------------------------------------------------------------------


class GraphRAGRequest(BaseModel):
    tokens: list[str]
    max_hops: int = 2
    limit: int = 5
    edge_types: Optional[list[str]] = None
    include_extracts: bool = True
    include_neighbors: bool = True
    include_references: bool = True
    fuzzy: bool = False


class NeighborTopic(BaseModel):
    topic_natural_key: str
    display_text_hi: str


class NeighborGatha(BaseModel):
    shastra_natural_key: str
    gatha_number: Optional[int] = None


class NeighborKeyword(BaseModel):
    keyword_natural_key: str


class TopicNeighbors(BaseModel):
    related_topics: list[NeighborTopic] = []
    mentioned_in_gathas: list[NeighborGatha] = []
    related_keywords: list[NeighborKeyword] = []


class RankedTopicItem(BaseModel):
    topic_natural_key: str
    topic_pg_id: str
    display_text_hi: str
    ancestors_hi: list[str]
    score: float
    overlap_count: int
    matched_seed_keywords: list[str]
    is_leaf: bool
    source: str
    extracts_hi: Optional[list[ExtractBlock]] = None
    references: Optional[list[TopicReference]] = None
    neighbors: Optional[TopicNeighbors] = None


class GraphRAGResponse(BaseModel):
    ranked_topics: list[RankedTopicItem]
    unresolved_tokens: list[str]
    tool_trace_id: str


# ---------------------------------------------------------------------------
# Topic Neighbors endpoint schemas
# ---------------------------------------------------------------------------


class TopicNeighborsRequest(BaseModel):
    topic_natural_keys: list[str]
    max_neighbors_per_topic: int = 25
    include_extracts: bool = False
    include_references: bool = False
    max_hops: int = 1
    edge_types: Optional[list[str]] = None


class ExpandedNeighborTopic(BaseModel):
    topic_natural_key: str
    display_text_hi: str
    ancestors_hi: list[str] = []
    is_leaf: bool = True
    source: str = ""
    # Content depth at which this topic was collected (1 = direct neighbor).
    hops: int = 1
    # Denormalized displayable extract count (from the Topic node prop) so
    # consumers can decide the "पढ़ें" affordance without a Mongo round-trip.
    extract_count: int = 0
    extracts_hi: list[ExtractBlock] = []
    references: list[TopicReference] = []


class AnchorTopicNeighbors(BaseModel):
    anchor_topic_natural_key: str
    related_topics: list[ExpandedNeighborTopic] = []
    related_keywords: list[NeighborKeyword] = []
    mentioned_in_gathas: list[NeighborGatha] = []


class TopicNeighborsResponse(BaseModel):
    neighbors_by_anchor: list[AnchorTopicNeighbors]
    unresolved_topic_keys: list[str]
    tool_trace_id: str

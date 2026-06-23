"""Iterate source blocks from keyword_definitions and topic_extracts."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import AsyncIterator

from jain_kb_common.matching import pick_refs_to_show

logger = logging.getLogger("jain_kb.matching.source_iter")

_SKIP_KINDS = frozenset({"see_also", "table"})


@dataclass
class SourceBlock:
    kind: str                        # "keyword_definition" | "topic_extract"
    parent_natural_key: str
    section_index: int | None        # keyword_definition only
    definition_index: int | None     # keyword_definition only
    block_index: int
    block_kind: str
    text_devanagari: str | None
    reference_text: str | None
    references: list[dict]
    # Absorbed Hindi translation of the block, if any. Used to match the gatha's
    # Hindi anvayartha (शब्दार्थ panel) in addition to the source-language verse.
    hindi_translation: str | None = None


async def iter_keyword_blocks(
    mongo,
    *,
    keyword_natural_key: str | None = None,
) -> AsyncIterator[SourceBlock]:
    """Yield SourceBlock from keyword_definitions. Skips see_also/table and blocks with no shown refs."""
    query: dict = {}
    if keyword_natural_key is not None:
        query["natural_key"] = keyword_natural_key

    async for doc in mongo.keyword_definitions.find(query):
        parent_nk = doc["natural_key"]
        for section in doc.get("page_sections", []):
            sec_idx = section.get("section_index", 0)
            for defn in section.get("definitions", []):
                def_idx = defn.get("definition_index", 0)
                for blk_idx, block in enumerate(defn.get("blocks", [])):
                    block_kind = block.get("kind", "")
                    if block_kind in _SKIP_KINDS:
                        continue
                    refs = block.get("references", [])
                    shown = pick_refs_to_show(refs)
                    if not shown:
                        logger.debug(
                            "skip block parent=%s sec=%d def=%d blk=%d: no shown refs",
                            parent_nk, sec_idx, def_idx, blk_idx,
                        )
                        continue
                    yield SourceBlock(
                        kind="keyword_definition",
                        parent_natural_key=parent_nk,
                        section_index=sec_idx,
                        definition_index=def_idx,
                        block_index=blk_idx,
                        block_kind=block_kind,
                        text_devanagari=block.get("text_devanagari"),
                        reference_text=shown[0].get("text") if shown else None,
                        references=refs,
                        hindi_translation=block.get("hindi_translation"),
                    )


async def iter_topic_extract_blocks(
    mongo,
    *,
    topic_natural_key: str | None = None,
) -> AsyncIterator[SourceBlock]:
    """Yield SourceBlock from topic_extracts. Skips see_also/table and blocks with no shown refs."""
    query: dict = {}
    if topic_natural_key is not None:
        query["natural_key"] = topic_natural_key

    async for doc in mongo.topic_extracts.find(query):
        parent_nk = doc["natural_key"]
        for blk_idx, block in enumerate(doc.get("blocks", [])):
            block_kind = block.get("kind", "")
            if block_kind in _SKIP_KINDS:
                continue
            refs = block.get("references", [])
            shown = pick_refs_to_show(refs)
            if not shown:
                logger.debug(
                    "skip block parent=%s blk=%d: no shown refs",
                    parent_nk, blk_idx,
                )
                continue
            yield SourceBlock(
                kind="topic_extract",
                parent_natural_key=parent_nk,
                section_index=None,
                definition_index=None,
                block_index=blk_idx,
                block_kind=block_kind,
                text_devanagari=block.get("text_devanagari"),
                reference_text=shown[0].get("text") if shown else None,
                references=refs,
                hindi_translation=block.get("hindi_translation"),
            )

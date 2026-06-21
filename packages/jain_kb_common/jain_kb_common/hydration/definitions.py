from __future__ import annotations

import logging

from jain_kb_common.db.mongo.collections import KEYWORD_DEFINITIONS
from jain_kb_common.hydration.blocks import EXCLUDED_BLOCK_KINDS, block_text_hi

logger = logging.getLogger(__name__)


async def hydrate_definitions_hi(
    mongo_db: object,
    keyword_nks: list[str],
    cap_per_keyword: int = 0,
) -> dict[str, list[dict]]:
    """
    Single find() against keyword_definitions.

    For each doc, walks page_sections[].definitions[].blocks[], keeps every
    block except the no-text kinds (see_also / table), emitting each block's
    Hindi meaning (hindi_translation) and falling back to the original
    text_devanagari when no translation exists. Text is truncated to 1500 chars
    (appends '…' if truncated).

    cap_per_keyword > 0 → keep at most N blocks per keyword.

    Returns {keyword_nk: [{source_natural_key, block_index, text_hi}]}.
    block_index counts only the kept (non-excluded) blocks within that doc.
    """
    result: dict[str, list[dict]] = {}
    cursor = mongo_db[KEYWORD_DEFINITIONS].find(  # type: ignore[index]
        {"natural_key": {"$in": keyword_nks}},
        {"natural_key": 1, "page_sections": 1, "_id": 0},
    )
    async for doc in cursor:
        nk = doc["natural_key"]
        blocks_out: list[dict] = []
        block_index = 0
        for section in doc.get("page_sections", []):
            for defn in section.get("definitions", []):
                for block in defn.get("blocks", []):
                    if block.get("kind", "") in EXCLUDED_BLOCK_KINDS:
                        continue
                    text_hi = block_text_hi(block)
                    if text_hi:
                        blocks_out.append({
                            "source_natural_key": nk,
                            "block_index": block_index,
                            "text_hi": text_hi,
                        })
                    block_index += 1
        if cap_per_keyword > 0:
            blocks_out = blocks_out[:cap_per_keyword]
        result[nk] = blocks_out

    logger.debug(
        "hydrate_definitions_hi keywords=%d → docs_fetched=%d",
        len(keyword_nks), len(result),
    )
    return result

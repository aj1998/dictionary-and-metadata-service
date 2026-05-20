from __future__ import annotations

import logging

from jain_kb_common.db.mongo.collections import TOPIC_EXTRACTS

logger = logging.getLogger(__name__)

HINDI_BLOCK_KINDS = frozenset({"hindi_text", "hindi_gatha"})
BLOCK_TEXT_CAP = 1500


def extract_references(blocks: list[dict]) -> list[dict]:
    """
    Pure function. Walks block inline annotations and returns the unique set of
    references in document order.

    Each reference: {shastra_natural_key, gatha_number, teeka_natural_key, page_number}.
    Any field may be None.
    """
    refs: list[dict] = []
    seen: set[tuple] = set()
    for block in blocks:
        for ref in block.get("references", []):
            rf: dict = {f["field"]: f["value"] for f in ref.get("resolved_fields", [])}

            shastra_nk = rf.get("shastra") or ref.get("shastra_name") or None
            if shastra_nk == "":
                shastra_nk = None

            raw_gatha = rf.get("gatha_number") or rf.get("gatha")
            gatha_num: int | None = None
            try:
                gatha_num = int(raw_gatha) if raw_gatha is not None else None
            except (ValueError, TypeError):
                pass

            teeka_nk = rf.get("teeka") or ref.get("teeka_name") or None
            if teeka_nk == "":
                teeka_nk = None

            raw_page = rf.get("page_number") or rf.get("page")
            page_num: int | None = None
            try:
                page_num = int(raw_page) if raw_page is not None else None
            except (ValueError, TypeError):
                pass

            key = (shastra_nk, gatha_num, teeka_nk, page_num)
            if any(v is not None for v in key) and key not in seen:
                seen.add(key)
                refs.append({
                    "shastra_natural_key": shastra_nk,
                    "gatha_number": gatha_num,
                    "teeka_natural_key": teeka_nk,
                    "page_number": page_num,
                })
    return refs


async def hydrate_topic_extracts_hi(
    mongo_db: object,
    topic_nks: list[str],
    block_index_per_topic: dict[str, int] | None = None,
    cap_per_topic: int = 0,
) -> dict[str, list[dict]]:
    """
    Single find() against topic_extracts.

    For each doc, walks blocks[], keeps only Hindi blocks (hindi_text / hindi_gatha),
    truncates text to 1500 chars (appends '…' if truncated).

    block_index_per_topic[topic_nk] set → return only that absolute block index.
    cap_per_topic > 0 → keep at most N blocks per topic.

    Returns {topic_nk: [{block_index, text_hi, references[]}]}.
    block_index is the absolute position in the blocks list.
    references[] is the list of unique reference dicts for that block.
    """
    result: dict[str, list[dict]] = {}
    cursor = mongo_db[TOPIC_EXTRACTS].find(  # type: ignore[index]
        {"natural_key": {"$in": topic_nks}},
        {"natural_key": 1, "blocks": 1, "_id": 0},
    )
    async for doc in cursor:
        nk = doc["natural_key"]
        target_idx = (block_index_per_topic or {}).get(nk)
        blocks_out: list[dict] = []
        for idx, block in enumerate(doc.get("blocks", [])):
            if block.get("kind", "") not in HINDI_BLOCK_KINDS:
                continue
            if target_idx is not None and idx != target_idx:
                continue
            raw = block.get("text_devanagari") or ""
            if len(raw) > BLOCK_TEXT_CAP:
                text_hi = raw[:BLOCK_TEXT_CAP] + "…"
            else:
                text_hi = raw
            if not text_hi:
                continue
            blocks_out.append({
                "block_index": idx,
                "text_hi": text_hi,
                "references": extract_references([block]),
            })
        if cap_per_topic > 0:
            blocks_out = blocks_out[:cap_per_topic]
        result[nk] = blocks_out

    logger.debug(
        "hydrate_topic_extracts_hi topics=%d → docs_fetched=%d",
        len(topic_nks), len(result),
    )
    return result

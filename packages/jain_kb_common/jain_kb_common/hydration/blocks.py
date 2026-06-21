"""Shared block-projection helpers for the Hindi hydrators.

Both ``hydrate_definitions_hi`` and ``hydrate_topic_extracts_hi`` project the
same parsed ``blocks[]`` shape down to a single Hindi string per block. The
content taxonomy is:

- ``hindi_text``: pure Hindi prose; text lives in ``text_devanagari``, no
  ``hindi_translation``.
- ``prakrit_text`` / ``sanskrit_text`` / ``prakrit_gatha`` / ``sanskrit_gatha``:
  the original scriptural verse lives in ``text_devanagari``; its Hindi meaning
  lives in ``hindi_translation``.
- ``see_also``: cross-reference pointer, no usable text.
- ``table``: structured rows, no inline text.

The earlier hydrators kept only ``{hindi_text, hindi_gatha}`` and read
``text_devanagari``. That dropped every prakrit/sanskrit verse and every gatha
(the real gatha kinds are ``prakrit_gatha`` / ``sanskrit_gatha`` — ``hindi_gatha``
never appears in the data), leaving the Hindi RAG context with empty extracts
even when ``extract_count > 0``. We now keep every block except the excluded
kinds and emit its Hindi meaning (``hindi_translation``), falling back to the
original ``text_devanagari`` when no translation exists.
"""
from __future__ import annotations

# Block kinds that carry no usable inline Hindi text.
EXCLUDED_BLOCK_KINDS = frozenset({"see_also", "table"})

BLOCK_TEXT_CAP = 1500


def block_text_hi(block: dict) -> str:
    """Return the Hindi text for a single parsed block, or "" if none.

    Prefers ``hindi_translation`` (the Hindi meaning of a prakrit/sanskrit
    block); falls back to ``text_devanagari`` (pure-Hindi blocks, and any block
    that lacks a translation). Truncates to ``BLOCK_TEXT_CAP`` chars, appending
    a single ``…`` when truncated.
    """
    if block.get("kind", "") in EXCLUDED_BLOCK_KINDS:
        return ""
    raw = (block.get("hindi_translation") or "").strip() or (block.get("text_devanagari") or "")
    if len(raw) > BLOCK_TEXT_CAP:
        return raw[:BLOCK_TEXT_CAP] + "…"
    return raw

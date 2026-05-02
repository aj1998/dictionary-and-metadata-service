"""Definition parsing for SiddhantKosh and PuranKosh sections."""

from __future__ import annotations

import re
from typing import Optional

from selectolax.parser import Node

from .config import JainkoshConfig
from .models import Block, Definition
from .normalize import normalize_text
from .parse_blocks import make_block, _emit, _strip_eq_prefix, _is_translation_block
from .refs import is_leading_reference_node, extract_refs_from_node
from .selectors import block_class_kind


def parse_siddhantkosh_definitions(
    pre_heading_elements: list[Node],
    config: JainkoshConfig,
    *,
    current_keyword: str = "",
) -> list[Definition]:
    """Parse SiddhantKosh pre-heading content into Definition objects."""
    from .parse_blocks import parse_block_stream

    defs: list[Definition] = []
    cur_elements: list[Node] = []
    cur_refs_context: list[Node] = []  # leading ref nodes for current def

    def flush_def():
        nonlocal cur_elements
        if not cur_elements:
            return
        blocks = parse_block_stream(cur_elements, config, current_keyword=current_keyword)
        if blocks:
            defs.append(Definition(definition_index=len(defs) + 1, blocks=blocks))
        cur_elements = []

    for el in pre_heading_elements:
        if is_leading_reference_node(el, config):
            # A new leading ref starts a new definition boundary
            # But only if we already have content
            if cur_elements:
                # Check if cur_elements has any non-ref content
                has_content = any(
                    not is_leading_reference_node(e, config) for e in cur_elements
                )
                if has_content:
                    flush_def()
            cur_elements.append(el)
        else:
            cur_elements.append(el)

    flush_def()
    _strip_numbering(defs, config)
    return defs


def parse_puraankosh_definitions(
    pre_heading_elements: list[Node],
    config: JainkoshConfig,
    *,
    current_keyword: str = "",
) -> list[Definition]:
    """Parse PuranKosh pre-heading content into Definition objects."""
    from .parse_blocks import make_block, parse_block_stream

    # PuranKosh is wrapped in <div class="HindiText">
    inner_div = None
    for el in pre_heading_elements:
        if el.tag == "div":
            cls = el.attributes.get("class", "") or ""
            if "HindiText" in cls.split():
                inner_div = el
                break

    if inner_div is None:
        # Fallback: treat all elements as one definition
        blocks = parse_block_stream(pre_heading_elements, config, current_keyword=current_keyword)
        if blocks:
            defs = [Definition(definition_index=1, blocks=blocks)]
            _strip_numbering(defs, config)
            return defs
        return []

    # Check for multiple <p id="N"> elements
    p_with_id = inner_div.css("p[id]")
    # Filter to those that are class="HindiText" and start with (N)
    valid_p = []
    for p in p_with_id:
        cls = p.attributes.get("class", "") or ""
        if "HindiText" in cls.split():
            valid_p.append(p)

    if len(valid_p) >= 1 and _any_starts_with_paren_number(valid_p):
        defs = []
        for p in valid_p:
            blocks = parse_block_stream([p], config, current_keyword=current_keyword)
            if blocks:
                defs.append(Definition(definition_index=len(defs) + 1, blocks=blocks))
        _strip_numbering(defs, config)
        return defs

    # Single paragraph case
    p = inner_div.css_first("p.HindiText") or inner_div
    blocks = parse_block_stream([p], config, current_keyword=current_keyword)
    if blocks:
        defs = [Definition(definition_index=1, blocks=blocks)]
        _strip_numbering(defs, config)
        return defs
    return []


def _strip_numbering(definitions: list, config: JainkoshConfig) -> None:
    if not config.definitions.numbering_strip.enabled:
        return
    pat = re.compile(config.definitions.numbering_strip.leading_re)
    prose_kinds = {"hindi_text", "hindi_gatha", "prakrit_text", "prakrit_gatha", "sanskrit_text", "sanskrit_gatha"}
    for d in definitions:
        for b in d.blocks:
            if b.kind in prose_kinds and b.text_devanagari:
                stripped = pat.sub("", b.text_devanagari, count=1)
                if stripped != b.text_devanagari:
                    b.text_devanagari = stripped
                break


def _any_starts_with_paren_number(paragraphs: list[Node]) -> bool:
    """Check if any paragraph text starts with (N) pattern."""
    for p in paragraphs:
        text = normalize_text(p.text(strip=True) or "")
        if re.match(r"^\(\d+\)", text):
            return True
    return False

"""Parse a single page section (h2 → next h2) into a PageSection."""

from __future__ import annotations

from typing import Optional

from selectolax.parser import Node

from .config import JainkoshConfig
from .models import Block, PageSection, SectionKind, Subsection
from .normalize import normalize_text
from .parse_blocks import parse_block_stream
from .parse_definitions import parse_puraankosh_definitions, parse_siddhantkosh_definitions
from .parse_index import parse_index_relations
from .parse_subsections import (
    contains_heading,
    parse_subsections,
    extract_br_dekhen_seeds_from_elements,
    _strip_br_dekhen_lines,
    _make_label_seed_subsection,
)
from .tables import extract_table_block


def parse_section(
    elements: list[Node],
    *,
    section_kind: SectionKind,
    section_index: int,
    h2_text: str,
    keyword: str,
    config: JainkoshConfig,
) -> PageSection:
    """Parse a section's DOM elements into a PageSection."""
    # Phase 1: split into pre_heading, index_ols, body, orphan_tables
    pre_heading: list[Node] = []
    index_ols: list[Node] = []
    body: list[Node] = []
    orphan_tables: list[Node] = []

    seen_first_heading = False

    for el in elements:
        if el.tag == "table":
            if config.table.attach_to == "section_root":
                orphan_tables.append(el)
            elif seen_first_heading:
                body.append(el)
            elif config.table.fallback_when_no_subsection == "section_root":
                orphan_tables.append(el)
            else:
                body.append(el)
            continue

        if not seen_first_heading:
            if el.tag == "ol" and not contains_heading(el, config):
                index_ols.append(el)
                continue
            if not contains_heading(el, config):
                pre_heading.append(el)
                continue

        seen_first_heading = True
        body.append(el)

    # Phase 2: definitions
    if section_kind == "siddhantkosh":
        definitions = parse_siddhantkosh_definitions(
            pre_heading, config, current_keyword=keyword, section_kind=section_kind
        )
    elif section_kind == "puraankosh":
        definitions = parse_puraankosh_definitions(
            pre_heading, config, current_keyword=keyword, section_kind=section_kind
        )
    else:
        definitions = parse_siddhantkosh_definitions(
            pre_heading, config, current_keyword=keyword, section_kind=section_kind
        )

    # Phase 3: index relations
    if section_kind in config.index.enabled_for:
        index_relations = parse_index_relations(index_ols, keyword, config)
    else:
        index_relations = []

    # Phase 4: subsections tree
    subsections = parse_subsections(body, keyword, config)

    # Phase 5: section-level label-topic seeds from <br/>-separated देखें patterns in pre_heading
    label_topic_seeds: list[Subsection] = []
    br_seed_candidates = extract_br_dekhen_seeds_from_elements(
        pre_heading, keyword=keyword, config=config
    )
    if br_seed_candidates:
        covered_keys: set[tuple] = set()
        for label, candidate in br_seed_candidates:
            see_also_block = Block(
                kind="see_also",
                target_keyword=candidate.get("target_keyword"),
                target_topic_path=candidate.get("target_topic_path"),
                target_url=candidate.get("target_url"),
                is_self=bool(candidate.get("is_self", False)),
                target_exists=bool(candidate.get("target_exists", True)),
            )
            seed = _make_label_seed_subsection(
                label=label,
                keyword=keyword,
                parent=None,
                config=config,
                row_see_alsos=[see_also_block],
            )
            label_topic_seeds.append(seed)
            covered_keys.add((
                candidate.get("target_keyword"),
                candidate.get("target_topic_path"),
                candidate.get("target_url"),
                bool(candidate.get("is_self", False)),
            ))

        # Post-process definitions: strip देखें lines from hindi_translation
        # and remove see_also blocks that are now represented as seeds
        for defn in definitions:
            new_blocks: list[Block] = []
            for block in defn.blocks:
                if block.kind == "see_also":
                    bkey = (
                        block.target_keyword,
                        block.target_topic_path,
                        block.target_url,
                        block.is_self,
                    )
                    if bkey in covered_keys:
                        continue
                if block.hindi_translation and any(
                    trigger in block.hindi_translation
                    for trigger in config.index.see_also_triggers
                ):
                    block.hindi_translation = _strip_br_dekhen_lines(
                        block.hindi_translation, config
                    ) or block.hindi_translation
                new_blocks.append(block)
            defn.blocks = new_blocks

    # Phase 6: section-level tables (orphan only)
    extra_blocks = [extract_table_block(t, config) for t in orphan_tables]

    return PageSection(
        section_kind=section_kind,
        section_index=section_index,
        h2_text=h2_text,
        definitions=definitions,
        index_relations=index_relations,
        subsections=subsections,
        label_topic_seeds=label_topic_seeds,
        extra_blocks=extra_blocks,
    )

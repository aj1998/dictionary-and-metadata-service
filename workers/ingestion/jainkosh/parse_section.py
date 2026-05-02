"""Parse a single page section (h2 → next h2) into a PageSection."""

from __future__ import annotations

from typing import Optional

from selectolax.parser import Node

from .config import JainkoshConfig
from .models import Block, PageSection, SectionKind
from .normalize import normalize_text
from .parse_blocks import parse_block_stream
from .parse_definitions import parse_puraankosh_definitions, parse_siddhantkosh_definitions
from .parse_index import parse_index_relations
from .parse_subsections import contains_heading, parse_subsections
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
            pre_heading, config, current_keyword=keyword
        )
    elif section_kind == "puraankosh":
        definitions = parse_puraankosh_definitions(
            pre_heading, config, current_keyword=keyword
        )
    else:
        definitions = parse_siddhantkosh_definitions(
            pre_heading, config, current_keyword=keyword
        )

    # Phase 3: index relations
    if section_kind in config.index.enabled_for:
        index_relations = parse_index_relations(index_ols, keyword, config)
    else:
        index_relations = []

    # Phase 4: subsections tree
    subsections = parse_subsections(body, keyword, config)

    # Phase 5: section-level tables (orphan only)
    extra_blocks = [extract_table_block(t, config) for t in orphan_tables]

    return PageSection(
        section_kind=section_kind,
        section_index=section_index,
        h2_text=h2_text,
        definitions=definitions,
        index_relations=index_relations,
        subsections=subsections,
        label_topic_seeds=[],
        extra_blocks=extra_blocks,
    )

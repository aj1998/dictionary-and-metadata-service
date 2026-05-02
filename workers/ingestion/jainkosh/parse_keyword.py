"""Top-level entry point: parse a keyword HTML page."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from selectolax.parser import HTMLParser, Node

from .config import JainkoshConfig
from .models import KeywordParseResult, Nav, PageSection, ParserWarning, Subsection
from .nav import drop_nav_nodes, extract_nav
from .normalize import decode_keyword_from_url, normalize_text
from .parse_section import parse_section


class ParseError(Exception):
    def __init__(self, message: str, *, file: Optional[str] = None,
                 location: Optional[str] = None):
        super().__init__(message)
        self.file = file
        self.location = location


def _classify_section(h2: Node, config: JainkoshConfig) -> str:
    headline_id = h2.attributes.get("id", "") or ""
    return config.section_kind_for(headline_id)


def _collect_siblings_until_next_h2(h2: Node) -> list[Node]:
    """
    Collect all top-level sibling elements that come after this h2
    and before the next h2 (or end of mw-parser-output).
    """
    elements: list[Node] = []
    node = h2.parent  # The <h2> tag
    # Walk forward through the parent's children
    sibling = node.next
    while sibling is not None:
        tag = sibling.tag
        if tag and tag.lower() == "h2":
            break
        if tag and tag not in ("-text", "#text"):
            elements.append(sibling)
        sibling = sibling.next
    return elements


def _walk_subsection_tree(subsections: list[Subsection]):
    for sub in subsections:
        yield sub
        yield from _walk_subsection_tree(sub.children)


def _resolve_index_relation_natural_keys(section: PageSection) -> None:
    path_to_nk: dict[str, str] = {}
    for sub in _walk_subsection_tree(section.subsections):
        if sub.topic_path is not None:
            path_to_nk[sub.topic_path] = sub.natural_key
    for rel in section.index_relations:
        rel.source_topic_natural_key_chain = [
            path_to_nk[p] for p in rel.source_topic_path_chain if p in path_to_nk
        ]


def parse_keyword_html(
    html: str,
    url: str,
    config: JainkoshConfig,
    *,
    frozen_time: Optional[datetime] = None,
) -> KeywordParseResult:
    """Parse a JainKosh keyword HTML page into a KeywordParseResult."""
    tree = HTMLParser(html)
    main = tree.css_first(config.sections.selector)
    if main is None:
        raise ParseError(f"no {config.sections.selector!r} found in page")

    keyword = decode_keyword_from_url(url)
    warnings: list[ParserWarning] = []

    # Extract and drop nav
    nav = extract_nav(main, config)
    drop_nav_nodes(main, config)

    # Find all h2 headlines
    h2_nodes = main.css(config.sections.h2_headline_selector)

    page_sections = []
    for i, h2 in enumerate(h2_nodes):
        section_kind = _classify_section(h2, config)
        h2_text = normalize_text(h2.text(strip=True) or "")
        # Collect DOM elements in this section
        elements = _collect_siblings_until_next_h2(h2)
        section = parse_section(
            elements,
            section_kind=section_kind,
            section_index=i,
            h2_text=h2_text,
            keyword=keyword,
            config=config,
        )
        _resolve_index_relation_natural_keys(section)
        page_sections.append(section)

    parsed_at = frozen_time if frozen_time is not None else datetime.now(timezone.utc)
    # Strip tzinfo for consistency if naive
    if parsed_at.tzinfo is not None:
        parsed_at = parsed_at.replace(tzinfo=None)

    return KeywordParseResult(
        keyword=keyword,
        source_url=url,
        page_sections=page_sections,
        nav=nav,
        parser_version=config.parser_rules_version,
        parsed_at=parsed_at,
        warnings=warnings,
    )

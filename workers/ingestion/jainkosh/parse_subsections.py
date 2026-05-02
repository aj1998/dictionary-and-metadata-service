"""Subsection tree assembly from body DOM elements."""

from __future__ import annotations

import re
from typing import Optional

from selectolax.parser import Node

from .config import JainkoshConfig, HeadingVariant
from .models import Block, Subsection
from .normalize import normalize_text, nfc
from .parse_blocks import parse_block_stream
from .selectors import block_class_kind
from .topic_keys import natural_key as compute_natural_key, parent_of, slug
from .see_also import extract_label_before_trigger, find_see_also_candidates_in_element


# ---------------------------------------------------------------------------
# Heading detection
# ---------------------------------------------------------------------------

def detect_heading(node: Node, config: JainkoshConfig) -> Optional[tuple[str, str, str]]:
    """
    Try each heading variant on node. Return (variant_name, topic_path, heading_text)
    on first match, or None.
    """
    for variant in config.headings.variants:
        result = _try_variant(node, variant, config)
        if result is not None:
            return (variant.name,) + result
    return None


def _try_variant(
    node: Node, variant: HeadingVariant, config: JainkoshConfig
) -> Optional[tuple[str, str]]:
    """Return (topic_path, heading_text) if node matches this variant, else None."""
    name = variant.name

    if name == "V1":
        # <strong id="N">heading</strong>
        if node.tag != "strong":
            return None
        node_id = node.attributes.get("id", "") or ""
        if not node_id:
            return None
        text = normalize_text(node.text(strip=True) or "")
        if not text:
            return None
        return node_id, text

    elif name == "V2":
        # <span class="HindiText" id="N"><strong>heading</strong></span>
        if node.tag != "span":
            return None
        cls = node.attributes.get("class", "") or ""
        if "HindiText" not in cls.split():
            return None
        node_id = node.attributes.get("id", "") or ""
        if not node_id:
            return None
        strong = node.css_first("strong")
        if strong is None:
            return None
        text = normalize_text(strong.text(strip=True) or "")
        if not text:
            return None
        return node_id, text

    elif name == "V3":
        # <li id="N"><span class="HindiText"><strong>heading</strong></span>
        if node.tag != "li":
            return None
        node_id = node.attributes.get("id", "") or ""
        if not node_id:
            return None
        span = node.css_first("span.HindiText")
        if span is None:
            return None
        strong = span.css_first("strong")
        if strong is None:
            return None
        text = normalize_text(strong.text(strip=True) or "")
        if not text:
            return None
        # Exclude footer-* ids
        if node_id.startswith("footer-"):
            return None
        return node_id, text

    elif name == "V4":
        # <p class="HindiText"><b>N. heading</b></p>  (b is only-child element)
        if node.tag != "p":
            return None
        cls = node.attributes.get("class", "") or ""
        if "HindiText" not in cls.split():
            return None
        # Find <b> that is the only element child
        elem_children = [c for c in node.iter(include_text=False) if c != node]
        if len(elem_children) != 1:
            return None
        b = elem_children[0]
        if b.tag != "b":
            return None
        raw_text = normalize_text(b.text(strip=True) or "")
        if not raw_text:
            return None
        if not variant.regex:
            return None
        m = re.match(variant.regex, raw_text)
        if not m:
            return None
        try:
            topic_path = m.group("topic_path")
            heading = m.group("heading")
        except IndexError:
            return None
        if not topic_path:
            return None
        return topic_path, normalize_text(heading)

    return None


def contains_heading(el: Node, config: JainkoshConfig) -> bool:
    """Return True if el itself or any descendant matches a heading variant."""
    # Check el itself first
    if detect_heading(el, config) is not None:
        return True
    # Use css("*") for deep traversal (iter() only returns direct children in selectolax)
    for child in el.css("*"):
        if detect_heading(child, config) is not None:
            return True
    return False


# ---------------------------------------------------------------------------
# Walk and collect headings
# ---------------------------------------------------------------------------

def walk_and_collect_headings(
    body_elements: list[Node],
    config: JainkoshConfig,
) -> list[tuple[str, str, list[Node]]]:
    """
    Walk body elements in document order (full DFS). For each detected heading, emit:
      (topic_path, heading_text, content_elements_after_heading_until_next_heading)

    Returns flat list (tree assembly is done by parse_subsections).
    """
    # We do a full DFS traversal, collecting (heading | content_node) markers in order.
    # "content_node" = a leaf-ish node that's a block (p, span with block class, table)
    # We DON'T recurse INTO structural containers (ol, ul, li) as content nodes;
    # instead we recurse into them to find headings and block-level content.

    events: list[tuple[str, Node]] = []  # ("heading" | "block", node)

    def _dfs(nodes: list[Node]) -> None:
        for el in nodes:
            tag = el.tag or ""
            if not tag or tag in ("-text", "#text", "script", "style", "br"):
                continue

            # Check if this node IS a heading
            match = detect_heading(el, config)
            if match is not None:
                events.append(("heading", el))
                # For V3 (li[id]), recurse into the li's children after the heading span
                if el.tag == "li":
                    _dfs_after_v3_heading(el)
                # For V1 (strong[id]) and V2 (span.HindiText[id]) and V4 (p.HindiText b),
                # the heading node is a leaf - content is siblings (handled by parent recursion)
                continue

            # Not a heading - is it a "block" node (contains actual text content)?
            from .selectors import block_class_kind
            kind = block_class_kind(el, config)
            if kind is not None or el.tag == "table":
                # If a block-class element directly contains a heading child, recurse
                # (e.g. <li class="HindiText"><strong id="N">heading</strong>...)
                has_heading_child = any(
                    detect_heading(ch, config) is not None
                    for ch in _iter_direct_children(el)
                )
                if has_heading_child:
                    _dfs(list(_iter_direct_children(el)))
                    continue
                # Otherwise treat as a content block
                events.append(("block", el))
                continue

            # It's a structural container - recurse into it
            if tag in ("ol", "ul", "li", "div", "tbody", "tr", "td", "th"):
                _dfs(list(_iter_direct_children(el)))
            elif tag == "p":
                # Plain p (no block class) - if it's not empty, treat as content
                text = (el.text(strip=True) or "")
                if text:
                    events.append(("block", el))
            else:
                # Any other container - recurse
                _dfs(list(_iter_direct_children(el)))

    def _dfs_after_v3_heading(li_node: Node) -> None:
        """After a V3 li heading, process its children (skip the heading span)."""
        skip_first_span = True
        for child in _iter_direct_children(li_node):
            if skip_first_span:
                cls = child.attributes.get("class", "") or ""
                if child.tag == "span" and "HindiText" in cls.split():
                    skip_first_span = False
                    continue
            _dfs([child])

    _dfs(body_elements)

    # Slice events into segments: each heading starts a new segment
    segments: list[tuple[str, str, list[Node]]] = []
    current_path: str | None = None
    current_text: str | None = None
    current_content: list[Node] = []

    for kind, node in events:
        if kind == "heading":
            if current_path is not None:
                segments.append((current_path, current_text, current_content))
            match = detect_heading(node, config)
            if match:
                _, current_path, current_text = match
            current_content = []
        else:
            current_content.append(node)

    if current_path is not None:
        segments.append((current_path, current_text, current_content))

    return segments


def _iter_direct_children(node: Node):
    """Iterate direct children of a node (iter() returns direct children in selectolax)."""
    yield from node.iter(include_text=False)


# ---------------------------------------------------------------------------
# Tree assembly
# ---------------------------------------------------------------------------

def parse_subsections(
    body_elements: list[Node],
    keyword: str,
    config: JainkoshConfig,
) -> list[Subsection]:
    """Parse body elements into a subsection tree."""
    flat = walk_and_collect_headings(body_elements, config)

    nodes: dict[str, Subsection] = {}
    roots: list[Subsection] = []

    # Build heading path for each node (ancestors + this)
    # We need to track the heading texts for each path level
    path_to_heading: dict[str, str] = {}

    for topic_path, heading_text, content_els in flat:
        path_to_heading[topic_path] = heading_text

        # Ensure all ancestors exist (synthesise if missing)
        _ensure_ancestors_exist(topic_path, nodes, roots, keyword, config, path_to_heading)

        # Build heading_path
        heading_path = _build_heading_path(topic_path, path_to_heading, config)

        # Build natural key
        nk = compute_natural_key(keyword, heading_path, config)

        # Compute parent info
        parent_path = parent_of(topic_path)
        parent_nk: Optional[str] = None
        if parent_path and parent_path in nodes:
            parent_nk = nodes[parent_path].natural_key

        # Parse blocks
        blocks = parse_block_stream(content_els, config, current_keyword=keyword)
        label_seed_candidates = extract_label_seed_candidates_from_elements(
            content_els,
            keyword=keyword,
            config=config,
        )

        # Check if synthetic was already created and replace it
        if topic_path in nodes and nodes[topic_path].is_synthetic:
            synth = nodes[topic_path]
            synth.heading_text = heading_text
            synth.heading_path = heading_path
            synth.natural_key = nk
            synth.parent_natural_key = parent_nk
            synth.is_synthetic = False
            synth.blocks = blocks
            _append_label_seed_children(
                synth,
                keyword,
                config,
                label_seed_candidates=label_seed_candidates,
            )
        else:
            node = Subsection(
                topic_path=topic_path,
                heading_text=heading_text,
                heading_path=heading_path,
                natural_key=nk,
                parent_natural_key=parent_nk,
                is_leaf=True,  # updated later
                is_synthetic=False,
                blocks=blocks,
                children=[],
            )
            _append_label_seed_children(
                node,
                keyword,
                config,
                label_seed_candidates=label_seed_candidates,
            )
            nodes[topic_path] = node
            _attach_to_parent(node, parent_path, nodes, roots)

    # Mark is_leaf bottom-up
    for n in nodes.values():
        n.is_leaf = len(n.children) == 0

    return roots


def _build_heading_path(topic_path: str, path_to_heading: dict[str, str], config) -> list[str]:
    """Build the list of ancestor heading texts + this heading."""
    parts = topic_path.split(".")
    path = []
    for i in range(1, len(parts) + 1):
        p = ".".join(parts[:i])
        text = path_to_heading.get(p, "")
        if text:
            path.append(text)
    return path


def _ensure_ancestors_exist(
    path: str,
    nodes: dict[str, Subsection],
    roots: list[Subsection],
    keyword: str,
    config: JainkoshConfig,
    path_to_heading: dict[str, str],
) -> None:
    """Create synthetic parent nodes for any missing ancestor paths."""
    parts = path.split(".")
    for i in range(1, len(parts)):
        p = ".".join(parts[:i])
        if p not in nodes:
            synth_nk = f"{keyword}:__synthetic_{p}"
            parent_path = parent_of(p)
            parent_nk = nodes[parent_path].natural_key if parent_path and parent_path in nodes else None
            synth = Subsection(
                topic_path=p,
                heading_text="",
                heading_path=[],
                natural_key=synth_nk,
                parent_natural_key=parent_nk,
                is_leaf=False,
                is_synthetic=True,
                blocks=[],
                children=[],
            )
            nodes[p] = synth
            _attach_to_parent(synth, parent_path, nodes, roots)


def _attach_to_parent(
    node: Subsection,
    parent_path: Optional[str],
    nodes: dict[str, Subsection],
    roots: list[Subsection],
) -> None:
    """Attach node to its parent, or add to roots if no parent."""
    if parent_path and parent_path in nodes:
        parent = nodes[parent_path]
        if node not in parent.children:
            parent.children.append(node)
    elif node not in roots:
        roots.append(node)


def _append_label_seed_children(
    node: Subsection,
    keyword: str,
    config: JainkoshConfig,
    *,
    label_seed_candidates: Optional[list[str]] = None,
) -> None:
    seeds = extract_label_topic_seeds(
        node.blocks,
        parent_subsection=node,
        keyword=keyword,
        config=config,
        label_seed_candidates=label_seed_candidates or [],
    )
    for seed in seeds:
        if all(c.natural_key != seed.natural_key for c in node.children):
            node.children.append(seed)
    if seeds:
        node.is_leaf = False


def extract_label_topic_seeds(
    blocks: list[Block],
    *,
    parent_subsection: Optional[Subsection],
    keyword: str,
    config: JainkoshConfig,
    label_seed_candidates: list[str],
) -> list[Subsection]:
    if not config.label_to_topic.enabled:
        return []
    seeds: list[Subsection] = []
    emitted_labels: set[str] = set()
    for label in label_seed_candidates:
        if not label or label in emitted_labels:
            continue
        emitted_labels.add(label)
        seeds.append(
            _make_label_seed_subsection(
                label=label,
                keyword=keyword,
                parent=parent_subsection,
                config=config,
            )
        )

    emitted_in_block = bool(seeds)
    for i, block in enumerate(blocks):
        if block.kind != "see_also":
            continue
        if emitted_in_block:
            continue
        if not _should_emit_for_anchor(block, config):
            continue
        prose = _find_preceding_text_block(blocks, i)
        if prose is None:
            continue
        label = extract_label_before_trigger(prose.text_devanagari or "", config)
        if not label or label in emitted_labels:
            continue
        emitted_labels.add(label)
        seeds.append(
            _make_label_seed_subsection(
                label=label,
                keyword=keyword,
                parent=parent_subsection,
                config=config,
            )
        )
        emitted_in_block = True
    return seeds


def extract_label_seed_candidates_from_elements(
    elements: list[Node],
    *,
    keyword: str,
    config: JainkoshConfig,
) -> list[str]:
    labels: list[str] = []
    for el in elements:
        for candidate in find_see_also_candidates_in_element(el, config, current_keyword=keyword):
            block = Block(
                kind="see_also",
                target_keyword=candidate.get("target_keyword"),
                target_topic_path=candidate.get("target_topic_path"),
                target_url=candidate.get("target_url"),
                is_self=bool(candidate.get("is_self", False)),
                target_exists=bool(candidate.get("target_exists", True)),
            )
            if not _should_emit_for_anchor(block, config):
                continue
            label = _normalize_label_seed_text((candidate.get("label_text") or ""), config)
            if label:
                labels.append(label)
                break
    return labels


def _normalize_label_seed_text(label: str, config: JainkoshConfig) -> str:
    out = label
    out = out.lstrip()
    for bullet in config.label_to_topic.bullet_prefixes:
        out = out.lstrip(bullet)
    out = re.sub(r"[\-–]\s*$", "", out)
    out = out.strip(config.label_to_topic.label_trim_chars + " \t\n")
    return nfc(out)


def _find_preceding_text_block(blocks: list[Block], see_also_index: int) -> Optional[Block]:
    for i in range(see_also_index - 1, -1, -1):
        block = blocks[i]
        if block.kind in {"hindi_text", "hindi_gatha", "sanskrit_text", "sanskrit_gatha", "prakrit_text", "prakrit_gatha"}:
            return block
    return None


def _should_emit_for_anchor(block: Block, config: JainkoshConfig) -> bool:
    if block.target_exists is False and config.label_to_topic.emit_for_redlink:
        return True
    if block.is_self and config.label_to_topic.emit_for_self_link:
        return True
    if (not block.is_self) and block.target_exists and config.label_to_topic.emit_for_wiki_link:
        return True
    return False


def _make_label_seed_subsection(
    *,
    label: str,
    keyword: str,
    parent: Optional[Subsection],
    config: JainkoshConfig,
) -> Subsection:
    sl = slug(label, config)
    if parent is not None:
        nk = f"{parent.natural_key}:{sl}"
    else:
        nk = f"{keyword}:{sl}"
    heading_path = (parent.heading_path if parent else []) + [label]
    return Subsection(
        topic_path=None,
        heading_text=label,
        heading_path=heading_path,
        natural_key=nk,
        parent_natural_key=(parent.natural_key if parent else None),
        is_leaf=config.label_to_topic.is_leaf,
        is_synthetic=config.label_to_topic.is_synthetic,
        label_topic_seed=True,
        source_subkind=config.label_to_topic.source_marker,
        blocks=[],
        children=[],
        idempotency_contract={
            "conflict_key": ["natural_key"],
            "on_conflict": "do_update",
            "fields_replace": [
                "display_text", "is_leaf", "is_synthetic",
                "parent_topic_natural_key", "topic_path", "source", "source_subkind",
            ],
            "fields_append": [],
            "fields_skip_if_set": [],
            "stores": ["postgres", "mongo:topic_extracts", "neo4j:Topic"],
        },
    )

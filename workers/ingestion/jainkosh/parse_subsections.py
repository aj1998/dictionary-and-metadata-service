"""Subsection tree assembly from body DOM elements."""

from __future__ import annotations

import re
from typing import Optional

from selectolax.parser import Node

from .config import JainkoshConfig, HeadingVariant
from .models import Block, Subsection
from .normalize import normalize_text, nfc
from .parse_blocks import parse_block_stream, _is_row_style_element
from .selectors import block_class_kind, is_gref_node
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
                elif el.tag == "span" and config.dfs.process_v2_inline_content:
                    # V2 heading: extract inline content from inside the heading span
                    synthetic = _make_v2_content_block(el)
                    if synthetic is not None:
                        events.append(("block", synthetic))
                continue

            # Not a heading - is it a "block" node (contains actual text content)?
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

            if config.dfs.passthrough_leading_gref and is_gref_node(el, config):
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

    def _make_v2_content_block(span: Node) -> Optional[Node]:
        """Create a synthetic <p class="HindiText"> from the inline content of a V2 heading
        span, stripping the leading <strong>. Returns None if no meaningful content remains."""
        from selectolax.parser import HTMLParser

        html = span.html or ""
        start = html.find(">")
        end = html.rfind("<")
        if start < 0 or end <= start:
            return None
        inner = html[start + 1:end]

        # Remove the leading <strong>...</strong> (first occurrence only)
        inner = re.sub(r"^\s*<strong[^>]*>.*?</strong>\s*", "", inner, count=1, flags=re.DOTALL)

        # Strip leading <br> / whitespace
        inner = re.sub(r"^\s*(<br\s*/?>)?\s*", "", inner)

        if not re.sub(r"<[^>]+>", "", inner).strip():
            return None

        # Reverse-lookup the CSS class for "hindi_text"
        css_class = next(
            (cls for cls, kind in config.block_classes.items() if kind == "hindi_text"),
            "HindiText",
        )
        synthetic_html = f'<p class="{css_class}">{inner}</p>'
        tree = HTMLParser(synthetic_html)
        return tree.css_first(f"p.{css_class}")

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
        row_relations = extract_row_relations_from_elements(
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
                row_relations=row_relations,
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
                row_relations=row_relations,
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


def extract_row_relations_from_elements(
    elements: list[Node],
    *,
    keyword: str,
    config: JainkoshConfig,
) -> dict[str, list[Block]]:
    """Extract see_also Blocks from row-style bullet entries, keyed by normalized label.

    Row-style entries (• label - देखें target) have their see_also blocks assigned to
    the corresponding child label-seed subsection, not the parent.
    """
    result: dict[str, list[Block]] = {}
    for el in elements:
        if not _is_row_style_element(el, config):
            continue
        raw_text = normalize_text(el.text(strip=True) or "")
        label = extract_label_before_trigger(raw_text, config)
        if not label:
            continue
        label = _normalize_label_seed_text(label, config)
        if not label:
            continue
        candidates = find_see_also_candidates_in_element(el, config, current_keyword=keyword)
        see_also_blocks: list[Block] = []
        seen: set[tuple] = set()
        for c in candidates:
            block = Block(
                kind="see_also",
                target_keyword=c.get("target_keyword"),
                target_topic_path=c.get("target_topic_path"),
                target_url=c.get("target_url"),
                is_self=bool(c.get("is_self", False)),
                target_exists=bool(c.get("target_exists", True)),
            )
            dedup_key = (
                block.target_keyword,
                block.target_topic_path,
                block.target_url,
                block.is_self,
                block.target_exists,
            )
            if dedup_key not in seen:
                seen.add(dedup_key)
                see_also_blocks.append(block)
        if see_also_blocks:
            if label not in result:
                result[label] = see_also_blocks
            else:
                # Merge, deduplicating
                existing_keys = {
                    (b.target_keyword, b.target_topic_path, b.target_url, b.is_self, b.target_exists)
                    for b in result[label]
                }
                for block in see_also_blocks:
                    k = (block.target_keyword, block.target_topic_path, block.target_url, block.is_self, block.target_exists)
                    if k not in existing_keys:
                        result[label].append(block)
                        existing_keys.add(k)
    return result


def _append_label_seed_children(
    node: Subsection,
    keyword: str,
    config: JainkoshConfig,
    *,
    label_seed_candidates: Optional[list[str]] = None,
    row_relations: Optional[dict[str, list[Block]]] = None,
) -> None:
    seeds = extract_label_topic_seeds(
        node.blocks,
        parent_subsection=node,
        keyword=keyword,
        config=config,
        label_seed_candidates=label_seed_candidates or [],
        row_relations=row_relations or {},
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
    row_relations: Optional[dict[str, list[Block]]] = None,
) -> list[Subsection]:
    if not config.label_to_topic.enabled:
        return []
    if row_relations is None:
        row_relations = {}
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
                row_see_alsos=row_relations.get(label, []),
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
        prose_text, prose_kind = _text_source_for_label_seed(prose, config)
        inside_brackets = _trigger_inside_brackets(prose_text, config)
        if (
            inside_brackets
            and prose_kind in config.label_to_topic.skip_in_source_kinds
            and not _is_row_like_label_context(prose_text, config)
        ):
            continue
        label = extract_label_before_trigger(prose_text, config)
        if not label or label in emitted_labels:
            continue
        emitted_labels.add(label)
        seeds.append(
            _make_label_seed_subsection(
                label=label,
                keyword=keyword,
                parent=parent_subsection,
                config=config,
                row_see_alsos=row_relations.get(label, []),
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
        source_kind = block_class_kind(el, config)
        parent_text = normalize_text(el.text(strip=False) or "")
        inside_brackets = _trigger_inside_brackets(parent_text, config)
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
            if (
                inside_brackets
                and source_kind in config.label_to_topic.skip_in_source_kinds
                and not _is_row_like_label_context(parent_text, config)
            ):
                continue
            label = extract_label_before_trigger(parent_text, config)
            if not label:
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


def _text_source_for_label_seed(block: Block, config: JainkoshConfig) -> tuple[str, str]:
    translation = block.hindi_translation or ""
    if translation and _contains_any_trigger(translation, config):
        return translation, "hindi_text"
    return (block.text_devanagari or ""), block.kind


def _contains_any_trigger(text: str, config: JainkoshConfig) -> bool:
    return any(trigger in text for trigger in config.index.see_also_triggers)


def _trigger_inside_brackets(text: str, config: JainkoshConfig) -> bool:
    if not text:
        return False
    trigger_positions: list[int] = []
    for trigger in config.index.see_also_triggers:
        start = 0
        while True:
            idx = text.find(trigger, start)
            if idx < 0:
                break
            trigger_positions.append(idx)
            start = idx + 1
    if not trigger_positions:
        return False
    opens = {op: cl for op, cl in config.paren_dekhen_strip.bracket_pairs}
    closes = {cl: op for op, cl in config.paren_dekhen_strip.bracket_pairs}
    target_positions = set(trigger_positions)
    stack: list[str] = []
    for idx, ch in enumerate(text):
        if ch in opens:
            stack.append(ch)
            continue
        if ch in closes:
            if stack and stack[-1] == closes[ch]:
                stack.pop()
            continue
        if idx in target_positions and stack:
            return True
    return False


def _is_row_like_label_context(text: str, config: JainkoshConfig) -> bool:
    triggers = "|".join(
        re.escape(t) for t in sorted(config.index.see_also_triggers, key=len, reverse=True)
    )
    return re.search(r"[\-–]\s*(?:" + triggers + r")", text) is not None


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
    row_see_alsos: Optional[list[Block]] = None,
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
        blocks=list(row_see_alsos) if row_see_alsos else [],
        children=[],
    )

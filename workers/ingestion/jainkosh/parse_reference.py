"""Structured resolution of GRef citation strings against shastra.json."""

from __future__ import annotations

import itertools
import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Union

if TYPE_CHECKING:
    from .config import (
        DevanagariNormalizationConfig,
        ReferenceConfig,
        ReferenceMoolConfig,
        ReferenceNeedsManualMatchConfig,
        ReferenceNoisePhraseConfig,
        ReferenceSectionKeywordsConfig,
    )

from .models import ResolvedField


# ---------------------------------------------------------------------------
# Format string data structures
# ---------------------------------------------------------------------------

@dataclass
class FormatField:
    name: str
    optional: bool


@dataclass
class FormatGroup:
    fields: list[FormatField]
    sub_separator: Optional[str]  # None | "," | "-"
    keyword_triggers: list[str] = field(default_factory=list)
    # Non-empty → this group matches by exact keyword prefix in the numeric string.
    # The first matching keyword is consumed; the trailing number maps to fields[0].
    is_passthrough: bool = False
    # When True, the value at this position is stored as-is (no numeric parsing,
    # no sub-separator splitting, no range expansion).  Field name is taken
    # verbatim from inside the <…> brackets in the format string.

    @property
    def is_optional(self) -> bool:
        return any(f.optional for f in self.fields)

    @property
    def has_required_field(self) -> bool:
        return any(not f.optional for f in self.fields)

    @property
    def is_keyword_group(self) -> bool:
        return bool(self.keyword_triggers)


# ---------------------------------------------------------------------------
# Registry data structures
# ---------------------------------------------------------------------------

@dataclass
class ShastraEntry:
    shastra_name: str
    alternate_names: list[str]   # 14A.3: list (was single Optional[str])
    short_form: str
    format_str: str
    format_groups: list[FormatGroup]
    all_format_groups: list[list[FormatGroup]] = field(default_factory=list)
    # When non-empty, parse_reference_text tries each entry in order, picking the
    # first that resolves without needs_manual_match.  Falls back to [format_groups]
    # for entries built by old test helpers that don't set this field.
    publisher: str = ""
    type: str = ""


@dataclass
class _ResolutionResult:
    needs_manual_match: bool
    is_teeka: bool
    teeka_name: str
    shastra_name: Optional[str]
    match_method: Optional[str]
    resolved_fields: list[ResolvedField]


class ShastraRegistry:
    def __init__(self) -> None:
        self.entries: list[ShastraEntry] = []
        self._by_primary: dict[str, ShastraEntry] = {}
        self._by_alternate: dict[str, ShastraEntry] = {}
        self._by_short_form: dict[str, ShastraEntry] = {}

    @classmethod
    def load(
        cls,
        path: Path,
        norm_config: "DevanagariNormalizationConfig",
    ) -> "ShastraRegistry":
        raw = json.loads(path.read_text("utf-8"))
        registry = cls()
        for item in raw:
            # 14A.3: accept string (legacy) or list for alternate_name(s)
            raw_alt = item.get("alternate_names") or item.get("alternate_name") or []
            if isinstance(raw_alt, str):
                raw_alt = [raw_alt]
            alternate_names = [a for a in raw_alt if a]

            raw_format = item.get("format", [])
            if isinstance(raw_format, str):
                raw_format = [raw_format] if raw_format else []
            format_strings = [f for f in raw_format if f]
            all_fmt_groups = [parse_format_string(f) for f in format_strings]

            entry = ShastraEntry(
                shastra_name=item["shastra_name"],
                alternate_names=alternate_names,
                short_form=item.get("short_form", ""),
                format_str=format_strings[0] if format_strings else "",
                format_groups=all_fmt_groups[0] if all_fmt_groups else [],
                all_format_groups=all_fmt_groups,
                publisher=item.get("publisher", ""),
                type=item.get("type", ""),
            )
            registry.entries.append(entry)
            registry._by_primary[_normalise(entry.shastra_name, norm_config)] = entry
            for alt in entry.alternate_names:
                key = _normalise(alt, norm_config)
                if key in registry._by_alternate:
                    import warnings
                    warnings.warn(
                        f"Alternate name collision: '{alt}' already registered; first entry wins."
                    )
                else:
                    registry._by_alternate[key] = entry
            if entry.short_form:
                registry._by_short_form[_normalise(entry.short_form, norm_config)] = entry
        return registry

    def get_type(self, shastra_name: str) -> Optional[str]:
        """Return raw 'type' field of registry entry; None if missing."""
        entry = self._by_primary.get(shastra_name)
        if entry is None:
            return None
        return entry.type if entry.type else None

    def lookup(
        self,
        normalised_name: str,
    ) -> tuple[Optional[ShastraEntry], Optional[str]]:
        entry = self._by_primary.get(normalised_name)
        if entry:
            return entry, "shastra_name"
        entry = self._by_alternate.get(normalised_name)
        if entry:
            return entry, "alternate_name"
        entry = self._by_short_form.get(normalised_name)
        if entry:
            return entry, "short_form"
        return None, None


# ---------------------------------------------------------------------------
# Publisher registry
# ---------------------------------------------------------------------------

class PublisherRegistry:
    def __init__(self) -> None:
        self._by_name: dict[str, str] = {}  # NFC publisher name -> publisher_id

    @classmethod
    def load(cls, path: Path) -> "PublisherRegistry":
        raw = json.loads(path.read_text("utf-8"))
        reg = cls()
        for item in raw:
            name_nfc = unicodedata.normalize("NFC", item["publisher"])
            reg._by_name[name_nfc] = item["publisher_id"]
        return reg

    def get_id(self, publisher_name: str) -> str:
        return self._by_name.get(
            unicodedata.normalize("NFC", publisher_name),
            "publisher_to_be_added",
        )


# ---------------------------------------------------------------------------
# Devanagari normalisation
# ---------------------------------------------------------------------------

def _normalise(text: str, config: "DevanagariNormalizationConfig") -> str:
    text = unicodedata.normalize("NFC", text)
    if config.enabled:
        for sub in config.substitutions:
            text = text.replace(sub.from_, sub.to)
    # Normalise whitespace around "/" so "name / teeka" and "name/teeka" share a key
    text = re.sub(r"\s*/\s*", "/", text)
    # Remove all remaining spaces — enables "तत्त्वार्थ सूत्र" ↔ "तत्त्वार्थसूत्र"
    text = text.replace(" ", "")
    return text


# ---------------------------------------------------------------------------
# Text pre-processing  (14A.6a, 14A.4A pipeline)
# ---------------------------------------------------------------------------

def _strip_parens(text: str) -> str:
    return text.replace("(", "").replace(")", "")


def _strip_punct(text: str) -> str:
    # Strip Devanagari sentence terminators (dandas) that never appear inside
    # citation numerics. ASCII comma is intentionally NOT stripped here because
    # commas serve as field separators in numeric groups (e.g. "1,1,1").
    return text.replace("।", " ").replace("॥", " ")


def _strip_noise_phrases(text: str, config: "ReferenceNoisePhraseConfig") -> str:
    if not config.enabled:
        return text
    for phrase in config.phrases:
        text = text.replace(phrase, " ")
    return text


def _strip_section_keywords(text: str, config: "ReferenceSectionKeywordsConfig") -> str:
    if not config.enabled:
        return text
    for kw in config.keywords:
        # Only remove when the keyword is surrounded by whitespace on both sides
        text = re.sub(r"\s+" + re.escape(kw) + r"\s+", " ", text)
    return text


def _collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _preprocess_text(
    text: str,
    config: "ReferenceConfig",
    skip_section_keywords: bool = False,
) -> str:
    # 14A.6a: pipeline is parens → punct → noise → keywords → collapse
    text = _strip_parens(text)
    text = _strip_punct(text)
    text = _strip_noise_phrases(text, config.noise_phrases)
    if not skip_section_keywords:
        text = _strip_section_keywords(text, config.section_keywords)
    text = _collapse_ws(text)
    return text


# ---------------------------------------------------------------------------
# Format string parser
# ---------------------------------------------------------------------------

_FIELD_RE = re.compile(r"(§?)([^/,\-§]+)")
_KEYWORD_GROUP_RE = re.compile(r"^\{([^}]+)\}(.+)$")
_PASSTHROUGH_GROUP_RE = re.compile(r"^<(.+)>$")


def _split_format_string_groups(fmt: str) -> list[str]:
    """Split a format string on '/' while respecting '{...}' and '<...>' blocks."""
    groups: list[str] = []
    current: list[str] = []
    brace_depth = 0
    angle_depth = 0
    for ch in fmt:
        if ch == "{":
            brace_depth += 1
            current.append(ch)
        elif ch == "}":
            brace_depth -= 1
            current.append(ch)
        elif ch == "<":
            angle_depth += 1
            current.append(ch)
        elif ch == ">":
            angle_depth -= 1
            current.append(ch)
        elif ch == "/" and brace_depth == 0 and angle_depth == 0:
            groups.append("".join(current))
            current = []
        else:
            current.append(ch)
    if current:
        groups.append("".join(current))
    return groups


def parse_format_string(fmt: str) -> list[FormatGroup]:
    if not fmt:
        return []
    groups = []
    for group_str in _split_format_string_groups(fmt):
        group_str = group_str.strip()
        if not group_str:
            continue

        # Passthrough group: <fieldname>  — value stored as-is, no numeric parsing
        m_pt = _PASSTHROUGH_GROUP_RE.match(group_str)
        if m_pt:
            field_name = m_pt.group(1).strip()
            groups.append(FormatGroup(
                fields=[FormatField(name=field_name, optional=False)],
                sub_separator=None,
                is_passthrough=True,
            ))
            continue

        # Keyword trigger group: {word1/word2}fieldname
        m_kw = _KEYWORD_GROUP_RE.match(group_str)
        if m_kw:
            triggers = [t.strip() for t in m_kw.group(1).split("/") if t.strip()]
            field_name = m_kw.group(2).strip()
            groups.append(FormatGroup(
                fields=[FormatField(name=field_name, optional=False)],
                sub_separator=None,
                keyword_triggers=triggers,
            ))
            continue

        if "," in group_str:
            sub_sep: Optional[str] = ","
            raw_fields = group_str.split(",")
        elif "-" in group_str and len(re.findall(r"[^ऀ-ॿ]", group_str)) > 0:
            sub_sep = "-"
            raw_fields = group_str.split("-")
        else:
            sub_sep = None
            raw_fields = [group_str]

        fields = []
        for rf in raw_fields:
            rf = rf.strip()
            m = _FIELD_RE.match(rf)
            if not m:
                continue
            optional = m.group(1) == "§"
            name = m.group(2).strip()
            fields.append(FormatField(name=name, optional=optional))

        if fields:
            groups.append(FormatGroup(fields=fields, sub_separator=sub_sep))
    return groups


# ---------------------------------------------------------------------------
# Name / numeric splitting
# ---------------------------------------------------------------------------

def split_name_and_numeric(text: str) -> tuple[str, str]:
    m = re.search(r"[\d§]", text)
    if m is None:
        return text.strip().strip("/").strip(), ""
    name_raw = text[: m.start()].strip().strip("/").strip()
    numeric_raw = text[m.start() :].strip().strip("/").strip()
    return name_raw, numeric_raw


# ---------------------------------------------------------------------------
# 14A.8: Strip trailing non-numeric slash-segments from numeric portion
# ---------------------------------------------------------------------------

def _strip_trailing_non_numeric(numeric: str) -> str:
    """Drop trailing slash-segments that contain no digits.

    Example: '3/1,2,1/2/ नं.' -> '3/1,2,1/2'
    """
    parts = numeric.split("/")
    while parts and not re.search(r"\d", parts[-1]):
        parts.pop()
    return "/".join(parts)


# ---------------------------------------------------------------------------
# Second-level keyword extraction
# ---------------------------------------------------------------------------

def _extract_keyword_fields(
    text: str,
    keywords: list[str],
) -> list[ResolvedField]:
    """Scan *original* text for 'keyword <number>' patterns.

    Returns one ResolvedField per keyword found.  Keywords are matched as
    standalone words (preceded by whitespace or start-of-string) so that
    compound names like "गाथासंग्रह" are not accidentally matched by "गाथा".
    Only plain integers are extracted; ranges/lists are not supported here.
    """
    fields: list[ResolvedField] = []
    for kw in keywords:
        # (?<!\S) = not preceded by a non-whitespace char  (= start or whitespace)
        pattern = r"(?<!\S)" + re.escape(kw) + r"\s+(\d+)"
        m = re.search(pattern, text)
        if m:
            fields.append(ResolvedField(field=kw, value=int(m.group(1))))
    return fields


# ---------------------------------------------------------------------------
# Shastra matching
# ---------------------------------------------------------------------------

def _strip_mool(name: str, config: "ReferenceMoolConfig") -> str:
    norm_name = unicodedata.normalize("NFC", name)
    for exc in config.exceptions:
        exc_nfc = unicodedata.normalize("NFC", exc)
        if norm_name == exc_nfc:
            return name
        if norm_name.startswith(exc_nfc):
            return name

    for kw in config.keywords:
        kw_nfc = unicodedata.normalize("NFC", kw)
        if norm_name.endswith(" " + kw_nfc):
            # 14A.6b: trim trailing "/" and whitespace after keyword removal
            return name[: -(1 + len(kw))].rstrip(" /").strip()
        if norm_name.endswith("/" + kw_nfc):
            # 14A.6b: trim trailing "/" and whitespace
            return name[: -(1 + len(kw))].rstrip(" /").strip()
    return name


def match_shastra(
    name_raw: str,
    registry: ShastraRegistry,
    config: "ReferenceConfig",
) -> tuple[Optional[ShastraEntry], Optional[str], bool, str]:
    norm = lambda s: _normalise(s, config.devanagari_normalization)

    # Step 1: try full name_raw as-is
    entry, method = registry.lookup(norm(name_raw))
    if entry:
        return entry, method, False, ""

    # Step 2: strip mool keyword and retry
    stripped = _strip_mool(name_raw, config.mool)
    if stripped != name_raw:
        entry, method = registry.lookup(norm(stripped))
        if entry:
            return entry, method, False, ""

    # Step 2.5: try replacing spaces with "/" to handle "(नयचक्र (श्रुतभवन)/N)" →
    # "नयचक्र श्रुतभवन" → "नयचक्र/श्रुतभवन" after paren stripping
    if " " in name_raw:
        slash_variant = re.sub(r"\s+", "/", name_raw.strip())
        entry, method = registry.lookup(norm(slash_variant))
        if entry:
            return entry, method, False, ""

    # Step 3: teeka detection (slash split)
    name_for_split = re.sub(r"\s*/\s*", "/", name_raw)
    if "/" in name_for_split:
        base, _, teeka_candidate = name_for_split.partition("/")
        base = base.strip()
        teeka_candidate = teeka_candidate.strip()

        # 14A.6b: if teeka_candidate is a mool marker, retry base-only lookup
        first_token = teeka_candidate.split()[0] if teeka_candidate else ""
        is_mool_marker = (
            teeka_candidate in config.mool.keywords
            or first_token in config.mool.keywords
        )
        if is_mool_marker:
            entry, method = registry.lookup(norm(base))
            if entry:
                return entry, method, False, ""
            # no match — fall through to no-match
        else:
            # Normal teeka path
            entry, method = registry.lookup(norm(base))
            if not entry:
                stripped_base = _strip_mool(base, config.mool)
                if stripped_base != base:
                    entry, method = registry.lookup(norm(stripped_base))
                    if entry:
                        base = stripped_base
            if entry:
                # Strip all trailing /<field_keyword> segments from teeka name.
                # Field keywords include both section keywords (गाथा, पंक्ति, …)
                # and entity keywords (पृष्ठ, कलश, …) that appear as format
                # descriptors in GRef text like "teeka/गाथा /पृष्ठ / पंक्ति".
                ek = config.entity_keywords
                all_field_kws = set(config.section_keywords.keywords) | set(
                    ek.gatha + ek.page + ek.kalash + ek.pankti
                )
                changed = True
                while changed:
                    changed = False
                    for kw in all_field_kws:
                        suffix = "/" + kw
                        if teeka_candidate.endswith(suffix):
                            teeka_candidate = teeka_candidate[: -len(suffix)].strip()
                            changed = True
                            break
                        if teeka_candidate == kw:
                            teeka_candidate = ""
                            changed = True
                            break
                return entry, method, True, teeka_candidate

    return None, None, False, ""


# ---------------------------------------------------------------------------
# Value resolution
# ---------------------------------------------------------------------------

_LEADING_DIGITS_RE = re.compile(r"^\s*(\d+)")
_RANGE_LIST_RE = re.compile(r"^\s*(\d+(?:-\d+)?)(?:\s*,\s*(\d+(?:-\d+)?))*\s*$")


def _coerce_value(s: str) -> Optional[int]:
    """Extract leading digit run as int; return None for non-numeric strings."""
    m = _LEADING_DIGITS_RE.match(s)
    return int(m.group(1)) if m else None


def _expand_value(s: Union[int, str]) -> Optional[list[int]]:
    """Expand a range/list value string into a list of ints.

    '95-96' -> [95, 96]; '8,86' -> [8, 86]; '1-3,39' -> [1,2,3,39].
    Pure int -> [int].  Returns None if the pattern is unrecognised or overflow.
    """
    if isinstance(s, int):
        return [s]
    if not _RANGE_LIST_RE.match(s):
        return None
    out: list[int] = []
    for chunk in s.split(","):
        chunk = chunk.strip()
        if "-" in chunk:
            parts = chunk.split("-", 1)
            a, b = int(parts[0]), int(parts[1])
            if b < a or b - a > 50:
                return None
            out.extend(range(a, b + 1))
        else:
            out.append(int(chunk))
    return out


def _expand_resolved_fields(
    resolved_fields: list[ResolvedField],
) -> Optional[list[list[ResolvedField]]]:
    """Expand range/list field values into cartesian product of result sets.

    Passthrough fields (is_passthrough=True) are never expanded — their string
    value is kept verbatim even when it looks like a range (e.g. "13-14").

    Returns None if total expansion exceeds 50 (overflow → needs_manual).
    """
    per_field: list[list] = []
    field_names: list[str] = []
    pt_flags: list[bool] = []

    for rf in resolved_fields:
        if rf.is_passthrough:
            per_field.append([rf.value])
            pt_flags.append(True)
        else:
            values = _expand_value(rf.value)
            if values is None:
                # Non-expandable (guard: shouldn't happen post-coerce)
                per_field.append([rf.value])  # type: ignore[list-item]
            else:
                per_field.append(values)
            pt_flags.append(False)
        field_names.append(rf.field)

    total = 1
    for vals in per_field:
        total *= len(vals)
    if total > 50:
        return None

    results: list[list[ResolvedField]] = []
    for combo in itertools.product(*per_field):
        results.append([
            ResolvedField(field=name, value=val, is_passthrough=pt)
            for name, val, pt in zip(field_names, combo, pt_flags)
        ])
    return results


def _assign_group(
    f_group: FormatGroup,
    value_str: str,
) -> tuple[list[ResolvedField], bool]:
    """Split value_str using the group's sub_separator, assign to fields in order.

    Returns (resolved_fields, mismatch_flag).
    mismatch_flag=True when counts don't align or a value is non-numeric.
    Range/list values (e.g. '95-96', '1-3,39') are stored as strings for
    later expansion by _expand_resolved_fields.
    """
    sep = f_group.sub_separator
    if sep:
        parts = [p.strip() for p in value_str.split(sep)]
    else:
        parts = [value_str.strip()]

    fields = f_group.fields
    mismatch = len(parts) != len(fields)
    resolved = []

    for i, f in enumerate(fields):
        if i >= len(parts):
            break
        part = parts[i]
        # 14A.5: detect range/list BEFORE _coerce_value to avoid lossy coercion
        if ("-" in part or "," in part) and _RANGE_LIST_RE.match(part):
            value: Union[int, str] = part  # keep as string for _expand_value
        else:
            coerced = _coerce_value(part)
            if coerced is None:
                mismatch = True
                continue  # non-numeric part → don't emit a field
            value = coerced
        resolved.append(ResolvedField(field=f.name, value=value))

    return resolved, mismatch


def _assign_keyword_group(
    f_group: FormatGroup,
    value_str: str,
) -> tuple[list[ResolvedField], bool, str]:
    """Match a keyword-trigger group: value_str must start with one of the triggers.

    Returns (resolved_fields, mismatch_flag, matched_trigger).
    matched_trigger is the keyword that was consumed, or "" on mismatch.
    """
    for trigger in f_group.keyword_triggers:
        if value_str.startswith(trigger):
            numeric_part = value_str[len(trigger):]
            coerced = _coerce_value(numeric_part)
            if coerced is not None:
                field_name = f_group.fields[0].name
                return [ResolvedField(field=field_name, value=coerced)], False, trigger
    return [], True, ""


def resolve_fields(
    numeric_clean: str,
    format_groups: list[FormatGroup],
    config: "ReferenceNeedsManualMatchConfig",
) -> tuple[list[ResolvedField], bool, set[str]]:
    """Resolve numeric string against format groups.

    Returns (resolved_fields, needs_manual, consumed_keyword_triggers).
    consumed_keyword_triggers: keyword trigger words consumed by keyword groups —
    callers should suppress these from secondary _extract_keyword_fields extraction.
    """
    consumed_keyword_triggers: set[str] = set()

    if not numeric_clean:
        has_required = any(g.has_required_field for g in format_groups)
        return [], has_required and config.on_missing_fields, consumed_keyword_triggers

    value_groups = numeric_clean.split("/")
    resolved: list[ResolvedField] = []
    needs_manual = False
    v_idx = 0

    for f_group in format_groups:
        if v_idx >= len(value_groups):
            if f_group.has_required_field and config.on_missing_fields:
                needs_manual = True
            continue

        if f_group.is_passthrough:
            value_str = value_groups[v_idx]
            field_name = f_group.fields[0].name
            resolved.append(ResolvedField(field=field_name, value=value_str, is_passthrough=True))
            v_idx += 1
        elif f_group.is_keyword_group:
            value_str = value_groups[v_idx]
            partial, mismatch, matched_trigger = _assign_keyword_group(f_group, value_str)
            resolved.extend(partial)
            if mismatch and config.on_missing_fields:
                needs_manual = True
            elif matched_trigger:
                consumed_keyword_triggers.add(matched_trigger)
            v_idx += 1
        elif f_group.is_optional:
            if value_groups[v_idx].startswith("§"):
                value_str = value_groups[v_idx][1:]
                partial, mismatch = _assign_group(f_group, value_str)
                resolved.extend(partial)
                if mismatch and config.on_missing_fields:
                    needs_manual = True
                v_idx += 1
            # else: skip optional group, don't advance v_idx
        else:
            value_str = value_groups[v_idx]
            partial, mismatch = _assign_group(f_group, value_str)
            resolved.extend(partial)
            if mismatch and config.on_missing_fields:
                needs_manual = True
            v_idx += 1

    if v_idx < len(value_groups) and config.on_extra_groups:
        needs_manual = True

    return resolved, needs_manual, consumed_keyword_triggers


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------

def parse_reference_text(
    text: str,
    registry: ShastraRegistry,
    config: "ReferenceConfig",
) -> list[_ResolutionResult]:
    """Parse a reference text and return a list of resolution results.

    Returns a list because range/list field values expand into multiple results
    (one per concrete numeric combination). Simple references return a list of one.
    """
    EMPTY = _ResolutionResult(
        needs_manual_match=False,
        is_teeka=False,
        teeka_name="",
        shastra_name=None,
        match_method=None,
        resolved_fields=[],
    )

    if not text:
        return [EMPTY]

    clean = _preprocess_text(text, config)
    if not clean:
        return [EMPTY]

    name_raw, numeric_raw = split_name_and_numeric(clean)
    if not name_raw:
        return [EMPTY]

    # 14A.8: strip trailing non-numeric segments before space removal
    numeric_raw = _strip_trailing_non_numeric(numeric_raw)
    numeric_clean = numeric_raw.replace(" ", "")

    # Keyword-group formats need the numeric string WITH section keywords preserved
    # so that keyword triggers (e.g. "गाथा", "श्लोक") are visible in the value stream.
    clean_with_kw = _preprocess_text(text, config, skip_section_keywords=True)
    _, numeric_raw_with_kw = split_name_and_numeric(clean_with_kw)
    numeric_raw_with_kw = _strip_trailing_non_numeric(numeric_raw_with_kw)
    numeric_clean_with_kw = numeric_raw_with_kw.replace(" ", "")

    entry, method, is_teeka, teeka_name = match_shastra(name_raw, registry, config)

    if entry is None:
        return [_ResolutionResult(
            needs_manual_match=True,
            is_teeka=False,
            teeka_name="",
            shastra_name=None,
            match_method=None,
            resolved_fields=[],
        )]

    # ── Level 1: try each format alternative; pick the first that resolves ──
    format_groups_list = entry.all_format_groups if entry.all_format_groups else [entry.format_groups]
    resolved_fields: list[ResolvedField] = []
    needs_manual = True
    consumed_keyword_triggers: set[str] = set()

    for fmt_groups in format_groups_list:
        # Keyword-group formats need the kw-preserved numeric string.
        has_kw_groups = any(g.is_keyword_group for g in fmt_groups)
        numeric = numeric_clean_with_kw if has_kw_groups else numeric_clean
        rf, nm, consumed_kws = resolve_fields(numeric, fmt_groups, config.needs_manual_match)
        if not nm:
            resolved_fields = rf
            needs_manual = False
            consumed_keyword_triggers = consumed_kws
            break

    # Invariant: when first-level fails, format-resolved fields are discarded.
    if needs_manual:
        resolved_fields = []

    # ── Level 2: scan original text for 'keyword <number>' patterns ─────────
    # Keyword fields take priority over format-matched fields (add or override).
    # Keywords already consumed by a keyword-group format are suppressed here
    # to avoid double-extraction or conflicting values.
    # This runs whenever the shastra was identified, regardless of level-1 outcome.
    remaining_kw_keywords = [
        kw for kw in config.section_keywords.keywords
        if kw not in consumed_keyword_triggers
    ]
    keyword_fields = _extract_keyword_fields(text, remaining_kw_keywords)
    if keyword_fields:
        field_map: dict[str, ResolvedField] = {rf.field: rf for rf in resolved_fields}
        for kf in keyword_fields:
            if kf.field in field_map:
                # Same field: flag if Level 2 disagrees with Level 1's value.
                if not needs_manual and field_map[kf.field].value != kf.value:
                    needs_manual = True
            else:
                # New field from Level 2: flag if BOTH of:
                #  (a) the keyword appeared inside the NUMERIC portion of the reference
                #      (i.e. visible in numeric_raw_with_kw — between the name and end),
                #  (b) its value is already claimed by a different Level 1 field.
                #
                # Rationale: when a keyword like "गाथा" appears inside a slash-group
                # of the numeric string (e.g. "/ गाथा 108/253"), it is stripped by
                # section-keyword processing and the adjacent number is mapped to
                # a format field (e.g. पृष्ठ=108).  Level 2 then re-extracts the
                # same keyword+number (गाथा=108), creating two conflicting labels for
                # the same position → manual review required.
                #
                # Exclusion: keywords in the name portion (e.g. "कलश" in a teeka
                # sub-title like "समयसार/आत्मख्याति/कलश 2") are NOT in
                # numeric_raw_with_kw and should NOT trigger this check — they provide
                # additional type information (e.g. kalash-type verse) rather than
                # competing for a format slot.
                if not needs_manual:
                    kw_pattern = r"(?<!\S)" + re.escape(kf.field) + r"\s*\d"
                    kw_in_numeric = bool(re.search(kw_pattern, numeric_raw_with_kw))
                    if kw_in_numeric:
                        for existing_rf in field_map.values():
                            if existing_rf.value == kf.value:
                                needs_manual = True
                                break
            field_map[kf.field] = kf
        resolved_fields = list(field_map.values())

    # When first-level failed, return a single result (no range expansion).
    # resolved_fields may be non-empty from level-2 keyword extraction.
    if needs_manual:
        return [_ResolutionResult(
            needs_manual_match=True,
            is_teeka=is_teeka,
            teeka_name=teeka_name,
            shastra_name=entry.shastra_name,
            match_method=method,
            resolved_fields=resolved_fields,
        )]

    # ── Level 1 succeeded: expand range/list field values (14A.4) ───────────
    expanded = _expand_resolved_fields(resolved_fields)
    if expanded is None:
        # Overflow: too many expansions → needs_manual
        return [_ResolutionResult(
            needs_manual_match=True,
            is_teeka=is_teeka,
            teeka_name=teeka_name,
            shastra_name=entry.shastra_name,
            match_method=method,
            resolved_fields=[],
        )]

    return [
        _ResolutionResult(
            needs_manual_match=False,
            is_teeka=is_teeka,
            teeka_name=teeka_name,
            shastra_name=entry.shastra_name,
            match_method=method,
            resolved_fields=fields,
        )
        for fields in expanded
    ]

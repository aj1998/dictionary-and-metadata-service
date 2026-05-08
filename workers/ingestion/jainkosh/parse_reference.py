"""Structured resolution of GRef citation strings against shastra.json."""

from __future__ import annotations

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

    @property
    def is_optional(self) -> bool:
        return any(f.optional for f in self.fields)

    @property
    def has_required_field(self) -> bool:
        return any(not f.optional for f in self.fields)


# ---------------------------------------------------------------------------
# Registry data structures
# ---------------------------------------------------------------------------

@dataclass
class ShastraEntry:
    shastra_name: str
    alternate_name: Optional[str]
    short_form: str
    format_str: str
    format_groups: list[FormatGroup]


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
            entry = ShastraEntry(
                shastra_name=item["shastra_name"],
                alternate_name=item.get("alternate_name"),
                short_form=item.get("short_form", ""),
                format_str=item.get("format", ""),
                format_groups=parse_format_string(item.get("format", "")),
            )
            registry.entries.append(entry)
            registry._by_primary[_normalise(entry.shastra_name, norm_config)] = entry
            if entry.alternate_name:
                registry._by_alternate[_normalise(entry.alternate_name, norm_config)] = entry
            if entry.short_form:
                registry._by_short_form[_normalise(entry.short_form, norm_config)] = entry
        return registry

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
# Text pre-processing
# ---------------------------------------------------------------------------

def _strip_parens(text: str) -> str:
    return text.replace("(", "").replace(")", "")


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


def _preprocess_text(text: str, config: "ReferenceConfig") -> str:
    text = _strip_parens(text)
    text = _strip_noise_phrases(text, config.noise_phrases)
    text = _strip_section_keywords(text, config.section_keywords)
    text = _collapse_ws(text)
    return text


# ---------------------------------------------------------------------------
# Format string parser
# ---------------------------------------------------------------------------

_FIELD_RE = re.compile(r"(§?)([^/,\-§]+)")


def parse_format_string(fmt: str) -> list[FormatGroup]:
    if not fmt:
        return []
    groups = []
    for group_str in fmt.split("/"):
        group_str = group_str.strip()
        if not group_str:
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
            return name[: -(1 + len(kw))].strip()
        if norm_name.endswith("/" + kw_nfc):
            return name[: -(1 + len(kw))].rstrip("/").strip()
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

    # Step 3: teeka detection (slash split)
    name_for_split = re.sub(r"\s*/\s*", "/", name_raw)
    if "/" in name_for_split:
        base, _, teeka_candidate = name_for_split.partition("/")
        base = base.strip()
        teeka_candidate = teeka_candidate.strip()
        entry, method = registry.lookup(norm(base))
        if not entry:
            stripped_base = _strip_mool(base, config.mool)
            if stripped_base != base:
                entry, method = registry.lookup(norm(stripped_base))
                if entry:
                    base = stripped_base
        if entry:
            return entry, method, True, teeka_candidate

    return None, None, False, ""


# ---------------------------------------------------------------------------
# Value resolution
# ---------------------------------------------------------------------------

def _coerce_value(s: str) -> Union[int, str]:
    s = s.strip()
    if s.isdigit():
        return int(s)
    return s


def _assign_group(
    f_group: FormatGroup,
    value_str: str,
) -> tuple[list[ResolvedField], bool]:
    sep = f_group.sub_separator
    if sep:
        parts = [p.strip() for p in value_str.split(sep)]
    else:
        parts = [value_str.strip()]

    fields = f_group.fields
    mismatch = len(parts) != len(fields)
    resolved = []

    for i, f in enumerate(fields):
        if i < len(parts):
            resolved.append(ResolvedField(field=f.name, value=_coerce_value(parts[i])))

    return resolved, mismatch


def resolve_fields(
    numeric_clean: str,
    format_groups: list[FormatGroup],
    config: "ReferenceNeedsManualMatchConfig",
) -> tuple[list[ResolvedField], bool]:
    if not numeric_clean:
        has_required = any(g.has_required_field for g in format_groups)
        return [], has_required and config.on_missing_fields

    value_groups = numeric_clean.split("/")
    resolved: list[ResolvedField] = []
    needs_manual = False
    v_idx = 0

    for f_group in format_groups:
        if v_idx >= len(value_groups):
            if f_group.has_required_field and config.on_missing_fields:
                needs_manual = True
            continue

        if f_group.is_optional:
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

    return resolved, needs_manual


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------

def parse_reference_text(
    text: str,
    registry: ShastraRegistry,
    config: "ReferenceConfig",
) -> _ResolutionResult:
    EMPTY = _ResolutionResult(
        needs_manual_match=False,
        is_teeka=False,
        teeka_name="",
        shastra_name=None,
        match_method=None,
        resolved_fields=[],
    )

    if not text:
        return EMPTY

    clean = _preprocess_text(text, config)
    if not clean:
        return EMPTY

    name_raw, numeric_raw = split_name_and_numeric(clean)
    if not name_raw:
        return EMPTY

    numeric_clean = numeric_raw.replace(" ", "")

    entry, method, is_teeka, teeka_name = match_shastra(name_raw, registry, config)

    if entry is None:
        return _ResolutionResult(
            needs_manual_match=True,
            is_teeka=False,
            teeka_name="",
            shastra_name=None,
            match_method=None,
            resolved_fields=[],
        )

    resolved_fields, needs_manual = resolve_fields(
        numeric_clean, entry.format_groups, config.needs_manual_match
    )

    # Invariant: needs_manual_match=True → resolved_fields=[]
    if needs_manual:
        resolved_fields = []

    return _ResolutionResult(
        needs_manual_match=needs_manual,
        is_teeka=is_teeka,
        teeka_name=teeka_name,
        shastra_name=entry.shastra_name,
        match_method=method,
        resolved_fields=resolved_fields,
    )

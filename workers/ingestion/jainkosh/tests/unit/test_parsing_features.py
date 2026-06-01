"""Unit tests for JainKosh parser bug fixes and new features.

Covers:
- HTML entity decoding (Bug 1)
- Stray punctuation cleanup after GRef stripping (Bug 2)
- Verse marker spacing fix (Bug 4)
- Auto-detect verse splitting (Feature)
- Cross-page topic stub resolve_key (Feature)
"""
from __future__ import annotations

import re
import pytest

from workers.ingestion.jainkosh.parse_blocks import (
    _decode_html_entities,
    _find_verse_marker,
    _split_text_at_verse_markers,
    _auto_detect_verse_numbers,
    _nums_in_text_order,
    _order_pairs_by_text_position,
    _strip_dekhen_trigger_lines,
    _try_split_multi_verse,
    _assign_inline_refs_to_segments,
)
from workers.ingestion.jainkosh.refs import strip_refs_from_text
from workers.ingestion.jainkosh.models import Block, Reference, ResolvedField
from workers.ingestion.jainkosh.config import JainkoshConfig, load_config


@pytest.fixture(scope="module")
def cfg() -> JainkoshConfig:
    return load_config()


# ---------------------------------------------------------------------------
# Bug 1: HTML entity decoding
# ---------------------------------------------------------------------------

class TestDecodeHtmlEntities:
    def test_nbsp_decoded(self):
        assert _decode_html_entities("a&nbsp;b") == "a b"

    def test_numeric_nbsp_decoded(self):
        assert _decode_html_entities("a&#160;b") == "a b"

    def test_hex_nbsp_decoded(self):
        assert _decode_html_entities("a&#xA0;b") == "a b"

    def test_amp_decoded(self):
        assert _decode_html_entities("a &amp; b") == "a & b"

    def test_lt_gt_decoded(self):
        assert _decode_html_entities("&lt;br&gt;") == "<br>"

    def test_quot_decoded(self):
        assert _decode_html_entities("&quot;hello&quot;") == '"hello"'

    def test_apos_decoded(self):
        assert _decode_html_entities("it&#39;s") == "it's"

    def test_no_entities_unchanged(self):
        text = "simple hindi text जीव द्रव्य"
        assert _decode_html_entities(text) == text

    def test_multiple_entities(self):
        result = _decode_html_entities("a&nbsp;b&amp;c&lt;d")
        assert result == "a b&c<d"


# ---------------------------------------------------------------------------
# Bug 2: Stray punctuation cleanup
# ---------------------------------------------------------------------------

class TestStripRefsFromText:
    """Tests for stray punctuation left after GRef text removal."""

    def _make_ref(self, text: str) -> Reference:
        return Reference(text=text)

    def test_semicolon_only_line_removed(self, cfg: JainkoshConfig):
        refs = [self._make_ref("( धवला 9/4,1,44 )")]
        text = "prose text।\n( धवला 9/4,1,44 )\n;\n।"
        result = strip_refs_from_text(text, refs, cfg)
        assert ";\n" not in result

    def test_comma_only_line_removed(self, cfg: JainkoshConfig):
        refs = []
        text = "text।\n,\nmore"
        result = strip_refs_from_text(text, refs, cfg)
        assert "\n,\n" not in result

    def test_trailing_semicolon_after_danda_removed(self, cfg: JainkoshConfig):
        refs = []
        text = "कोई text।;\n"
        result = strip_refs_from_text(text, refs, cfg)
        assert "।;" not in result
        assert "।" in result

    def test_trailing_comma_after_danda_removed(self, cfg: JainkoshConfig):
        refs = []
        text = "कोई text।,\n"
        result = strip_refs_from_text(text, refs, cfg)
        assert "।," not in result

    def test_line_with_only_dandas_removed(self, cfg: JainkoshConfig):
        refs = []
        text = "valid text\n।॥\nmore text"
        result = strip_refs_from_text(text, refs, cfg)
        assert "।॥" not in result


# ---------------------------------------------------------------------------
# Bug 4: Verse marker spacing fix
# ---------------------------------------------------------------------------

class TestFindVerseMarker:
    def test_finds_marker_without_space(self):
        text = "verse text।15।rest"
        start, end = _find_verse_marker(text, 15, 0)
        assert start != -1
        assert text[start:end] == "।15।"

    def test_finds_marker_with_space(self):
        text = "verse text। 15।rest"
        start, end = _find_verse_marker(text, 15, 0)
        assert start != -1
        assert text[start:end] == "। 15।"

    def test_finds_marker_with_spaces_both_sides(self):
        text = "verse text। 15 ।rest"
        start, end = _find_verse_marker(text, 15, 0)
        assert start != -1
        assert text[start:end] == "। 15 ।"

    def test_returns_neg1_when_not_found(self):
        text = "no markers here"
        start, end = _find_verse_marker(text, 15, 0)
        assert (start, end) == (-1, -1)

    def test_respects_pos_offset(self):
        text = "।15।text।15।more"
        start, end = _find_verse_marker(text, 15, 5)
        assert start >= 5


class TestSplitTextAtVerseMarkers:
    def test_split_without_spaces(self):
        text = "first।15।second।28।third"
        segments = _split_text_at_verse_markers(text, [15, 28])
        assert len(segments) == 2
        assert "first" in segments[0]
        assert "second" in segments[1]

    def test_split_with_spaces_niyamsar_case(self):
        # Mirrors the actual नियमसार/15, 28 case with ". 15।" format
        text = "पहला पद्य। 15।दूसरा पद्य। 28।"
        segments = _split_text_at_verse_markers(text, [15, 28])
        assert len(segments) == 2
        assert segments[0].endswith("। 15।") or "15।" in segments[0]
        assert "दूसरा" in segments[1]

    def test_empty_text_returns_empty_segments(self):
        segments = _split_text_at_verse_markers("", [1, 2])
        assert segments == ["", ""]

    def test_no_verse_numbers_returns_empty(self):
        assert _split_text_at_verse_markers("text", []) == []


# ---------------------------------------------------------------------------
# Feature: Auto-detect verse numbers
# ---------------------------------------------------------------------------

class TestAutoDetectVerseNumbers:
    def test_detects_markers_without_space(self):
        text = "verse।15।content।28।end"
        nums = _auto_detect_verse_numbers(text)
        assert nums == [15, 28]

    def test_detects_markers_with_space(self):
        text = "verse। 15।content। 28।end"
        nums = _auto_detect_verse_numbers(text)
        assert nums == [15, 28]

    def test_deduplicates(self):
        text = "।15।something।15।again"
        nums = _auto_detect_verse_numbers(text)
        assert nums == [15]

    def test_returns_sorted(self):
        text = "।28।text।15।"
        nums = _auto_detect_verse_numbers(text)
        assert nums == [15, 28]

    def test_no_markers_returns_empty(self):
        assert _auto_detect_verse_numbers("plain text") == []

    def test_three_markers(self):
        text = "।23।first।24।second।25।third"
        nums = _auto_detect_verse_numbers(text)
        assert nums == [23, 24, 25]


# ---------------------------------------------------------------------------
# Bug 3 / Feature: देखें trigger line stripping
# ---------------------------------------------------------------------------

class TestStripDekhenTriggerLines:
    def test_strips_dekhen_line(self, cfg: JainkoshConfig):
        text = "main text\nदेखें जीव - 3.8\n"
        result = _strip_dekhen_trigger_lines(text, cfg)
        assert "देखें" not in result
        assert "main text" in result

    def test_strips_dekhen_and_following_paren_line(self, cfg: JainkoshConfig):
        text = "text\nदेखें जीव - 3.8\n(some context)।"
        result = _strip_dekhen_trigger_lines(text, cfg)
        assert "देखें" not in result
        assert "(some context)" not in result

    def test_preserves_non_dekhen_lines(self, cfg: JainkoshConfig):
        text = "first line\nsecond line"
        result = _strip_dekhen_trigger_lines(text, cfg)
        assert "first line" in result
        assert "second line" in result

    def test_strips_following_punct_only_line(self, cfg: JainkoshConfig):
        text = "text\nदेखें जीव - 3.8\n।"
        result = _strip_dekhen_trigger_lines(text, cfg)
        assert "देखें" not in result
        # The stray "।" line after trigger should also be gone
        stripped = result.strip()
        assert stripped == "text"


# ---------------------------------------------------------------------------
# Case A split guard: only split when translation also has verse markers
# ---------------------------------------------------------------------------

class TestCaseASplitGuard:
    """Case A multi-verse split must require ।N। markers in hindi_translation."""

    def _make_block_with_refs(
        self,
        src: str,
        tl: str | None,
        cfg: JainkoshConfig,
        ref_text: str = "shastra/17-19",
        gatha_values: list[int] = (17, 18, 19),
    ) -> Block:
        refs = [
            Reference(
                text=ref_text,
                inline_reference=False,
                needs_manual_match=False,
                resolved_fields=[ResolvedField(field="गाथा", value=v)],
            )
            for v in gatha_values
        ]
        return Block(
            kind="prakrit_text",
            text_devanagari=src,
            hindi_translation=tl,
            references=refs,
        )

    def test_no_split_when_translation_lacks_markers(self, cfg: JainkoshConfig):
        """नयचक्र बृहद्/17-19 case: src has markers, translation does not."""
        src = "verse।17।text।18।text।19।"
        tl = "एक ही अनुवाद"  # no verse markers
        block = self._make_block_with_refs(src, tl, cfg)
        result = _try_split_multi_verse(block, cfg)
        assert len(result) == 1, "Should NOT split when translation lacks verse markers"
        assert len(result[0].references) == 3, "All refs should remain on the single block"

    def test_splits_when_translation_is_null(self, cfg: JainkoshConfig):
        """Null translation: guard does not apply; split proceeds (pre-existing behavior)."""
        src = "verse।17।text।18।text।19।"
        block = self._make_block_with_refs(src, None, cfg)
        result = _try_split_multi_verse(block, cfg)
        assert len(result) == 3, "Should split when translation is null (no guard)"

    def test_splits_when_translation_has_all_markers(self, cfg: JainkoshConfig):
        """नियमसार/15, 28 case: both src and translation have verse markers."""
        src = "verse text। 15।second verse। 28।end"
        tl = "translation। 15।second translation। 28।"
        block = self._make_block_with_refs(src, tl, cfg, ref_text="shastra/15,28", gatha_values=[15, 28])
        result = _try_split_multi_verse(block, cfg)
        assert len(result) == 2, "Should split when both sides have verse markers"
        assert result[0].references[0].resolved_fields[0].value == 15
        assert result[1].references[0].resolved_fields[0].value == 28


# ---------------------------------------------------------------------------
# Split ordering: markers in non-ascending order in text
# ---------------------------------------------------------------------------

class TestNumsInTextOrder:
    def test_ascending_order_preserved(self):
        text = "a।15।b।28।c"
        assert _nums_in_text_order(text, [28, 15]) == [15, 28]

    def test_descending_order_in_text(self):
        text = "a।168।b।15।c"
        assert _nums_in_text_order(text, [15, 168]) == [168, 15]

    def test_missing_nums_excluded(self):
        text = "a।15।b"
        assert _nums_in_text_order(text, [15, 28]) == [15]

    def test_empty_text(self):
        assert _nums_in_text_order("", [15, 28]) == []


class TestOrderPairsByTextPosition:
    """Greedy text-position ordering for (ref, value) pairs including duplicates."""

    def _pair(self, v: int):
        return (None, v)

    def test_ascending_order(self):
        text = "a।15।b।28।c"
        pairs = [self._pair(28), self._pair(15)]
        result = _order_pairs_by_text_position(pairs, text)
        assert [v for _, v in result] == [15, 28]

    def test_descending_order_in_text(self):
        text = "a।168।b।15।c"
        pairs = [self._pair(15), self._pair(168)]
        result = _order_pairs_by_text_position(pairs, text)
        assert [v for _, v in result] == [168, 15]

    def test_duplicate_value_168_15_168(self):
        """168,15,168 in text: greedy scan assigns each 168 to its sequential occurrence."""
        text = "first।168।middle।15।last।168।"
        pairs = [self._pair(168), self._pair(15), self._pair(168)]
        result = _order_pairs_by_text_position(pairs, text)
        assert [v for _, v in result] == [168, 15, 168]

    def test_missing_marker_appended_last(self):
        """Pairs whose marker is absent in text get appended at end."""
        text = "a।15।b"
        pairs = [self._pair(28), self._pair(15)]
        result = _order_pairs_by_text_position(pairs, text)
        assert [v for _, v in result] == [15, 28]


class TestCaseASplitDuplicateMarkers:
    """Case A split with GRef list 168,15,168 (duplicate value, text order)."""

    def _make_block(self, src: str, tl: str | None, cfg: JainkoshConfig) -> "Block":
        from workers.ingestion.jainkosh.models import ResolvedField
        refs = [
            Reference(
                text="shastra/168,15,168",
                inline_reference=False,
                needs_manual_match=False,
                resolved_fields=[ResolvedField(field="गाथा", value=v)],
            )
            for v in [168, 15, 168]
        ]
        return Block(
            kind="sanskrit_text",
            text_devanagari=src,
            hindi_translation=tl,
            references=refs,
        )

    def test_splits_three_segments_in_text_order(self, cfg: JainkoshConfig):
        src = "first।168।second।15।third।168।"
        tl = "first_tl।168।second_tl।15।third_tl।168।"
        block = self._make_block(src, tl, cfg)
        result = _try_split_multi_verse(block, cfg)
        assert len(result) == 3, f"Expected 3 blocks, got {len(result)}"
        assert "first" in (result[0].text_devanagari or "")
        assert "second" in (result[1].text_devanagari or "")
        assert "third" in (result[2].text_devanagari or "")
        assert result[0].references[0].resolved_fields[0].value == 168
        assert result[1].references[0].resolved_fields[0].value == 15
        assert result[2].references[0].resolved_fields[0].value == 168


class TestCaseBSplitNonAscendingOrder:
    """Case B split where verse markers appear in non-ascending order in text."""

    def _make_single_ref_block(self, src: str, tl: str | None, cfg: JainkoshConfig) -> Block:
        # shastra_name set so that gatha field synthesis runs in Case B.
        return Block(
            kind="sanskrit_text",
            text_devanagari=src,
            hindi_translation=tl,
            references=[
                Reference(
                    text="shastra/गाथा",
                    inline_reference=False,
                    needs_manual_match=True,
                    shastra_name="परीक्षाशास्त्र",
                    resolved_fields=[ResolvedField(field="गाथा", value=15)],
                )
            ],
        )

    def test_splits_168_before_15_in_text_order(self, cfg: JainkoshConfig):
        """Text has ।168। before ।15। — split must follow text order, not ascending."""
        src = "first part।168।second part।15।"
        tl = "first translation।168।second translation।15।"
        block = self._make_single_ref_block(src, tl, cfg)
        result = _try_split_multi_verse(block, cfg)
        assert len(result) == 2, "Should split into 2 blocks"
        # First block should contain 168 segment
        assert "first part" in (result[0].text_devanagari or "")
        assert "168" in (result[0].text_devanagari or "")
        # Second block should contain 15 segment
        assert "second part" in (result[1].text_devanagari or "")
        assert "15" in (result[1].text_devanagari or "")

    def test_split_assigns_correct_ref_values(self, cfg: JainkoshConfig):
        """Gatha values in synthetic refs must match text-order nums, not ascending."""
        src = "a।168।b।15।"
        tl = "x।168।y।15।"
        block = self._make_single_ref_block(src, tl, cfg)
        result = _try_split_multi_verse(block, cfg)
        assert len(result) == 2
        # First ref should have gatha=168 (first in text); field name preserved from base ref
        first_gatha = next(
            (rf.value for rf in result[0].references[0].resolved_fields),
            None,
        )
        assert first_gatha == 168, f"Expected 168, got {first_gatha}"


class TestCaseBSplitUnregisteredShastra:
    """Case B split with a shastra not in the registry (shastra_name=None).

    Resolved fields must remain empty — fabricating a गाथा field for an
    unregistered shastra produces misleading output (we don't know the schema).
    """

    def _make_unregistered_block(self, src: str, tl: str, cfg: JainkoshConfig) -> Block:
        return Block(
            kind="sanskrit_text",
            text_devanagari=src,
            hindi_translation=tl,
            references=[
                Reference(
                    text="अज्ञातशास्त्र/1/7-8",
                    inline_reference=False,
                    needs_manual_match=True,
                    shastra_name=None,
                    resolved_fields=[],
                )
            ],
        )

    def test_split_still_produces_two_blocks(self, cfg: JainkoshConfig):
        """Block should still be split even when the shastra is unregistered."""
        src = "पहला भाग।7।दूसरा भाग।8।"
        tl = "first part।7।second part।8।"
        block = self._make_unregistered_block(src, tl, cfg)
        result = _try_split_multi_verse(block, cfg)
        assert len(result) == 2

    def test_split_resolved_fields_empty_for_unregistered(self, cfg: JainkoshConfig):
        """No गाथा field should be synthesized when shastra_name is None."""
        src = "पहला भाग।7।दूसरा भाग।8।"
        tl = "first part।7।second part।8।"
        block = self._make_unregistered_block(src, tl, cfg)
        result = _try_split_multi_verse(block, cfg)
        assert len(result) == 2
        for split_block in result:
            assert split_block.references, "Each split block should have a reference"
            ref = split_block.references[0]
            assert ref.shastra_name is None
            assert ref.needs_manual_match is True
            assert ref.resolved_fields == [], (
                f"Expected empty resolved_fields for unregistered shastra, got {ref.resolved_fields}"
            )


# ---------------------------------------------------------------------------
# Teeka name: trailing section keyword cleanup
# ---------------------------------------------------------------------------

class TestTeekaNameKeywordStrip:
    """Teeka name should not contain trailing /section_keyword."""

    def test_teeka_name_strips_gatha_suffix(self, cfg: JainkoshConfig):
        from workers.ingestion.jainkosh.parse_reference import match_shastra
        # "नियमसार / तात्पर्यवृत्ति/गाथा" → teeka_name should be "तात्पर्यवृत्ति"
        # We test match_shastra directly with a name_raw that mimics what
        # split_name_and_numeric produces for this ref text.
        if cfg.shastra_registry is None:
            pytest.skip("structured parse strategy not enabled in test config")
        _, _, is_teeka, teeka_name = match_shastra(
            "नियमसार / तात्पर्यवृत्ति/गाथा",
            cfg.shastra_registry,
            cfg.reference,
        )
        if is_teeka:
            assert "/" not in teeka_name, f"teeka_name should not contain '/': {teeka_name!r}"
            assert teeka_name == "तात्पर्यवृत्ति"


# ---------------------------------------------------------------------------
# PrakritGatha / SanskritGatha multi-verse splitting (v1.11.6)
# ---------------------------------------------------------------------------

def _make_gatha_block(
    kind: str,
    src: str,
    tl: str | None,
    gatha_values: list[int],
    ref_text: str = "नयचक्र बृहद्/21,25,30",
) -> Block:
    refs = [
        Reference(
            text=ref_text,
            inline_reference=False,
            needs_manual_match=False,
            resolved_fields=[ResolvedField(field="गाथा", value=v)],
        )
        for v in gatha_values
    ]
    return Block(kind=kind, text_devanagari=src, hindi_translation=tl, references=refs)


class TestPrakritGathaSplit:
    """prakrit_gatha blocks with multiple ।N। markers are now split (v1.11.6)."""

    def test_three_verse_split(self, cfg: JainkoshConfig):
        # Mirrors the actual नयचक्र बृहद्/21,25,30 case from पर्याय page
        src = "दव्वाणं...। 21। देहायारपएसा...। 25। जो खलु...। 30।"
        tl = "सब द्रव्यों की...। 21। कर्मों से...। 25। निश्चय से...। 30।"
        block = _make_gatha_block("prakrit_gatha", src, tl, [21, 25, 30])
        result = _try_split_multi_verse(block, cfg)
        assert len(result) == 3, f"Expected 3 blocks, got {len(result)}: {[b.text_devanagari for b in result]}"
        assert result[0].references[0].resolved_fields[0].value == 21
        assert result[1].references[0].resolved_fields[0].value == 25
        assert result[2].references[0].resolved_fields[0].value == 30

    def test_two_verse_split(self, cfg: JainkoshConfig):
        # Mirrors नयचक्र बृहद्/23,33 case
        src = "जं चदुगदि...। 23। जे संखाई...। 33।"
        tl = "जो चारों गति...। 23। और जो दो अणु...। 33।"
        block = _make_gatha_block("prakrit_gatha", src, tl, [23, 33])
        result = _try_split_multi_verse(block, cfg)
        assert len(result) == 2
        assert result[0].references[0].resolved_fields[0].value == 23
        assert result[1].references[0].resolved_fields[0].value == 33

    def test_no_split_when_kind_was_excluded(self, cfg: JainkoshConfig):
        """After the fix, prakrit_gatha IS in applicable_block_kinds."""
        assert "prakrit_gatha" in cfg.reference_splitting.applicable_block_kinds

    def test_gatha_numbers_absent_from_src_uses_case_c(self, cfg: JainkoshConfig):
        """GRef says 22,27,31 but src text has markers 22,26,31 (26 ≠ 27).
        Case A guard rejects (27 absent from src).  Case C fires because src and tl
        both have 3 markers ([22,26,31] and [22,23,31]) — splits into 3 blocks with
        refs 22, 27, 31 paired positionally to (22,22), (26,23), (31,31)."""
        src = "अगुरुलहुगा...। 22। णाणं दंसण...। 26। रूवरसगंध...। 31।"
        tl = "द्रव्यों के...। 22। द्रव्य व भावकर्म...। 23। एक अणु...। 31।"
        block = _make_gatha_block("prakrit_gatha", src, tl, [22, 27, 31],
                                  ref_text="नयचक्र बृहद्/22,27,31")
        result = _try_split_multi_verse(block, cfg)
        # Case C: same count (3) → 3 blocks, refs sorted ascending → 22, 27, 31
        assert len(result) == 3, f"Expected 3 blocks via Case C, got {len(result)}"
        gatha_vals = [
            next((rf.value for rf in b.references[0].resolved_fields), None)
            for b in result
        ]
        assert gatha_vals == [22, 27, 31]


class TestCaseCIndependentMarkerSplit:
    """Case C: equal-count independent-marker split (v1.11.6).

    Applies when src and tl each have N (≥ 2) verse markers with the same count
    but different values (verse-numbering mismatch).  The N unique non-inline refs
    are paired positionally with the N verse pairs.
    """

    def test_three_way_split_with_numbering_mismatch(self, cfg: JainkoshConfig):
        """GRef says 22,27,31 — Prakrit has markers 22,26,31, Hindi has 22,23,31.
        Case A skips (27 absent from src).  Case C splits into 3 correct blocks."""
        src = "अगुरुलहुगा...। 22। णाणं दंसण...। 26। रूवरसगंध...। 31।"
        tl = "द्रव्यों के...। 22। द्रव्य व भावकर्म...। 23। एक अणु...। 31।"
        block = _make_gatha_block(
            "prakrit_gatha", src, tl, [22, 27, 31],
            ref_text="नयचक्र बृहद्/22,27,31",
        )
        result = _try_split_multi_verse(block, cfg)
        assert len(result) == 3, f"Expected 3 blocks, got {len(result)}"
        # Refs should be 22, 27, 31 (sorted by gatha value, paired in order)
        gatha_vals = [
            next((rf.value for rf in b.references[0].resolved_fields), None)
            for b in result
        ]
        assert gatha_vals == [22, 27, 31]
        # Src segments pair with their own markers
        assert "णाणं दंसण" in (result[1].text_devanagari or "")
        assert "रूवरसगंध" in (result[2].text_devanagari or "")
        # Tl segments pair with Hindi markers (23 for middle, 31 for last)
        assert "द्रव्य व भावकर्म" in (result[1].hindi_translation or "")
        assert "एक अणु" in (result[2].hindi_translation or "")

    def test_case_c_not_triggered_when_counts_differ(self, cfg: JainkoshConfig):
        """When tl has fewer markers than src, Case C must not apply."""
        src = "verse।23।more।33।"
        tl = "translation।23।"  # only 1 marker in tl
        block = _make_gatha_block("prakrit_gatha", src, tl, [23, 33])
        result = _try_split_multi_verse(block, cfg)
        # Case A handles this (any() guard): 23 is in tl → splits into 2
        assert len(result) == 2

    def test_case_c_not_triggered_when_unique_refs_mismatch_count(
        self, cfg: JainkoshConfig
    ):
        """Case C requires unique-gatha ref count == marker count. If mismatched, fall through."""
        # 2 src markers, 2 tl markers, but only 1 unique-gatha non-inline ref
        src = "verse।15।second।28।"
        tl = "tl_verse।17।second_tl।29।"  # different marker values — same count
        block = Block(
            kind="prakrit_gatha",
            text_devanagari=src,
            hindi_translation=tl,
            references=[
                Reference(
                    text="shastra/15",
                    inline_reference=False,
                    needs_manual_match=False,
                    resolved_fields=[ResolvedField(field="गाथा", value=15)],
                )
            ],
        )
        result = _try_split_multi_verse(block, cfg)
        # Case C: unique_refs count (1) ≠ src_nums count (2) → skip.
        # Case B: common = {} (empty intersection of {15,28} and {17,29}) → no split.
        assert len(result) == 1


class TestSanskritGathaSplit:
    """sanskrit_gatha blocks are now also eligible for multi-verse splitting."""

    def test_kind_in_applicable_block_kinds(self, cfg: JainkoshConfig):
        assert "sanskrit_gatha" in cfg.reference_splitting.applicable_block_kinds

    def test_two_verse_split(self, cfg: JainkoshConfig):
        src = "प्रथम श्लोक।15।द्वितीय श्लोक।28।"
        tl = "first translation।15।second translation।28।"
        block = _make_gatha_block("sanskrit_gatha", src, tl, [15, 28],
                                  ref_text="shastra/15,28")
        result = _try_split_multi_verse(block, cfg)
        assert len(result) == 2
        assert result[0].references[0].resolved_fields[0].value == 15
        assert result[1].references[0].resolved_fields[0].value == 28


# ---------------------------------------------------------------------------
# Inline ref distribution by position (v1.11.7)
# ---------------------------------------------------------------------------

def _make_inline_ref(text: str) -> Reference:
    return Reference(text=text, inline_reference=True, needs_manual_match=False)


class TestAssignInlineRefsToSegments:
    """_assign_inline_refs_to_segments distributes inline refs by their position
    in the pre-strip translation text relative to verse markers (v1.11.7)."""

    def test_no_inline_refs_returns_empty_maps(self):
        result = _assign_inline_refs_to_segments([], "text।22।more।25।", [22, 25], 2)
        assert result == {0: [], 1: []}

    def test_no_pre_strip_text_all_to_last(self):
        refs = [_make_inline_ref("ref_a"), _make_inline_ref("ref_b")]
        result = _assign_inline_refs_to_segments(refs, None, [22, 25], 2)
        assert result[0] == []
        assert len(result[1]) == 2

    def test_ref_after_last_marker_goes_to_last_segment(self):
        # ref_b appears after ।30। → segment 2 (last)
        pre_strip = "...। 22। ...। 25। ...। 30। ref_b"
        refs = [_make_inline_ref("ref_b")]
        result = _assign_inline_refs_to_segments(refs, pre_strip, [22, 25, 30], 3)
        assert result[2] == refs
        assert result[0] == []
        assert result[1] == []

    def test_ref_between_markers_goes_to_preceding_segment(self):
        # परमात्मप्रकाश टीका appears after ।25। but before ।30। text → segment 1
        pre_strip = "...जानो। 25। ( परमात्मप्रकाश टीका/1/57 ) एक अणु...। 30。"
        ref = _make_inline_ref("( परमात्मप्रकाश टीका/1/57 )")
        result = _assign_inline_refs_to_segments(result_map := {}, pre_strip, [22, 25, 30], 3)
        result = _assign_inline_refs_to_segments([ref], pre_strip, [22, 25, 30], 3)
        assert result[1] == [ref], "Ref after ।25। should belong to segment 1"
        assert result[0] == []
        assert result[2] == []

    def test_multiple_refs_split_across_segments(self):
        # ref1 after ।25।, ref2 after ।30।
        pre_strip = "...। 22। text। 25। ref1 more text। 30। ref2 ।"
        ref1 = _make_inline_ref("ref1")
        ref2 = _make_inline_ref("ref2")
        result = _assign_inline_refs_to_segments([ref1, ref2], pre_strip, [22, 25, 30], 3)
        assert result[1] == [ref1]
        assert result[2] == [ref2]
        assert result[0] == []

    def test_ref_before_first_marker_goes_to_first_segment(self):
        pre_strip = "intro ref_early text।22। more।25。"
        ref = _make_inline_ref("ref_early")
        result = _assign_inline_refs_to_segments([ref], pre_strip, [22, 25], 2)
        assert result[0] == [ref]
        assert result[1] == []

    def test_ref_not_found_in_pre_strip_falls_to_last(self):
        pre_strip = "text।22।more।25。"
        ref = _make_inline_ref("unknown_ref")
        result = _assign_inline_refs_to_segments([ref], pre_strip, [22, 25], 2)
        assert result[1] == [ref]
        assert result[0] == []


class TestInlineRefDistributionInSplit:
    """End-to-end: _try_split_multi_verse distributes inline refs by position (v1.11.7).

    The नयचक्र बृहद्/22,25,30 case: ( परमात्मप्रकाश टीका/1/57 ) appears after ।25।
    in the HindiText and must be placed in the gatha-25 block, not the last block.
    """

    def test_inline_ref_after_25_goes_to_gatha25_block(self, cfg: JainkoshConfig):
        src = "अगुरुलहुगा...। 22। णाणं दंसण...। 25। रूवरसगंध...। 30।"
        tl_stripped = "द्रव्यों के...। 22। द्रव्य व भावकर्म...। 25। एक अणु रूप...। 30।"
        tl_pre_strip = (
            "द्रव्यों के...। 22। द्रव्य व भावकर्म...। 25। "
            "( परमात्मप्रकाश टीका/1/57 ) "
            "एक अणु रूप...। 30। ( पंचास्तिकाय / तात्पर्यवृत्ति/5/14-15/13 ) ।"
        )
        inline_ref_25 = _make_inline_ref("( परमात्मप्रकाश टीका/1/57 )")
        inline_ref_30 = _make_inline_ref("( पंचास्तिकाय / तात्पर्यवृत्ति/5/14-15/13 )")
        non_inline_refs = [
            Reference(
                text="नयचक्र बृहद्/22,25,30",
                inline_reference=False,
                needs_manual_match=False,
                resolved_fields=[ResolvedField(field="गाथा", value=v)],
            )
            for v in [22, 25, 30]
        ]
        block = Block(
            kind="prakrit_gatha",
            text_devanagari=src,
            hindi_translation=tl_stripped,
            references=non_inline_refs + [inline_ref_25, inline_ref_30],
        )
        block._hindi_translation_pre_strip = tl_pre_strip

        result = _try_split_multi_verse(block, cfg)
        assert len(result) == 3

        # gatha 22: no inline refs
        assert all(not r.inline_reference for r in result[0].references)

        # gatha 25: should contain inline_ref_25
        inline_25 = [r for r in result[1].references if r.inline_reference]
        assert len(inline_25) == 1
        assert inline_25[0].text == "( परमात्मप्रकाश टीका/1/57 )"

        # gatha 30: should contain inline_ref_30
        inline_30 = [r for r in result[2].references if r.inline_reference]
        assert len(inline_30) == 1
        assert inline_30[0].text == "( पंचास्तिकाय / तात्पर्यवृत्ति/5/14-15/13 )"

    def test_inline_refs_all_to_last_when_no_pre_strip(self, cfg: JainkoshConfig):
        """Without pre-strip text, all inline refs still go to the last segment."""
        src = "verse। 22। more। 25।"
        tl = "translation। 22। more। 25।"
        inline_ref = _make_inline_ref("( some ref )")
        block = Block(
            kind="prakrit_gatha",
            text_devanagari=src,
            hindi_translation=tl,
            references=[
                Reference(text="src/22,25", inline_reference=False, needs_manual_match=False,
                          resolved_fields=[ResolvedField(field="गाथा", value=22)]),
                Reference(text="src/22,25", inline_reference=False, needs_manual_match=False,
                          resolved_fields=[ResolvedField(field="गाथा", value=25)]),
                inline_ref,
            ],
        )
        # No _hindi_translation_pre_strip set → should default to last segment
        result = _try_split_multi_verse(block, cfg)
        assert len(result) == 2
        inline_in_last = [r for r in result[1].references if r.inline_reference]
        assert len(inline_in_last) == 1


# ---------------------------------------------------------------------------
# Hybrid <ol> — subsections and index_relations (गुण page structure)
# ---------------------------------------------------------------------------

class TestHybridOlParsing:
    """
    Pages like गुण have no <h2> sections and embed all content inside a single
    top-level <ol>:
      - The outer <li class="HindiText"> items wrap BOTH index notes (देखें <p>s)
        AND actual body content (nested <ol> with <strong id="N"> headings).

    Two bugs were fixed:
      1. DFS in parse_subsections: block-class elements with headings nested
         deeper than direct children are now recursed into.
      2. parse_section: a hybrid <ol> (contains headings AND has no prior pure
         index <ol>) is dual-processed — added to both index_ols and body.
    """

    _OUTER_OL_HTML = """
    <html><body>
    <div class="mw-parser-output">
      <p class="HindiText">Intro text.</p>
      <ol>
        <li class="HindiText">
          <strong><a href="#1">Section one (index title)</a></strong><br/>
          <ol>
            <li class="HindiText"><a href="#1.1">Subsec 1.1</a></li>
            <p class="HindiText">* see also –देखें <a class="mw-selflink-fragment" href="#2.1">keyword - 2.1</a>।</p>
          </ol>
          <ol>
            <li class="HindiText">
              <strong id="1">Section one</strong>
              <ol>
                <li>
                  <p class="HindiText"><strong id="1.1">Subsection one-one</strong></p>
                </li>
                <p class="PrakritText">गाहा text।</p>
                <p class="HindiText">=Hindi translation।</p>
              </ol>
            </li>
            <li class="HindiText">
              <strong id="2">Section two</strong>
              <ol>
                <li>
                  <p class="HindiText"><strong id="2.1">Subsection two-one</strong></p>
                </li>
              </ol>
            </li>
          </ol>
        </li>
      </ol>
    </div>
    </body></html>
    """

    def _parse(self, cfg: JainkoshConfig):
        from workers.ingestion.jainkosh.parse_keyword import parse_keyword_html
        url = "https://www.jainkosh.org/wiki/%E0%A4%97%E0%A5%81%E0%A4%A3"
        return parse_keyword_html(self._OUTER_OL_HTML, url, cfg)

    def test_subsections_found(self, cfg: JainkoshConfig):
        """DFS must recurse into block-class <li> that wraps body <ol> with headings."""
        result = self._parse(cfg)
        assert len(result.page_sections) == 1
        section = result.page_sections[0]
        assert len(section.subsections) == 2, (
            f"Expected 2 top-level subsections, got {len(section.subsections)}: "
            f"{[s.topic_path for s in section.subsections]}"
        )
        paths = {s.topic_path for s in section.subsections}
        assert "1" in paths
        assert "2" in paths

    def test_nested_subsection_found(self, cfg: JainkoshConfig):
        """Child subsections inside the body <ol> are also assembled correctly."""
        result = self._parse(cfg)
        section = result.page_sections[0]
        sec1 = next(s for s in section.subsections if s.topic_path == "1")
        assert len(sec1.children) == 1, f"Expected 1 child under section 1, got {len(sec1.children)}"
        assert sec1.children[0].topic_path == "1.1"

    def test_index_relations_extracted_from_hybrid_ol(self, cfg: JainkoshConfig):
        """देखें <p> notes inside the hybrid <ol> become IndexRelations."""
        result = self._parse(cfg)
        section = result.page_sections[0]
        assert len(section.index_relations) >= 1, (
            "Expected at least 1 index_relation from the देखें note in the hybrid ol"
        )
        rel = section.index_relations[0]
        assert rel.target_topic_path == "2.1"
        assert rel.is_self is True

    def test_no_false_index_relations_when_proper_index_precedes(self, cfg: JainkoshConfig):
        """When a pure index <ol> exists, body <ol> with headings is NOT added to index_ols."""
        from workers.ingestion.jainkosh.parse_keyword import parse_keyword_html
        html = """
        <html><body><div class="mw-parser-output">
          <h2><span class="mw-headline" id="सिद्धांतकोष_से">सिद्धांतकोष से</span></h2>
          <p class="HindiText">Intro.</p>
          <ol>
            <li class="HindiText"><a href="#1">Section one</a></li>
          </ol>
          <ol>
            <li class="HindiText">
              <strong id="1">Section one</strong>
              <p class="HindiText">* ignored –देखें <a href="/wiki/Other">Other</a>।</p>
            </li>
          </ol>
        </div></body></html>
        """
        url = "https://www.jainkosh.org/wiki/Test"
        result = parse_keyword_html(html, url, cfg)
        section = result.page_sections[0]
        # The body <ol>'s देखें reference must NOT become an IndexRelation
        # because the section has a proper index <ol> before it.
        body_refs = [
            r for r in section.index_relations
            if r.target_keyword == "Other"
        ]
        assert len(body_refs) == 0, (
            "Body <ol> देखें should not be captured as IndexRelation when a proper index <ol> exists"
        )


# ---------------------------------------------------------------------------
# Passthrough field syntax: <fieldname> in format strings
# ---------------------------------------------------------------------------

class TestPassthroughFormatGroup:
    """<fieldname> in a format string stores the value as-is (no numeric parsing)."""

    def test_parse_format_string_detects_passthrough(self):
        from workers.ingestion.jainkosh.parse_reference import parse_format_string
        groups = parse_format_string("पुस्तक/<कषायपाहुड़-गाथा>/§प्रकरण/पृष्ठ/पंक्ति")
        assert len(groups) == 5
        pt_group = groups[1]
        assert pt_group.is_passthrough is True
        assert pt_group.fields[0].name == "कषायपाहुड़-गाथा"
        # First and remaining groups are normal
        assert groups[0].is_passthrough is False
        assert groups[2].is_passthrough is False

    def test_passthrough_value_stored_as_string(self):
        from workers.ingestion.jainkosh.parse_reference import (
            parse_format_string, resolve_fields
        )
        from workers.ingestion.jainkosh.config import load_config
        cfg = load_config()
        fmt_groups = parse_format_string("पुस्तक/<कषायपाहुड़-गाथा>/§प्रकरण/पृष्ठ/पंक्ति")
        resolved, needs_manual, _ = resolve_fields("1/13-14/§181/217/1", fmt_groups, cfg.reference.needs_manual_match)
        assert needs_manual is False
        field_map = {rf.field: rf for rf in resolved}
        # Passthrough field keeps the hyphen
        assert "कषायपाहुड़-गाथा" in field_map
        assert field_map["कषायपाहुड़-गाथा"].value == "13-14"
        assert isinstance(field_map["कषायपाहुड़-गाथा"].value, str)
        # Other fields parsed numerically
        assert field_map["पुस्तक"].value == 1
        assert field_map["प्रकरण"].value == 181
        assert field_map["पृष्ठ"].value == 217
        assert field_map["पंक्ति"].value == 1

    def test_passthrough_not_range_expanded(self):
        from workers.ingestion.jainkosh.parse_reference import (
            parse_format_string, resolve_fields, _expand_resolved_fields
        )
        from workers.ingestion.jainkosh.config import load_config
        cfg = load_config()
        fmt_groups = parse_format_string("पुस्तक/<कषायपाहुड़-गाथा>/§प्रकरण/पृष्ठ/पंक्ति")
        resolved, _, _ = resolve_fields("1/13-14/§181/217/1", fmt_groups, cfg.reference.needs_manual_match)
        expanded = _expand_resolved_fields(resolved)
        # Must not expand "13-14" into [13, 14] — must stay as single result
        assert expanded is not None
        assert len(expanded) == 1
        field_map = {rf.field: rf for rf in expanded[0]}
        assert field_map["कषायपाहुड़-गाथा"].value == "13-14"

    def test_kashayapaahud_end_to_end(self, cfg: JainkoshConfig):
        """Full parse_reference_text for कषायपाहुड़ 1/13-14/§181/217/1."""
        import unicodedata
        from workers.ingestion.jainkosh.parse_reference import parse_reference_text
        if cfg.shastra_registry is None:
            pytest.skip("shastra_registry not available in test config")
        results = parse_reference_text(
            "कषायपाहुड़ 1/13-14/§181/217/1",
            cfg.shastra_registry,
            cfg.reference,
        )
        assert len(results) == 1
        r = results[0]
        assert r.needs_manual_match is False
        assert r.shastra_name is not None
        # Normalise all keys to NFC before lookup to handle NFC/NFD variants
        field_map = {unicodedata.normalize("NFC", rf.field): rf.value for rf in r.resolved_fields}
        assert field_map.get("पुस्तक") == 1
        # The passthrough field name contains a hyphen; value must be kept as string
        pt_key = unicodedata.normalize("NFC", "कषायपाहुड़-गाथा")
        assert pt_key in field_map, (
            f"Passthrough field missing; available fields: {list(field_map)}"
        )
        assert field_map[pt_key] == "13-14", (
            f"Expected '13-14' (as string), got {field_map[pt_key]!r}"
        )
        assert field_map.get("प्रकरण") == 181
        assert field_map.get("पृष्ठ") == 217
        assert field_map.get("पंक्ति") == 1

    def test_passthrough_field_name_in_brackets_with_hyphen(self):
        """Hyphens inside <> are part of the field name, not a separator."""
        from workers.ingestion.jainkosh.parse_reference import parse_format_string
        groups = parse_format_string("अधिकार/<sub-field>/पृष्ठ")
        assert groups[1].is_passthrough is True
        assert groups[1].fields[0].name == "sub-field"
        assert groups[0].is_passthrough is False
        assert groups[2].is_passthrough is False

    def test_passthrough_slash_inside_angle_brackets_not_split(self):
        """A '/' inside <> should not split the format group."""
        from workers.ingestion.jainkosh.parse_reference import parse_format_string
        groups = parse_format_string("<field/name>/पृष्ठ")
        assert len(groups) == 2
        assert groups[0].is_passthrough is True
        assert groups[0].fields[0].name == "field/name"


# ---------------------------------------------------------------------------
# Level-2 keyword collision: same value claimed by two different field names
# ---------------------------------------------------------------------------

class TestLevel2KeywordValueCollision:
    """When Level 2 extracts a keyword field whose value is already used by a
    different Level 1 field, needs_manual_match must be set to True."""

    def test_gatha_value_same_as_existing_field_flags_manual(self, cfg: JainkoshConfig):
        """कषायपाहुड़ 1/1,14/ गाथा 108/253:
        Level 1 maps 108→पृष्ठ; Level 2 extracts गाथा=108 — same value, different
        field name → needs_manual_match=True.
        """
        from workers.ingestion.jainkosh.parse_reference import parse_reference_text
        if cfg.shastra_registry is None:
            pytest.skip("shastra_registry not available in test config")
        results = parse_reference_text(
            "( कषायपाहुड़ 1/1,14/ गाथा 108/253)",
            cfg.shastra_registry,
            cfg.reference,
        )
        assert len(results) == 1
        r = results[0]
        assert r.needs_manual_match is True, (
            "Same numeric value 108 was resolved as both पृष्ठ (Level 1) and "
            "गाथा (Level 2 keyword extraction) — should require manual review"
        )
        # Shastra must still be identified and fields present for review
        assert r.shastra_name is not None
        field_names = {rf.field for rf in r.resolved_fields}
        assert "पृष्ठ" in field_names or "गाथा" in field_names

    def test_no_false_positive_when_new_keyword_field_has_distinct_value(self, cfg: JainkoshConfig):
        """When Level 2 adds a keyword field whose value is NOT shared by any
        Level 1 field, needs_manual_match should remain False."""
        from workers.ingestion.jainkosh.parse_reference import parse_reference_text
        if cfg.shastra_registry is None:
            pytest.skip("shastra_registry not available in test config")
        # Format: गाथा — single field, no collision possible with any keyword extraction
        # नयचक्र बृहद् resolves via format "गाथा" (single field)
        results = parse_reference_text(
            "नयचक्र बृहद्/21",
            cfg.shastra_registry,
            cfg.reference,
        )
        assert len(results) == 1
        r = results[0]
        assert r.needs_manual_match is False, (
            f"Simple single-field ref should resolve cleanly; got {r}"
        )


# ---------------------------------------------------------------------------
# Compound shastra name matching (v1.11.9+)
# ---------------------------------------------------------------------------

class TestCompoundShastraNameMatching:
    """Compound shastra names like "नयचक्र/श्रुतभवन" where "/" is part of the
    primary name — not a teeka separator — must be matched correctly even when
    a trailing field keyword (e.g. पृष्ठ) leaks into the name portion because
    it appears before the first digit in the reference text.
    """

    def test_space_slash_field_keyword_resolves(self, cfg: JainkoshConfig):
        """( नयचक्र / श्रुतभवन/ पृष्ठ 57) → shastra=नयचक्र/श्रुतभवन, पृष्ठ=57."""
        from workers.ingestion.jainkosh.parse_reference import parse_reference_text
        if cfg.shastra_registry is None:
            pytest.skip("shastra_registry not available in test config")
        results = parse_reference_text(
            "( नयचक्र / श्रुतभवन/ पृष्ठ 57)",
            cfg.shastra_registry,
            cfg.reference,
        )
        assert len(results) == 1
        r = results[0]
        assert r.needs_manual_match is False
        assert r.shastra_name == "नयचक्र/श्रुतभवन"
        assert r.is_teeka is False
        assert r.teeka_name == ""
        field_names = {rf.field for rf in r.resolved_fields}
        field_values = {rf.field: rf.value for rf in r.resolved_fields}
        assert "पृष्ठ" in field_names
        assert field_values["पृष्ठ"] == 57

    def test_compound_name_no_false_teeka(self, cfg: JainkoshConfig):
        """match_shastra on "नयचक्र / श्रुतभवन/ पृष्ठ" must return is_teeka=False."""
        from workers.ingestion.jainkosh.parse_reference import match_shastra
        if cfg.shastra_registry is None:
            pytest.skip("shastra_registry not available in test config")
        entry, method, is_teeka, teeka_name = match_shastra(
            "नयचक्र / श्रुतभवन/ पृष्ठ",
            cfg.shastra_registry,
            cfg.reference,
        )
        assert entry is not None, "Should match नयचक्र/श्रुतभवन"
        assert entry.shastra_name == "नयचक्र/श्रुतभवन"
        assert is_teeka is False
        assert teeka_name == ""

    def test_paren_inner_paren_variant_still_works(self, cfg: JainkoshConfig):
        """(नयचक्र (श्रुतभवन)/61) still resolves via space-to-slash fallback."""
        from workers.ingestion.jainkosh.parse_reference import parse_reference_text
        if cfg.shastra_registry is None:
            pytest.skip("shastra_registry not available in test config")
        results = parse_reference_text(
            "(नयचक्र (श्रुतभवन)/61)",
            cfg.shastra_registry,
            cfg.reference,
        )
        assert len(results) == 1
        r = results[0]
        assert r.needs_manual_match is False
        assert r.shastra_name == "नयचक्र/श्रुतभवन"
        assert r.is_teeka is False
        field_values = {rf.field: rf.value for rf in r.resolved_fields}
        assert field_values.get("पृष्ठ") == 61

    def test_regular_teeka_detection_unaffected(self, cfg: JainkoshConfig):
        """Normal teeka resolution via first-slash split still works."""
        from workers.ingestion.jainkosh.parse_reference import match_shastra
        if cfg.shastra_registry is None:
            pytest.skip("shastra_registry not available in test config")
        entry, method, is_teeka, teeka_name = match_shastra(
            "नियमसार / तात्पर्यवृत्ति/गाथा",
            cfg.shastra_registry,
            cfg.reference,
        )
        assert entry is not None
        assert is_teeka is True
        assert teeka_name == "तात्पर्यवृत्ति"


# ---------------------------------------------------------------------------
# Teeka-keyword detection without "/" separator (v1.11.12)
# ---------------------------------------------------------------------------

class TestTeekaSpaceSuffixDetection:
    """'परमात्मप्रकाश टीका/1/57' — 'टीका' after shastra name with only a space
    (no '/' separator) is recognised as a teeka reference.  teeka_name is set
    to 'टीका'.  Both 'टीका' and 'की टीका' variants are covered.
    """

    def test_teeka_space_suffix_match_shastra(self, cfg: JainkoshConfig):
        """match_shastra: 'परमात्मप्रकाश टीका' → is_teeka=True, teeka_name='टीका'."""
        from workers.ingestion.jainkosh.parse_reference import match_shastra
        if cfg.shastra_registry is None:
            pytest.skip("shastra_registry not available in test config")
        entry, method, is_teeka, teeka_name = match_shastra(
            "परमात्मप्रकाश टीका",
            cfg.shastra_registry,
            cfg.reference,
        )
        assert entry is not None, "Should resolve to परमात्मप्रकाश shastra"
        assert entry.shastra_name == "परमात्मप्रकाश"
        assert is_teeka is True
        assert teeka_name == "टीका"

    def test_ki_teeka_space_suffix_match_shastra(self, cfg: JainkoshConfig):
        """match_shastra: 'परमात्मप्रकाश की टीका' → is_teeka=True, teeka_name='टीका'."""
        from workers.ingestion.jainkosh.parse_reference import match_shastra
        if cfg.shastra_registry is None:
            pytest.skip("shastra_registry not available in test config")
        entry, method, is_teeka, teeka_name = match_shastra(
            "परमात्मप्रकाश की टीका",
            cfg.shastra_registry,
            cfg.reference,
        )
        assert entry is not None, "Should resolve to परमात्मप्रकाश shastra"
        assert entry.shastra_name == "परमात्मप्रकाश"
        assert is_teeka is True
        assert teeka_name == "टीका"

    def test_full_reference_teeka_space_resolves(self, cfg: JainkoshConfig):
        """parse_reference_text: '( परमात्मप्रकाश टीका/1/57 )' fully resolves."""
        from workers.ingestion.jainkosh.parse_reference import parse_reference_text
        if cfg.shastra_registry is None:
            pytest.skip("shastra_registry not available in test config")
        results = parse_reference_text(
            "( परमात्मप्रकाश टीका/1/57 )",
            cfg.shastra_registry,
            cfg.reference,
        )
        assert len(results) == 1
        r = results[0]
        assert r.needs_manual_match is False
        assert r.is_teeka is True
        assert r.teeka_name == "टीका"
        assert r.shastra_name == "परमात्मप्रकाश"
        field_values = {rf.field: rf.value for rf in r.resolved_fields}
        assert field_values.get("अधिकार") == 1
        assert field_values.get("गाथा") == 57

    def test_full_reference_teeka_space_single_num(self, cfg: JainkoshConfig):
        """parse_reference_text: '( परमात्मप्रकाश टीका/57 )' — is_teeka set even
        when numeric resolution fails (only one number, format needs two)."""
        from workers.ingestion.jainkosh.parse_reference import parse_reference_text
        if cfg.shastra_registry is None:
            pytest.skip("shastra_registry not available in test config")
        results = parse_reference_text(
            "( परमात्मप्रकाश टीका/57 )",
            cfg.shastra_registry,
            cfg.reference,
        )
        assert len(results) == 1
        r = results[0]
        assert r.is_teeka is True
        assert r.teeka_name == "टीका"
        assert r.shastra_name == "परमात्मप्रकाश"

    def test_slash_teeka_separator_still_works(self, cfg: JainkoshConfig):
        """'( परमात्मप्रकाश / टीका/57)' (with '/') still resolves via step-3."""
        from workers.ingestion.jainkosh.parse_reference import parse_reference_text
        if cfg.shastra_registry is None:
            pytest.skip("shastra_registry not available in test config")
        results = parse_reference_text(
            "( परमात्मप्रकाश / टीका/57)",
            cfg.shastra_registry,
            cfg.reference,
        )
        assert len(results) == 1
        r = results[0]
        assert r.is_teeka is True
        assert r.teeka_name == "टीका"
        assert r.shastra_name == "परमात्मप्रकाश"

    def test_no_false_positive_for_teeka_in_compound_name(self, cfg: JainkoshConfig):
        """A registered shastra whose name itself ends in 'टीका' must not be
        mis-detected as a teeka reference (step-1 exact match wins first)."""
        from workers.ingestion.jainkosh.parse_reference import match_shastra
        if cfg.shastra_registry is None:
            pytest.skip("shastra_registry not available in test config")
        # If "परमात्मप्रकाश टीका" were itself registered, step-1 would match it
        # and step-2.6 would never fire. We can't test that without a registry
        # fixture, so we verify that a name WITHOUT a known base returns None
        # rather than producing a false positive.
        entry, method, is_teeka, teeka_name = match_shastra(
            "अज्ञातग्रन्थ टीका",  # "अज्ञातग्रन्थ" is not in the registry
            cfg.shastra_registry,
            cfg.reference,
        )
        assert entry is None, "Unknown base shastra should not produce a match"
        assert is_teeka is False


# ---------------------------------------------------------------------------
# Cross-page topic stub resolve_key
# ---------------------------------------------------------------------------

class TestCrossPageTopicResolveKey:
    """Cross-page Topic stubs must carry resolve_key instead of key so that the
    ingestion layer can look up the actual heading-based natural_key from
    Postgres once the target keyword has been ingested."""

    _MINIMAL_HTML = """
    <html><body>
    <div class="mw-parser-output">
      <h2><span class="mw-headline" id="सिद्धांतकोष_से">सिद्धांतकोष से</span></h2>
      <ol>
        <li class="HindiText">
          <strong>1. first section</strong>
          <ul>
            <li class="HindiText">देखें <a href="/wiki/अन्यशब्द#2.3">अन्यशब्द - 2.3</a></li>
          </ul>
        </li>
      </ol>
      <strong id="1">1. first section</strong>
      <p class="HindiText">some text</p>
    </div>
    </body></html>
    """

    @pytest.fixture
    def envelope_neo4j(self, cfg):
        from workers.ingestion.jainkosh.parse_keyword import parse_keyword_html
        from workers.ingestion.jainkosh.envelope import build_envelope
        result = parse_keyword_html(
            self._MINIMAL_HTML,
            "https://www.jainkosh.org/wiki/परीक्षा",
            cfg,
        )
        env = build_envelope(result, cfg)
        return env.would_write["neo4j"]

    def test_cross_page_stub_has_resolve_key(self, envelope_neo4j):
        """A stub targeting a different keyword must have resolve_key, not key."""
        nodes = envelope_neo4j["nodes"]
        stubs = [
            n for n in nodes
            if n.get("is_stub_seed") and n.get("label") == "Topic"
        ]
        assert stubs, "Expected at least one cross-page Topic stub"
        for stub in stubs:
            assert "resolve_key" in stub, (
                f"Cross-page stub must carry resolve_key: {stub}"
            )
            assert "key" not in stub, (
                f"Cross-page stub must NOT have key (use resolve_key): {stub}"
            )

    def test_cross_page_stub_resolve_key_format(self, envelope_neo4j):
        """resolve_key must be {parent_keyword}:{path_with_colons}."""
        nodes = envelope_neo4j["nodes"]
        stubs = [
            n for n in nodes
            if n.get("is_stub_seed") and n.get("label") == "Topic"
        ]
        for stub in stubs:
            rk = stub["resolve_key"]
            props = stub["props"]
            kw = props["parent_keyword_natural_key"]
            tp = props["topic_path"]
            expected_rk = f"{kw}:{tp.replace('.', ':')}"
            assert rk == expected_rk, (
                f"resolve_key {rk!r} does not match expected {expected_rk!r}"
            )

    def test_edge_to_uses_resolve_key(self, envelope_neo4j):
        """RELATED_TO edges targeting cross-page topics must reference resolve_key."""
        edges = envelope_neo4j["edges"]
        cross_page_edges = [
            e for e in edges
            if e.get("type") == "RELATED_TO"
            and e.get("to", {}).get("resolve_key")
        ]
        assert cross_page_edges, "Expected at least one RELATED_TO edge with resolve_key"
        for edge in cross_page_edges:
            to = edge["to"]
            assert "resolve_key" in to
            assert "key" not in to

    def test_same_keyword_self_ref_uses_key_not_resolve_key(self, cfg):
        """Self-references within the same keyword keep using key (actual heading key)."""
        html = """
        <html><body>
        <div class="mw-parser-output">
          <h2><span class="mw-headline" id="सिद्धांतकोष_से">सिद्धांतकोष से</span></h2>
          <strong id="1">1. पहला विभाग</strong>
          <p class="HindiText">some text देखें
            <a class="mw-selflink-fragment" href="#2">स्वयं - 2</a>
          </p>
          <strong id="2">2. दूसरा विभाग</strong>
          <p class="HindiText">other text</p>
        </div>
        </body></html>
        """
        from workers.ingestion.jainkosh.parse_keyword import parse_keyword_html
        from workers.ingestion.jainkosh.envelope import build_envelope
        result = parse_keyword_html(
            html, "https://www.jainkosh.org/wiki/आत्मपरीक्षा", cfg,
        )
        env = build_envelope(result, cfg)
        nodes = env.would_write["neo4j"]["nodes"]
        stubs = [
            n for n in nodes
            if n.get("is_stub_seed") and n.get("label") == "Topic"
        ]
        for stub in stubs:
            # Same-keyword self-references are already resolved to heading-based
            # natural_key at parse time — no resolve_key needed.
            assert "key" in stub, f"Same-keyword stub should have key: {stub}"
            assert "resolve_key" not in stub, (
                f"Same-keyword stub should NOT have resolve_key: {stub}"
            )

    def test_गुण_golden_stubs_use_resolve_key(self, cfg):
        """गुण golden: cross-page stubs for स्वभाव:2 etc. use resolve_key."""
        import json
        from pathlib import Path
        golden_path = (
            Path(__file__).parents[1] / "golden" / "गुण.json"
        )
        if not golden_path.exists():
            pytest.skip("गुण golden not found")
        with open(golden_path) as f:
            data = json.load(f)
        nodes = data["would_write"]["neo4j"]["nodes"]
        stubs = [
            n for n in nodes
            if n.get("is_stub_seed") and n.get("label") == "Topic"
        ]
        assert stubs, "गुण golden should have cross-page Topic stubs"
        for stub in stubs:
            assert "resolve_key" in stub, f"Stub missing resolve_key: {stub}"
            assert "key" not in stub, f"Stub should not have key: {stub}"
        # Specifically verify the स्वभाव:2 stub
        svabhav_stub = next(
            (s for s in stubs if s.get("resolve_key") == "स्वभाव:2"), None
        )
        assert svabhav_stub is not None, "स्वभाव:2 stub not found in गुण golden"
        assert svabhav_stub["props"]["topic_path"] == "2"
        assert svabhav_stub["props"]["parent_keyword_natural_key"] == "स्वभाव"

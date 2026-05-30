"""Tests for multi-verse block splitting, keyword underscore handling,
नयचक्र/श्रुतभवन matching, and hindi_text bhaavarth edge emission."""

from __future__ import annotations

import pytest

from workers.ingestion.jainkosh.config import load_config
from workers.ingestion.jainkosh.models import Block, Reference, ResolvedField
from workers.ingestion.jainkosh.parse_blocks import (
    _split_text_at_verse_markers,
    split_multi_verse_blocks,
)


# ---------------------------------------------------------------------------
# 1. _split_text_at_verse_markers
# ---------------------------------------------------------------------------

class TestSplitTextAtVerseMarkers:
    def test_two_verse_both_markers_present(self):
        text = "अत्थित्ति...।59। चेदणमचेदणं...।60।"
        segs = _split_text_at_verse_markers(text, [59, 60])
        assert len(segs) == 2
        assert segs[0] == "अत्थित्ति...।59।"
        assert segs[1] == "चेदणमचेदणं...।60।"

    def test_three_verse_all_markers_present(self):
        text = "A।19। B।96। C।98।"
        segs = _split_text_at_verse_markers(text, [19, 96, 98])
        assert len(segs) == 3
        assert segs[0] == "A।19।"
        assert segs[1] == "B।96।"
        assert segs[2] == "C।98।"

    def test_last_verse_marker_absent_in_translation(self):
        text = "अस्तित्व...।59। चेतन...विशेष स्वभाव हैं।"
        segs = _split_text_at_verse_markers(text, [59, 60])
        assert len(segs) == 2
        assert segs[0] == "अस्तित्व...।59।"
        assert "चेतन" in segs[1]

    def test_empty_text_returns_empty_segments(self):
        segs = _split_text_at_verse_markers("", [1, 2])
        assert all(s == "" for s in segs)

    def test_single_verse_returns_unchanged(self):
        text = "कुछ पाठ।5।"
        segs = _split_text_at_verse_markers(text, [5])
        assert segs == [text]

    def test_middle_marker_absent(self):
        text = "A।1। C।3।"
        segs = _split_text_at_verse_markers(text, [1, 2, 3])
        assert len(segs) == 3
        assert segs[0] == "A।1।"
        # verse 2 marker absent → text up to verse 3 marker goes to segment 2
        assert segs[1] == "C"
        assert segs[2] == "।3।"


# ---------------------------------------------------------------------------
# 2. split_multi_verse_blocks integration
# ---------------------------------------------------------------------------

def _make_ref(text: str, gatha: int, inline: bool = False) -> Reference:
    return Reference(
        text=text,
        inline_reference=inline,
        needs_manual_match=False,
        is_teeka=False,
        teeka_name="",
        shastra_name="TestShastra",
        match_method="shastra_name",
        resolved_fields=[ResolvedField(field="गाथा", value=gatha)],
    )


class TestSplitMultiVerseBlocks:
    def setup_method(self):
        self.cfg = load_config()

    def test_splits_two_verse_block(self):
        block = Block(
            kind="prakrit_text",
            text_devanagari="TEXT_A।59। TEXT_B।60।",
            hindi_translation="TRANS_A।59। TRANS_B।60।",
            references=[
                _make_ref("नयचक्र बृहद्/59-60", 59),
                _make_ref("नयचक्र बृहद्/59-60", 60),
            ],
        )
        result = split_multi_verse_blocks([block], self.cfg)
        assert len(result) == 2
        assert result[0].text_devanagari == "TEXT_A।59।"
        assert result[0].hindi_translation == "TRANS_A।59।"
        assert len(result[0].references) == 1
        assert result[0].references[0].resolved_fields[0].value == 59

        assert result[1].text_devanagari == "TEXT_B।60।"
        assert result[1].hindi_translation == "TRANS_B।60।"
        assert len(result[1].references) == 1
        assert result[1].references[0].resolved_fields[0].value == 60

    def test_inline_refs_stay_in_last_block(self):
        inline_ref = Reference(
            text="(ग्रंथ/70)",
            inline_reference=True,
            needs_manual_match=False,
            is_teeka=False,
            teeka_name="",
            shastra_name="TestShastra",
            match_method="shastra_name",
            resolved_fields=[ResolvedField(field="गाथा", value=70)],
        )
        block = Block(
            kind="prakrit_text",
            text_devanagari="A।1। B।2।",
            references=[
                _make_ref("Ref/1-2", 1),
                _make_ref("Ref/1-2", 2),
                inline_ref,
            ],
        )
        result = split_multi_verse_blocks([block], self.cfg)
        assert len(result) == 2
        # Inline ref is in the last block
        assert any(r.inline_reference for r in result[1].references)
        assert not any(r.inline_reference for r in result[0].references)

    def test_single_ref_block_unchanged(self):
        block = Block(
            kind="sanskrit_text",
            text_devanagari="A।5।",
            references=[_make_ref("Ref/5", 5)],
        )
        result = split_multi_verse_blocks([block], self.cfg)
        assert len(result) == 1
        assert result[0] is block

    def test_mixed_source_refs_not_split(self):
        """Two non-inline refs from different GRefs → not split."""
        block = Block(
            kind="sanskrit_text",
            text_devanagari="A।1। B।2।",
            references=[
                _make_ref("Ref_A/1", 1),
                _make_ref("Ref_B/2", 2),
            ],
        )
        result = split_multi_verse_blocks([block], self.cfg)
        assert len(result) == 1

    def test_see_also_block_not_split(self):
        block = Block(
            kind="see_also",
            target_keyword="X",
            references=[_make_ref("Ref/1-2", 1), _make_ref("Ref/1-2", 2)],
        )
        result = split_multi_verse_blocks([block], self.cfg)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# 3. Keyword underscore preservation (see_also.py fix)
# ---------------------------------------------------------------------------

class TestKeywordUnderscore:
    def test_underscore_preserved_in_wiki_link(self):
        from selectolax.parser import HTMLParser
        from workers.ingestion.jainkosh.see_also import parse_anchor

        cfg = load_config()
        html = '<a href="/wiki/प्रकृति_बंध">text</a>'
        tree = HTMLParser(html)
        node = tree.css_first("a")
        result = parse_anchor(node, cfg, current_keyword="स्वभाव")
        assert result["target_keyword"] == "प्रकृति_बंध"

    def test_no_underscore_plain_keyword(self):
        from selectolax.parser import HTMLParser
        from workers.ingestion.jainkosh.see_also import parse_anchor

        cfg = load_config()
        html = '<a href="/wiki/द्रव्य">text</a>'
        tree = HTMLParser(html)
        node = tree.css_first("a")
        result = parse_anchor(node, cfg, current_keyword="स्वभाव")
        assert result["target_keyword"] == "द्रव्य"


# ---------------------------------------------------------------------------
# 4. नयचक्र (श्रुतभवन) matching fix
# ---------------------------------------------------------------------------

class TestNayachakraShrutabhavana:
    def test_space_separated_name_matches_slash_entry(self):
        """'नयचक्र श्रुतभवन' (from paren stripping) should match 'नयचक्र/श्रुतभवन'."""
        cfg = load_config()
        registry = cfg.shastra_registry
        assert registry is not None, "shastra_registry not loaded"

        from workers.ingestion.jainkosh.parse_reference import match_shastra

        entry, method, is_teeka, teeka_name = match_shastra(
            "नयचक्र श्रुतभवन", registry, cfg.reference
        )
        assert entry is not None, "should match नयचक्र/श्रुतभवन"
        assert entry.shastra_name == "नयचक्र/श्रुतभवन"

    def test_full_reference_text_identifies_shastra(self):
        """Full GRef '(नयचक्र (श्रुतभवन)/61)' should identify shastra even if fields unresolved."""
        cfg = load_config()
        registry = cfg.shastra_registry
        assert registry is not None

        from workers.ingestion.jainkosh.parse_reference import parse_reference_text

        results = parse_reference_text(
            "(नयचक्र (श्रुतभवन)/61)", registry, cfg.reference
        )
        assert len(results) == 1
        r = results[0]
        # Shastra is identified; format mismatch (अधिकार/पृष्ठ needs 2 fields) sets needs_manual_match
        assert r.shastra_name == "नयचक्र/श्रुतभवन"
        assert r.match_method == "shastra_name"


# ---------------------------------------------------------------------------
# 5. hindi_text + hindi_translation=None → GathaTeekaBhaavarth
# ---------------------------------------------------------------------------

class TestHindiTextBhaavarth:
    def _make_stub_config(self):
        """Return a minimal config with a publication-type shastra."""
        from workers.ingestion.jainkosh.config import (
            DevanagariNormalizationConfig,
        )
        from workers.ingestion.jainkosh.parse_reference import (
            ShastraEntry,
            ShastraRegistry,
            PublisherRegistry,
            parse_format_string,
            _normalise,
        )
        from pathlib import Path

        cfg = load_config()
        norm = DevanagariNormalizationConfig(enabled=False, substitutions=[])

        registry = ShastraRegistry()
        entry = ShastraEntry(
            shastra_name="कार्तिकेयानुप्रेक्षा",
            alternate_names=[],
            short_form="",
            format_str="गाथा",
            format_groups=parse_format_string("गाथा"),
            publisher="राजचन्द्र ग्रन्थमाला",
            type="publication",
        )
        registry.entries.append(entry)
        registry._by_primary[_normalise(entry.shastra_name, norm)] = entry

        pub_reg = PublisherRegistry()
        pub_reg._by_name["राजचन्द्र ग्रन्थमाला"] = "23"

        cfg.shastra_registry = registry
        cfg.publisher_registry = pub_reg
        return cfg

    def test_hindi_text_null_translation_emits_bhaavarth(self):
        from workers.ingestion.jainkosh.reference_edges import build_reference_edges

        cfg = self._make_stub_config()
        ref = Reference(
            text="कार्तिकेयानुप्रेक्षा/312",
            inline_reference=False,
            needs_manual_match=False,
            is_teeka=False,
            teeka_name="",
            shastra_name="कार्तिकेयानुप्रेक्षा",
            match_method="shastra_name",
            resolved_fields=[ResolvedField(field="गाथा", value=312)],
        )
        block = Block(
            kind="hindi_text",
            text_devanagari="कुछ पाठ।",
            hindi_translation=None,
            references=[ref],
        )
        target = {"label": "Topic", "key": "test_topic"}
        edges = build_reference_edges(
            block, target=target, edge_type="MENTIONS_TOPIC", config=cfg,
        )
        assert len(edges) == 1
        assert edges[0]["from"]["label"] == "GathaTeekaBhaavarth"
        assert "312" in edges[0]["from"]["key"]
        assert "23" in edges[0]["from"]["key"]

    def test_hindi_text_with_translation_emits_gatha(self):
        from workers.ingestion.jainkosh.reference_edges import build_reference_edges

        cfg = self._make_stub_config()
        ref = Reference(
            text="कार्तिकेयानुप्रेक्षा/312",
            inline_reference=False,
            needs_manual_match=False,
            is_teeka=False,
            teeka_name="",
            shastra_name="कार्तिकेयानुप्रेक्षा",
            match_method="shastra_name",
            resolved_fields=[ResolvedField(field="गाथा", value=312)],
        )
        block = Block(
            kind="hindi_text",
            text_devanagari="कुछ पाठ।",
            hindi_translation="This has a translation",  # non-null → Gatha
            references=[ref],
        )
        target = {"label": "Topic", "key": "test_topic"}
        edges = build_reference_edges(
            block, target=target, edge_type="MENTIONS_TOPIC", config=cfg,
        )
        assert len(edges) == 1
        assert edges[0]["from"]["label"] == "Gatha"


# ---------------------------------------------------------------------------
# 6. Integration: स्वभाव fixture sanity checks
# ---------------------------------------------------------------------------

class TestSvabhavIntegration:
    def _parse_svabhav(self):
        from pathlib import Path
        from workers.ingestion.jainkosh.parse_keyword import parse_keyword_html

        cfg = load_config()
        fixture = Path("workers/ingestion/jainkosh/tests/fixtures/स्वभाव.html")
        html = fixture.read_text(encoding="utf-8")
        return parse_keyword_html(html, "https://jainkosh.org/wiki/स्वभाव", cfg)

    def test_prakrit_text_59_60_split(self):
        result = self._parse_svabhav()
        siddhantkosh = next(s for s in result.page_sections if s.section_kind == "siddhantkosh")

        def find_block_with_gatha_from_ref(subs, gatha_val, ref_text):
            """Find a block where the non-inline ref with matching ref_text has the given gatha."""
            for sub in subs:
                for b in sub.blocks:
                    for r in b.references:
                        if r.inline_reference or r.text != ref_text:
                            continue
                        for rf in r.resolved_fields:
                            if rf.field == "गाथा" and rf.value == gatha_val:
                                return b
                found = find_block_with_gatha_from_ref(sub.children or [], gatha_val, ref_text)
                if found:
                    return found
            return None

        ref_text = "नयचक्र बृहद्/59-60"
        block59 = find_block_with_gatha_from_ref(siddhantkosh.subsections, 59, ref_text)
        block60 = find_block_with_gatha_from_ref(siddhantkosh.subsections, 60, ref_text)

        assert block59 is not None, "Block for gatha 59 not found"
        assert block60 is not None, "Block for gatha 60 not found"
        assert block59 is not block60, "Gatha 59 and 60 must be in separate blocks"
        assert "।59।" in (block59.text_devanagari or "")
        assert "।60।" in (block60.text_devanagari or "")

    def test_sanskrit_text_19_96_98_split(self):
        result = self._parse_svabhav()
        siddhantkosh = next(s for s in result.page_sections if s.section_kind == "siddhantkosh")

        gatha_blocks = {}

        def collect(subs):
            for sub in subs:
                for b in sub.blocks:
                    for r in b.references:
                        if not r.inline_reference:
                            for rf in r.resolved_fields:
                                if rf.field == "गाथा" and rf.value in (19, 96, 98):
                                    gatha_blocks[rf.value] = b
                collect(sub.children or [])

        collect(siddhantkosh.subsections)

        for n in (19, 96, 98):
            assert n in gatha_blocks, f"Block for gatha {n} not found"

        assert gatha_blocks[19] is not gatha_blocks[96]
        assert gatha_blocks[96] is not gatha_blocks[98]

    def test_prakruti_bandha_keyword_uses_underscore(self):
        result = self._parse_svabhav()
        siddhantkosh = next(s for s in result.page_sections if s.section_kind == "siddhantkosh")

        def find_see_also(subs):
            for sub in subs:
                for b in sub.blocks:
                    if b.kind == "see_also" and b.target_keyword == "प्रकृति_बंध":
                        return b
                found = find_see_also(sub.children or [])
                if found:
                    return found
            return None

        block = find_see_also(siddhantkosh.subsections)
        assert block is not None, "see_also block for प्रकृति_बंध not found"
        assert block.target_keyword == "प्रकृति_बंध"

    def test_nayachakra_shrutabhavana_resolved(self):
        result = self._parse_svabhav()
        siddhantkosh = next(s for s in result.page_sections if s.section_kind == "siddhantkosh")

        def find_ref(subs):
            for sub in subs:
                for b in sub.blocks:
                    for r in b.references:
                        if r.shastra_name == "नयचक्र/श्रुतभवन":
                            return r
                found = find_ref(sub.children or [])
                if found:
                    return found
            return None

        ref = find_ref(siddhantkosh.subsections)
        assert ref is not None, "Reference to नयचक्र/श्रुतभवन not found"
        # Shastra is identified; format mismatch sets needs_manual_match=True but name is resolved
        assert ref.shastra_name == "नयचक्र/श्रुतभवन"
        assert ref.match_method == "shastra_name"

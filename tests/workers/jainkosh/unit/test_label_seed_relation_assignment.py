"""Tests that row-style see_also blocks are assigned to child label-seed subsections."""

from pathlib import Path

from workers.ingestion.jainkosh.config import load_config
from workers.ingestion.jainkosh.parse_keyword import parse_keyword_html


def _parse_aatma():
    html = Path(__file__).parents[1].joinpath("fixtures", "आत्मा.html").read_text(encoding="utf-8")
    return parse_keyword_html(html, "https://example.org/wiki/आत्मा", load_config())


def _walk(subs):
    for s in subs:
        yield s
        yield from _walk(s.children)


def test_row_seed_gets_see_also_block():
    """Child seed 'जीवको आत्मा कहनेकी विवक्षा' should have see_also जीव; parent should have none."""
    res = _parse_aatma()

    seed = None
    parent = None
    for sec in res.page_sections:
        for sub in _walk(sec.subsections):
            if sub.heading_text == "जीवको आत्मा कहनेकी विवक्षा":
                seed = sub
            if sub.heading_text == "एक आत्मा के तीन भेद करने का प्रयोजन":
                parent = sub

    assert seed is not None, "Seed 'जीवको आत्मा कहनेकी विवक्षा' not found"
    assert parent is not None, "Parent section 'एक आत्मा के तीन भेद करने का प्रयोजन' not found"

    see_also_blocks = [b for b in seed.blocks if b.kind == "see_also"]
    assert len(see_also_blocks) == 1, f"Expected 1 see_also in seed, got: {see_also_blocks}"
    assert see_also_blocks[0].target_keyword == "जीव", (
        f"Expected target_keyword='जीव', got: {see_also_blocks[0].target_keyword}"
    )

    parent_see_also = [b for b in parent.blocks if b.kind == "see_also"]
    assert parent_see_also == [], f"Parent should have NO see_also blocks, got: {parent_see_also}"


def test_redlink_row_seed_gets_see_also_block():
    """Child seed 'बहिरात्मा, अंतरात्मा व परमात्मा' should have redlink see_also; parent should have none."""
    res = _parse_aatma()

    seed = None
    parent = None
    for sec in res.page_sections:
        for sub in _walk(sec.subsections):
            if sub.heading_text == "बहिरात्मा, अंतरात्मा व परमात्मा":
                seed = sub
            if sub.heading_text == "गुण स्थानों की अपेक्षा बहिरात्मा आदि भेद":
                parent = sub

    assert seed is not None, "Seed 'बहिरात्मा, अंतरात्मा व परमात्मा' not found"
    assert parent is not None, "Parent section 'गुण स्थानों की अपेक्षा बहिरात्मा आदि भेद' not found"

    see_also_blocks = [b for b in seed.blocks if b.kind == "see_also"]
    assert len(see_also_blocks) == 1, f"Expected 1 see_also in seed, got: {see_also_blocks}"
    assert see_also_blocks[0].target_exists is False, (
        f"Expected target_exists=False (redlink), got: {see_also_blocks[0].target_exists}"
    )

    parent_see_also = [b for b in parent.blocks if b.kind == "see_also"]
    assert parent_see_also == [], f"Parent should have NO see_also blocks, got: {parent_see_also}"

    parent_hindi_with_bahiratma = [
        b for b in parent.blocks
        if b.kind == "hindi_text" and "बहिरात्मा" in (b.text_devanagari or "")
        and "अंतरात्मा" in (b.text_devanagari or "")
    ]
    assert parent_hindi_with_bahiratma == [], (
        f"Parent should have NO hindi_text block with 'बहिरात्मा', got: {parent_hindi_with_bahiratma}"
    )


def test_multi_row_seeds_correct_assignment():
    """All 3 child seeds of 'एक आत्मा के तीन भेद करने का प्रयोजन' should have correct see_also targets."""
    res = _parse_aatma()

    parent = None
    for sec in res.page_sections:
        for sub in _walk(sec.subsections):
            if sub.heading_text == "एक आत्मा के तीन भेद करने का प्रयोजन":
                parent = sub
                break

    assert parent is not None, "Parent section not found"

    # Collect direct children that are label seeds
    seed_children = [c for c in parent.children if c.label_topic_seed]

    # Build a map from heading_text to see_also blocks
    seed_map = {s.heading_text: s for s in seed_children}

    expected = {
        "जीवको आत्मा कहनेकी विवक्षा": ("जीव", None),
        "आत्मा ही कथंचित प्रमाण है": ("प्रमाण", "3.3"),
        "शुद्धात्माके अपर नाम": ("मोक्षमार्ग", "2.5"),
    }

    for seed_label, (exp_keyword, exp_topic_path) in expected.items():
        assert seed_label in seed_map, (
            f"Seed '{seed_label}' not found among children. Found: {list(seed_map.keys())}"
        )
        seed = seed_map[seed_label]
        see_also_blocks = [b for b in seed.blocks if b.kind == "see_also"]
        assert len(see_also_blocks) == 1, (
            f"Seed '{seed_label}' expected 1 see_also, got: {see_also_blocks}"
        )
        assert see_also_blocks[0].target_keyword == exp_keyword, (
            f"Seed '{seed_label}': expected target_keyword='{exp_keyword}', "
            f"got: {see_also_blocks[0].target_keyword}"
        )
        assert see_also_blocks[0].target_topic_path == exp_topic_path, (
            f"Seed '{seed_label}': expected target_topic_path='{exp_topic_path}', "
            f"got: {see_also_blocks[0].target_topic_path}"
        )

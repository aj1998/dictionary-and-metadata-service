from selectolax.parser import HTMLParser
from workers.ingestion.jainkosh.config import load_config
from workers.ingestion.jainkosh.parse_blocks import parse_block_stream


def test_dekhen_only_hindi_text_block_dropped_from_block_stream():
    html = '<p class="HindiText">• जीवको आत्मा कहनेकी विवक्षा - देखें <a href="/wiki/%E0%A4%9C%E0%A5%80%E0%A4%B5">जीव</a></p>'
    el = HTMLParser(html).css_first("p")
    blocks = parse_block_stream([el], load_config(), current_keyword="आत्मा")
    # Row-style entry: NEITHER hindi_text NOR see_also should appear in parent block stream
    assert blocks == [], f"Expected empty blocks, got: {blocks}"


def test_dekhen_redlink_row_fully_dropped_from_block_stream():
    html = (
        '<p class="HindiText">• बहिरात्मा, अंतरात्मा व परमात्मा - देखें '
        '<a class="new" href="/w/index.php?title=%E0%A4%B5%E0%A4%B9_%E0%A4%B5%E0%A4%B9_%E0%A4%A8%E0%A4%BE%E0%A4%AE&action=edit&redlink=1" '
        'title="वह वह नाम">वह वह नाम</a></p>'
    )
    el = HTMLParser(html).css_first("p")
    blocks = parse_block_stream([el], load_config(), current_keyword="आत्मा")
    # Row-style redlink entry: blocks should be empty (no cleaned prose, no see_also)
    assert blocks == [], f"Expected empty blocks for redlink row, got: {blocks}"


def test_real_prose_with_inline_dekhen_kept():
    html = '<p class="HindiText">जीव शुद्ध है। देखें <a href="/wiki/%E0%A4%9C%E0%A5%80%E0%A4%B5">जीव</a> - 3.8</p>'
    el = HTMLParser(html).css_first("p")
    blocks = parse_block_stream([el], load_config(), current_keyword="आत्मा")
    text_blocks = [b for b in blocks if b.kind == "hindi_text"]
    assert len(text_blocks) == 1
    assert "जीव शुद्ध है" in (text_blocks[0].text_devanagari or "")

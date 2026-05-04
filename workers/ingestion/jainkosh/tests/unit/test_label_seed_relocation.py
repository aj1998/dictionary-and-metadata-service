"""Test that inline see_also blocks are relocated from parent to label_seed child."""


def test_inline_see_also_relocated_to_label_seed_child():
    """
    Given: a HindiText block with an inline देखें that creates a label_seed child,
    When: parse_subsections runs,
    Then: the parent subsection's blocks must NOT contain the see_also block,
          and the child label_seed's blocks MUST contain it.
    """
    from workers.ingestion.jainkosh.parse_keyword import parse_keyword_html
    from workers.ingestion.jainkosh.config import load_config

    html = """
    <html><body><div class="mw-parser-output">
    <h2><span class="mw-headline" id="सिद्धांतकोष_से">सिद्धांतकोष से</span></h2>
    <li id="1"><span class="HindiText"><strong>अनुभव</strong></span></li>
    <p class="HindiText">
        यह लक्षण नहीं बनता (इसी प्रकार 'abc' भी वे नहीं कह सकते–देखें
        <a class="mw-selflink-fragment" href="#1.4">keyword - 1.4</a>)
        अनेकांतवादियों के मत में तो।
    </p>
    </div></body></html>
    """
    config = load_config()
    result = parse_keyword_html(html, "https://www.jainkosh.org/wiki/keyword", config)
    sec = result.page_sections[0]
    subsection = sec.subsections[0]  # topic_path="1"

    # Parent must have NO see_also in blocks
    parent_see_alsos = [b for b in subsection.blocks if b.kind == "see_also"]
    assert parent_see_alsos == [], "Parent must not hold the relocated see_also"

    # Child label_seed must have the see_also
    label_seeds = [c for c in subsection.children if c.label_topic_seed]
    assert len(label_seeds) == 1
    child_see_alsos = [b for b in label_seeds[0].blocks if b.kind == "see_also"]
    assert len(child_see_alsos) == 1
    assert child_see_alsos[0].target_topic_path == "1.4"

"""Golden tests: parse all three fixtures and compare byte-for-byte against goldens."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

FIXTURE_DIR = Path("workers/ingestion/jainkosh/tests/fixtures")
GOLDEN_DIR = Path("workers/ingestion/jainkosh/tests/golden")
FROZEN = "2026-05-02T00:00:00Z"

KEYWORDS = ["आत्मा", "द्रव्य", "पर्याय"]


def _walk_subs(subsections):
    for sub in subsections:
        yield sub
        yield from _walk_subs(sub.get("children", []))


def test_keyword_definitions_has_no_subsection_tree():
    from workers.ingestion.jainkosh.config import load_config
    from workers.ingestion.jainkosh.envelope import build_envelope
    from workers.ingestion.jainkosh.parse_keyword import parse_keyword_html

    config = load_config()
    with open(FIXTURE_DIR / "आत्मा.html", encoding="utf-8") as f:
        html = f.read()

    result = parse_keyword_html(html, "https://jainkosh.org/wiki/आत्मा", config)
    env = build_envelope(result)
    kdef = env.would_write["mongo"]["keyword_definitions"][0]
    for ps in kdef["page_sections"]:
        assert "subsection_tree" not in ps
        assert "extra_blocks" in ps
        assert "definitions" in ps
        assert "index_relations" not in ps


def run_cli(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "workers.ingestion.jainkosh.cli"] + args,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


@pytest.mark.parametrize("keyword", KEYWORDS)
def test_golden_match(keyword, tmp_path):
    out = tmp_path / f"{keyword}.json"
    result = run_cli([
        "parse",
        str(FIXTURE_DIR / f"{keyword}.html"),
        "--out", str(out),
        "--frozen-time", FROZEN,
    ])
    assert result.returncode == 0, result.stderr

    actual = out.read_bytes()
    expected = (GOLDEN_DIR / f"{keyword}.json").read_bytes()

    if actual != expected:
        # Show first diff for debugging
        actual_lines = actual.decode("utf-8").splitlines()
        expected_lines = expected.decode("utf-8").splitlines()
        for i, (a, e) in enumerate(zip(actual_lines, expected_lines)):
            if a != e:
                pytest.fail(
                    f"Golden mismatch for {keyword} at line {i+1}:\n"
                    f"  expected: {e!r}\n"
                    f"  actual:   {a!r}"
                )
        # Different length
        pytest.fail(
            f"Golden mismatch for {keyword}: "
            f"expected {len(expected_lines)} lines, got {len(actual_lines)}"
        )


@pytest.mark.parametrize("keyword", KEYWORDS)
def test_parser_is_byte_identical_on_rerun(keyword, tmp_path):
    out1 = tmp_path / f"{keyword}_1.json"
    out2 = tmp_path / f"{keyword}_2.json"

    for out in [out1, out2]:
        r = run_cli([
            "parse",
            str(FIXTURE_DIR / f"{keyword}.html"),
            "--out", str(out),
            "--frozen-time", FROZEN,
        ])
        assert r.returncode == 0, r.stderr

    assert out1.read_bytes() == out2.read_bytes(), \
        f"Parser not idempotent for {keyword}"


@pytest.mark.parametrize("keyword", KEYWORDS)
def test_no_warnings(keyword):
    """All three fixtures must produce zero warnings."""
    from workers.ingestion.jainkosh.config import load_config
    from workers.ingestion.jainkosh.parse_keyword import parse_keyword_html

    config = load_config()
    with open(FIXTURE_DIR / f"{keyword}.html", encoding="utf-8") as f:
        html = f.read()
    url = f"https://jainkosh.org/wiki/{keyword}"
    result = parse_keyword_html(html, url, config)
    assert result.warnings == [], \
        f"Unexpected warnings for {keyword}: {result.warnings}"


def test_atma_sanity():
    """आत्मा specific sanity checks."""
    from workers.ingestion.jainkosh.config import load_config
    from workers.ingestion.jainkosh.parse_keyword import parse_keyword_html

    config = load_config()
    with open(FIXTURE_DIR / "आत्मा.html", encoding="utf-8") as f:
        html = f.read()
    result = parse_keyword_html(html, "https://jainkosh.org/wiki/आत्मा", config)

    assert result.keyword == "आत्मा"
    assert len(result.page_sections) == 2
    assert result.page_sections[0].section_kind == "siddhantkosh"
    assert result.page_sections[1].section_kind == "puraankosh"

    # PuranKosh has 2 definitions
    puraankosh = result.page_sections[1]
    assert len(puraankosh.definitions) == 2

    # First siddhantkosh subsection is path "2" (no "1" in this page)
    siddhantkosh = result.page_sections[0]
    if siddhantkosh.subsections:
        assert siddhantkosh.subsections[0].topic_path == "2"


def test_dravya_sanity():
    """द्रव्य specific sanity checks."""
    from workers.ingestion.jainkosh.config import load_config
    from workers.ingestion.jainkosh.parse_keyword import parse_keyword_html

    config = load_config()
    with open(FIXTURE_DIR / "द्रव्य.html", encoding="utf-8") as f:
        html = f.read()
    result = parse_keyword_html(html, "https://jainkosh.org/wiki/द्रव्य", config)

    siddhantkosh = result.page_sections[0]
    # Has an index
    assert len(siddhantkosh.index_relations) > 10
    # Has many subsections
    def count_subs(subs):
        t = len(subs)
        for s in subs: t += count_subs(s.children)
        return t
    total = count_subs(siddhantkosh.subsections)
    assert total >= 50
    # In phase-4, in-flow tables attach to subsection blocks.
    assert len(siddhantkosh.extra_blocks) == 0
    def has_table(subs):
        for s in subs:
            if any(b.kind == "table" for b in s.blocks):
                return True
            if has_table(s.children):
                return True
        return False
    assert has_table(siddhantkosh.subsections)


def test_paryay_sanity():
    """पर्याय specific sanity checks."""
    from workers.ingestion.jainkosh.config import load_config
    from workers.ingestion.jainkosh.parse_keyword import parse_keyword_html

    config = load_config()
    with open(FIXTURE_DIR / "पर्याय.html", encoding="utf-8") as f:
        html = f.read()
    result = parse_keyword_html(html, "https://jainkosh.org/wiki/पर्याय", config)

    siddhantkosh = result.page_sections[0]
    def count_subs(subs):
        t = len(subs)
        for s in subs: t += count_subs(s.children)
        return t
    total = count_subs(siddhantkosh.subsections)
    assert total >= 40

    # Check 3-level depth exists
    def max_depth(subs, d=0):
        if not subs:
            return d
        return max(max_depth(s.children, d+1) for s in subs)
    assert max_depth(siddhantkosh.subsections) >= 2

    # No synthetic nodes in पर्याय
    def any_synthetic(subs):
        return any(s.is_synthetic or any_synthetic(s.children) for s in subs)
    assert not any_synthetic(siddhantkosh.subsections)


def test_no_truncated_table_raw_html_in_goldens():
    for keyword in KEYWORDS:
        with open(GOLDEN_DIR / f"{keyword}.json", encoding="utf-8") as f:
            payload = json.load(f)
        result = payload["keyword_parse_result"]
        for sec in result["page_sections"]:
            for sub in _walk_subs(sec.get("subsections", [])):
                for block in sub.get("blocks", []):
                    if block.get("kind") != "table":
                        continue
                    assert block["raw_html"].startswith("<table")
                    assert block["raw_html"].rstrip().endswith("</table>")


def test_envelope_carries_root_idempotency_contracts():
    for keyword in KEYWORDS:
        with open(GOLDEN_DIR / f"{keyword}.json", encoding="utf-8") as f:
            payload = json.load(f)
        env = payload["would_write"]
        assert "idempotency_contracts" in env
        for row in env["postgres"]["topics"]:
            assert "idempotency_contract" not in row

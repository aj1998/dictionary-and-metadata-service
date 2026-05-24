"""Unit tests for CLI (workers.ingestion.jainkosh.cli)."""

import json
import subprocess
import sys
import pytest
from pathlib import Path

FIXTURE_DIR = Path("workers/ingestion/jainkosh/tests/fixtures")
FROZEN = "2026-05-02T00:00:00Z"


def run_cli(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "workers.ingestion.jainkosh.cli"] + args,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


class TestCLIParse:
    def test_parse_produces_valid_envelope(self, tmp_path):
        out = tmp_path / "out.json"
        result = run_cli([
            "parse",
            str(FIXTURE_DIR / "आत्मा.html"),
            "--out", str(out),
            "--frozen-time", FROZEN,
        ])
        assert result.returncode == 0, result.stderr
        assert out.exists()
        data = json.loads(out.read_text(encoding="utf-8"))
        assert "keyword_parse_result" in data
        assert "would_write" in data

    def test_parse_keyword_matches_filename(self, tmp_path):
        out = tmp_path / "out.json"
        run_cli([
            "parse",
            str(FIXTURE_DIR / "द्रव्य.html"),
            "--out", str(out),
            "--frozen-time", FROZEN,
        ])
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["keyword_parse_result"]["keyword"] == "द्रव्य"

    def test_validate_only_no_output_file(self, tmp_path):
        result = run_cli([
            "parse",
            str(FIXTURE_DIR / "आत्मा.html"),
            "--validate-only",
            "--frozen-time", FROZEN,
        ])
        assert result.returncode == 0, result.stderr

    def test_custom_url_overrides_filename_url(self, tmp_path):
        out = tmp_path / "out.json"
        custom_url = "https://example.com/custom"
        run_cli([
            "parse",
            str(FIXTURE_DIR / "आत्मा.html"),
            "--url", custom_url,
            "--out", str(out),
            "--frozen-time", FROZEN,
        ])
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["keyword_parse_result"]["source_url"] == custom_url

    def test_frozen_time_in_output(self, tmp_path):
        out = tmp_path / "out.json"
        run_cli([
            "parse",
            str(FIXTURE_DIR / "आत्मा.html"),
            "--out", str(out),
            "--frozen-time", FROZEN,
        ])
        data = json.loads(out.read_text(encoding="utf-8"))
        parsed_at = data["keyword_parse_result"]["parsed_at"]
        assert "2026-05-02" in parsed_at

    def test_would_write_has_three_stores(self, tmp_path):
        out = tmp_path / "out.json"
        run_cli([
            "parse",
            str(FIXTURE_DIR / "आत्मा.html"),
            "--out", str(out),
            "--frozen-time", FROZEN,
        ])
        data = json.loads(out.read_text(encoding="utf-8"))
        ww = data["would_write"]
        assert "postgres" in ww
        assert "mongo" in ww
        assert "neo4j" in ww

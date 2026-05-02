"""CLI: python -m workers.ingestion.jainkosh.cli parse <html_path> [options]"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from .config import load_config
from .envelope import build_envelope
from .parse_keyword import ParseError, parse_keyword_html


def _derive_url_from_path(path: Path) -> str:
    stem = path.stem
    encoded = quote(stem, safe="")
    return f"https://www.jainkosh.org/wiki/{encoded}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m workers.ingestion.jainkosh.cli",
        description="JainKosh keyword page parser",
    )
    subparsers = parser.add_subparsers(dest="command")

    parse_cmd = subparsers.add_parser("parse", help="Parse an HTML file")
    parse_cmd.add_argument("html_path", type=Path, help="Path to the HTML file")
    parse_cmd.add_argument("--url", type=str, default=None, help="Source URL")
    parse_cmd.add_argument(
        "--config", type=Path, default=None, help="Path to jainkosh.yaml"
    )
    parse_cmd.add_argument(
        "--out", type=Path, default=None, help="Output JSON path"
    )
    parse_cmd.add_argument(
        "--pretty", action="store_true", default=True, help="Pretty-print JSON"
    )
    parse_cmd.add_argument(
        "--validate-only", action="store_true", default=False,
        help="Parse but don't write; print summary stats only"
    )
    parse_cmd.add_argument(
        "--frozen-time", type=str, default=None,
        help="Override parsed_at for reproducible output (ISO format)"
    )
    parse_cmd.add_argument(
        "--rules-version", type=str, default=None,
        help="Override parser_rules_version"
    )

    args = parser.parse_args(argv)

    if args.command != "parse":
        parser.print_help()
        return 1

    html_path: Path = args.html_path
    if not html_path.exists():
        print(f"Error: file not found: {html_path}", file=sys.stderr)
        return 3

    # Load config
    try:
        config = load_config(args.config)
    except (ValueError, FileNotFoundError) as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 2

    if args.rules_version:
        object.__setattr__(config, "parser_rules_version", args.rules_version)

    # Determine URL
    url = args.url or _derive_url_from_path(html_path)

    # Parse frozen time
    frozen_time = None
    if args.frozen_time:
        try:
            frozen_time = datetime.fromisoformat(args.frozen_time.rstrip("Z"))
        except ValueError as exc:
            print(f"Invalid --frozen-time: {exc}", file=sys.stderr)
            return 1

    # Read HTML
    try:
        html = html_path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"IO error: {exc}", file=sys.stderr)
        return 3

    # Parse
    try:
        result = parse_keyword_html(html, url, config, frozen_time=frozen_time)
    except ParseError as exc:
        print(f"Parse error: {exc}", file=sys.stderr)
        return 1

    envelope = build_envelope(result, config)

    if args.validate_only:
        # Print stats
        n_sections = len(result.page_sections)
        n_topics = sum(
            1 for sec in result.page_sections
            for sub in _walk_all_subsections(sec.subsections)
        )
        n_defs = sum(
            len(sec.definitions) for sec in result.page_sections
        )
        print(f"keyword: {result.keyword}")
        print(f"sections: {n_sections}")
        print(f"definitions: {n_defs}")
        print(f"topics: {n_topics}")
        print(f"warnings: {len(result.warnings)}")
        return 0

    # Determine output path
    out_path: Path = args.out or html_path.with_suffix(".parsed.json")

    # Serialize
    json_str = envelope.model_dump_json(indent=2 if args.pretty else None)

    try:
        out_path.write_text(json_str, encoding="utf-8")
    except OSError as exc:
        print(f"IO error writing output: {exc}", file=sys.stderr)
        return 3

    return 0


def _walk_all_subsections(subsections):
    for sub in subsections:
        yield sub
        yield from _walk_all_subsections(sub.children)


if __name__ == "__main__":
    sys.exit(main())

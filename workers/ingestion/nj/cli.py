"""CLI for NJ parser and golden envelope generation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import load_config
from .envelope import build_envelope
from .orchestrator import parse_shastra


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m workers.ingestion.nj.cli",
        description="Parse NJ shastra and generate ingestion-ready golden JSON",
    )
    subparsers = parser.add_subparsers(dest="command")

    parse_cmd = subparsers.add_parser("parse", help="Parse shastra and write JSON")
    parse_cmd.add_argument("--config", type=Path, required=True, help="Path to NJ parser config yaml")
    parse_cmd.add_argument("--out", type=Path, default=None, help="Output JSON path")
    parse_cmd.add_argument("--batch-offset", type=int, default=0, help="Eligible page offset")
    parse_cmd.add_argument("--batch-limit", type=int, default=None, help="Eligible page limit")
    parse_cmd.add_argument(
        "--format",
        choices=["parse_result", "golden"],
        default="golden",
        help="Output raw parse result or ingestion-ready golden envelope",
    )
    parse_cmd.add_argument("--validate-only", action="store_true", default=False)

    args = parser.parse_args(argv)
    if args.command != "parse":
        parser.print_help()
        return 1

    cfg = load_config(args.config)
    result = parse_shastra(cfg, batch_offset=args.batch_offset, batch_limit=args.batch_limit)
    payload = (
        result.model_dump(mode="json")
        if args.format == "parse_result"
        else build_envelope(result, cfg)
    )

    if args.validate_only:
        print(f"shastra: {result.shastra_natural_key}")
        print(f"processed_pages: {result.total_html_files_processed}")
        print(f"gathas: {len(result.gathas)}")
        print(f"secondary_kalashes: {len(result.secondary_kalashes)}")
        print(f"warnings: {len(result.warnings)}")
        return 0

    out_path = args.out
    if out_path is None:
        default_dir = Path("workers/ingestion/nj/tests/golden")
        default_dir.mkdir(parents=True, exist_ok=True)
        suffix = "golden" if args.format == "golden" else "parse_result"
        span = f"o{args.batch_offset}_l{args.batch_limit if args.batch_limit is not None else 'all'}"
        out_path = default_dir / f"{cfg.shastra.natural_key}_{suffix}_{span}.json"
    else:
        out_path.parent.mkdir(parents=True, exist_ok=True)

    out_path.write_text(
        __import__("json").dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"wrote: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

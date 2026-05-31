"""
Generate golden JSON files for all Jainkosh HTML fixtures.

Usage:
    python scripts/generate_jainkosh_goldens.py
"""

import subprocess
import sys
from pathlib import Path

FIXTURES_DIR = Path("workers/ingestion/jainkosh/tests/fixtures")
GOLDEN_DIR = Path("workers/ingestion/jainkosh/tests/golden")


def main():
    fixtures = sorted(FIXTURES_DIR.glob("*.html"))
    if not fixtures:
        print(f"No HTML fixtures found in {FIXTURES_DIR}")
        sys.exit(1)

    print(f"Found {len(fixtures)} fixture(s). Generating goldens...\n")

    failures = []
    for fixture in fixtures:
        word = fixture.stem
        golden = GOLDEN_DIR / f"{word}.json"
        cmd = [
            "python", "-m", "workers.ingestion.jainkosh.cli",
            "parse", str(fixture),
            "--out", str(golden),
        ]
        print(f"  {word} ... ", end="", flush=True)
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            print("ok")
        else:
            print("FAILED")
            print(f"    stdout: {result.stdout.strip()}")
            print(f"    stderr: {result.stderr.strip()}")
            failures.append(word)

    print()
    if failures:
        print(f"{len(failures)} failure(s): {', '.join(failures)}")
        sys.exit(1)
    else:
        print(f"All {len(fixtures)} golden(s) generated successfully.")


if __name__ == "__main__":
    main()

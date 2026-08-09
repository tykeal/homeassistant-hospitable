# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Guard synthetic JSON fixtures against committed private data."""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final

DOC_DOMAINS: Final = {"example.com", "example.org", "example.net", "invalid"}
OWNER_RE: Final = re.compile(r"tykeal|bardicgrove", re.IGNORECASE)
EMAIL_RE: Final = re.compile(r"[A-Z0-9._%+-]+@([A-Z0-9.-]+\.[A-Z]{2,}|invalid)", re.I)
BEARER_RE: Final = re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{12,}\b")
COORD_RE: Final = re.compile(r'"(?:latitude|longitude)"\s*:\s*(-?\d+(?:\.\d+)?)')
POSTCODE_RE: Final = re.compile(r'"postcode"\s*:\s*"([^"]+)"')
STREET_RE: Final = re.compile(r'"street"\s*:\s*"([^"]+)"')
ADDRESS_RE: Final = re.compile(r'"display"\s*:\s*"([^"]+)"')
ALLOWED_POSTCODES: Final = {"90210"}
ALLOWED_STREETS: Final = {"Example Avenue"}
SYNTHETIC_MIN_LAT: Final = 37.0
SYNTHETIC_MAX_LAT: Final = 38.0
SYNTHETIC_MIN_LON: Final = -123.0
SYNTHETIC_MAX_LON: Final = -122.0


@dataclass(frozen=True)
class Hit:
    """A sanitized fixture policy violation."""

    path: str
    line: int
    rule: str


def _line_for(text: str, index: int) -> int:
    """Return a one-based line number for a character offset.

    Args:
        text: Full text that was scanned.
        index: Match start offset.

    Returns:
        One-based line number.
    """
    return text.count("\n", 0, index) + 1


def _add(hits: list[Hit], path: str, text: str, index: int, rule: str) -> None:
    """Append a sanitized hit to the result list.

    Args:
        hits: Mutable hit list.
        path: Scanned path.
        text: Scanned text.
        index: Match start offset.
        rule: Rule name to report.
    """
    hits.append(Hit(path=path, line=_line_for(text, index), rule=rule))


def scan_text(path: str, text: str) -> list[Hit]:
    """Scan fixture text for private or non-synthetic values.

    Args:
        path: Path label to include in sanitized findings.
        text: Fixture content to scan.

    Returns:
        Sanitized findings containing file, line, and rule only.
    """
    hits: list[Hit] = []
    for match in EMAIL_RE.finditer(text):
        domain = match.group(1).casefold()
        if domain not in DOC_DOMAINS:
            _add(hits, path, text, match.start(), "email-domain")
    for match in OWNER_RE.finditer(text):
        _add(hits, path, text, match.start(), "owner-identity")
    for match in BEARER_RE.finditer(text):
        _add(hits, path, text, match.start(), "bearer-token")
    for match in COORD_RE.finditer(text):
        value = float(match.group(1))
        key = match.group(0).split('"', 2)[1]
        if key == "latitude" and not SYNTHETIC_MIN_LAT <= value <= SYNTHETIC_MAX_LAT:
            _add(hits, path, text, match.start(), "coordinate-box")
        if key == "longitude" and not SYNTHETIC_MIN_LON <= value <= SYNTHETIC_MAX_LON:
            _add(hits, path, text, match.start(), "coordinate-box")
    for match in POSTCODE_RE.finditer(text):
        if match.group(1) not in ALLOWED_POSTCODES:
            _add(hits, path, text, match.start(), "address-allowlist")
    for match in STREET_RE.finditer(text):
        if match.group(1) not in ALLOWED_STREETS:
            _add(hits, path, text, match.start(), "address-allowlist")
    for match in ADDRESS_RE.finditer(text):
        display_value = match.group(1)
        if not any(street in display_value for street in ALLOWED_STREETS):
            _add(hits, path, text, match.start(), "address-allowlist")
    return hits


def scan_paths(paths: list[str]) -> list[Hit]:
    """Scan JSON paths and report stray fixtures outside the fixture tree.

    Args:
        paths: Paths to inspect.

    Returns:
        Sanitized findings.
    """
    hits: list[Hit] = []
    for raw_path in paths:
        path = Path(raw_path)
        normalized = path.as_posix()
        if path.suffix == ".json" and not normalized.startswith("tests/fixtures/"):
            hits.append(Hit(path=normalized, line=1, rule="fixture-location"))
            continue
        if path.suffix != ".json" or not path.exists():
            continue
        hits.extend(scan_text(normalized, path.read_text(encoding="utf-8")))
    return hits


def format_hit(hit: Hit) -> str:
    """Format one sanitized finding without echoing matched content.

    Args:
        hit: Finding to render.

    Returns:
        Sanitized finding string.
    """
    return f"{hit.path}:{hit.line}: {hit.rule}"


def _repository_json_paths() -> list[str]:
    """Return repository JSON paths relevant to fixture policy checks.

    Returns:
        JSON paths under tests.
    """
    return [path.as_posix() for path in Path("tests").rglob("*.json")]


def main(argv: list[str] | None = None) -> int:
    """Run the fixture PII checker.

    Args:
        argv: Optional command-line arguments.

    Returns:
        Process exit code.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*")
    args = parser.parse_args(argv)
    paths = list(dict.fromkeys([*args.paths, *_repository_json_paths()]))
    hits = scan_paths(paths)
    for hit in hits:
        print(format_hit(hit))
    return 1 if hits else 0


if __name__ == "__main__":
    raise SystemExit(main())

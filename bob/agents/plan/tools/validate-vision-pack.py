#!/usr/bin/env python3
"""Validate a visionary vision pack (shape, success, HTML mocks). Exit 1 on failure."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

PRIMARY_SHAPES = ("service", "website", "app")
REQUIRED_MOCKS = ("home", "empty", "error")
POETRY_PHRASES = (
    "users will love it",
    "users love it",
    "a lot",
    "feelings",
)
OBSERVABLE_HOW_PATTERNS = (
    r"`[^`]+`",
    r"\bpython\b",
    r"\bpytest\b",
    r"\bpip\b",
    r"\bworkflow\b",
    r"\.github",
    r"GitHub Actions",
    r"\bGHA\b",
    r"\bCI\b",
    r"docs/",
    r"tests/",
    r"tools/",
    r"README",
    r"\bvalidator\b",
    r"\bfixture",
    r"file content",
    r"\bexit\s+[01]\b",
    r"\b\d+%\b",
    r"\b\d+\s+of\b",
    r"/",
    r"\\",
)


def section(text: str, name: str) -> str:
    pattern = rf"^##\s+{re.escape(name)}\s*$"
    match = re.search(pattern, text, re.MULTILINE | re.IGNORECASE)
    if not match:
        return ""
    start = match.end()
    nxt = re.search(r"^##\s+", text[start:], re.MULTILINE)
    end = start + nxt.start() if nxt else len(text)
    return text[start:end]


def shape_is_unknown(shape: str) -> bool:
    if re.search(r"Primary:\s*UNKNOWN\b", shape, re.IGNORECASE):
        return True
    if re.search(r"^UNKNOWN\s*$", shape, re.MULTILINE | re.IGNORECASE):
        if not re.search(r"^LOCKED\s*$", shape, re.MULTILINE):
            return True
    return False


def shape_locked_primary(shape: str) -> str | None:
    for line in shape.splitlines():
        m = re.match(
            r"^\s*Primary(?:\s*\(one\))?:\s*(service|website|app)\s*\.?\s*$",
            line,
            re.IGNORECASE,
        )
        if m:
            return m.group(1).lower()
        m = re.match(
            r"^\s*Primary(?:\s*\(one\))?:\s*\*\*(service|website|app)\*\*\s*$",
            line,
            re.IGNORECASE,
        )
        if m:
            return m.group(1).lower()
        m = re.match(
            r"^\s*Reuse repo primary:\s*\*\*(service|website|app)\*\*",
            line,
            re.IGNORECASE,
        )
        if m:
            return m.group(1).lower()
    return None


def shape_has_locked(shape: str) -> bool:
    for line in shape.splitlines():
        if re.match(r"^\s*LOCKED\s*/\s*UNKNOWN\s*:?\s*$", line, re.IGNORECASE):
            continue
        if re.match(r"^\s*LOCKED\s*$", line, re.IGNORECASE):
            return True
    return False


def validate_shape(shape: str, errors: list[str]) -> bool:
    if not shape.strip():
        errors.append("shape: missing ## Shape section")
        return False
    if shape_is_unknown(shape):
        return True
    primary = shape_locked_primary(shape)
    if primary is None:
        errors.append(
            "shape: set Primary to service, website, or app (or mark shape UNKNOWN)"
        )
        return False
    if primary not in PRIMARY_SHAPES:
        errors.append(f"shape: invalid primary '{primary}'")
        return False
    if not shape_has_locked(shape):
        errors.append("shape: primary chosen but Shape is not LOCKED")
        return False
    return True


def success_is_unknown(success: str) -> bool:
    if re.search(r"(?im)^\s*UNKNOWN\s*$", success):
        return True
    if re.search(r"(?i)success\s+(?:section\s+)?is\s+UNKNOWN", success):
        return True
    if re.search(r"(?i)whole\s+table\s+is\s+UNKNOWN", success):
        stripped = success.strip().lower()
        if "unknown" in stripped and "|" not in success:
            return True
    return False


def field_has_poetry(text: str) -> bool:
    lowered = text.strip().lower()
    return any(phrase in lowered for phrase in POETRY_PHRASES)


def how_measured_observable(how: str) -> bool:
    how = how.strip()
    if not how:
        return False
    for pattern in OBSERVABLE_HOW_PATTERNS:
        if re.search(pattern, how, re.IGNORECASE):
            return True
    return False


def row_is_measurable(metric: str, target: str, how: str) -> bool:
    if field_has_poetry(metric) or field_has_poetry(target) or field_has_poetry(how):
        return False
    return how_measured_observable(how)


def parse_success_rows(success: str) -> list[tuple[str, str, str, str]]:
    rows: list[tuple[str, str, str, str]] = []
    for line in success.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 5:
            continue
        if cells[0].lower() in ("id", "----"):
            continue
        if all(re.match(r"^-+$", c) for c in cells):
            continue
        metric, target, how, fail_when = cells[1], cells[2], cells[3], cells[4]
        rows.append((metric, target, how, fail_when))
    return rows


def validate_success(success: str, errors: list[str]) -> bool:
    if not success.strip():
        errors.append("success: missing ## Success section")
        return False
    if success_is_unknown(success):
        return True
    rows = parse_success_rows(success)
    complete = [
        r
        for r in rows
        if all(field and not re.match(r"^-+$", field) for field in r)
    ]
    if not complete:
        errors.append(
            "success: add a complete table row (metric, target, how measured, fail-when) "
            "or mark Success UNKNOWN"
        )
        return False
    measurable = [r for r in complete if row_is_measurable(*r[:3])]
    if measurable:
        return True
    if any(field_has_poetry(m) or field_has_poetry(t) or field_has_poetry(h) for m, t, h, _ in complete):
        errors.append(
            "success: poetry is not measurable (metric/target/how-measured must cite "
            "a command, path, workflow, or count)"
        )
    else:
        errors.append(
            "success: how-measured must cite an observable check "
            "(command, path, workflow, or count)"
        )
    return False


def validate_mocks(mocks_dir: Path, errors: list[str]) -> bool:
    if not mocks_dir.is_dir():
        errors.append(f"mocks: directory not found: {mocks_dir}")
        return False
    html_files = list(mocks_dir.glob("*.html"))
    png_files = list(mocks_dir.glob("*.png"))
    if not html_files and png_files:
        errors.append("mocks: PNG-only mocks are not allowed")
        return False
    missing: list[str] = []
    for key in REQUIRED_MOCKS:
        if not (mocks_dir / f"{key}.html").is_file():
            missing.append(f"{key}.html")
    if missing:
        errors.append(f"mocks: missing required HTML: {', '.join(missing)}")
        return False
    return True


def validate_pack(vision_path: Path, mocks_dir: Path, historical: bool = False) -> list[str]:
    if historical:
        return []
    errors: list[str] = []
    text = vision_path.read_text(encoding="utf-8")
    shape_sec = section(text, "Shape")
    success_sec = section(text, "Success")

    shape_ok = validate_shape(shape_sec, errors)
    validate_success(success_sec, errors)

    shape_unknown = shape_is_unknown(shape_sec)
    if shape_ok and not shape_unknown:
        validate_mocks(mocks_dir, errors)
    return errors


def default_mocks_dir(vision_path: Path) -> Path:
    # docs/vision.md -> docs/mocks
    if vision_path.parent.name == "docs":
        return vision_path.parent / "mocks"
    return vision_path.parent / "mocks"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a visionary vision pack.")
    parser.add_argument("vision_md", type=Path, help="Path to docs/vision.md or FR pack")
    parser.add_argument(
        "--mocks-dir",
        type=Path,
        default=None,
        help="Directory with home/empty/error HTML (default: sibling mocks/)",
    )
    parser.add_argument(
        "--historical",
        action="store_true",
        help="Skip validation for archived packs (explicit exclude; default is fail)",
    )
    args = parser.parse_args(argv)
    vision_path = args.vision_md
    if not vision_path.is_file():
        print(f"validate-vision-pack: file not found: {vision_path}", file=sys.stderr)
        return 1
    mocks_dir = args.mocks_dir if args.mocks_dir else default_mocks_dir(vision_path)

    errors = validate_pack(vision_path, mocks_dir, historical=args.historical)
    if errors:
        print(f"validate-vision-pack: FAIL {vision_path}", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1
    if args.historical:
        print(f"validate-vision-pack: OK (historical) {vision_path}")
    else:
        print(f"validate-vision-pack: OK {vision_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

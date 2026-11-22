"""FR #8765: write and scan BOM-less ASCII *.ps1 (pytest-ascii-bom / WinPS 5.1).

BOM-less PowerShell with U+2014 (em dash) or other ord>127 bytes fails
``test_fr3391_staged_ps1_parse_and_bomless_ascii``. Writers (agents, intake,
pack edits) must sanitize to ASCII and write UTF-8 without BOM.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Common typography that sneaks into comments / Write-Host from editors or LLMs.
_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("\u2014", "-"),  # em dash
    ("\u2013", "-"),  # en dash
    ("\u2018", "'"),  # left single quote
    ("\u2019", "'"),  # right single quote
    ("\u201c", '"'),  # left double quote
    ("\u201d", '"'),  # right double quote
    ("\u2026", "..."),  # ellipsis
    ("\u00a0", " "),  # nbsp
)


def sanitize_ps1_text(text: str) -> str:
    """Replace common non-ASCII punctuation with ASCII stand-ins."""
    out = str(text or "")
    for src, dst in _REPLACEMENTS:
        out = out.replace(src, dst)
    return out


def write_ps1_ascii_nobom(path: Path | str, text: str) -> None:
    """Write sanitized UTF-8 without BOM. Raise if non-ASCII remains (fail closed)."""
    cleaned = sanitize_ps1_text(text)
    bad = [ch for ch in cleaned if ord(ch) > 127]
    if bad:
        sample = " ".join(f"U+{ord(ch):04X}" for ch in bad[:8])
        raise ValueError(
            f"non-ASCII remains after sanitize in {path}: {sample} "
            "(prefer ASCII - / ' / \" only for *.ps1; FR #8765)"
        )
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    # encoding=utf-8 writes no BOM
    dest.write_text(cleaned, encoding="utf-8", newline="\n")


def scan_ps1_path(path: Path | str) -> str | None:
    """Return a problem string for one *.ps1, or None when clean.

    BOM-prefixed files are allowed to carry UTF-8 (WinPS reads BOM). BOM-less
    files must be pure ASCII (FR #3391 / #3975 / #8765).
    """
    p = Path(path)
    try:
        raw = p.read_bytes()
    except OSError as exc:
        return f"{p}: read {exc}"
    if raw.startswith(b"\xef\xbb\xbf"):
        return None
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        return f"{p}: decode {exc}"
    if any(ord(ch) > 127 for ch in text):
        return str(p)
    return None


def scan_ps1_paths(paths: list[Path | str]) -> list[str]:
    """Scan many paths; return problem lines (empty = clean)."""
    out: list[str] = []
    for path in paths:
        hit = scan_ps1_path(path)
        if hit:
            out.append(hit)
    return out


def iter_ps1_under(roots: list[Path | str]) -> list[Path]:
    found: list[Path] = []
    for root in roots:
        base = Path(root)
        if base.is_file() and base.suffix.lower() == ".ps1":
            found.append(base)
            continue
        if not base.is_dir():
            continue
        for path in base.rglob("*.ps1"):
            # Skip VCS / hidden dirs under the scan root (not parents like
            # C:\\Users\\...\\.grok\\... which host job worktrees).
            try:
                rel_parts = path.relative_to(base).parts
            except ValueError:
                rel_parts = path.parts
            if any(part in (".git", ".hg", ".venv", "node_modules") or part.startswith(".") for part in rel_parts[:-1]):
                continue
            found.append(path)
    return sorted(set(found))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="bobiverse_ps1_ascii")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("check", help="exit 2 when BOM-less *.ps1 has non-ASCII")
    c.add_argument("--path", action="append", default=[], help="file or directory")
    c.add_argument(
        "--repo",
        default="",
        help="repo root: scan common/scripts bob/scripts jeeves/scripts airc/scripts",
    )

    w = sub.add_parser("write", help="sanitize stdin -> ASCII UTF-8 no BOM file")
    w.add_argument("dest", help="output .ps1 path")

    s = sub.add_parser("sanitize", help="print sanitized stdin to stdout")

    args = p.parse_args(argv)
    if args.cmd == "sanitize":
        sys.stdout.write(sanitize_ps1_text(sys.stdin.read()))
        return 0
    if args.cmd == "write":
        write_ps1_ascii_nobom(args.dest, sys.stdin.read())
        print(f"wrote {args.dest}")
        return 0

    paths: list[Path] = []
    for item in args.path or []:
        paths.extend(iter_ps1_under([item]))
    if args.repo:
        root = Path(args.repo)
        paths.extend(
            iter_ps1_under(
                [
                    root / "common" / "scripts",
                    root / "bob" / "scripts",
                    root / "jeeves" / "scripts",
                    root / "airc" / "scripts",
                ]
            )
        )
    if not paths and not args.path and not args.repo:
        p.error("pass --path and/or --repo")
    problems = scan_ps1_paths(paths)
    if problems:
        print("BOM-less *.ps1 with non-ASCII (WinPS 5.1 ANSI mis-parse risk):")
        for line in problems[:80]:
            print(line)
        return 2
    print(f"PS1_ASCII_OK count={len(paths)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""BOB-D1 / FR #8805: parse-only Depends-on lines from an issue body.

Returns ordered, deduplicated (repo, number) tuples. No ingestion, queue,
GitClaim, or offer gating. Later BOB-D* slices own resolution and skip-until-closed.
"""
from __future__ import annotations

import re

# Dedicated line only. Use [^\S\n] (not \s) so the value cannot cross newlines.
_LINE_RE = re.compile(
    r"(?im)^[^\S\n]*"
    r"(?:\*{0,2}|`{0,2})"
    r"Depends-on"
    r"(?:\*{0,2}|`{0,2})"
    r"[^\S\n]*:"
    r"(?:\*{0,2}|`{0,2})?"
    r"[^\S\n]*(.*)$"
)
_QUALIFIED_RE = re.compile(r"^([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)#(\d+)$")
_RELATIVE_RE = re.compile(r"^#(\d+)$")
_NONE_RE = re.compile(r"^\(none\)$", re.I)


def parse_depends_on(body: str | None, repo: str = "") -> tuple[tuple[str, int], ...]:
    """Parse ``Depends-on:`` lines into ``(repo, number)`` tuples.

    Relative ``#N`` uses ``repo`` (default empty string). Qualified
    ``owner/repo#N`` keeps the owner/repo as written. Deduplicates in
    first-seen order. Ignores ``(none)``, planning IDs, and non-matching tokens.
    """
    if body is None:
        return ()
    text = str(body)
    if not text.strip():
        return ()
    home = str(repo or "").strip()
    out: list[tuple[str, int]] = []
    seen: set[tuple[str, int]] = set()
    for m in _LINE_RE.finditer(text):
        value = (m.group(1) or "").strip()
        if not value or _NONE_RE.match(value):
            continue
        for raw in re.split(r"[,;\s]+", value):
            tok = raw.strip().strip("`*")
            if not tok:
                continue
            qm = _QUALIFIED_RE.match(tok)
            if qm:
                pair = (qm.group(1), int(qm.group(2)))
            else:
                rm = _RELATIVE_RE.match(tok)
                if not rm:
                    continue
                pair = (home, int(rm.group(1)))
            if pair in seen:
                continue
            seen.add(pair)
            out.append(pair)
    return tuple(out)


def format_depends_on_line(
    refs: list[tuple[str, int]] | tuple[tuple[str, int], ...],
    repo: str = "",
) -> str:
    """Plain ``Depends-on:`` line (no markdown bold). Relative ``#N`` when same repo."""
    home = str(repo or "").strip()
    parts: list[str] = []
    seen: set[tuple[str, int]] = set()
    for r, n in refs or ():
        try:
            num = int(n)
        except (TypeError, ValueError):
            continue
        if num < 1:
            continue
        repo_s = str(r or "").strip()
        key = (repo_s.lower(), num)
        if key in seen:
            continue
        seen.add(key)
        if repo_s and home and repo_s.lower() == home.lower():
            parts.append(f"#{num}")
        elif repo_s:
            parts.append(f"{repo_s}#{num}")
        else:
            parts.append(f"#{num}")
    if not parts:
        return "Depends-on: (none)"
    return "Depends-on: " + ", ".join(parts)


def merge_depends_on_body(
    body: str | None,
    new_refs: list[tuple[str, int]] | tuple[tuple[str, int], ...],
    repo: str = "",
) -> tuple[str, bool]:
    """Union ``new_refs`` into a plain ``Depends-on:`` line; drop bold/legacy lines.

    Returns ``(new_body, changed)``. Existing parseable Depends-on refs are kept
    (FR #9469). ``(none)`` alone is replaced when real refs are added.
    """
    home = str(repo or "").strip()
    text = str(body or "")
    existing = list(parse_depends_on(text, repo=home))
    merged: list[tuple[str, int]] = []
    seen: set[tuple[str, int]] = set()
    for pair in list(existing) + list(new_refs or ()):
        try:
            repo_s = str(pair[0] or "").strip()
            num = int(pair[1])
        except (TypeError, ValueError, IndexError):
            continue
        if num < 1:
            continue
        key = (repo_s.lower(), num)
        if key in seen:
            continue
        seen.add(key)
        merged.append((repo_s, num))
    if not merged:
        return text, False
    if set((r.lower(), n) for r, n in existing) == set((r.lower(), n) for r, n in merged):
        # Still rewrite when body only has bold ``**Depends-on:**`` (not plain).
        plain_ok = False
        for m in _LINE_RE.finditer(text):
            raw = m.group(0) or ""
            if re.match(r"(?im)^[^\S\n]*Depends-on:", raw):
                plain_ok = True
                break
        if plain_ok:
            return text, False
    line = format_depends_on_line(merged, repo=home)
    # Drop every Depends-on line (plain or bold); keep the rest of the body.
    kept: list[str] = []
    for raw_line in text.splitlines(keepends=True):
        if _LINE_RE.match(raw_line.rstrip("\r\n")):
            continue
        kept.append(raw_line)
    rest = "".join(kept).lstrip("\n")
    if rest and not rest.endswith("\n"):
        rest = rest + "\n"
    new_body = line + "\n" + rest if rest else line + "\n"
    return new_body, new_body != text
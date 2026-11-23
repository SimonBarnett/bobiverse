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
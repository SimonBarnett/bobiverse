"""FR #3803 / FR #3414: exact-title twin selection for harvest-lesson tips.

PowerShell ``-match`` (regex) and short shared substrings (for example
``lessons that already live``) can sweep unrelated open tips. Callers must
use equality or a long unique ``StartsWith`` prefix of the full tip title
(or the exact Harvested-lessons bullet text).
"""

from __future__ import annotations

# Substrings that appear in many FAIL-supersede / already-covered tips.
# Using one of these alone as a twin needle is forbidden.
BANNED_SHARED_NEEDLES = (
    "lessons that already live",
    "must FAIL-supersede when intake",
    "must FAIL-supersede when intake parks a thin duplicate",
    "cite the skill-book row on main",
    "Closed unmerged",
)

# Minimum unique needle length (full lesson titles are far longer).
MIN_NEEDLE_LEN = 40


def is_exact_harvest_twin_title(title: str, needle: str) -> bool:
    """Return True only for exact title equality or unique long prefix match.

    Never treat a banned shared substring as a twin needle by itself.
    """
    if not isinstance(title, str) or not isinstance(needle, str):
        return False
    t = title.strip()
    n = needle.strip()
    if not t or not n:
        return False
    if len(n) < MIN_NEEDLE_LEN:
        return False
    n_low = n.lower()
    for banned in BANNED_SHARED_NEEDLES:
        if n_low == banned.lower():
            return False
    # Exact equality or StartsWith of the full unique title/lesson prefix.
    return t == n or t.startswith(n)


def select_exact_title_twins(titles: list[str], needle: str) -> list[str]:
    """Filter titles with :func:`is_exact_harvest_twin_title` (order preserved)."""
    return [t for t in titles if is_exact_harvest_twin_title(t, needle)]

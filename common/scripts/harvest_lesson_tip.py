"""FR #10373: harvest-lesson intake tips must stay single-book doc edits.

Stack pollution (hundreds of product files on ``intake/in_*``) breaks MRB CI.
Intake filing must only touch allowlisted skill-book paths; chair skips MRB
when a live PR changed paths outside that set.
"""
from __future__ import annotations

SKILL_PREFIX = "common/.grok/skills/"
INTAKE_HARVEST_PREFIX = "docs/intake-harvest/"
HARVEST_LOG_PATH = "common/docs/skill-harvest-log.md"
MAX_CHANGED_PATHS = 8


def _norm_path(path: str) -> str:
    return str(path or "").strip().replace("\\", "/").lstrip("/")


def harvest_lesson_path_allowed(path: str) -> bool:
    """True when ``path`` may appear on a harvest-lesson tip branch."""
    p = _norm_path(path)
    if not p:
        return False
    if p.startswith(INTAKE_HARVEST_PREFIX) and p.endswith(".md"):
        return True
    if p == HARVEST_LOG_PATH:
        return True
    if not p.startswith(SKILL_PREFIX):
        return False
    if p.endswith("/SKILL.md") or p.endswith("/lessons.md"):
        return True
    return False


def harvest_lesson_paths_ok(paths: list[str]) -> bool:
    """True when every changed path is allowlisted and count is bounded."""
    norm = [_norm_path(x) for x in paths if str(x or "").strip()]
    if not norm:
        return True
    if len(norm) > MAX_CHANGED_PATHS:
        return False
    return all(harvest_lesson_path_allowed(p) for p in norm)


def assert_lesson_files_allowlist(files: list[dict[str, str]]) -> None:
    """Raise ValueError when harvest lesson filing touches disallowed paths."""
    paths = [str(f.get("path") or "") for f in (files or []) if isinstance(f, dict)]
    bad = [p for p in paths if p and not harvest_lesson_path_allowed(p)]
    if bad:
        raise ValueError(f"harvest-lesson disallowed paths: {bad!r}")


def _row_is_harvest_lesson(row: dict) -> bool:
    labs = row.get("labels") or ()
    if isinstance(labs, str):
        labs = [labs]
    labs_l = {str(x).lower() for x in labs}
    title = str(row.get("title") or "").strip().lower()
    return "harvest-lesson" in labs_l or title.startswith("lesson(")


def harvest_lesson_row_polluted(row: dict) -> bool:
    """True when an MRB row looks like a stack-polluted harvest-lesson tip."""
    if not _row_is_harvest_lesson(row):
        return False
    paths: list[str] = []
    for key in ("changed_files", "files"):
        raw = row.get(key)
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, str):
                    paths.append(item)
                elif isinstance(item, dict):
                    paths.append(str(item.get("filename") or item.get("path") or ""))
        if paths:
            break
    return not harvest_lesson_paths_ok(paths)
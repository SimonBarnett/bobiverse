"""No-GitHub webhook intake (FR #26).

POST /bob/v1/intake accepts issues/FRs/skill harvests from machines without `gh`.
Service credential files on GitHub; zero AI tokens. Scripts only.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

KINDS = frozenset({"issue", "fr", "skill", "harvest"})
MAX_BODY_BYTES = 256 * 1024
MAX_FILES = 32
MAX_FILE_BYTES = 128 * 1024
DEFAULT_RATE_PER_MIN = 30
# FR #795: drop archived superseded repos (gh-Jeeves, agentic_build, AgentMonitor,
# bob-design-uat, agentic_irc). New work intakes to bobiverse (or live siblings).
DEFAULT_ALLOW_REPOS = frozenset(
    {
        "SimonBarnett/bobiverse",
        "SimonBarnett/skills-visionary",
        "SimonBarnett/agentic_fomprep",
        "SimonBarnett/a-search",  # FR #3023: Plan product; intake Flush must not drop
        "SimonBarnett/trutex",  # FR #3050: private Plan product; allowlist ignores visibility
    }
)
_SECRETISH = re.compile(
    r"(?i)(password\s*=\s*\S+|api[_-]?key\s*=\s*\S+|ghp_[A-Za-z0-9]{20,}|"
    r"sk-[A-Za-z0-9]{10,}|xox[baprs]-[A-Za-z0-9-]+|bearer\s+\S{8,})"
)
_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_WORKER_RECEIPT_MARKER = re.compile(
    r"(?i)\b(?:GIVEUP|SKIP|self-MRB|twin|DONE|CLOSED|duplicate|merged)\b"
    r"|\b(?:FR|MRB|UAT)\s*#\d+\b"
)


def is_worker_receipt_issue(*, kind: str, title: str, body: str) -> bool:
    """Keep DONE/GIVEUP/SKIP/self-MRB harvest receipts out of GitHub issues."""
    if kind not in ("issue", "fr"):
        return False
    if not re.match(r"(?i)^\s*harvest:", title or ""):
        return False
    if not re.search(r"(?i)Session summary:|_via-intake.*Invoke-BobiverseHarvest", body or ""):
        return False
    return bool(_WORKER_RECEIPT_MARKER.search(f"{title}\n{body}"))


_DO_NOT_FILE_PROBE_RE = re.compile(
    r"(?i)do-not-file|probe-do-not-file|probe-shape-only|redeploy-probe"
)


def is_do_not_file_probe(*, title: str, body: str = "") -> bool:
    """Drop intentional probe filings (FR #2595 / crash-probe class)."""
    return bool(_DO_NOT_FILE_PROBE_RE.search(f"{title or ''}\n{body or ''}"))


# FR #2595 drain / file_submission: stronger than _WORKER_RECEIPT_MARKER.
# Bare "FR #N", "CLOSED", or "merged" alone are common in real playbook harvests
# (MRB #2597); those must still open draft PRs. Receipts use DONE/GIVEUP/SKIP/
# self-MRB/twin/"duplicate of".
# FR #2650: also PASS/FAIL - "harvest: MRB #N PASS: merged" was filed as a draft
# PR and offered as MRB via the PR-opened webhook (#2647 class).
_HARVEST_KIND_RECEIPT_MARKER = re.compile(
    r"(?i)\b(?:GIVEUP|SKIP|self-MRB|twin|DONE|PASS|FAIL)\b"
    r"|\bduplicate of\b"
)


def is_harvest_worker_receipt(*, kind: str, title: str, body: str) -> bool:
    """kind=harvest session rows that are DONE/PASS/FAIL/twin/GIVEUP receipts.

    FR #2595 / #2650: these must not stay as open draft PRs (webhook would
    enqueue them as MRB work). Real playbook harvests without receipt markers
    still open draft PRs (MRB #2597: bare FR #N / merged alone are not enough).
    FR #2705: receipt markers never drop Lessons - callers that see lessons must
    open a non-draft skill-book PR instead of receipt_recorded alone.
    """
    if str(kind or "").strip().lower() != "harvest":
        return False
    return bool(_HARVEST_KIND_RECEIPT_MARKER.search(f"{title or ''}\n{body or ''}"))


# FR #2705: Lessons: bullets that are real playbook lines (not the placeholder).
_LESSONS_SECTION_RE = re.compile(
    r"(?is)(?:^|\n)\s*Lessons:\s*\n(?P<body>.*?)(?=\n\s*_[a-z]|\n\s*Existing PR:|\Z)"
)
_LESSON_BULLET_RE = re.compile(r"(?m)^\s*[-*]\s+(?P<text>.+?)\s*$")
_LESSON_PLACEHOLDER_RE = re.compile(r"(?i)^\(?\s*no new playbook line\s*\)?$")
HARVESTED_LESSONS_HEADING = "## Harvested lessons (intake)"
LESSON_PR_MRB_INSTRUCTION = (
    "MRB: verify that the lesson is generalised and placed in the right SKILL.md "
    "(move or reword it if not), then merge."
)
DEFAULT_SKILL_BOOK = "harvest"
SKILL_BOOK_PATHS: dict[str, str] = {
    "harvest": "common/.grok/skills/harvest/SKILL.md",
    "harvest-agent-skills": "common/.grok/skills/harvest-agent-skills/SKILL.md",
    "bobiverse-fleet-ops": "common/.grok/skills/bobiverse-fleet-ops/SKILL.md",
    "bobiverse-bob": "bob/.grok/skills/bobiverse-bob/SKILL.md",
    "bobiverse-bob-worker": "bob/.grok/skills/bobiverse-bob-worker/SKILL.md",
    "bobiverse-bob-job-irc": "bob/.grok/skills/bobiverse-bob-job-irc/SKILL.md",
    "bobiverse-bob-job-fr": "bob/.grok/skills/bobiverse-bob-job-fr/SKILL.md",
    "bobiverse-bob-job-mrb": "bob/.grok/skills/bobiverse-bob-job-mrb/SKILL.md",
    "bobiverse-bob-job-uat": "bob/.grok/skills/bobiverse-bob-job-uat/SKILL.md",
    "bobiverse-bob-commands": "bob/.grok/skills/bobiverse-bob-commands/SKILL.md",
    "bobiverse-bob-troubleshooting": "bob/.grok/skills/bobiverse-bob-troubleshooting/SKILL.md",
    "bobiverse-bob-plan": "bob/.grok/skills/bobiverse-bob-plan/SKILL.md",
    "bobiverse-worker-seat": "bob/agents/worker/.grok/skills/bobiverse-worker-seat/SKILL.md",
    "bobiverse-jeeves": "jeeves/.grok/skills/bobiverse-jeeves/SKILL.md",
    "bobiverse-jeeves-commands": "jeeves/.grok/skills/bobiverse-jeeves-commands/SKILL.md",
    "bobiverse-jeeves-monitor": "jeeves/.grok/skills/bobiverse-jeeves-monitor/SKILL.md",
    "bobiverse-jeeves-troubleshooting": "jeeves/.grok/skills/bobiverse-jeeves-troubleshooting/SKILL.md",
    "bobiverse-airc": "airc/.grok/skills/bobiverse-airc/SKILL.md",
    "bobiverse-airc-commands": "airc/.grok/skills/bobiverse-airc-commands/SKILL.md",
    "bobiverse-airc-troubleshooting": "airc/.grok/skills/bobiverse-airc-troubleshooting/SKILL.md",
}
# (keywords_all_present_lowercase, book_name) - first match wins.
# Product-specific cues before bare mrb/uat so "MRB #N PASS" + bob-worker lesson routes right.
_SKILL_BOOK_KEYWORD_HINTS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("bob-worker",), "bobiverse-bob-worker"),
    (("_release_gen",), "bobiverse-bob-worker"),
    (("release_gen",), "bobiverse-bob-worker"),
    (("done-miss",), "bobiverse-bob-worker"),
    (("boredemitter",), "bobiverse-bob-worker"),
    (("worker", "seat"), "bobiverse-worker-seat"),
    (("outbox", "privmsg"), "bobiverse-worker-seat"),
    (("fleet-ops",), "bobiverse-fleet-ops"),
    (("hotpatch",), "bobiverse-fleet-ops"),
    (("mrb", "hostile"), "bobiverse-bob-job-mrb"),
    (("mrb",), "bobiverse-bob-job-mrb"),
    (("uat",), "bobiverse-bob-job-uat"),
    (("jeeves", "monitor"), "bobiverse-jeeves-monitor"),
    (("jeeves",), "bobiverse-jeeves"),
    (("airc",), "bobiverse-airc"),
    (("plan", "vision"), "bobiverse-bob-plan"),
)
# FR #3004: when source.skill_book is the soft default "harvest", only these strong cues
# re-route. Bare "mrb"/"uat" appear in almost every job session summary and must not move
# MSI/outbox product tips (or EncodedCommand tips) off harvest.
_SOFT_HARVEST_OVERRIDE_HINTS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("bob-worker",), "bobiverse-bob-worker"),
    (("_release_gen",), "bobiverse-bob-worker"),
    (("release_gen",), "bobiverse-bob-worker"),
    (("done-miss",), "bobiverse-bob-worker"),
    (("boredemitter",), "bobiverse-bob-worker"),
    (("fleet-ops",), "bobiverse-fleet-ops"),
    (("hotpatch",), "bobiverse-fleet-ops"),
)


def infer_skill_book_from_text(title: str = "", body: str = "") -> str | None:
    """Return the first keyword-hint book for title+body, or None (FR #2705 / #3004)."""
    blob = f"{title or ''}\n{body or ''}".lower()
    for keys, book in _SKILL_BOOK_KEYWORD_HINTS:
        if all(k in blob for k in keys):
            return book
    return None


def infer_soft_harvest_override(title: str = "", body: str = "") -> str | None:
    """Product-book override when -Book default is harvest (FR #3004)."""
    blob = f"{title or ''}\n{body or ''}".lower()
    for keys, book in _SOFT_HARVEST_OVERRIDE_HINTS:
        if all(k in blob for k in keys):
            return book
    return None


def extract_harvest_lessons(body: str) -> list[str]:
    """Return real Lessons: bullets; drop the '(no new playbook line)' placeholder (FR #2705)."""
    text = str(body or "")
    m = _LESSONS_SECTION_RE.search(text)
    if not m:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for bm in _LESSON_BULLET_RE.finditer(m.group("body")):
        line = (bm.group("text") or "").strip()
        if not line or _LESSON_PLACEHOLDER_RE.match(line):
            continue
        if line in seen:
            continue
        seen.add(line)
        out.append(line)
    return out


def resolve_skill_book(
    *,
    skill_book: str = "",
    title: str = "",
    body: str = "",
) -> tuple[str, str]:
    """Map source.skill_book / path / keywords -> (book_name, repo-relative SKILL.md path).

    FR #2705: explicit book or path wins; else deterministic keyword routing; else harvest.
    FR #3004: default ``harvest`` (Invoke-BobiverseHarvest -Book default) yields to a
    keyword-inferred product book so bob-worker / fleet-ops playbooks are not parked
    under harvest when the owning skill already has the lesson on main.
    """
    raw = str(skill_book or "").strip().replace("\\", "/")
    if raw:
        lower = raw.lower()
        if lower.endswith("skill.md") or "/.grok/skills/" in lower:
            path = raw.lstrip("/")
            name = Path(path).parent.name or DEFAULT_SKILL_BOOK
            return name, path
        key = lower
        if key.startswith("bobiverse-"):
            pass
        elif key in SKILL_BOOK_PATHS:
            pass
        else:
            # bare name without prefix
            pass
        if key in SKILL_BOOK_PATHS:
            # Soft default only: harvest yields to strong product cues (not bare mrb/uat).
            if key == DEFAULT_SKILL_BOOK:
                soft = infer_soft_harvest_override(title, body)
                if soft and soft in SKILL_BOOK_PATHS:
                    return soft, SKILL_BOOK_PATHS[soft]
            return key, SKILL_BOOK_PATHS[key]
        # Unknown book name: still target harvest folder named after it under common.
        safe = re.sub(r"[^A-Za-z0-9._-]+", "-", key).strip("-") or DEFAULT_SKILL_BOOK
        if safe in SKILL_BOOK_PATHS:
            return safe, SKILL_BOOK_PATHS[safe]
        return safe, f"common/.grok/skills/{safe}/SKILL.md"

    inferred = infer_skill_book_from_text(title, body)
    if inferred and inferred in SKILL_BOOK_PATHS:
        return inferred, SKILL_BOOK_PATHS[inferred]
    return DEFAULT_SKILL_BOOK, SKILL_BOOK_PATHS[DEFAULT_SKILL_BOOK]


# FR #2970: FAIL-supersede / wrong-book / Harvest-lesson MRB *process* playbooks belong in
# bobiverse-bob-job-mrb. Default -Book harvest must not open lesson(harvest) twins that
# restate that routing and get FAIL-superseded forever.
# MRB #2973 hostile: bare "FAIL-supersede" alone must NOT match — a product harvest whose
# summary mentions FAIL-superseded would otherwise re-route MSI/outbox tips into job-mrb.
# Mirror Invoke-BobiverseHarvest Test-HarvestFailSupersedeProcessLoop: process cue required;
# FAIL-supersede alone is insufficient.
# FR #2991: thin already-covered twins ("fleet-ops already cover … close thin twins") also
# lack process cues but must skip when FAIL-supersede + thin-twin restatement cues match.
_FAIL_SUPERSEDE_RE = re.compile(r"(?i)FAIL[- ]supersede")
_MRB_PROCESS_CUE_RE = re.compile(
    r"(?i)(?:"
    r"wrong[- ]book|"
    r"belong(?:s)? in\s+`?bobiverse-bob-job-mrb`?|"
    r"docs/mrb-N after skill merge|"
    r"Harvest-lesson MRB:\s*process|"
    r"never merge a second copy(?:\s+that says keep MRB process)?\s+in harvest|"
    r"process playbooks?|"
    r"park(?:ed|s)?\s+under\s+harvest"
    r")"
)
_THIN_TWIN_CUE_RE = re.compile(
    r"(?i)(?:"
    r"already\s+cover(?:s|ed)?|"
    r"close\s+thin\b|"
    r"thin\s+harvest(?:ed)?[- ]?lessons?\b|"
    r"thin\s+harvest\s+twin|"
    r"Harvested-lessons\s+intake\s+twins?|"
    r"citing\s+(?:the\s+)?product(?:/move)?\s*PRs?"
    r")"
)


def is_fail_supersede_thin_twin_lesson(text: str) -> bool:
    """True for FAIL-supersede tips that only restate already-covered / close-thin-twin.

    FR #2991: requires FAIL-supersede AND a thin-twin cue. Bare FAIL-supersede plus a
    real product playbook (no thin-twin wording) returns False (MRB #2973 spirit).
    """
    t = str(text or "")
    if not t.strip():
        return False
    if not _FAIL_SUPERSEDE_RE.search(t):
        return False
    return bool(_THIN_TWIN_CUE_RE.search(t))


def is_mrb_process_routing_lesson(text: str) -> bool:
    """True when the lesson/summary is MRB process-routing (not a product playbook).

    Requires a process cue. Bare FAIL-supersede in a session summary does not qualify
    (MRB #2973) so real product lessons still open under harvest.
    """
    t = str(text or "")
    if not t.strip():
        return False
    if not _MRB_PROCESS_CUE_RE.search(t):
        return False
    # Strong process anchors: durable home is job-mrb / parked under harvest / promote order.
    if re.search(r"(?i)belong(?:s)? in\s+`?bobiverse-bob-job-mrb", t):
        return True
    if re.search(r"(?i)park(?:ed|s)?\s+under\s+harvest", t):
        return True
    if re.search(
        r"(?i)docs/mrb-N after skill merge|Harvest-lesson MRB:\s*process|"
        r"never merge a second copy",
        t,
    ):
        return True
    if re.search(r"(?i)process playbooks?", t) and re.search(
        r"(?i)bobiverse-bob-job-mrb|harvest", t
    ):
        return True
    # FAIL-supersede + process cue (e.g. wrong-book) — same AND as the PS1 client skip.
    if _FAIL_SUPERSEDE_RE.search(t):
        return True
    return False


def thin_twin_fail_supersede_already_covered(filer: Any, repo: str) -> bool:
    """True when fleet-ops / harvest / job-mrb already carry twin-close or MSI SkipCopy gates.

    FR #2991: thin FAIL-supersede restatements skip when CAST IRON coverage is on main.
    """
    harvest = _filer_get_file(filer, repo, SKILL_BOOK_PATHS["harvest"]).lower()
    mrb = _filer_get_file(filer, repo, SKILL_BOOK_PATHS["bobiverse-bob-job-mrb"]).lower()
    fleet_path = SKILL_BOOK_PATHS.get("bobiverse-fleet-ops") or (
        "common/.grok/skills/bobiverse-fleet-ops/SKILL.md"
    )
    fleet = _filer_get_file(filer, repo, fleet_path).lower()
    if mrb_process_routing_already_covered(filer, repo):
        return True
    harvest_ok = ("do not land a second copy" in harvest) or (
        "fail-supersede" in harvest and "twin" in harvest
    )
    fleet_ok = (
        ("skipcopy" in fleet.replace("-", "").replace(" ", ""))
        or ("sync-skip-stale-worktree" in fleet)
        or ("fr #2982" in fleet)
        or ("msi productversion" in fleet)
    )
    mrb_twin = ("fail-supersede" in mrb) or ("re-offered or already-merged" in mrb)
    return bool((harvest_ok and (fleet_ok or mrb_twin)) or (fleet_ok and mrb_twin))


def _normalize_lesson_key(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def filter_new_lessons(existing_md: str, lessons: list[str]) -> list[str]:
    """Drop lessons already present in existing_md (FR #2970 de-dupe)."""
    base = _normalize_lesson_key(existing_md)
    out: list[str] = []
    seen: set[str] = set()
    for raw in lessons:
        line = str(raw or "").strip()
        if not line:
            continue
        key = _normalize_lesson_key(line)
        if key in seen:
            continue
        seen.add(key)
        if key and key in base:
            continue
        out.append(line)
    return out


def mrb_process_routing_already_covered(filer: Any, repo: str) -> bool:
    """True when harvest + job-mrb already carry the CAST IRON process-routing gates."""
    harvest = _filer_get_file(filer, repo, SKILL_BOOK_PATHS["harvest"]).lower()
    mrb = _filer_get_file(filer, repo, SKILL_BOOK_PATHS["bobiverse-bob-job-mrb"]).lower()
    harvest_ok = ("do not land a second copy" in harvest) or (
        "bobiverse-bob-job-mrb" in harvest and "harvest-lesson mrb" in harvest
    )
    mrb_ok = (("docs/mrb-n" in mrb) or ("docs/mrb-" in mrb)) and (
        ("behind-main" in mrb)
        or ("harvest promote order" in mrb)
        or ("harvest-lesson" in mrb)
    )
    return bool(harvest_ok and mrb_ok)


def apply_lessons_to_skill_md(existing: str, lessons: list[str]) -> str:
    """Append lessons under ``## Harvested lessons (intake)`` (FR #2705)."""
    fresh = filter_new_lessons(existing, lessons)
    base = str(existing or "").rstrip() + "\n"
    bullets = "\n".join(f"- {x}" for x in fresh if str(x).strip())
    if not bullets:
        return base
    heading = HARVESTED_LESSONS_HEADING
    if heading in base:
        # Append under existing heading (before any later ## if present after it).
        idx = base.index(heading)
        after = base[idx + len(heading) :]
        next_h = re.search(r"\n##\s+", after)
        if next_h:
            insert_at = idx + len(heading) + next_h.start()
            return base[:insert_at].rstrip() + "\n" + bullets + "\n" + base[insert_at:]
        return base.rstrip() + "\n" + bullets + "\n"
    return base.rstrip() + "\n\n" + heading + "\n\n" + bullets + "\n"


def _filer_get_file(filer: Any, repo: str, path: str) -> str:
    getter = getattr(filer, "get_file_content", None)
    if not callable(getter):
        return ""
    try:
        val = getter(repo, path)
    except Exception:
        return ""
    return str(val or "")


def _filer_create_pr(
    filer: Any,
    repo: str,
    title: str,
    body: str,
    branch: str,
    files: list[dict[str, str]],
    labels: list[str],
    *,
    draft: bool,
) -> dict[str, Any]:
    """Prefer create_pr (non-draft) / create_draft_pr; Fake supports both (FR #2705)."""
    if draft:
        return filer.create_draft_pr(repo, title, body, branch, files, labels)
    create_pr = getattr(filer, "create_pr", None)
    if callable(create_pr):
        return create_pr(repo, title, body, branch, files, labels)
    # Fallback: draft API with draft=False kw if supported.
    try:
        return filer.create_draft_pr(
            repo, title, body, branch, files, labels, draft=False  # type: ignore[call-arg]
        )
    except TypeError:
        out = filer.create_draft_pr(repo, title, body, branch, files, labels)
        return out


def build_lesson_pr_title(book: str, lessons: list[str]) -> str:
    first = (lessons[0] if lessons else "harvest lesson").strip()
    tip = first[:72] + ("..." if len(first) > 72 else "")
    return f"lesson({book}): {tip}"


def build_lesson_pr_body(*, book: str, path: str, lessons: list[str], original_body: str) -> str:
    lines = [
        LESSON_PR_MRB_INSTRUCTION,
        "",
        f"Target skill book: `{book}` (`{path}`).",
        "",
        "Lessons:",
        *[f"- {x}" for x in lessons],
        "",
        "---",
        "",
        str(original_body or "").rstrip(),
        "",
    ]
    return "\n".join(lines)


_PR_URL_RE = re.compile(
    r"https://github\.com/(?P<owner>[A-Za-z0-9_.-]+)/(?P<name>[A-Za-z0-9_.-]+)/pull/(?P<num>\d+)",
    re.I,
)
_PR_OPENED_TITLE_RE = re.compile(r"(?i)\bPR\s+opened\b")


def extract_existing_pr_ref(repo: str, title: str, body: str) -> tuple[int, str] | None:
    """If title/body already points at a GitHub pull, return (number, html_url).

    Used so skill/harvest honesty-box summaries that follow an already-opened ``gh``
    PR do not file a second fallback issue (FR #1812).
    """
    blob = f"{title or ''}\n{body or ''}"
    m = _PR_URL_RE.search(blob)
    if not m:
        return None
    num = int(m.group("num"))
    owner, name = m.group("owner"), m.group("name")
    # Prefer the URL's repo; fall back to intake repo for display consistency.
    url_repo = f"{owner}/{name}"
    use_repo = url_repo if url_repo else repo
    return num, f"https://github.com/{use_repo}/pull/{num}"



class GitHubFiler(Protocol):
    """Service credential surface (fake in tests)."""

    def create_issue(
        self,
        repo: str,
        title: str,
        body: str,
        labels: list[str],
    ) -> dict[str, Any]:
        """Return {url, number}."""

    def create_draft_pr(
        self,
        repo: str,
        title: str,
        body: str,
        branch: str,
        files: list[dict[str, str]],
        labels: list[str],
    ) -> dict[str, Any]:
        """Return {url, number, branch}. May raise GitHubDown."""

    def create_pr(
        self,
        repo: str,
        title: str,
        body: str,
        branch: str,
        files: list[dict[str, str]],
        labels: list[str],
    ) -> dict[str, Any]:
        """Return {url, number, branch} for a non-draft PR (FR #2705 lesson PRs)."""

    def get_file_content(self, repo: str, path: str) -> str:
        """Optional: current file contents on the default branch (FR #2705)."""
        return ""

    def find_pull_by_head(self, repo: str, head_branch: str) -> dict[str, Any] | None:
        """Optional: return {url, number, branch} for an existing head branch, else None."""
        return None


class GitHubDown(RuntimeError):
    """GitHub filing failed. ``reason`` selects the intake log tag (FR #2579)."""

    def __init__(self, message: str = "", *, reason: str = "github_down") -> None:
        super().__init__(message)
        self.reason = (reason or "github_down").strip() or "github_down"


@dataclass
class FakeGitHubFiler:
    """In-memory GitHub for G1 / FR #26 tests."""

    issues: list[dict[str, Any]] = field(default_factory=list)
    prs: list[dict[str, Any]] = field(default_factory=list)
    repo_files: dict[str, str] = field(default_factory=dict)
    down: bool = False
    _n: int = 1000

    def create_issue(self, repo: str, title: str, body: str, labels: list[str]) -> dict[str, Any]:
        if self.down:
            raise GitHubDown("github unreachable")
        self._n += 1
        row = {
            "repo": repo,
            "number": self._n,
            "title": title,
            "body": body,
            "labels": list(labels),
            "url": f"https://github.com/{repo}/issues/{self._n}",
        }
        self.issues.append(row)
        return {"url": row["url"], "number": self._n}

    def get_file_content(self, repo: str, path: str) -> str:
        _ = repo
        key = str(path or "").replace("\\", "/").lstrip("/")
        return str(self.repo_files.get(key) or "")

    def create_draft_pr(
        self,
        repo: str,
        title: str,
        body: str,
        branch: str,
        files: list[dict[str, str]],
        labels: list[str],
    ) -> dict[str, Any]:
        return self._add_pr(
            repo, title, body, branch, files, labels, draft=True
        )

    def create_pr(
        self,
        repo: str,
        title: str,
        body: str,
        branch: str,
        files: list[dict[str, str]],
        labels: list[str],
    ) -> dict[str, Any]:
        """Non-draft PR (FR #2705 harvest-lesson skill-book edits)."""
        return self._add_pr(
            repo, title, body, branch, files, labels, draft=False
        )

    def _add_pr(
        self,
        repo: str,
        title: str,
        body: str,
        branch: str,
        files: list[dict[str, str]],
        labels: list[str],
        *,
        draft: bool,
    ) -> dict[str, Any]:
        if self.down:
            raise GitHubDown("github unreachable")
        self._n += 1
        row = {
            "repo": repo,
            "number": self._n,
            "title": title,
            "body": body,
            "branch": branch,
            "files": list(files),
            "labels": list(labels),
            "draft": bool(draft),
            "url": f"https://github.com/{repo}/pull/{self._n}",
        }
        self.prs.append(row)
        for item in files or []:
            p = str(item.get("path") or "").replace("\\", "/").lstrip("/")
            if p:
                self.repo_files[p] = str(item.get("content") or "")
        return {"url": row["url"], "number": self._n, "branch": branch}

    def find_pull_by_head(self, repo: str, head_branch: str) -> dict[str, Any] | None:
        want = str(head_branch or "").strip()
        if not want:
            return None
        for row in self.prs:
            if str(row.get("repo") or "") == repo and str(row.get("branch") or "") == want:
                return {
                    "url": row.get("url"),
                    "number": row.get("number"),
                    "branch": row.get("branch"),
                }
        return None


@dataclass
class DrainResult:
    """FR #2595: counts from a receipt-aware intake outbox drain."""

    filed: list[str] = field(default_factory=list)
    recorded_receipt: list[str] = field(default_factory=list)
    dropped_probe: list[str] = field(default_factory=list)
    skipped_duplicate: list[str] = field(default_factory=list)
    deferred: list[str] = field(default_factory=list)
    dry_run: bool = False

    def as_counts(self) -> dict[str, Any]:
        return {
            "filed": len(self.filed),
            "recorded_receipt": len(self.recorded_receipt),
            "dropped_probe": len(self.dropped_probe),
            "skipped_duplicate": len(self.skipped_duplicate),
            "deferred": len(self.deferred),
            "dry_run": self.dry_run,
            "handled": (
                len(self.filed)
                + len(self.recorded_receipt)
                + len(self.dropped_probe)
                + len(self.skipped_duplicate)
            ),
        }


@dataclass
class IntakeConfig:
    allow_repos: frozenset[str] = DEFAULT_ALLOW_REPOS
    rate_per_min: int = DEFAULT_RATE_PER_MIN
    max_body_bytes: int = MAX_BODY_BYTES
    fleet_key: str | None = None  # optional X-Bob-Intake-Key
    require_key: bool = False


@dataclass
class IntakeResult:
    status: int
    body: dict[str, Any]
    log_safe: str = ""  # never contains secrets/contact


def _utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def intake_root(home: Path) -> Path:
    p = Path(home) / "intake"
    p.mkdir(parents=True, exist_ok=True)
    (p / "outbox").mkdir(parents=True, exist_ok=True)
    (p / "records").mkdir(parents=True, exist_ok=True)
    return p


def _redact(text: str) -> str:
    return _SECRETISH.sub("[redacted]", text or "")


def _byte_len(s: str) -> int:
    return len((s or "").encode("utf-8"))


def payload_size_bytes(payload: dict) -> int:
    return len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))


def validate_payload(
    payload: dict,
    *,
    cfg: IntakeConfig | None = None,
    keyed: bool = False,
) -> tuple[str | None, dict[str, Any]]:
    """Return (error, normalized). error set -> 4xx."""
    cfg = cfg or IntakeConfig()
    if not isinstance(payload, dict):
        return "malformed", {}
    kind = str(payload.get("kind") or "").strip().lower()
    if not kind:
        kind = "issue"
    if kind not in KINDS:
        return "bad_kind", {}
    repo = str(payload.get("repo") or "").strip()
    if not repo:
        return "missing_repo", {}
    if not _REPO_RE.fullmatch(repo):
        return "bad_repo", {}
    if repo not in cfg.allow_repos:
        return "repo_not_allowed", {}
    title = str(payload.get("title") or "").strip()
    if not title or len(title) > 200:
        return "bad_title", {}
    body = str(payload.get("body") or "")
    if is_worker_receipt_issue(kind=kind, title=title, body=body):
        return "worker_receipt_not_issue", {}
    files = payload.get("files") or []
    if not isinstance(files, list):
        return "bad_files", {}
    if len(files) > MAX_FILES:
        return "too_many_files", {}
    norm_files: list[dict[str, str]] = []
    file_bytes = 0
    for f in files:
        if not isinstance(f, dict):
            return "bad_files", {}
        path = str(f.get("path") or "").strip().replace("\\", "/")
        content = str(f.get("content") or "")
        if not path or ".." in path.split("/") or path.startswith("/"):
            return "bad_file_path", {}
        cb = _byte_len(content)
        if cb > MAX_FILE_BYTES:
            return "file_too_large", {}
        file_bytes += cb
        norm_files.append({"path": path, "content": content})
    total = _byte_len(title) + _byte_len(body) + file_bytes
    if total > cfg.max_body_bytes or payload_size_bytes(payload) > cfg.max_body_bytes + 4096:
        return "payload_too_large", {}
    if kind in ("skill", "harvest") and not norm_files and not body.strip():
        return "empty_harvest", {}
    source = payload.get("source") if isinstance(payload.get("source"), dict) else {}
    contact = str(payload.get("contact") or "").strip()
    contact_public = bool(payload.get("contact_public"))
    idem = str(payload.get("idempotency_key") or "").strip()
    if len(idem) > 128:
        return "bad_idempotency_key", {}
    norm = {
        "kind": kind,
        "repo": repo,
        "title": title,
        "body": body,
        "files": norm_files,
        "source": {
            "machine": str(source.get("machine") or "")[:64],
            "agent": str(source.get("agent") or "")[:64],
            "skill_book": str(source.get("skill_book") or "")[:64],
            "version": str(source.get("version") or "")[:32],
            "seat": str(source.get("seat") or "")[:64],
        },
        "contact": contact[:200] if contact else "",
        "contact_public": contact_public,
        "idempotency_key": idem,
        "keyed": keyed,
    }
    return None, norm


# Validation / allow-list rejects that must never be retried from a local outbox (FR #139 / #611).
PERMANENT_INTAKE_ERRORS = frozenset(
    {
        "malformed",
        "bad_kind",
        "missing_repo",
        "bad_repo",
        "repo_not_allowed",
        "bad_title",
        "bad_files",
        "too_many_files",
        "bad_file_path",
        "file_too_large",
        "payload_too_large",
        "empty_harvest",
        "bad_idempotency_key",
        "unauthorized",
        "worker_receipt_not_issue",
    }
)


def parse_intake_error_body(text: str) -> str | None:
    """Extract ``error`` from an intake JSON error body (FR #611)."""
    raw = (text or "").strip()
    if not raw:
        return None
    try:
        doc = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        m = re.search(r'"error"\s*:\s*"([^"]+)"', raw)
        return m.group(1).strip().lower() if m else None
    if isinstance(doc, dict):
        err = str(doc.get("error") or "").strip().lower()
        return err or None
    return None


def outbox_drop_reason(
    payload: Any,
    *,
    allow_repos: frozenset[str] | None = None,
    http_status: int | None = None,
    error: str | None = None,
) -> str | None:
    """FR #139 / #611: why a local report/harvest outbox JSON must be dropped (not retried forever).

    Returns a short reason, or None when Flush should keep/retry the file (transient errors).
    Permanent rejects: missing/bad repo, allow-list, HTTP 403, and HTTP 400 validation errors
    (``bad_title``, ``bad_kind``, ``payload_too_large``, ...).
    """
    allow = DEFAULT_ALLOW_REPOS if allow_repos is None else allow_repos
    err = (error or "").strip().lower()
    if err in PERMANENT_INTAKE_ERRORS:
        return err
    if http_status == 403:
        return "repo_not_allowed"
    if http_status == 401:
        return "unauthorized"
    if http_status == 400 and err:
        # Unknown 400 string still permanent if it matches a known token in the message.
        for token in PERMANENT_INTAKE_ERRORS:
            if token in err:
                return token
        return "http_400"
    if http_status == 400 and not err:
        return "http_400"
    if not isinstance(payload, dict):
        return "malformed"
    repo = str(payload.get("repo") or "").strip()
    if not repo:
        return "missing_repo"
    if not _REPO_RE.fullmatch(repo):
        return "bad_repo"
    if repo not in allow:
        return "repo_not_allowed"
    title = str(payload.get("title") or "").strip()
    if not title or len(title) > 200:
        return "bad_title"
    kind = str(payload.get("kind") or "issue").strip().lower() or "issue"
    if kind not in KINDS:
        return "bad_kind"
    if is_worker_receipt_issue(kind=kind, title=title, body=str(payload.get("body") or "")):
        return "worker_receipt_not_issue"
    return None


class RateLimiter:
    def __init__(self, per_min: int = DEFAULT_RATE_PER_MIN) -> None:
        self.per_min = max(1, int(per_min))
        self._hits: dict[str, list[float]] = {}

    def allow(self, key: str, now: float | None = None) -> bool:
        t = float(now if now is not None else time.time())
        bucket = self._hits.setdefault(key, [])
        cutoff = t - 60.0
        self._hits[key] = [x for x in bucket if x >= cutoff]
        if len(self._hits[key]) >= self.per_min:
            return False
        self._hits[key].append(t)
        return True


def _provenance_footer(norm: dict, intake_id: str, *, quarantine: bool) -> str:
    src = norm.get("source") or {}
    bits = [
        "",
        "---",
        f"_via-intake id=`{intake_id}` ts=`{_utc()}`_",
        f"_source machine=`{src.get('machine') or '-'}` agent=`{src.get('agent') or '-'}` "
        f"book=`{src.get('skill_book') or '-'}` ver=`{src.get('version') or '-'}`"
        + (f" seat=`{src.get('seat')}`" if src.get("seat") else "")
        + "_",
    ]
    if quarantine:
        bits.append("_quarantine: unkeyed source - triage before FR queue_")
    if norm.get("contact_public") and norm.get("contact"):
        bits.append(f"_contact: {_redact(str(norm['contact']))}_")
    return "\n".join(bits)


def _labels_for(norm: dict, *, quarantine: bool) -> list[str]:
    labels = ["via-intake"]
    kind = norm["kind"]
    if kind == "fr":
        labels.append("feature-request")
    if kind in ("skill", "harvest"):
        labels.append("skill")
    # Operator 2026-10-04: do not stamp needs-mrb1 - it was a hallucination that
    # blocked !bored offers (FR #1363) while open counts climbed on skill/ops FRs.
    if quarantine:
        labels.append("via-intake-untriaged")
    return labels


def _record_path(home: Path, intake_id: str) -> Path:
    return intake_root(home) / "records" / f"{intake_id}.json"


def _idem_path(home: Path, key: str) -> Path:
    h = hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]
    return intake_root(home) / "records" / f"idem-{h}.json"


def load_record(home: Path, intake_id: str) -> dict | None:
    p = _record_path(home, intake_id)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _save_record(home: Path, rec: dict) -> None:
    intake_id = str(rec["intake_id"])
    path = _record_path(home, intake_id)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
    idem = str(rec.get("idempotency_key") or "")
    if idem:
        ip = _idem_path(home, idem)
        ip.write_text(json.dumps({"intake_id": intake_id}) + "\n", encoding="utf-8")


def _find_idempotent(home: Path, key: str) -> dict | None:
    if not key:
        return None
    ip = _idem_path(home, key)
    if not ip.is_file():
        return None
    try:
        meta = json.loads(ip.read_text(encoding="utf-8"))
        return load_record(home, str(meta.get("intake_id") or ""))
    except (OSError, json.JSONDecodeError):
        return None


def _safe_log(norm: dict, intake_id: str, msg: str) -> str:
    # never include contact or body/file content
    return (
        f"intake id={intake_id} kind={norm.get('kind')} repo={norm.get('repo')} "
        f"machine={((norm.get('source') or {}).get('machine') or '-')} {msg}"
    )


def file_submission(
    home: Path,
    norm: dict,
    filer: GitHubFiler,
    *,
    intake_id: str | None = None,
    quarantine: bool = False,
) -> dict[str, Any]:
    """File now or raise GitHubDown. Returns record dict."""
    iid = intake_id or f"in_{uuid.uuid4().hex[:16]}"
    labels = _labels_for(norm, quarantine=quarantine)
    body = _redact(str(norm.get("body") or ""))
    body = body + _provenance_footer(norm, iid, quarantine=quarantine)
    title = str(norm["title"])
    repo = str(norm["repo"])
    kind = norm["kind"]
    rec: dict[str, Any] = {
        "intake_id": iid,
        "kind": kind,
        "repo": repo,
        "title": title,
        "idempotency_key": norm.get("idempotency_key") or "",
        "quarantine": quarantine,
        "ts": _utc(),
        "state": "filing",
        "url": None,
        "queued": False,
    }
    # FR #2595: probes never file. Harvest worker receipts record-only (no draft PR)
    # unless FR #1812 already cites an existing PR URL (link, still no second filing).
    # FR #2705: Lessons always open a non-draft skill-book PR (receipt / existing-PR
    # markers suppress only the status part; they never drop lessons).
    raw_body = str(norm.get("body") or "")
    if is_do_not_file_probe(title=title, body=raw_body):
        rec["state"] = "dropped_probe"
        rec["queued"] = False
        _save_record(home, rec)
        return rec
    try:
        if kind in ("issue", "fr"):
            out = filer.create_issue(repo, title, body, labels)
            rec["url"] = out["url"]
            rec["number"] = out["number"]
            rec["state"] = "filed"
        else:
            branch = f"intake/{iid}"
            files = list(norm.get("files") or [])
            lessons = extract_harvest_lessons(raw_body)
            if kind in ("harvest", "skill") and lessons:
                src = norm.get("source") if isinstance(norm.get("source"), dict) else {}
                book, skill_path = resolve_skill_book(
                    skill_book=str((src or {}).get("skill_book") or ""),
                    title=title,
                    body=raw_body,
                )
                lesson_blob = "\n".join(lessons) + "\n" + raw_body + "\n" + title
                # FR #2991: thin FAIL-supersede already-covered twins never open lesson(harvest).
                # Meta restatements ("already cover / close thin twins") are not product tips.
                if is_fail_supersede_thin_twin_lesson(lesson_blob):
                    rec["state"] = "lesson_already_covered"
                    rec["skill_book"] = book
                    rec["lesson_count"] = 0
                    rec["queued"] = False
                    if thin_twin_fail_supersede_already_covered(filer, repo):
                        rec["thin_twin_coverage"] = True
                    _save_record(home, rec)
                    return rec
                # FR #2970: MRB process-routing lessons never open lesson(harvest).
                if is_mrb_process_routing_lesson(lesson_blob):
                    book = "bobiverse-bob-job-mrb"
                    skill_path = SKILL_BOOK_PATHS[book]
                    if mrb_process_routing_already_covered(filer, repo):
                        rec["state"] = "lesson_already_covered"
                        rec["skill_book"] = book
                        rec["lesson_count"] = 0
                        rec["queued"] = False
                        _save_record(home, rec)
                        return rec
                existing_md = _filer_get_file(filer, repo, skill_path)
                new_lessons = filter_new_lessons(existing_md, lessons)
                if not new_lessons:
                    rec["state"] = "lesson_already_covered"
                    rec["skill_book"] = book
                    rec["lesson_count"] = 0
                    rec["queued"] = False
                    _save_record(home, rec)
                    return rec
                new_md = apply_lessons_to_skill_md(existing_md, new_lessons)
                lesson_files = [{"path": skill_path, "content": new_md}]
                lesson_title = build_lesson_pr_title(book, new_lessons)
                lesson_body = build_lesson_pr_body(
                    book=book,
                    path=skill_path,
                    lessons=new_lessons,
                    original_body=body,
                )
                lesson_labels = ["via-intake", "harvest-lesson"]
                try:
                    out = _filer_create_pr(
                        filer,
                        repo,
                        lesson_title,
                        lesson_body,
                        branch,
                        lesson_files,
                        lesson_labels,
                        draft=False,
                    )
                    rec["url"] = out["url"]
                    rec["number"] = out["number"]
                    rec["branch"] = out.get("branch")
                    rec["state"] = "filed"
                    rec["skill_book"] = book
                    rec["lesson_count"] = len(new_lessons)
                except Exception as exc:
                    rec["draft_pr_error"] = f"{type(exc).__name__}: {exc}"[:500]
                    rec["state"] = "queued"
                    rec["queued"] = True
                    outbox = intake_root(home) / "outbox" / f"{iid}.json"
                    safe_norm = dict(norm)
                    safe_norm["contact"] = ""
                    if norm.get("contact_public") and norm.get("contact"):
                        safe_norm["contact"] = _redact(str(norm["contact"]))
                    outbox.write_text(
                        json.dumps(
                            {"norm": safe_norm, "intake_id": iid, "quarantine": quarantine},
                            indent=2,
                        )
                        + "\n",
                        encoding="utf-8",
                    )
                    _save_record(home, rec)
                    raise GitHubDown(
                        "harvest lesson PR filing failed", reason="github_down"
                    ) from exc
            # FR #1812: skill/harvest summary that already cites an open PR -> link, no second issue.
            elif not files and extract_existing_pr_ref(repo, title, body) is not None:
                num, url = extract_existing_pr_ref(repo, title, body)  # type: ignore[misc]
                rec["url"] = url
                rec["number"] = num
                rec["state"] = "linked_existing_pr"
            elif is_harvest_worker_receipt(kind=kind, title=title, body=raw_body):
                rec["state"] = "receipt_recorded"
                rec["queued"] = False
                _save_record(home, rec)
                return rec
            else:
                try:
                    out = filer.create_draft_pr(repo, title, body, branch, files, labels)
                    rec["url"] = out["url"]
                    rec["number"] = out["number"]
                    rec["branch"] = out.get("branch")
                    rec["state"] = "filed"
                except Exception as exc:
                    # Log why draft PR failed (was swallowed silently before FR #1812).
                    rec["draft_pr_error"] = f"{type(exc).__name__}: {exc}"[:500]
                    if kind == "harvest":
                        # MRB #2269 / follow-up #2181: harvest receipts must never become
                        # GitHub issues when draft-PR filing fails - queue for retry.
                        rec["state"] = "queued"
                        rec["queued"] = True
                        outbox = intake_root(home) / "outbox" / f"{iid}.json"
                        safe_norm = dict(norm)
                        safe_norm["contact"] = ""
                        if norm.get("contact_public") and norm.get("contact"):
                            safe_norm["contact"] = _redact(str(norm["contact"]))
                        outbox.write_text(
                            json.dumps(
                                {"norm": safe_norm, "intake_id": iid, "quarantine": quarantine},
                                indent=2,
                            )
                            + "\n",
                            encoding="utf-8",
                        )
                        _save_record(home, rec)
                        msg = str(exc)
                        reason = (
                            "draft_pr_unsupported"
                            if "draft PR not implemented" in msg
                            or "draft_pr_unsupported" in msg.lower()
                            else "github_down"
                        )
                        raise GitHubDown(
                            "harvest draft PR filing failed", reason=reason
                        ) from exc
                    # Non-harvest skill payloads retain the issue fallback with a file list.
                    listing = "\n".join(f"- `{f.get('path')}`" for f in files) or "- (no files)"
                    issue_body = body + "\n\n### Files\n" + listing
                    out = filer.create_issue(repo, title, issue_body, labels)
                    rec["url"] = out["url"]
                    rec["number"] = out["number"]
                    rec["state"] = "filed_issue_fallback"
    except GitHubDown:
        rec["state"] = "queued"
        rec["queued"] = True
        # durable outbox (no contact in clear log fields)
        outbox = intake_root(home) / "outbox" / f"{iid}.json"
        safe_norm = dict(norm)
        safe_norm["contact"] = ""  # never persist contact in outbox by default
        if norm.get("contact_public") and norm.get("contact"):
            safe_norm["contact"] = _redact(str(norm["contact"]))
        outbox.write_text(
            json.dumps({"norm": safe_norm, "intake_id": iid, "quarantine": quarantine}, indent=2)
            + "\n",
            encoding="utf-8",
        )
        _save_record(home, rec)
        raise
    _save_record(home, rec)
    return rec


def process_intake(
    home: Path,
    payload: dict,
    *,
    filer: GitHubFiler,
    cfg: IntakeConfig | None = None,
    client_ip: str = "0.0.0.0",
    intake_key_header: str = "",
    rate: RateLimiter | None = None,
    now: float | None = None,
) -> IntakeResult:
    """Full POST handler logic. Returns HTTP status + JSON body."""
    cfg = cfg or IntakeConfig()
    rate = rate or RateLimiter(cfg.rate_per_min)
    key_ok = False
    if cfg.fleet_key:
        key_ok = (intake_key_header or "") == cfg.fleet_key
    if cfg.require_key and not key_ok:
        return IntakeResult(401, {"error": "unauthorized"}, log_safe="intake unauthorized")

    # rate limit by IP + source machine
    src_machine = ""
    if isinstance(payload, dict) and isinstance(payload.get("source"), dict):
        src_machine = str(payload["source"].get("machine") or "")
    rk = f"{client_ip}|{src_machine or '-'}"
    if not rate.allow(rk, now=now):
        return IntakeResult(429, {"error": "rate_limited"}, log_safe=f"intake rate_limited ip={client_ip}")

    err, norm = validate_payload(payload, cfg=cfg, keyed=key_ok)
    if err:
        code = 400
        if err == "repo_not_allowed":
            code = 403
        return IntakeResult(code, {"error": err}, log_safe=f"intake reject={err}")

    # idempotency
    existing = _find_idempotent(home, str(norm.get("idempotency_key") or ""))
    if existing and existing.get("url"):
        return IntakeResult(
            202,
            {
                "intake_id": existing["intake_id"],
                "url": existing["url"],
                "queued": False,
                "duplicate": True,
            },
            log_safe=_safe_log(norm, existing["intake_id"], "duplicate"),
        )
    # FR #2595: receipt_recorded / dropped_probe also settle the idempotency key.
    # FR #2970: lesson_already_covered settles too (no lesson PR opened).
    if existing and str(existing.get("state") or "") in (
        "receipt_recorded",
        "dropped_probe",
        "lesson_already_covered",
        "filed",
        "linked_existing_pr",
        "filed_issue_fallback",
    ):
        return IntakeResult(
            202,
            {
                "intake_id": existing["intake_id"],
                "url": existing.get("url"),
                "queued": False,
                "duplicate": True,
                "state": existing.get("state"),
            },
            log_safe=_safe_log(norm, existing["intake_id"], "duplicate"),
        )
    if existing and existing.get("queued"):
        return IntakeResult(
            202,
            {"intake_id": existing["intake_id"], "queued": True, "duplicate": True},
            log_safe=_safe_log(norm, existing["intake_id"], "duplicate_queued"),
        )

    quarantine = not key_ok and bool(cfg.fleet_key)  # unkeyed when key configured
    if not cfg.fleet_key:
        quarantine = False  # open lab mode still labels via-intake only

    iid = f"in_{uuid.uuid4().hex[:16]}"
    try:
        rec = file_submission(home, norm, filer, intake_id=iid, quarantine=quarantine)
    except GitHubDown as exc:
        rec = load_record(home, iid) or {
            "intake_id": iid,
            "queued": True,
            "state": "queued",
        }
        # FR #2579: do not announce stub draft-PR failures as github_down.
        tag = f"queued_{getattr(exc, 'reason', 'github_down') or 'github_down'}"
        if tag not in (
            "queued_github_down",
            "queued_draft_pr_unsupported",
        ):
            tag = "queued_github_down"
        return IntakeResult(
            202,
            {"intake_id": iid, "queued": True},
            log_safe=_safe_log(norm, iid, tag),
        )

    return IntakeResult(
        202,
        {"intake_id": rec["intake_id"], "url": rec.get("url"), "queued": False},
        log_safe=_safe_log(norm, rec["intake_id"], f"filed state={rec.get('state')}"),
    )


def get_intake_status(home: Path, intake_id: str) -> tuple[int, dict[str, Any]]:
    rec = load_record(home, intake_id)
    if not rec:
        return 404, {"error": "not_found"}
    out = {
        "intake_id": rec.get("intake_id"),
        "state": rec.get("state"),
        "url": rec.get("url"),
        "queued": bool(rec.get("queued")),
        "repo": rec.get("repo"),
        "kind": rec.get("kind"),
    }
    return 200, out


def _filer_find_pull(filer: GitHubFiler, repo: str, head_branch: str) -> dict[str, Any] | None:
    finder = getattr(filer, "find_pull_by_head", None)
    if not callable(finder):
        return None
    try:
        return finder(repo, head_branch)
    except Exception:
        return None


def drain_intake_outbox(
    home: Path,
    filer: GitHubFiler,
    *,
    limit: int = 20,
    dry_run: bool = False,
    source_dir: Path | str | None = None,
) -> DrainResult:
    """Retry queued filings when GitHub is back (FR #2595 receipt-aware).

    Rules per outbox row:
    - drop do-not-file probes
    - skip when idempotency key already settled, or ``intake/<iid>`` PR exists
    - harvest worker receipts with no Lessons: record-only (no draft PR / no offer)
    - harvest with Lessons: non-draft skill-book PR via ``file_submission`` (FR #2705)
    - otherwise file via ``file_submission``
    - ``source_dir``: optional hold directory (e.g. outbox-hold-2583) instead of outbox
    - ``dry_run=True``: count only; leave outbox files and GitHub untouched
    """
    if source_dir is not None:
        root = Path(source_dir)
    else:
        root = intake_root(home) / "outbox"
    stats = DrainResult(dry_run=bool(dry_run))
    for path in sorted(root.glob("*.json"))[: max(0, int(limit))]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        norm = data.get("norm") or {}
        if not isinstance(norm, dict):
            continue
        iid = str(data.get("intake_id") or path.stem)
        quarantine = bool(data.get("quarantine"))
        title = str(norm.get("title") or "")
        body = str(norm.get("body") or "")
        kind = str(norm.get("kind") or "").strip().lower()
        repo = str(norm.get("repo") or "").strip()
        idem = str(norm.get("idempotency_key") or "").strip()

        if is_do_not_file_probe(title=title, body=body):
            stats.dropped_probe.append(iid)
            if not dry_run:
                rec = {
                    "intake_id": iid,
                    "kind": kind or "harvest",
                    "repo": repo,
                    "title": title,
                    "idempotency_key": idem,
                    "quarantine": quarantine,
                    "ts": _utc(),
                    "state": "dropped_probe",
                    "url": None,
                    "queued": False,
                }
                _save_record(home, rec)
                path.unlink(missing_ok=True)
            continue

        existing = _find_idempotent(home, idem) if idem else None
        if existing and (
            existing.get("url")
            or str(existing.get("state") or "")
            in (
                "receipt_recorded",
                "dropped_probe",
                "lesson_already_covered",
                "filed",
                "linked_existing_pr",
                "filed_issue_fallback",
            )
        ):
            stats.skipped_duplicate.append(iid)
            if not dry_run:
                path.unlink(missing_ok=True)
            continue

        branch = f"intake/{iid}"
        if repo and _filer_find_pull(filer, repo, branch):
            stats.skipped_duplicate.append(iid)
            if not dry_run:
                rec = {
                    "intake_id": iid,
                    "kind": kind or "harvest",
                    "repo": repo,
                    "title": title,
                    "idempotency_key": idem,
                    "quarantine": quarantine,
                    "ts": _utc(),
                    "state": "linked_existing_pr",
                    "url": None,
                    "queued": False,
                    "branch": branch,
                }
                found = _filer_find_pull(filer, repo, branch) or {}
                if found.get("url"):
                    rec["url"] = found.get("url")
                    rec["number"] = found.get("number")
                _save_record(home, rec)
                path.unlink(missing_ok=True)
            continue

        # FR #2705: Lessons in a receipt body must file (skill-book PR), not record-only.
        if (
            is_harvest_worker_receipt(kind=kind, title=title, body=body)
            and not extract_harvest_lessons(body)
        ):
            stats.recorded_receipt.append(iid)
            if not dry_run:
                try:
                    file_submission(home, norm, filer, intake_id=iid, quarantine=quarantine)
                except GitHubDown:
                    stats.recorded_receipt.remove(iid)
                    stats.deferred.append(iid)
                    continue
                path.unlink(missing_ok=True)
            continue

        # Real playbook / issue / skill / fr row (including harvest Lessons).
        if dry_run:
            stats.filed.append(iid)
            continue
        try:
            file_submission(home, norm, filer, intake_id=iid, quarantine=quarantine)
        except GitHubDown:
            stats.deferred.append(iid)
            continue
        path.unlink(missing_ok=True)
        stats.filed.append(iid)
    return stats


def harvest_should_use_intake(*, gh_available: bool, gh_authenticated: bool) -> bool:
    """Route order: gh auth -> gh; else intake (FR #26)."""
    if gh_available and gh_authenticated:
        return False
    return True


def report_should_use_intake(*, gh_available: bool, gh_authenticated: bool) -> bool:
    """Same gate as harvest for bug/FR filings (FR #179)."""
    return harvest_should_use_intake(
        gh_available=gh_available, gh_authenticated=gh_authenticated
    )


def build_report_payload(
    *,
    kind: str,
    repo: str,
    title: str,
    body: str,
    source: dict[str, str] | None = None,
    idempotency_key: str = "",
    contact: str = "",
    contact_public: bool = False,
) -> dict[str, Any]:
    """Build a FR #26 intake payload for a skill-surfaced bug (`issue`) or FR (`fr`).

    Script-only helper for agents with no GitHub account (FR #179). Does not
    network; caller POSTs or writes ``report-outbox/``.
    """
    k = str(kind or "").strip().lower()
    if k not in ("issue", "fr"):
        raise ValueError("kind must be 'issue' or 'fr'")
    src = source or {}
    payload: dict[str, Any] = {
        "kind": k,
        "repo": str(repo or "").strip(),
        "title": str(title or "").strip(),
        "body": str(body or ""),
        "source": {
            "machine": str(src.get("machine") or "")[:64],
            "agent": str(src.get("agent") or "")[:64],
            "skill_book": str(src.get("skill_book") or "")[:64],
            "version": str(src.get("version") or "")[:32],
        },
    }
    idem = str(idempotency_key or "").strip()
    if idem:
        payload["idempotency_key"] = idem[:128]
    c = str(contact or "").strip()
    if c:
        payload["contact"] = c[:200]
        payload["contact_public"] = bool(contact_public)
    return payload


def write_local_report_outbox(
    outbox_dir: Path,
    payload: dict[str, Any],
    *,
    filename: str | None = None,
) -> Path:
    """Persist a report payload when intake is unreachable (agent-side queue).

    Uses the same ``idempotency_key`` on retry. Never writes secrets into the
    filename. Returns the path written.
    """
    outbox_dir = Path(outbox_dir)
    outbox_dir.mkdir(parents=True, exist_ok=True)
    idem = str(payload.get("idempotency_key") or "").strip()
    if filename:
        name = filename
    elif idem:
        digest = hashlib.sha256(idem.encode("utf-8")).hexdigest()[:16]
        name = f"report-{digest}.json"
    else:
        name = f"report-{uuid.uuid4().hex[:12]}.json"
    path = outbox_dir / name
    # Do not persist contact in the local outbox by default
    safe = dict(payload)
    if "contact" in safe and not safe.get("contact_public"):
        safe = {k: v for k, v in safe.items() if k != "contact"}
        safe.pop("contact_public", None)
    path.write_text(json.dumps(safe, indent=2) + "\n", encoding="utf-8")
    return path


def _cli_drain(argv: list[str] | None = None) -> int:
    """CLI: ``python intake.py drain --home <path> [--limit N] [--dry-run] [--source-dir]``."""
    import argparse

    p = argparse.ArgumentParser(prog="intake.py drain", description="Receipt-aware intake outbox drain")
    p.add_argument("--home", required=True, help="Bobiverse home containing intake/outbox")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument(
        "--source-dir",
        default="",
        help="Optional hold directory (FR #2705); default is <home>/intake/outbox",
    )
    ns = p.parse_args(argv)
    home = Path(ns.home)
    try:
        from gh_filer import default_filer as _default_filer
    except Exception:
        _default_filer = None  # type: ignore[assignment]
    filer = _default_filer() if _default_filer else FakeGitHubFiler()
    src = str(ns.source_dir or "").strip() or None
    stats = drain_intake_outbox(
        home,
        filer,
        limit=int(ns.limit),
        dry_run=bool(ns.dry_run),
        source_dir=src,
    )
    counts = stats.as_counts()
    print(json.dumps(counts, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    import sys

    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help"):
        print(
            "usage: intake.py drain --home <path> [--limit N] [--dry-run] [--source-dir PATH]"
        )
        return 0
    if args[0] == "drain":
        return _cli_drain(args[1:])
    print(f"unknown command: {args[0]}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

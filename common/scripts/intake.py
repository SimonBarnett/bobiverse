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
from typing import Any, Callable, NamedTuple, Protocol

KINDS = frozenset({"issue", "fr", "skill", "harvest"})
MAX_BODY_BYTES = 256 * 1024
MAX_FILES = 32
MAX_FILE_BYTES = 128 * 1024
DEFAULT_RATE_PER_MIN = 30
# FR #795: historical examples (archived gh-Jeeves / agentic_build / ... retired from
# the exclusive list). FR #3135: any SimonBarnett/<name> matching _REPO_RE is allowed;
# DEFAULT_ALLOW_REPOS remains an optional extra allow for non-SimonBarnett owners later
# and as documentation of known products (FR #3023 / #3050).
DEFAULT_ALLOW_REPOS = frozenset(
    {
        "SimonBarnett/bobiverse",
        "SimonBarnett/skills-visionary",
        "SimonBarnett/agentic_fomprep",
        "SimonBarnett/a-search",  # FR #3023: Plan product; intake Flush must not drop
        "SimonBarnett/trutex",  # FR #3050: private Plan product; allowlist ignores visibility
        "SimonBarnett/ce-priority",  # FR #4830: dayworks-launcher park; never invent-harvest
        "SimonBarnett/rees",  # FR #4970: priority-customer topic (docs; not the lookup list)
        "SimonBarnett/euroflo",
    }
)
_ALLOW_OWNER = "simonbarnett"  # FR #3135: case-insensitive owner gate
_SECRETISH = re.compile(
    r"(?i)(password\s*=\s*\S+|api[_-]?key\s*=\s*\S+|ghp_[A-Za-z0-9]{20,}|"
    r"sk-[A-Za-z0-9]{10,}|xox[baprs]-[A-Za-z0-9-]+|bearer\s+\S{8,})"
)
_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def repo_allowed(repo: str, allow_repos: frozenset[str] | None = None) -> bool:
    """FR #3135: allow any SimonBarnett/<name> matching _REPO_RE; else optional extra list."""
    repo = (repo or "").strip()
    if not repo or not _REPO_RE.fullmatch(repo):
        return False
    owner, _, name = repo.partition("/")
    if owner.lower() == _ALLOW_OWNER and name:
        return True
    allow = DEFAULT_ALLOW_REPOS if allow_repos is None else allow_repos
    return repo in allow

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
# FR #2705: classic placeholder. FR #4986: bare skip/none/n/a (euroflo#24 tip class).
_LESSON_PLACEHOLDER_RE = re.compile(
    r"(?i)^\(?\s*(?:no new playbook line|skip|none|n/?a|noop|nothing|no lessons?)\s*\)?$"
)


def is_noop_harvest_lesson(line: str) -> bool:
    """True when a Lessons: bullet is empty or a noop token (FR #4986)."""
    text = str(line or "").strip()
    if not text:
        return True
    return bool(_LESSON_PLACEHOLDER_RE.match(text))

HARVESTED_LESSONS_HEADING = "## Harvested lessons (intake)"
# FR #3299 / #3317: light triage in the owning repo (useful / generalised / vision);
# re-file / hold-open only when ownership is wrong or the owner repo is missing.
LESSON_PR_MRB_INSTRUCTION = (
    "MRB (light triage): is the lesson useful, generalised, non-duplicate, and a fit for this "
    "repo's vision/AGENTS.md? PASS -> merge. Not useful / off-vision -> close with a one-line "
    "reason (board CLOSED not-useful). Duplicate -> close citing the existing lesson. Wrong "
    "owner -> re-file or MOVED (FR #3299); leave OPEN if the owner repo does not exist yet. "
    "Plan content only (requirements, designs, product decisions, FR/issue lists from a Plan seat) "
    "-> close 'plan content, not a lesson' (never hold it OPEN); move any how-to-plan lesson inside "
    "to SimonBarnett/skills-visionary."
)
DEFAULT_SKILL_BOOK = "harvest"

# Planned products that may not exist on GitHub yet (hold as bobiverse issue; do not open a PR).
MISSING_PRODUCT_REPOS = frozenset(
    {
        "simonbarnett/iphone-text-bridge",
    }
)
# Label on held harvest issues so Jeeves skips FR/MRB offer (FR #3317).
OWNER_MISSING_LABEL = "owner-missing"


class LessonOwner(NamedTuple):
    """FR #3299: owning GitHub repo for a harvest/skill lesson tip."""

    repo: str | None
    missing: bool = False


def _priority_customer_topic_repos(topic_repos=None, home=None) -> set[str]:
    """FR #4970 / #4969: topic set from caller, else last on-disk lookup (never drop)."""
    if topic_repos is not None:
        return {str(x).strip().lower() for x in topic_repos if str(x).strip()}
    if home is None:
        return set()
    try:
        import priority_customer as _pc

        return set(_pc.load_topic_repos(Path(home)))
    except Exception:  # noqa: BLE001
        return set()


def _customer_repo_from_topics(low: str, topics: set[str]) -> str | None:
    """Match a topic-repo slug in lesson text (new tags via fake/live topic set)."""
    hits: list[str] = []
    for repo in topics:
        short = repo.rsplit("/", 1)[-1]
        if len(short) < 3:
            continue
        if re.search(rf"(?<![A-Za-z0-9_]){re.escape(short)}(?![A-Za-z0-9_])", low):
            hits.append(repo)
    if not hits:
        return None
    hits.sort()
    full = hits[0]
    name = full.split("/", 1)[1] if "/" in full else full
    return f"SimonBarnett/{name}"


CUSTOMER_DEFAULT_SKILL_BOOK = (
    "harvest-agent-skills",
    ".grok/skills/harvest-agent-skills/SKILL.md",
)


def product_default_skill_book(
    repo: str, topic_repos=None, home=None
) -> tuple[str, str] | None:
    """Fixed PRODUCT_DEFAULT first (ce-priority dayworks-launcher); else topic customers."""
    repo_l = str(repo or "").strip().lower()
    if not repo_l:
        return None
    hit = PRODUCT_DEFAULT_SKILL_BOOK.get(repo_l)
    if hit:
        return hit
    topics = _priority_customer_topic_repos(topic_repos, home)
    short = repo_l.rsplit("/", 1)[-1]
    if repo_l in topics or any(t == short or t.endswith("/" + short) for t in topics):
        return CUSTOMER_DEFAULT_SKILL_BOOK
    # FR #4976: topic set may be empty on intake (never refreshed). Other
    # SimonBarnett product/customer repos still must not invent bobiverse
    # common/.grok/skills/harvest (euroflo#7 class).
    if repo_l.startswith("simonbarnett/") and repo_l != "simonbarnett/bobiverse":
        return CUSTOMER_DEFAULT_SKILL_BOOK
    return None


def lesson_owner_repo(
    title: str = "",
    body: str = "",
    source: str = "",
    topic_repos=None,
    home=None,
) -> LessonOwner:
    """Return the skill-book owning repo for a harvest/skill lesson (FR #3299 / #4970).

    ``missing=True`` means the intended owner is a planned product that does not
    exist yet - MRB must leave the tip OPEN (never FAIL-close).
    ``repo=None`` means ownership could not be decided from the text.
    """
    blob = f"{title or ''}\n{body or ''}\n{source or ''}"
    low = blob.lower()
    topics = _priority_customer_topic_repos(topic_repos, home)

    # Explicit owner/name first.
    m = re.search(r"(?i)\b(SimonBarnett/[A-Za-z0-9_.-]+)\b", blob)
    if m:
        repo = m.group(1)
        repo_l = repo.lower()
        # Normalise casing to SimonBarnett/...
        parts = repo.split("/", 1)
        repo = f"SimonBarnett/{parts[1]}" if len(parts) == 2 else repo
        return LessonOwner(repo, missing=(repo_l in MISSING_PRODUCT_REPOS))

    # FR #4970: customer slug from priority-customer topic set before generic Priority.
    cust = _customer_repo_from_topics(low, topics)
    if cust:
        return LessonOwner(cust, missing=False)

    # Product / plan cues (fixtures from FR #3299).
    if re.search(r"(?i)iphone[- ]?text[- ]?bridge|shortcuts?\s+all-?sms", low):
        return LessonOwner("SimonBarnett/iphone-text-bridge", missing=True)
    if re.search(r"(?i)skills-visionary|plan-seat|plan\s+xlsx|harvest-skills-visionary", low):
        return LessonOwner("SimonBarnett/skills-visionary", missing=False)
    if re.search(r"(?i)\ba-search\b|awin\s+local|defaultqueryparts|cdk\s+synth", low):
        return LessonOwner("SimonBarnett/a-search", missing=False)
    if re.search(r"(?i)\btrutex\b", low):
        return LessonOwner("SimonBarnett/trutex", missing=False)
    if re.search(r"(?i)agentic_fomprep|priority\s+catalog|cat-t\d+", low):
        return LessonOwner("SimonBarnett/agentic_fomprep", missing=False)

    # Bob fleet tooling stays in bobiverse.
    if re.search(
        r"(?i)bob-worker|_release_gen|bobiverse-bob|ircjeeves|ircbob|jeeves|airc|"
        r"harvest-lesson|invoke-bobiverseharvest|gitclaim|!bored|outbox\.txt",
        low,
    ):
        return LessonOwner("SimonBarnett/bobiverse", missing=False)

    return LessonOwner(None, missing=False)


# FR #3189: product repos own their skill trees (not bobiverse common/harvest).
# Map lowercased owner/name -> (book_name, repo-relative SKILL.md path).
PRODUCT_DEFAULT_SKILL_BOOK: dict[str, tuple[str, str]] = {
    "simonbarnett/a-search": (
        "harvest-agent-skills",
        ".grok/skills/harvest-agent-skills/SKILL.md",
    ),
    "simonbarnett/skills-visionary": (
        "harvest-skills-visionary",
        ".grok/skills/harvest-skills-visionary/SKILL.md",
    ),
    # FR #3318: Priority Agent / Plan product homes use repo-root honesty box.
    "simonbarnett/agentic_fomprep": (
        "harvest-agent-skills",
        ".grok/skills/harvest-agent-skills/SKILL.md",
    ),
    # euroflo#15 / FR #4990: priority-customer honesty box (never invent
    # common/.grok/skills/harvest). Topic peers: euroflo / lynton / trutex / rees.
    "simonbarnett/euroflo": (
        "harvest-agent-skills",
        ".grok/skills/harvest-agent-skills/SKILL.md",
    ),
    "simonbarnett/lynton": (
        "harvest-agent-skills",
        ".grok/skills/harvest-agent-skills/SKILL.md",
    ),
    "simonbarnett/trutex": (
        "harvest-agent-skills",
        ".grok/skills/harvest-agent-skills/SKILL.md",
    ),
    "simonbarnett/rees": (
        "harvest-agent-skills",
        ".grok/skills/harvest-agent-skills/SKILL.md",
    ),
    # FR #4830: never invent common/.grok/skills/harvest on ce-priority; park in
    # unlocked dayworks-launcher (assert-lock / tip-loop class of ce-priority#36/#37/#38).
    "simonbarnett/ce-priority": (
        "dayworks-launcher",
        "dayworks/.grok/skills/dayworks-launcher/SKILL.md",
    ),
}

def harvest_priority_customer_repos(*, home=None, topic_repos=None, fetch_json=None):
    """FR #5184: customer harvest set from the saved priority-customer topic.

    Prefer ``load_topic_repos``. If that file is missing or empty, refresh via
    the topic search (injected ``fetch_json``). Never fall back to a hardcoded list.
    """
    if topic_repos is not None:
        return frozenset(_priority_customer_topic_repos(topic_repos, None))
    home_p = Path(home) if home else None
    if home_p is not None:
        loaded = _priority_customer_topic_repos(None, home_p)
        if loaded:
            return frozenset(loaded)
        try:
            import priority_customer as _pc

            fetch = fetch_json or _pc.github_topic_fetch
            return frozenset(_pc.refresh_topic_repos(home_p, fetch_json=fetch))
        except Exception:  # noqa: BLE001
            return frozenset()
    return frozenset()

def rewrite_harvest_repo_for_skill_book(repo: str, skill_book: str) -> str:
    """FR #3959: bobiverse-* books never tip into product repos (a-search stubs).

    When FR #3004 / client inference sets skill_book=bobiverse-bob-worker but the
    payload still carries -Repo SimonBarnett/a-search, rewrite the tip home to
    SimonBarnett/bobiverse so we never ADD bob/.grok/skills/... into the product.
    Product honesty-box books (harvest-agent-skills, etc.) stay on the product.
    """
    repo_l = str(repo or "").strip().lower()
    book = str(skill_book or "").strip().lower()
    if not repo_l or not book:
        return str(repo or "").strip()
    if repo_l not in PRODUCT_DEFAULT_SKILL_BOOK:
        return str(repo or "").strip()
    if book.startswith("bobiverse-"):
        return "SimonBarnett/bobiverse"
    return str(repo or "").strip()


SKILL_BOOK_PATHS: dict[str, str] = {
    "harvest": "common/.grok/skills/harvest/SKILL.md",
    "harvest-agent-skills": "common/.grok/skills/harvest-agent-skills/SKILL.md",
    # FR #4830: ce-priority unlocked park (not common invent-harvest).
    "dayworks-launcher": "dayworks/.grok/skills/dayworks-launcher/SKILL.md",
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


_EXPLICIT_SKILL_BOOK_RE = re.compile(
    r"(?i)\b(?:belongs in|belong in|durable home is|file in)\s+`?"
    r"(?P<book>[a-z0-9][a-z0-9._-]{2,63})`?"
)


def explicit_named_skill_book(title: str = "", body: str = "") -> str | None:
    """Skill book named in the lesson (FR #4514). Keyword inference must not override it."""
    blob = f"{title or ''}\n{body or ''}"
    for match in _EXPLICIT_SKILL_BOOK_RE.finditer(blob):
        book = str(match.group("book") or "").strip("`").lower()
        if book in SKILL_BOOK_PATHS:
            return book
    return None


def lesson_sentence_already_in_book(existing_md: str, lessons: list[str]) -> bool:
    """True when a substantial sentence from the lesson is already in the skill book."""
    base = _normalize_lesson_key(existing_md)
    if not base:
        return False
    for raw in lessons or []:
        if lesson_covered_by_existing_md(existing_md, str(raw or "")):
            return True
        for part in re.split(r"(?<=[.!?])\s+|;\s+", str(raw or "")):
            key = _normalize_lesson_key(part).strip(" .")
            if len(key) >= 40 and (
                key in base or lesson_covered_by_existing_md(existing_md, part)
            ):
                return True
    return False


def extract_harvest_lessons(body: str) -> list[str]:
    """Return real Lessons: bullets; drop placeholders / noop tokens (FR #2705 / #4986)."""
    text = str(body or "")
    m = _LESSONS_SECTION_RE.search(text)
    if not m:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for bm in _LESSON_BULLET_RE.finditer(m.group("body")):
        line = (bm.group("text") or "").strip()
        if is_noop_harvest_lesson(line):
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
    repo: str = "",
    topic_repos=None,
    home=None,
) -> tuple[str, str]:
    """Map source.skill_book / path / keywords -> (book_name, repo-relative SKILL.md path).

    FR #2705: explicit book or path wins; else deterministic keyword routing; else harvest.
    FR #3004: default ``harvest`` (Invoke-BobiverseHarvest -Book default) yields to a
    keyword-inferred product book so bob-worker / fleet-ops playbooks are not parked
    under harvest when the owning skill already has the lesson on main.
    FR #3189: when ``repo`` is a product (e.g. SimonBarnett/a-search), never return
    bobiverse ``common/.grok/skills/harvest/SKILL.md`` - use that product's default
    honesty-box path (``.grok/skills/harvest-agent-skills/SKILL.md``).
    FR #4830: SimonBarnett/ce-priority parks at ``dayworks/.grok/skills/dayworks-launcher/SKILL.md``
    (never invent ``common/.grok/skills/harvest``).
    FR #4970: other ``priority-customer`` topic repos park at repo-root harvest-agent-skills
    (topic set, not a hardcoded customer list).
    FR #4990: euroflo/lynton/trutex/rees are also in PRODUCT_DEFAULT_SKILL_BOOK so
    DryRun cannot invent common/.grok/skills/harvest when the topic set is empty.
    FR #4976: when the topic set is empty, any non-bobiverse ``SimonBarnett/*`` repo
    still parks at repo-root harvest-agent-skills (euroflo#7).
    """
    repo_l = str(repo or "").strip().lower()
    product = product_default_skill_book(repo_l, topic_repos=topic_repos, home=home)

    def _product_or_bobiverse(book: str, path: str) -> tuple[str, str]:
        path_n = path.replace("\\", "/")
        if product and (
            path_n == SKILL_BOOK_PATHS[DEFAULT_SKILL_BOOK]
            or book == DEFAULT_SKILL_BOOK
            or book == "harvest-agent-skills"
            # FR #4830: invent-harvest path under product repos (ce-priority).
            or path_n.endswith("common/.grok/skills/harvest/SKILL.md")
        ):
            # a-search harvest-agent-skills lives at repo-root .grok/skills/, not common/.
            # ce-priority parks at dayworks-launcher (never invent common harvest).
            if (
                book in (DEFAULT_SKILL_BOOK, "harvest-agent-skills")
                or path_n.endswith("harvest/SKILL.md")
                or path_n.endswith("common/.grok/skills/harvest/SKILL.md")
            ):
                return product[0], product[1]
        return book, path

    # FR #4514: "belongs in bobiverse-bob-job-irc" wins over done-miss -> bob-worker.
    named = explicit_named_skill_book(title, body)
    if named:
        return _product_or_bobiverse(named, SKILL_BOOK_PATHS[named])

    raw = str(skill_book or "").strip().replace("\\", "/")
    if raw:
        lower = raw.lower()
        if lower.endswith("skill.md") or "/.grok/skills/" in lower:
            path = raw.lstrip("/")
            name = Path(path).parent.name or DEFAULT_SKILL_BOOK
            return _product_or_bobiverse(name, path)
        key = lower
        if key in SKILL_BOOK_PATHS:
            # Soft default only: harvest yields to strong product cues (not bare mrb/uat).
            if key == DEFAULT_SKILL_BOOK:
                soft = infer_soft_harvest_override(title, body)
                if soft and soft in SKILL_BOOK_PATHS:
                    # Soft bobiverse books on a product repo payload: still avoid
                    # bobiverse harvest path; product default unless soft is explicit.
                    if product and soft.startswith("bobiverse-"):
                        return product[0], product[1]
                    return soft, SKILL_BOOK_PATHS[soft]
                return _product_or_bobiverse(key, SKILL_BOOK_PATHS[key])
            if key == "harvest-agent-skills" and product:
                return product[0], product[1]
            return key, SKILL_BOOK_PATHS[key]
        # Unknown book name: product folder skills (a-search-awin) or common harvest tree.
        safe = re.sub(r"[^A-Za-z0-9._-]+", "-", key).strip("-") or DEFAULT_SKILL_BOOK
        if product and (safe.startswith("a-search-") or safe == "harvest-agent-skills"):
            return safe, f".grok/skills/{safe}/SKILL.md"
        if safe in SKILL_BOOK_PATHS:
            return _product_or_bobiverse(safe, SKILL_BOOK_PATHS[safe])
        if product:
            return product[0], product[1]
        return safe, f"common/.grok/skills/{safe}/SKILL.md"

    inferred = infer_skill_book_from_text(title, body)
    if inferred and inferred in SKILL_BOOK_PATHS:
        if product and inferred.startswith("bobiverse-"):
            return product[0], product[1]
        return _product_or_bobiverse(inferred, SKILL_BOOK_PATHS[inferred])
    if product:
        return product[0], product[1]
    return DEFAULT_SKILL_BOOK, SKILL_BOOK_PATHS[DEFAULT_SKILL_BOOK]


# FR #2970: FAIL-supersede / wrong-book / Harvest-lesson MRB *process* playbooks belong in
# bobiverse-bob-job-mrb. Default -Book harvest must not open lesson(harvest) twins that
# restate that routing and get FAIL-superseded forever.
# MRB #2973 hostile: bare "FAIL-supersede" alone must NOT match - a product harvest whose
# summary mentions FAIL-superseded would otherwise re-route MSI/outbox tips into job-mrb.
# Mirror Invoke-BobiverseHarvest Test-HarvestFailSupersedeProcessLoop: process cue required;
# FAIL-supersede alone is insufficient.
# FR #2991: thin already-covered twins ("fleet-ops already cover ... close thin twins") also
# lack process cues but must skip when FAIL-supersede + thin-twin restatement cues match.
_FAIL_SUPERSEDE_RE = re.compile(r"(?i)FAIL[- ]supersede")
_MRB_PROCESS_CUE_RE = re.compile(
    r"(?i)(?:"
    r"wrong[- ]book|"
    r"belong(?:s)? in\s+`?bobiverse-bob-job-mrb`?|"
    # FR #3827: tip #3826 used "stay in" / "durable in" instead of "belong(s) in"
    r"(?:stay|durable)\s+in\s+`?bobiverse-bob-job-mrb`?|"
    # FR #3959 / #3957: tip #3958 used "durable home is bobiverse-bob-job-mrb"
    r"durable\s+home\s+is\s+`?bobiverse-bob-job-mrb`?|"
    r"docs/mrb-N after skill merge|"
    r"Harvest-lesson MRB:\s*process|"
    r"never merge a second copy(?:\s+that says keep MRB process)?\s+in harvest|"
    # FR #3827: "do not append a second copy under harvest/SKILL.md"
    r"(?:do not|never)\s+(?:append|merge|land)\s+a\s+second\s+copy|"
    r"second\s+copy\s+under\s+harvest|"
    r"process playbooks?|"
    r"restatement playbooks?|"
    r"park(?:ed|s)?\s+under\s+harvest|"
    # FR #3959: "do not park FR #3948 ... under harvest/SKILL.md" (words between)
    r"(?:do not|never)\s+park\b[\s\S]{0,120}?under\s+(?:`?harvest|harvest/SKILL)"
    r")"
)
_THIN_TWIN_CUE_RE = re.compile(
    r"(?i)(?:"
    r"already\s+cover(?:s|ed)?|"
    r"already\s+CAST\s+IRON|"
    # FR #3959: summary said "CAST IRON already on main" (flipped order)
    r"CAST\s+IRON\s+already|"
    r"close\s+thin\b|"
    r"thin\s+harvest(?:ed)?[- ]?lessons?\b|"
    r"thin\s+harvest\s+twin|"
    # FR #3827: tip #3826 summary said "thin harvest tip" / "restatement"
    r"thin\s+harvest\s+(?:tip|restatement)s?\b|"
    r"thin\s+harvest\s+restatement|"
    r"Harvested-lessons\s+intake\s+twins?|"
    r"citing\s+(?:the\s+)?product(?:/move)?\s*PRs?|"
    # FR #4231: tip-loop meta / only-restate Thin FAIL-supersede already on main
    # (class of a-search#1839 under Book=harvest-agent-skills)
    r"tip[- ]?loop\s+meta|"
    r"only\s+restate(?:s|ing)?\s+(?:Thin\s+)?FAIL|"
    r"restate(?:s|ing)?\s+Thin\s+FAIL[- ]supersede|"
    r"Thin\s+FAIL[- ]supersede[\s\S]{0,80}?already\s+on\s+main|"
    r"already\s+on\s+main[\s\S]{0,80}?Thin\s+FAIL[- ]supersede|"
    # FR #4308: a-search#1980/#2283 - thinner tip + durable lesson already on main
    r"thinner?\b[\s\S]{0,120}?(?:harvest\s+)?tip|"
    r"FAIL[- ]supersede[d]?\b[\s\S]{0,220}?already\s+on\s+main|"
    r"durable\s+lesson\s+already|"
    r"closed\s+unmerged[\s\S]{0,100}?already\s+on\s+main|"
    # FR #4484: "restates main" / "admit main already has" (class of a-search#3470)
    r"restate(?:s|ing)?\s+main|"
    r"admit\s+main\s+already\s+has"
    r")"
)


def is_fail_supersede_thin_twin_lesson(text: str) -> bool:
    """True for FAIL-supersede tips that only restate already-covered / close-thin-twin.

    FR #2991: requires FAIL-supersede AND a thin-twin cue. Bare FAIL-supersede plus a
    real product playbook (no thin-twin wording) returns False (MRB #2973 spirit).
    FR #4231: tip-loop meta / only-restate Thin FAIL-supersede already-on-main cues
    also count (any skill book, including harvest-agent-skills).
    FR #4308: thinner tip + durable lesson already on main (a-search#1980/#2283) also count.
    FR #4484: restates main / admit main already has (a-search#3470) also count.
    """
    t = str(text or "")
    if not t.strip():
        return False
    if not _FAIL_SUPERSEDE_RE.search(t):
        return False
    return bool(_THIN_TWIN_CUE_RE.search(t))


def is_lesson_review_meta_loop(text: str) -> bool:
    """FR #4780: True when harvest text is about reviewing/closing harvest-lessons.

    MRB of a harvest-lesson / skills-only tip must not open another lesson tip.
    Honesty-box for that review is the review itself. Also matches lessons whose
    subject is reviewing, harvesting, or closing lessons (tip-loop meta).

    Does not steal FR #2970 process-routing lessons that should re-home to
    bobiverse-bob-job-mrb when coverage is missing. Genuine product playbooks
    return False.
    """
    import re as _re

    t = str(text or "")
    if not t.strip():
        return False
    # FR #2970 / #2991 own these; do not short-circuit their re-route / covered paths.
    if is_fail_supersede_thin_twin_lesson(t) or is_mrb_process_routing_lesson(t):
        return False
    is_meta_subject = bool(
        _re.search(
            r"(?i)review(?:ing|ed|s)?\s+(?:harvest[- ]?lesson|lesson\s+tips?|lessons?\b)|"
            r"(?:about|when)\s+(?:reviewing|harvesting|closing)\s+lessons?|"
            r"do not (?:harvest|open|land|merge)\s+a\s+(?:new|second)\s+"
            r"(?:harvest[- ]?lesson|lesson)\s+(?:tip|PR|bullet)|"
            r"second\s+Harvested[- ]lessons\s+bullet|"
            r"tip[- ]?loop|process\s+meta|lesson[- ]review|"
            r"CLOSED\s+not[- ]useful|CLOSED\s+already[- ]covered|"
            r"CLOSED\s+wrong[- ]path",
            t,
        )
    )
    if is_meta_subject:
        return True
    is_lesson_context = bool(
        _re.search(
            r"(?i)harvest[- ]lesson|lesson\(harvest|docs/mrb|\bmrb\d{3,}\b|"
            r"skills[- ]only|Harvested[- ]lessons|light\s+triage",
            t,
        )
    )
    # FR #4917: FIX / DONE FIX closeouts on lesson or pin tips (not only \bMRB\b).
    is_job_closeout = bool(
        _re.search(
            r"(?i)\bMRB\b.{0,120}(?:CLOSED|DONE\s+(?:PASS|FAIL)|FAIL[- ]supersede)|"
            r"(?:CLOSED|DONE\s+(?:PASS|FAIL)).{0,120}\bMRB\b|"
            r"\bFIX\b.{0,160}(?:docs/mrb|harvest[- ]lesson|\bmrb\d{3,}\b)|"
            r"(?:docs/mrb|harvest[- ]lesson|\bmrb\d{3,}\b).{0,160}\bFIX\b|"
            r"\bDONE\s+FIX\b|"
            r"CLOSED\s+harvest\s+tip|CLOSED[- ]duplicate|"
            r"light\s+triage.{0,80}(?:PASS|CLOSED|FAIL)",
            t,
        )
    )
    if is_lesson_context and is_job_closeout:
        return True
    return False



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
    # FR #3827: "stay in" / "durable in" synonyms for belong(s) in
    if re.search(r"(?i)(?:stay|durable)\s+in\s+`?bobiverse-bob-job-mrb", t):
        return True
    # FR #3959 / #3957: "durable home is bobiverse-bob-job-mrb"
    if re.search(r"(?i)durable\s+home\s+is\s+`?bobiverse-bob-job-mrb", t):
        return True
    if re.search(r"(?i)park(?:ed|s)?\s+under\s+harvest", t):
        return True
    # FR #3959: "do not park ... under harvest/SKILL.md"
    if re.search(
        r"(?i)(?:do not|never)\s+park\b[\s\S]{0,120}?under\s+(?:`?harvest|harvest/SKILL)",
        t,
    ):
        return True
    if re.search(
        r"(?i)docs/mrb-N after skill merge|Harvest-lesson MRB:\s*process|"
        r"never merge a second copy|"
        r"(?:do not|never)\s+(?:append|merge|land)\s+a\s+second\s+copy|"
        r"second\s+copy\s+under\s+harvest",
        t,
    ):
        return True
    if re.search(r"(?i)(?:process|restatement) playbooks?", t) and re.search(
        r"(?i)bobiverse-bob-job-mrb|harvest", t
    ):
        return True
    # FAIL-supersede + process cue (e.g. wrong-book) - same AND as the PS1 client skip.
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


# FR #4865: stopwords for abbreviated-twin coverage (not used for exact substring).
_LESSON_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "or",
        "of",
        "to",
        "in",
        "on",
        "for",
        "with",
        "at",
        "by",
        "from",
        "into",
        "when",
        "while",
        "that",
        "this",
        "those",
        "is",
        "are",
        "be",
        "been",
        "was",
        "were",
        "do",
        "does",
        "not",
        "no",
        "if",
        "then",
        "than",
        "as",
        "it",
        "its",
        "their",
        "them",
        "they",
        "above",
        "below",
        "until",
        "never",
        "keep",
        "after",
        "before",
        "pct",
        "per",
        "via",
        "also",
        "only",
        "same",
        "just",
    }
)


def _canon_lesson_token(token: str) -> str:
    t = str(token or "").strip("_")
    if t.endswith("able") and len(t) > 8:
        t = t[:-4]
    elif t.endswith("ed") and len(t) > 6:
        t = t[:-2]
    return t


def _lesson_sig_tokens(text: str) -> list[str]:
    key = _normalize_lesson_key(text)
    parts = re.findall(r"[a-z0-9_]+", key)
    out: list[str] = []
    for raw in parts:
        p = _canon_lesson_token(raw)
        if len(p) >= 4 and p not in _LESSON_STOPWORDS:
            out.append(p)
    return out


def _token_in_haystack(token: str, hay: str) -> bool:
    """True if token appears in hay, or is a trailing abbrev of an underscore name."""
    if not token or not hay:
        return False
    if token in hay:
        return True
    # MIN_HOLD_S matches BOB_WORKER_OUT_OF_FUEL_MIN_HOLD_S (incident #4863).
    if len(token) >= 6 and re.search(
        rf"(?:^|[^a-z0-9])[a-z0-9_]*_{re.escape(token)}(?:[^a-z0-9]|$)",
        hay,
    ):
        return True
    return False


def _shorter_lesson_covered_by_longer(shorter: str, longer: str) -> bool:
    """FR #4865: abbreviated restatement of a longer bullet already on main."""
    s = _normalize_lesson_key(shorter)
    L = _normalize_lesson_key(longer)
    if not s or not L:
        return False
    if s in L:
        return True
    tokens = _lesson_sig_tokens(s)
    if not tokens:
        return False
    prefix = 0
    for ca, cb in zip(s, L):
        if ca != cb:
            break
        prefix += 1
    # Shared lead-in then abbreviated env names (tip #4863 vs main after #4860).
    if prefix >= 40:
        return all(_token_in_haystack(t, L) for t in tokens)
    # Without a long shared prefix, require a denser token set so unrelated
    # bullets that share a few fleet words do not collapse.
    if len(tokens) < 6:
        return False
    return all(_token_in_haystack(t, L) for t in tokens)


def _iter_skill_bullet_texts(existing_md: str) -> list[str]:
    out: list[str] = []
    for raw_line in str(existing_md or "").splitlines():
        line = raw_line.strip()
        if line.startswith(("- ", "* ")):
            text = line[2:].strip()
            if text:
                out.append(text)
    return out


def lesson_covered_by_existing_md(existing_md: str, lesson: str) -> bool:
    """True when lesson is already on main, including abbreviated twins (FR #4865)."""
    key = _normalize_lesson_key(lesson)
    base = _normalize_lesson_key(existing_md)
    if key and key in base:
        return True
    for bullet in _iter_skill_bullet_texts(existing_md):
        bkey = _normalize_lesson_key(bullet)
        if not bkey:
            continue
        if key in bkey or bkey in key:
            return True
        # Only treat the shorter text as the candidate abbrev of the longer.
        if len(key) <= len(bkey):
            if _shorter_lesson_covered_by_longer(lesson, bullet):
                return True
        # Do not drop a more-specific (longer) new lesson when main only has
        # a short form --- that is a real upgrade, not a twin.
    return False


_SEAT_FOOTER_RE = re.compile(
    r"(?i)\bseat=`?(?P<seat>[A-Za-z0-9_.+-]+)`?",
)


def extract_seat_from_text(*parts: str) -> str:
    """Best-effort seat= nick from provenance footer or free text (FR #3824)."""
    blob = "\n".join(str(p or "") for p in parts)
    m = _SEAT_FOOTER_RE.search(blob)
    return (m.group("seat") if m else "").strip()


def filter_new_lessons(existing_md: str, lessons: list[str]) -> list[str]:
    """Drop lessons already present in existing_md (FR #2970 / FR #4865 de-dupe)."""
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
        if lesson_covered_by_existing_md(existing_md, line):
            continue
        out.append(line)
    return out


def _filer_list_open_pulls(filer: Any, repo: str) -> list[dict[str, Any]]:
    """Open PRs for repo (FakeGitHubFiler.prs or GhCliFiler.list_open_pulls)."""
    lister = getattr(filer, "list_open_pulls", None)
    if callable(lister):
        try:
            rows = lister(repo)
        except Exception:
            return []
        return [r for r in (rows or []) if isinstance(r, dict)]
    out: list[dict[str, Any]] = []
    for row in getattr(filer, "prs", []) or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("repo") or "") != str(repo or ""):
            continue
        if row.get("closed"):
            continue
        labs = {str(x).lower() for x in (row.get("labels") or [])}
        if "harvest-lesson" in labs or str(row.get("title") or "").lower().startswith(
            "lesson("
        ):
            out.append(row)
    return out


_LESSON_TITLE_PREFIX_RE = re.compile(r"(?i)^lesson\([^)]+\):\s*")
_HARVEST_GENERIC_TOKENS = frozenset(
    {
        "selftest",
        "entry",
        "require",
        "must",
        "gate",
        "fixture",
        "probes",
        "probe",
        "local",
        "provider",
        "providers",
        "checks",
        "behind",
        "unless",
        "absent",
        "skip",
        "green",
        "stay",
        "without",
        "deps",
        "typeof",
        "function",
        "config",
        "box",
        "secrets",
        "harvest",
        "agent",
        "skills",
        "skill",
        "invoke",
        "bobiverseharvest",
        "intake",
        "machine",
        "source",
        "book",
        "seat",
        "lesson",
        "lessons",
        "session",
        "summary",
        "via",
        "search",
        "asearch",
        "flamingo",
        "ionos",
        "marchhare",
        "html",
        "utf8",
        "from",
        "with",
        "that",
        "this",
        "when",
        "into",
    }
)


def harvest_lesson_title_stem(title: str) -> str:
    """FR #4953: lesson(<book>): body, truncated ellipsis stripped, first 56 chars."""
    raw = _normalize_lesson_key(title)
    raw = _LESSON_TITLE_PREFIX_RE.sub("", raw)
    raw = re.sub(r"\.{2,}$", "", raw).strip()
    return raw[:56]


def harvest_lesson_title_stems_match(title_a: str, title_b: str) -> bool:
    """True when two harvest-lesson titles share a long stem (not a short substring)."""
    sa = harvest_lesson_title_stem(title_a)
    sb = harvest_lesson_title_stem(title_b)
    if len(sa) < 28 or len(sb) < 28:
        return False
    if sa in sb or sb in sa:
        return True
    n = min(len(sa), len(sb), 48)
    return n >= 32 and sa[:n] == sb[:n]


def _lesson_distinctive_tokens(text: str) -> set[str]:
    return {
        t
        for t in _lesson_sig_tokens(text)
        if t not in _HARVEST_GENERIC_TOKENS
    }


def harvest_pr_covers_new_lesson(
    existing_title: str,
    existing_lesson: str,
    new_lesson: str,
    *,
    new_title: str = "",
) -> bool:
    """FR #4953: title-stem or distinctive-token twin (any seat).

    Vendor-secrets HTTP tips share a stem. MSSQL /selftest rewords share
    distinctive tokens (mssql, connect, injectable) without collapsing
    HTTP vendor-secrets into the MSSQL gate.
    """
    exist_l = str(existing_lesson or "").strip()
    new_l = str(new_lesson or "").strip()
    if not exist_l or not new_l:
        return False
    nt = str(new_title or "").strip()
    if nt and harvest_lesson_title_stems_match(existing_title, nt):
        return True
    if harvest_lesson_title_stems_match(existing_title, new_l):
        return True
    tip_md = f"{existing_title}\n{exist_l}"
    if lesson_covered_by_existing_md(tip_md, new_l):
        return True
    if lesson_covered_by_existing_md(new_l, exist_l):
        return True
    da = _lesson_distinctive_tokens(exist_l + " " + existing_title)
    db = _lesson_distinctive_tokens(new_l + " " + nt)
    shared = da & db
    # Two distinctive tokens (never a single shared word: provenance
    # "bobiverse" / "secrets" must not collapse unrelated playbooks).
    return len(shared) >= 2


def _pr_lesson_blob(pr: dict[str, Any]) -> str:
    title = str(pr.get("title") or "")
    body = str(pr.get("body") or "")
    return f"{title}\n{body}"


def _harvest_pr_matches_lessons(
    pr: dict[str, Any],
    lessons: list[str],
    *,
    new_title: str = "",
) -> bool:
    title = str(pr.get("title") or "")
    body = str(pr.get("body") or "")
    blob = _normalize_lesson_key(f"{title}\n{body}")
    tip_md = f"{title}\n{body}"
    rows = [str(x or "").strip() for x in (lessons or []) if str(x or "").strip()]
    keys = [_normalize_lesson_key(x) for x in rows]
    keys = [k for k in keys if k and k != "(no new playbook line)"]
    if not keys:
        return False
    if any(k in blob for k in keys):
        return True
    if any(lesson_covered_by_existing_md(tip_md, row) for row in rows):
        return True
    bullets = _iter_skill_bullet_texts(body) or [body]
    for row in rows:
        if any(
            harvest_pr_covers_new_lesson(title, exist, row, new_title=new_title)
            for exist in bullets
        ):
            return True
    return False


def _is_harvest_lesson_pr(pr: dict[str, Any]) -> bool:
    """True for harvest-lesson labelled or ``lesson(book):`` title tips (FR #5569)."""
    labs = {str(x).lower() for x in (pr.get("labels") or [])}
    title = str(pr.get("title") or "")
    return "harvest-lesson" in labs or title.lower().startswith("lesson(")


def find_open_harvest_lesson_twin(
    filer: Any,
    repo: str,
    lessons: list[str],
    *,
    seat: str = "",
    new_title: str = "",
) -> dict[str, Any] | None:
    """Return an open harvest-lesson PR that already covers this lesson.

    FR #3824: same seat + same lesson text must not open a second tip PR.
    FR #4953: any seat; title stem or distinctive-token reword also matches
    (a-search #4866-#4877 flood). ``seat`` is kept for callers; it no longer
    excludes a covering tip from another seat.
    """
    _ = seat
    lesson_rows = [str(x or "").strip() for x in (lessons or []) if str(x or "").strip()]
    keys = [_normalize_lesson_key(x) for x in lesson_rows]
    keys = [k for k in keys if k and k != "(no new playbook line)"]
    if not keys:
        return None
    for pr in _filer_list_open_pulls(filer, repo):
        # FR #5569: live list_open_pulls is every open PR. Never treat a
        # product FR tip as an open harvest-lesson twin.
        if not _is_harvest_lesson_pr(pr):
            continue
        if _harvest_pr_matches_lessons(pr, lesson_rows, new_title=new_title):
            return pr
    return None


def _filer_list_harvest_lesson_pulls(filer: Any, repo: str) -> list[dict[str, Any]]:
    """Open and closed harvest-lesson PRs (FakeGitHubFiler.prs or Gh list)."""
    lister = getattr(filer, "list_harvest_lesson_pulls", None)
    if callable(lister):
        try:
            rows = lister(repo)
        except Exception:
            rows = []
        return [r for r in (rows or []) if isinstance(r, dict)]
    out: list[dict[str, Any]] = []
    for row in getattr(filer, "prs", []) or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("repo") or "") != str(repo or ""):
            continue
        labs = {str(x).lower() for x in (row.get("labels") or [])}
        title = str(row.get("title") or "")
        if "harvest-lesson" in labs or title.lower().startswith("lesson("):
            out.append(row)
    return out


def _pr_created_recent(pr: dict[str, Any], *, hours: float = 24.0) -> bool:
    raw = str(pr.get("createdAt") or pr.get("created_at") or "").strip()
    if not raw:
        # In-memory fixtures without a timestamp count as recent.
        return True
    try:
        ts = raw.replace("Z", "+00:00")
        created = time.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S")
        age = time.time() - time.mktime(created)
        return age <= hours * 3600
    except Exception:
        return True


def find_recent_harvest_lesson_twin(
    filer: Any,
    repo: str,
    lessons: list[str],
    *,
    new_title: str = "",
    hours: float = 24.0,
) -> dict[str, Any] | None:
    """FR #4953: open or recently closed harvest-lesson PR covering this lesson."""
    lesson_rows = [str(x or "").strip() for x in (lessons or []) if str(x or "").strip()]
    keys = [_normalize_lesson_key(x) for x in lesson_rows]
    keys = [k for k in keys if k and k != "(no new playbook line)"]
    if not keys:
        return None
    for pr in _filer_list_harvest_lesson_pulls(filer, repo):
        if not _pr_created_recent(pr, hours=hours):
            continue
        if _harvest_pr_matches_lessons(pr, lesson_rows, new_title=new_title):
            return pr
    return None


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


# FR a-search #3907: GitHub closes the named issue when a harvest tip body says
# Closes/Fixes/Resolves #N. Skill-book tips must Refs the product FR. Only the
# product implement PR may Closes it. Class of #3876 closing #3867 while #3871
# was still open.
_HARVEST_CLOSES_RE = re.compile(
    r"(?i)\b(?:close[sd]?|fix(?:es|ed)?|resolve[sd]?)\s+"
    r"((?:[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)?#\d+(?:/#\d+)*)"
)


def neutralize_harvest_closes(text: str) -> str:
    """Rewrite GitHub closing keywords that name an issue into Refs."""
    return _HARVEST_CLOSES_RE.sub(r"Refs \1", str(text or ""))


def build_lesson_pr_body(*, book: str, path: str, lessons: list[str], original_body: str) -> str:
    safe_lessons = [neutralize_harvest_closes(x) for x in lessons]
    lines = [
        LESSON_PR_MRB_INSTRUCTION,
        "",
        f"Target skill book: `{book}` (`{path}`).",
        "",
        "Lessons:",
        *[f"- {x}" for x in safe_lessons],
        "",
        "---",
        "",
        neutralize_harvest_closes(str(original_body or "").rstrip()),
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

    def comment_issue(self, repo: str, number: int, body: str) -> None:
        """Add a comment. May raise GitHubDown."""

    def reopen_issue(self, repo: str, number: int) -> None:
        """Reopen a closed issue. May raise GitHubDown."""

    def get_issue_state(self, repo: str, number: int) -> str:
        """Return 'open' or 'closed'. May raise GitHubDown."""

    def search_issue_by_marker(self, repo: str, marker: str) -> dict[str, Any] | None:
        """Find issue by hidden body marker. Return {number, url, state} or None."""


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
    comments: list[dict[str, Any]] = field(default_factory=list)
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
            "state": "open",
            "url": f"https://github.com/{repo}/issues/{self._n}",
        }
        self.issues.append(row)
        return {"url": row["url"], "number": self._n}

    def comment_issue(self, repo: str, number: int, body: str) -> None:
        if self.down:
            raise GitHubDown("github unreachable")
        self.comments.append({"repo": repo, "number": int(number), "body": body})

    def reopen_issue(self, repo: str, number: int) -> None:
        if self.down:
            raise GitHubDown("github unreachable")
        for row in self.issues:
            if str(row.get("repo") or "") == repo and int(row.get("number") or 0) == int(number):
                row["state"] = "open"
                return

    def get_issue_state(self, repo: str, number: int) -> str:
        if self.down:
            raise GitHubDown("github unreachable")
        for row in self.issues:
            if str(row.get("repo") or "") == repo and int(row.get("number") or 0) == int(number):
                return str(row.get("state") or "open")
        return "open"

    def search_issue_by_marker(self, repo: str, marker: str) -> dict[str, Any] | None:
        if self.down:
            raise GitHubDown("github unreachable")
        needle = str(marker or "")
        if not needle:
            return None
        for row in self.issues:
            if str(row.get("repo") or "") != repo:
                continue
            if needle in str(row.get("body") or ""):
                return {
                    "number": row.get("number"),
                    "url": row.get("url"),
                    "state": str(row.get("state") or "open"),
                }
        return None

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

    def list_open_pulls(self, repo: str) -> list[dict[str, Any]]:
        """FR #3824: open (non-closed) pulls for open-lesson twin checks."""
        out: list[dict[str, Any]] = []
        for row in self.prs:
            if str(row.get("repo") or "") != str(repo or ""):
                continue
            if row.get("closed"):
                continue
            out.append(row)
        return out


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

    def extend(self, other: "DrainResult") -> None:
        self.filed.extend(other.filed)
        self.recorded_receipt.extend(other.recorded_receipt)
        self.dropped_probe.extend(other.dropped_probe)
        self.skipped_duplicate.extend(other.skipped_duplicate)
        self.deferred.extend(other.deferred)


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
    if not repo_allowed(repo, cfg.allow_repos):
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
    dedupe = str(payload.get("dedupe_key") or "").strip()
    if len(dedupe) > 128:
        return "bad_dedupe_key", {}
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
        "dedupe_key": dedupe,
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
        "bad_dedupe_key",
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
    if not repo_allowed(repo, allow_repos):
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


def intake_dedupe_sha(repo: str, dedupe_key: str) -> str:
    """sha256(repo|dedupe_key) hex - scoped per repo (FR #4963)."""
    blob = f"{str(repo or '').strip()}|{str(dedupe_key or '').strip()}"
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def intake_dedupe_marker(repo: str, dedupe_key: str) -> str:
    return f"<!-- intake-dedupe:{intake_dedupe_sha(repo, dedupe_key)} -->"


def _dedupe_path(home: Path, repo: str, dedupe_key: str) -> Path:
    return intake_root(home) / "records" / f"dedupe-{intake_dedupe_sha(repo, dedupe_key)[:32]}.json"


def _save_dedupe(
    home: Path,
    repo: str,
    dedupe_key: str,
    *,
    number: int,
    url: str,
    intake_id: str,
) -> None:
    if not str(dedupe_key or "").strip():
        return
    path = _dedupe_path(home, repo, dedupe_key)
    path.write_text(
        json.dumps(
            {
                "repo": repo,
                "number": int(number),
                "url": url,
                "intake_id": intake_id,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _find_dedupe(home: Path, repo: str, dedupe_key: str) -> dict | None:
    if not str(dedupe_key or "").strip():
        return None
    path = _dedupe_path(home, repo, dedupe_key)
    if not path.is_file():
        return None
    try:
        meta = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if str(meta.get("repo") or "") != str(repo or ""):
        return None
    if not meta.get("number"):
        return None
    return meta


def _lookup_dedupe_hit(
    home: Path,
    filer: GitHubFiler,
    repo: str,
    dedupe_key: str,
) -> dict | None:
    hit = _find_dedupe(home, repo, dedupe_key)
    if hit:
        return hit
    search = getattr(filer, "search_issue_by_marker", None)
    if not callable(search):
        return None
    marker = intake_dedupe_marker(repo, dedupe_key)
    found = search(repo, marker)
    if not found or not found.get("number"):
        return None
    url = str(found.get("url") or f"https://github.com/{repo}/issues/{found['number']}")
    return {
        "repo": repo,
        "number": int(found["number"]),
        "url": url,
        "state": found.get("state"),
        "intake_id": "",
    }


def _issue_already_commented(filer: GitHubFiler, repo: str, number: int, intake_id: str) -> bool:
    needle = str(intake_id or "")
    if not needle:
        return False
    for row in getattr(filer, "comments", None) or []:
        if (
            str(row.get("repo") or "") == repo
            and int(row.get("number") or 0) == int(number)
            and needle in str(row.get("body") or "")
        ):
            return True
    return False


def _comment_payload(norm: dict, intake_id: str, *, quarantine: bool) -> str:
    title = _redact(str(norm.get("title") or ""))
    body = _redact(str(norm.get("body") or ""))
    return f"{title}\n\n{body}{_provenance_footer(norm, intake_id, quarantine=quarantine)}"


def _apply_dedupe_match(
    home: Path,
    norm: dict,
    filer: GitHubFiler,
    rec: dict[str, Any],
    hit: dict,
    *,
    quarantine: bool,
) -> dict[str, Any]:
    repo = str(norm["repo"])
    key = str(norm.get("dedupe_key") or "")
    number = int(hit["number"])
    url = str(hit.get("url") or f"https://github.com/{repo}/issues/{number}")
    iid = str(rec["intake_id"])
    getter = getattr(filer, "get_issue_state", None)
    state = str(hit.get("state") or "")
    if callable(getter):
        state = str(getter(repo, number) or state or "open")
    state = (state or "open").lower()
    action = "commented"
    if state == "closed":
        filer.reopen_issue(repo, number)
        action = "reopened"
    if not _issue_already_commented(filer, repo, number, iid):
        filer.comment_issue(repo, number, _comment_payload(norm, iid, quarantine=quarantine))
    rec["url"] = url
    rec["number"] = number
    rec["state"] = "filed"
    rec["action"] = action
    rec["queued"] = False
    _save_dedupe(home, repo, key, number=number, url=url, intake_id=iid)
    _save_record(home, rec)
    return rec


def _intake_public_fields(rec: dict) -> dict[str, Any]:
    out: dict[str, Any] = {
        "intake_id": rec.get("intake_id"),
        "url": rec.get("url"),
        "queued": bool(rec.get("queued")),
    }
    if rec.get("action"):
        out["action"] = rec.get("action")
    if rec.get("number") is not None:
        out["number"] = rec.get("number")
    if rec.get("state"):
        out["state"] = rec.get("state")
    return out


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
        "dedupe_key": norm.get("dedupe_key") or "",
        "quarantine": quarantine,
        "ts": _utc(),
        "state": "filing",
        "url": None,
        "queued": False,
    }
    # FR #3824: claim the idempotency key before create_pr so a concurrent /
    # retry POST with the same key cannot open a twin tip while we are filing.
    _save_record(home, rec)
    # FR #2595: probes never file. Harvest worker receipts record-only (no draft PR)
    # unless FR #1812 already cites an existing PR URL (link, still no second filing).
    # FR #2705: Lessons open a non-draft skill-book PR unless FR #1812/#4288 ExistingPrUrl
    # is cited (linked_existing_pr; no tip-loop beside the product PR).
    raw_body = str(norm.get("body") or "")
    if is_do_not_file_probe(title=title, body=raw_body):
        rec["state"] = "dropped_probe"
        rec["queued"] = False
        _save_record(home, rec)
        return rec
    try:
        if kind in ("issue", "fr"):
            dkey = str(norm.get("dedupe_key") or "").strip()
            if dkey:
                marker = intake_dedupe_marker(repo, dkey)
                if marker not in body:
                    body = body.rstrip() + "\n\n" + marker + "\n"
                hit = _lookup_dedupe_hit(home, filer, repo, dkey)
                if hit:
                    return _apply_dedupe_match(
                        home, norm, filer, rec, hit, quarantine=quarantine
                    )
            out = filer.create_issue(repo, title, body, labels)
            rec["url"] = out["url"]
            rec["number"] = out["number"]
            rec["state"] = "filed"
            rec["action"] = "filed"
            if dkey:
                _save_dedupe(
                    home,
                    repo,
                    dkey,
                    number=int(out["number"]),
                    url=str(out["url"]),
                    intake_id=iid,
                )
        else:
            branch = f"intake/{iid}"
            files = list(norm.get("files") or [])
            lessons = extract_harvest_lessons(raw_body)
            if kind in ("harvest", "skill") and lessons:
                # FR #4288 / #1812: ExistingPrUrl in title/body wins over tip filing.
                existing_early = extract_existing_pr_ref(repo, title, body)
                if existing_early is not None:
                    num, url = existing_early
                    rec["url"] = url
                    rec["number"] = num
                    rec["state"] = "linked_existing_pr"
                    rec["queued"] = False
                    _save_record(home, rec)
                    return rec
                src = norm.get("source") if isinstance(norm.get("source"), dict) else {}
                # FR #3317: planned/missing owner product -> held bobiverse issue (no PR).
                owner = lesson_owner_repo(
                    title=title,
                    body=raw_body,
                    source=str((src or {}).get("skill_book") or ""),
                )
                repo_l = str(repo or "").strip().lower()
                hold_repo = owner.repo if owner.missing else None
                if hold_repo is None and repo_l in MISSING_PRODUCT_REPOS:
                    hold_repo = (
                        f"SimonBarnett/{str(repo).split('/', 1)[-1]}"
                        if "/" in str(repo)
                        else str(repo)
                    )
                if hold_repo or owner.missing:
                    intended = hold_repo or owner.repo or str(repo or "")
                    hold_title = f"harvest: hold for {intended} - {title}"[:200]
                    hold_body = (
                        f"FR #3317: owner repo `{intended}` does not exist yet "
                        f"(or is listed as a planned product). Held on bobiverse; "
                        f"not offerable as MRB until the repo exists, then re-file.\n\n"
                        f"Intended owner: `{intended}`\n\n"
                        f"{raw_body}"
                    )
                    hold_labels = [
                        "via-intake",
                        "harvest",
                        OWNER_MISSING_LABEL,
                        "feature-request",
                    ]
                    out = filer.create_issue(
                        "SimonBarnett/bobiverse",
                        hold_title,
                        hold_body,
                        hold_labels,
                    )
                    rec["url"] = out["url"]
                    rec["number"] = out["number"]
                    rec["state"] = "held_owner_missing"
                    rec["intended_owner"] = intended
                    rec["queued"] = False
                    _save_record(home, rec)
                    return rec
                book, skill_path = resolve_skill_book(
                    skill_book=str((src or {}).get("skill_book") or ""),
                    title=title,
                    body=raw_body,
                    repo=str(repo or ""),
                )
                # FR #3959: bobiverse-* books tip on bobiverse, never ADD bob/ into product repos.
                tip_repo = rewrite_harvest_repo_for_skill_book(str(repo or ""), book)
                if tip_repo != str(repo or "").strip():
                    repo = tip_repo
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
                # FR #4780: lesson-review / tip-loop meta never opens another lesson tip
                # (after FR #2970 process re-route so job-mrb homes still file when uncovered).
                if is_lesson_review_meta_loop(lesson_blob):
                    rec["state"] = "lesson_review_meta_skipped"
                    rec["skill_book"] = book
                    rec["lesson_count"] = 0
                    rec["queued"] = False
                    _save_record(home, rec)
                    return rec
                # FR #3824: open harvest-lesson tip with same seat+lesson -> link, no twin.
                # Check before main-tip filter: open tips are not on main yet.
                src_seat = ""
                if isinstance(src, dict):
                    src_seat = str(src.get("seat") or "").strip()
                if not src_seat:
                    src_seat = extract_seat_from_text(raw_body, title)
                twin = find_open_harvest_lesson_twin(
                    filer, repo, lessons, seat=src_seat, new_title=title
                )
                if twin and twin.get("url"):
                    rec["url"] = twin.get("url")
                    rec["number"] = twin.get("number")
                    rec["state"] = "open_lesson_twin"
                    rec["skill_book"] = book
                    rec["lesson_count"] = len(lessons)
                    rec["queued"] = False
                    rec["twin_of"] = twin.get("url")
                    _save_record(home, rec)
                    return rec
                # FR #4953: recently closed harvest-lesson PR (any seat) covering
                # this title stem / distinctive lesson -> lesson_already_covered.
                recent = find_recent_harvest_lesson_twin(
                    filer, repo, lessons, new_title=title
                )
                if recent and recent.get("url"):
                    rec["url"] = recent.get("url")
                    rec["number"] = recent.get("number")
                    rec["state"] = "lesson_already_covered"
                    rec["skill_book"] = book
                    rec["lesson_count"] = 0
                    rec["queued"] = False
                    rec["twin_of"] = recent.get("url")
                    _save_record(home, rec)
                    return rec
                existing_md = _filer_get_file(filer, repo, skill_path)
                # FR #4514: named book already has the sentence -> no second tip.
                if explicit_named_skill_book(title, raw_body) and lesson_sentence_already_in_book(
                    existing_md, lessons
                ):
                    rec["state"] = "lesson_already_covered"
                    rec["skill_book"] = book
                    rec["lesson_count"] = 0
                    rec["queued"] = False
                    _save_record(home, rec)
                    return rec
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
            # FR #1812 / #4288: cited ExistingPrUrl wins even when files are attached.
            elif extract_existing_pr_ref(repo, title, body) is not None:
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
                    # FR #3299: draft skill (no Lessons:) still carries the owning-repo MRB line.
                    draft_body = body
                    if kind == "skill" and LESSON_PR_MRB_INSTRUCTION not in (body or ""):
                        draft_body = f"{LESSON_PR_MRB_INSTRUCTION}\n\n{body}".rstrip() + "\n"
                    out = filer.create_draft_pr(repo, title, draft_body, branch, files, labels)
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
        body = _intake_public_fields(existing)
        body["queued"] = False
        body["duplicate"] = True
        return IntakeResult(
            202,
            body,
            log_safe=_safe_log(norm, existing["intake_id"], "duplicate"),
        )
    # FR #2595: receipt_recorded / dropped_probe also settle the idempotency key.
    # FR #2970: lesson_already_covered settles too (no lesson PR opened).
    # FR #3824: filing + open_lesson_twin settle so retries/races cannot twin.
    if existing and str(existing.get("state") or "") in (
        "receipt_recorded",
        "dropped_probe",
        "lesson_already_covered",
        "filed",
        "linked_existing_pr",
        "filed_issue_fallback",
        "filing",
        "open_lesson_twin",
        "held_owner_missing",
    ):
        body = _intake_public_fields(existing)
        body["queued"] = False
        body["duplicate"] = True
        return IntakeResult(
            202,
            body,
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

    pub = _intake_public_fields(rec)
    pub["queued"] = False
    return IntakeResult(
        202,
        pub,
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


def gh_cli_available() -> bool:
    """True when ``gh`` is on PATH (FR #5359 loud fail if missing)."""
    import shutil

    return bool(shutil.which("gh"))


def intake_outbox_snapshot(home: Path, *, now: float | None = None) -> dict[str, Any]:
    """Queued intake/outbox size and age for digest / health (FR #5359)."""
    root = intake_root(home) / "outbox"
    files = sorted(root.glob("*.json")) if root.is_dir() else []
    oldest = None
    for path in files:
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if oldest is None or mtime < oldest:
            oldest = mtime
    clock = time.time() if now is None else float(now)
    age = None if oldest is None else max(0.0, clock - float(oldest))
    return {
        "count": len(files),
        "oldest_age_s": age,
        "gh_cli": gh_cli_available(),
    }


def drain_intake_outbox_all(
    home: Path,
    filer: GitHubFiler,
    *,
    batch: int = 20,
    max_batches: int = 100,
    dry_run: bool = False,
    source_dir: Path | str | None = None,
) -> DrainResult:
    """FR #5359: drain every outbox row in batches (not only the first 20)."""
    merged = DrainResult(dry_run=bool(dry_run))
    limit = max(1, int(batch))
    for _ in range(max(1, int(max_batches))):
        stats = drain_intake_outbox(
            home, filer, limit=limit, dry_run=dry_run, source_dir=source_dir
        )
        merged.extend(stats)
        if stats.as_counts()["handled"] == 0:
            break
    return merged


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

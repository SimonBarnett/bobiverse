"""Focus + ignore for the Jeeves chair (bobiverse#39 gaps 2 and 3).

Behaviour and on-disk formats follow gh-Jeeves (read-only reference @ 8d76d9a) so the
``focus.json`` / ``ignored.json`` already sitting in the digest home keep working:

  focus.json   {"v":1,"repos":{name:{"priority","label","ts"}},
                "items":{"owner/repo#N":{"rank","repo","id","label","ts"}},
                "item_seq":N,"strict":bool,"updated":ts}
  ignored.json {"v":1,"repos":[...],"updated":ts}

Order used by !list and !bored:
  1. item-focused rows by rank, 2. repo-focused rows by priority, 3. queue seq.
Strict mode keeps only focused rows. Ignored repos are dropped everywhere.

This is a clean re-implementation of the subset needed, NOT a vendored copy of the
gh-Jeeves package (no pinned tag exists to vendor). Closed item focus is pruned on
resync via ``prune_closed_focus_items`` (FR #1508). Left out: retarget_item_focus.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

import bobreport

FOCUS_FILE = "focus.json"
IGNORE_FILE = "ignored.json"
NAMED_PRIORITY = {"high": 1, "medium": 5, "low": 9}
DEFAULT_PRIORITY = 1
UNFOCUSED_RANK = 10_000

_REPO_TOKEN = re.compile(r"^[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)?$")
_ITEM_TOKEN = re.compile(r"^([A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)?)\s*#\s*(\d+)\s*$")
_FOCUS_CMD = re.compile(r"^!+\s*focus(?:\s+(.*))?$", re.I)
_UNFOCUS_CMD = re.compile(r"^!+\s*unfocus(?:\s+(.*))?$", re.I)
_IGNORE_CMD = re.compile(r"^!+\s*ignore(?:\s+(\S+))?\s*$", re.I)
_UNIGNORE_CMD = re.compile(r"^!+\s*unignore(?:\s+(\S+))?\s*$", re.I)
_IGNORED_CMD = re.compile(r"^!+\s*ignored\s*$", re.I)


def _root(home: Path) -> Path:
    return bobreport.fleet_digest_home(Path(home))


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def _label(pr: int) -> str:
    for name, n in NAMED_PRIORITY.items():
        if n == pr:
            return name
    return str(pr)


# ---------------------------------------------------------------- tokens
def normalize_repo(token: str) -> str | None:
    s = (token or "").strip().strip("{}").strip().rstrip(".,;:!?)")
    for prefix in ("https://github.com/", "http://github.com/"):
        if s.lower().startswith(prefix):
            s = s[len(prefix):]
            break
    s = s.strip().strip("/")
    if not s or _ITEM_TOKEN.match(s) or not _REPO_TOKEN.match(s):
        return None
    return s


def normalize_item_ref(token: str) -> tuple[str, str, str] | None:
    """(repo, '#N', 'repo#N') for owner/repo#N, repo#N or a github issue/pull URL."""
    s = (token or "").strip().strip("{}").strip().rstrip(".,;:!?)")
    for prefix in ("https://github.com/", "http://github.com/"):
        if s.lower().startswith(prefix):
            s = s[len(prefix):]
            m = re.match(r"^([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)/(?:issues|pull)/(\d+)\s*$", s, re.I)
            if m:
                return m.group(1), f"#{int(m.group(2))}", f"{m.group(1)}#{int(m.group(2))}"
            break
    m = _ITEM_TOKEN.match(s)
    if not m:
        return None
    return m.group(1), f"#{int(m.group(2))}", f"{m.group(1)}#{int(m.group(2))}"


def _short(repo: str) -> str:
    return (repo or "").rsplit("/", 1)[-1].lower()


def repo_match(key: str, repo: str) -> bool:
    """Focus/ignore key vs a job repo: exact, or bare key == job short name,
    or full key vs bare job repo with the same short name."""
    k, r = (key or "").strip().lower(), (repo or "").strip().lower()
    if not k or not r:
        return False
    if k == r:
        return True
    if "/" not in k:
        return k == _short(r)
    return "/" not in r and _short(k) == r


# ---------------------------------------------------------------- focus store
def empty_focus() -> dict[str, Any]:
    return {"v": 1, "repos": {}, "items": {}, "item_seq": 0, "strict": False}


def load_focus(home: Path) -> dict[str, Any]:
    p = _root(home) / FOCUS_FILE
    if not p.is_file():
        return empty_focus()
    try:
        raw = json.loads(p.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return empty_focus()
    if not isinstance(raw, dict):
        return empty_focus()
    doc = empty_focus()
    repos = raw.get("repos")
    if isinstance(repos, list):
        repos = {str(r): {"priority": 1} for r in repos}
    for k, v in (repos if isinstance(repos, dict) else {}).items():
        key = normalize_repo(str(k))
        if not key:
            continue
        try:
            pr = int(v.get("priority") if isinstance(v, dict) else v)
        except (TypeError, ValueError):
            pr = DEFAULT_PRIORITY
        pr = max(1, pr)
        doc["repos"][key] = {
            "priority": pr,
            "label": str(v.get("label") or _label(pr)) if isinstance(v, dict) else _label(pr),
            "ts": str(v.get("ts") or "") if isinstance(v, dict) else "",
        }
    items = raw.get("items") if isinstance(raw.get("items"), dict) else {}
    for k, v in items.items():
        parsed = normalize_item_ref(str(k))
        if not parsed:
            continue
        repo, ident, key = parsed
        try:
            rk = int(v.get("rank") or v.get("priority") or 1) if isinstance(v, dict) else int(v)
        except (TypeError, ValueError):
            rk = DEFAULT_PRIORITY
        rk = max(1, rk)
        doc["items"][key] = {
            "rank": rk,
            "repo": str((v.get("repo") if isinstance(v, dict) else None) or repo),
            "id": ident,
            "label": str((v.get("label") if isinstance(v, dict) else None) or _label(rk)),
            "ts": str((v.get("ts") if isinstance(v, dict) else "") or ""),
        }
    try:
        doc["item_seq"] = int(raw.get("item_seq") or 0)
    except (TypeError, ValueError):
        doc["item_seq"] = 0
    doc["strict"] = bool(raw.get("strict"))
    return doc


def save_focus(home: Path, doc: dict[str, Any]) -> None:
    _atomic_write(
        _root(home) / FOCUS_FILE,
        {
            "v": 1,
            "repos": dict(doc.get("repos") or {}),
            "items": dict(doc.get("items") or {}),
            "item_seq": int(doc.get("item_seq") or 0),
            "strict": bool(doc.get("strict")),
            "updated": _now(),
        },
    )



def prune_closed_focus_items(home: Path, open_keys: set[str] | frozenset[str]) -> int:
    """Drop focus *items* whose owner/repo#N is not in `open_keys` (FR #1508).

    Repo-level focus lives in ``focus.repos`` and is never touched here.
    Only runs when ``open_keys`` is non-empty (empty set = resync saw nothing /
    API miss — keep focus as-is). ``open_keys`` should be lower-case
    ``owner/repo#n`` for every still-open issue and pull the resync fetched.
    """
    doc = load_focus(home)
    items = doc.get("items") if isinstance(doc.get("items"), dict) else {}
    if not items:
        return 0
    open_l = {str(k).strip().lower() for k in (open_keys or set()) if str(k).strip()}
    if not open_l:
        return 0
    keep: dict[str, Any] = {}
    dropped = 0
    for key, meta in items.items():
        kl = str(key).strip().lower()
        # Defensive: keys without '#' are not issue/PR items — keep them.
        if "#" not in kl:
            keep[key] = meta
            continue
        if kl in open_l:
            keep[key] = meta
            continue
        # Reconstruct from meta when the map key spelling differs.
        if isinstance(meta, dict):
            repo = str(meta.get("repo") or "").strip().lower()
            ident = str(meta.get("id") or "").strip().lower()
            if ident and not ident.startswith("#"):
                ident = f"#{ident}"
            alt = f"{repo}{ident}" if repo and ident else ""
            if alt and alt in open_l:
                keep[key] = meta
                continue
        dropped += 1
    if dropped:
        doc["items"] = keep
        doc["updated"] = _now()
        save_focus(home, doc)
    return dropped

def is_strict(home: Path) -> bool:
    return bool(load_focus(home).get("strict"))


def repo_priority(doc: dict, repo: str) -> int | None:
    best = None
    for key, meta in (doc.get("repos") or {}).items():
        if repo_match(key, repo):
            pr = int(meta.get("priority") or DEFAULT_PRIORITY)
            best = pr if best is None else min(best, pr)
    return best


def item_rank(doc: dict, row: dict) -> int | None:
    repo = str(row.get("repo") or "").strip()
    num = str(row.get("id") or "").strip().lstrip("#")
    if not repo or not num:
        return None
    for key, meta in (doc.get("items") or {}).items():
        parsed = normalize_item_ref(key)
        if not parsed:
            continue
        k_repo, k_id, _ = parsed
        if k_id.lstrip("#") == num and repo_match(k_repo, repo):
            return int(meta.get("rank") or DEFAULT_PRIORITY)
    return None


def row_is_focused(doc: dict, row: dict) -> bool:
    return item_rank(doc, row) is not None or repo_priority(doc, str(row.get("repo") or "")) is not None


# ---------------------------------------------------------------- ignore store
def ignored_list(home: Path) -> list[str]:
    p = _root(home) / IGNORE_FILE
    if not p.is_file():
        return []
    try:
        raw = json.loads(p.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for r in (raw.get("repos") if isinstance(raw, dict) else None) or []:
        s = str(r or "").strip()
        if s and s.lower() not in seen:
            seen.add(s.lower())
            out.append(s)
    return out


def _save_ignored(home: Path, repos: list[str]) -> None:
    _atomic_write(_root(home) / IGNORE_FILE, {"v": 1, "repos": repos, "updated": _now()})


def is_ignored(home: Path, repo: str) -> bool:
    return any(repo_match(ig, repo) for ig in ignored_list(home))


# ---------------------------------------------------------------- ordering
_TASK_ORDER = {"MRB": 0, "UAT": 1, "FR": 2}


def _task_order(row: dict) -> int:
    return _TASK_ORDER.get(str(row.get("task") or "").strip().upper(), 3)


def _repo_entry(doc: dict, repo: str) -> tuple[int, str] | None:
    """(priority, ts) of the best matching repo-level focus entry (lowest priority number, then
    earliest focused), or None."""
    best = None
    for key, meta in (doc.get("repos") or {}).items():
        if repo_match(key, repo):
            cand = (int(meta.get("priority") or DEFAULT_PRIORITY), str(meta.get("ts") or ""))
            if best is None or cand < best:
                best = cand
    return best


def repo_row_admitted(row: dict, now: float | None = None) -> bool:
    """FR #628: under a repo-level focus a row is real work unless a skip filter hits.

    FR rows: open issue, not a board/harvest/CRITICAL-spam/needs-human row. MRB rows: any open PR
    row. UAT rows: only for PRs merged within ``gitclaim.UAT_MAX_AGE_S`` (older UAT history stays
    hidden). Cooldown / author-seat / superseded-FR checks happen at offer time.
    """
    import gitclaim

    if gitclaim.row_skip_fr_reason(row) or gitclaim.row_needs_human(row):
        return False
    if str(row.get("task") or "").strip().upper() == "UAT":
        return gitclaim.is_repo_uat(row)  # t853u / #818 / #821: only UAT #0 + repo_uat
    return True


def sort_unaccepted_rows(home: Path, rows: list[dict]) -> list[dict]:
    """Drop ignored rows; strict drops unfocused rows; then item rank > repo priority (focus order)
    > MRB, UAT, FR > seq. A repo-level focus admits every real offerable row of that repo (FR #628)."""
    ignored = ignored_list(home)
    doc = load_focus(home)
    kept = [
        r for r in rows
        if isinstance(r, dict) and not any(repo_match(ig, str(r.get("repo") or "")) for ig in ignored)
    ]
    if doc.get("strict"):
        kept = [
            r for r in kept
            if item_rank(doc, r) is not None
            or (repo_priority(doc, str(r.get("repo") or "")) is not None and repo_row_admitted(r))
        ]

    def key(r: dict) -> tuple:
        try:
            seq = int(r.get("seq") or 0)
        except (TypeError, ValueError):
            seq = 0
        ir = item_rank(doc, r)
        if ir is not None:
            return (0, ir, "", "", 0, seq)
        ent = _repo_entry(doc, str(r.get("repo") or ""))
        if ent is None:
            return (1, UNFOCUSED_RANK, "", "", 0, seq)
        return (1, ent[0], ent[1], str(r.get("repo") or "").lower(), _task_order(r), seq)

    return sorted(kept, key=key)


# ---------------------------------------------------------------- commands
def parse_focus_cmd(body: str) -> str | None:
    m = _FOCUS_CMD.match((body or "").strip())
    return None if not m else (m.group(1) or "").strip()


def parse_unfocus_cmd(body: str) -> str | None:
    m = _UNFOCUS_CMD.match((body or "").strip())
    return None if not m else (m.group(1) or "").strip()


def parse_ignore_cmd(body: str) -> str | None:
    m = _IGNORE_CMD.match((body or "").strip())
    return None if not m else (m.group(1) or "").strip()


def parse_unignore_cmd(body: str) -> str | None:
    m = _UNIGNORE_CMD.match((body or "").strip())
    return None if not m else (m.group(1) or "").strip()


def is_ignored_cmd(body: str) -> bool:
    return bool(_IGNORED_CMD.match((body or "").strip()))


def is_focus_family(body: str) -> bool:
    return any(
        f(body) is not None
        for f in (parse_focus_cmd, parse_unfocus_cmd, parse_ignore_cmd, parse_unignore_cmd)
    ) or is_ignored_cmd(body)


def _priority_token(tok: str) -> tuple[int, str] | None:
    t = (tok or "").strip().lower()
    if t in NAMED_PRIORITY:
        return NAMED_PRIORITY[t], t
    if t.isdigit() and int(t) >= 1:
        return int(t), _label(int(t))
    return None


def _set_item(home: Path, token: str, rank: int | None, label: str | None) -> list[str]:
    parsed = normalize_item_ref(token)
    if not parsed:
        return ["focus: bad item (use owner/repo#N or repo#N)"]
    repo, ident, key = parsed
    doc = load_focus(home)
    items = {k: v for k, v in doc["items"].items() if k.lower() != key.lower()}
    if rank is None:
        doc["item_seq"] = int(doc.get("item_seq") or 0) + 1
        rank = doc["item_seq"]
    items[key] = {"rank": max(1, rank), "repo": repo, "id": ident,
                  "label": label or _label(max(1, rank)), "ts": _now()}
    doc["items"] = items
    save_focus(home, doc)
    return [f"focus: item {key} rank={max(1, rank)}"]


def _set_repo(home: Path, token: str, pr: int, label: str) -> list[str]:
    canon = normalize_repo(token)
    if not canon:
        return ["focus: usage !focus [n|high|medium|low] {repo|owner/repo#N}"]
    doc = load_focus(home)
    repos = {k: v for k, v in doc["repos"].items() if k.lower() != canon.lower()
             and not (_short(k) == _short(canon) and (("/" in k) != ("/" in canon)))}
    repos[canon] = {"priority": max(1, pr), "label": label, "ts": _now()}
    doc["repos"] = repos
    save_focus(home, doc)
    return [f"focus: {canon} priority={max(1, pr)} ({label})"]


def format_focus_lines(home: Path) -> list[str]:
    doc = load_focus(home)
    out = [f"focus strict: {'on' if doc['strict'] else 'off'}"]
    if not doc["items"] and not doc["repos"]:
        return out + ["focus: (none)"]
    if doc["items"]:
        out.append(f"focus items ({len(doc['items'])}):")
        for k, v in sorted(doc["items"].items(), key=lambda kv: (kv[1]["rank"], kv[0].lower())):
            out.append(f"  {v['rank']} ({v['label']}) {k}")
    if doc["repos"]:
        out.append(f"focus repos ({len(doc['repos'])}):")
        for k, v in sorted(doc["repos"].items(), key=lambda kv: (kv[1]["priority"], kv[0].lower())):
            out.append(f"  {v['priority']} ({v['label']}) {k}")
    return out


def handle_focus_cmd(home: Path, arg: str) -> list[str]:
    raw = (arg or "").strip()
    if not raw:
        return format_focus_lines(home)
    parts = raw.split()
    if parts[0].lower() == "strict":
        if len(parts) == 1:
            return [f"focus strict: {'on' if is_strict(home) else 'off'}"]
        flag = parts[1].lower()
        if flag in ("on", "1", "true", "yes", "off", "0", "false", "no"):
            doc = load_focus(home)
            doc["strict"] = flag in ("on", "1", "true", "yes")
            save_focus(home, doc)
            return [f"focus strict: {'on' if doc['strict'] else 'off'}"]
        return ["focus: usage !focus strict on|off"]
    pri = _priority_token(parts[0])
    if pri is not None and len(parts) > 1:
        rest = " ".join(parts[1:]).strip()
        if normalize_item_ref(rest):
            return _set_item(home, rest, pri[0], pri[1])
        return _set_repo(home, rest, pri[0], pri[1])
    if pri is not None:
        return ["focus: usage !focus [n|high|medium|low] {repo|repo#N}"]
    if normalize_item_ref(parts[0]):
        p2 = _priority_token(parts[1]) if len(parts) > 1 else None
        return _set_item(home, parts[0], p2[0] if p2 else None, p2[1] if p2 else "high")
    return _set_repo(home, raw if len(parts) > 1 else parts[0], DEFAULT_PRIORITY, "high")


def handle_unfocus_cmd(home: Path, arg: str) -> list[str]:
    raw = (arg or "").strip()
    if not raw:
        return ["unfocus: usage !unfocus {repo|repo#N}|all"]
    doc = load_focus(home)
    if raw.lower() == "all":
        n_r, n_i = len(doc["repos"]), len(doc["items"])
        doc["repos"], doc["items"], doc["item_seq"] = {}, {}, 0
        save_focus(home, doc)
        return [f"unfocus: cleared {n_r} repo + {n_i} item entries"]
    parsed = normalize_item_ref(raw)
    if parsed:
        repo, ident, key = parsed
        kept = {}
        for k, v in doc["items"].items():
            p = normalize_item_ref(k)
            if p and p[1] == ident and repo_match(p[0], repo):
                continue
            kept[k] = v
        if len(kept) == len(doc["items"]):
            return [f"unfocus: {key} was not focused"]
        doc["items"] = kept
        save_focus(home, doc)
        return [f"unfocus: removed {key}"]
    canon = normalize_repo(raw)
    if not canon:
        return ["unfocus: bad repo"]
    kept_r = {k: v for k, v in doc["repos"].items() if not repo_match(k, canon) and not repo_match(canon, k)}
    if len(kept_r) == len(doc["repos"]):
        return [f"unfocus: {canon} was not focused"]
    doc["repos"] = kept_r
    save_focus(home, doc)
    return [f"unfocus: removed {canon}"]


def _purge_repo_from_queue(home: Path, repo: str) -> int:
    import gitclaim

    try:
        with gitclaim._lock(home):
            doc = gitclaim._load_queue_unlocked(home)
            n = 0
            for bucket in ("unaccepted", "accepted"):
                keep = [r for r in doc.get(bucket) or [] if not repo_match(repo, str(r.get("repo") or ""))]
                n += len(doc.get(bucket) or []) - len(keep)
                doc[bucket] = keep
            if n:
                gitclaim._write_queue(gitclaim.queue_path(home), doc)
            return n
    except (OSError, TimeoutError, ValueError, json.JSONDecodeError):
        return 0


def handle_ignore_cmd(home: Path, token: str) -> list[str]:
    canon = normalize_repo(token)
    if not canon:
        return ["ignore: bad repo (use name or owner/name)"]
    repos = ignored_list(home)
    if any(r.lower() == canon.lower() for r in repos):
        return [f"ignore: already ignoring {canon} (purged 0 queued)"]
    if "/" in canon:
        repos = [r for r in repos if r.lower() != _short(canon)]
    repos.append(canon)
    _save_ignored(home, repos)
    return [f"ignore: now ignoring {canon} (purged {_purge_repo_from_queue(home, canon)} queued)"]


def handle_unignore_cmd(home: Path, token: str) -> list[str]:
    canon = normalize_repo(token)
    if not canon:
        return ["unignore: bad repo (use name or owner/name)"]
    repos = ignored_list(home)
    kept = [r for r in repos if not (repo_match(r, canon) or repo_match(canon, r))]
    if len(kept) == len(repos):
        return [f"unignore: {canon} was not ignored"]
    _save_ignored(home, kept)
    return [f"unignore: resumed {canon} (new events only)"]


def format_ignored_lines(home: Path) -> list[str]:
    repos = ignored_list(home)
    if not repos:
        return ["ignored: (none)"]
    return [f"ignored ({len(repos)}):"] + [f"  {r}" for r in repos]


# ---------------------------------------------------------------- permission
def owner_account() -> str:
    return (os.environ.get("JEEVES_OWNER_ACCOUNT") or "simon").strip().lower() or "simon"


def _csv_env(name: str) -> set[str]:
    return {p.strip().lower() for p in (os.environ.get(name) or "").split(",") if p.strip()}


def may_mutate(nick: str, account: str | None) -> bool:
    """Owner SERVICES ACCOUNT, or an additive allowlist (gh-Jeeves #170 style).

    A bare nick is NOT enough for the owner (anyone can take ``simon-x``); the account
    must come from the server (account-tag / extended-join -> AccountMap). Allowlisted
    nicks (JEEVES_FOCUS_MUTATORS) are exact matches and are only for ops ears.
    """
    acct = (account or "").strip().lower()
    if acct and (acct == owner_account() or acct in _csv_env("JEEVES_FOCUS_MUTATOR_ACCOUNTS")):
        return True
    return (nick or "").strip().lower() in _csv_env("JEEVES_FOCUS_MUTATORS")


def dispatch(
    home: Path,
    nick: str,
    account: str | None,
    body: str,
    *,
    ops: bool | None = None,
    focus_ok: bool | None = None,
) -> list[str] | None:
    """Run a focus/ignore-family command. None = not one of ours. Reads (!focus bare,
    !focus strict, !ignored) are open; every mutation needs ``may_mutate`` OR the chair's own
    principal check: ``ops`` (owner account / bob-<machine> ear, chair_commands.classify) allows all
    mutations, ``focus_ok`` (adds the JEEVES_FOCUS_MUTATORS allowlist) allows !focus/!unfocus.
    Denial replies are the gh-Jeeves strings."""
    if ops is None:                      # no chair principal supplied: legacy account / allowlist rule
        ops = may_mutate(nick, account)
        focus_ok = ops if focus_ok is None else focus_ok
    ops_ok = bool(ops)
    foc_ok = bool(focus_ok) or ops_ok
    arg = parse_focus_cmd(body)
    if arg is not None:
        read_only = arg == "" or arg.lower() == "strict"
        if not read_only and not foc_ok:
            return ["focus: denied (owner account required)"]
        return handle_focus_cmd(home, arg)
    arg = parse_unfocus_cmd(body)
    if arg is not None:
        if not foc_ok:
            return ["unfocus: denied (owner account required)"]
        return handle_unfocus_cmd(home, arg)
    if is_ignored_cmd(body):
        return format_ignored_lines(home)
    arg = parse_ignore_cmd(body)
    if arg is not None:
        if not ops_ok:
            return ["ignore: denied (simon or bob-* ops only)"]
        return handle_ignore_cmd(home, arg) if arg else ["ignore: usage !ignore {repo}"]
    arg = parse_unignore_cmd(body)
    if arg is not None:
        if not ops_ok:
            return ["unignore: denied (simon or bob-* ops only)"]
        return handle_unignore_cmd(home, arg) if arg else ["unignore: usage !unignore {repo}"]
    return None
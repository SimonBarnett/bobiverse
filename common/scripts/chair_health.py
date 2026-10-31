"""Chair background jobs (deterministic, no LLM, no IRC I/O of their own):

* webhook health probes every 30 min  (``WEBHOOK_PROBE_S``): GET report, GET jira, GET intake/<id> (404 = up) and a
  synthetic ``ping`` to POST git, against the local receiver and the public https URL. State in
  ``webhook-health.json``; announce on #bobiverse (via chair-outbox) ONLY when a target flips up<->down.
* FR #5510 stuck-job sweep every 10 min (+ startup): classify queue/open catalog,
  release silent/dead-holder accepts, enqueue untracked offerable items, digest/!stuck report.
* authenticated ``gitclaim.resync_from_github`` on a **low cadence** (``RESYNC_S`` = 1h, FR #3212) plus gap-triggered
  reconcile when git webhooks go quiet (``WEBHOOK_GAP_S``). Uses ETag/304 conditional GETs and the shared
  ``github_api_budget`` hourly counter. Token SOURCE (never the value) is written once per process to
  ``resync-token-source.log``. Webhooks remain the source of truth; REST is the exception path.

Everything network/clock/disk is injectable so tests use fakes.
"""
from __future__ import annotations

import contextlib

import json
import os
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import github_api_budget as gab

WEBHOOK_PROBE_S = 1800.0
# FR #3212: hourly (or slower) reconcile — webhooks carry live state; 15-min polling burned the core bucket.
RESYNC_S = 3600.0
# FR #3948: drain merge-on-green pending without seat CI polls.
MERGE_ON_GREEN_S = 60.0
FIRST_MERGE_ON_GREEN_DELAY_S = 15.0
# FR #5170: Copilot virtual-seat poll + webhook ensure (not a resync).
COPILOT_TICK_S = 45.0
FIRST_COPILOT_DELAY_S = 20.0
WEBHOOK_ENSURE_S = 3600.0
FIRST_WEBHOOK_ENSURE_DELAY_S = 8.0
STALL_S = 180.0
FIRST_STALL_DELAY_S = 90.0
# FR #5510: stuck-job sweep (classify / release silent accepts / enqueue untracked).
STUCK_SWEEP_S = 600.0
FIRST_STUCK_SWEEP_DELAY_S = 20.0
# FR #5359: retry intake/outbox while the chair runs (not only at BobCallback start).
INTAKE_OUTBOX_S = 60.0
FIRST_INTAKE_OUTBOX_DELAY_S = 30.0
INTAKE_OUTBOX_BACKOFF_MAX_S = 900.0
WEBHOOK_GAP_S = gab.WEBHOOK_GAP_S
FIRST_RESYNC_DELAY_S = 120.0
FIRST_PROBE_DELAY_S = 45.0
STATE_NAME = "webhook-health.json"
TOKEN_SOURCE_LOG = "resync-token-source.log"
LOCAL_BASE = "http://127.0.0.1:7700"
try:
    import bob_public_base as _bpb
    PUBLIC_BASE = _bpb.DEFAULT_PUBLIC_BASE
except ImportError:  # pragma: no cover - flat install without helper
    PUBLIC_BASE = "https://bob.ntsa.uk"
PROBE_ZEN = "jeeves-health-probe"          # bobcallback acks this ping quietly (no queue, no announce)
PROBE_REPO = "SimonBarnett/bobiverse"
MAX_REPOS = 60
# FR #4725: fleet defaults for chair + digest resync-repos.txt (fresh install / wipe).
# Ops may add more; ensure_resync_repos_file merges these without dropping extras.
DEFAULT_RESYNC_REPOS = (
    "SimonBarnett/a-search",
    "SimonBarnett/agentic_fomprep",
    "SimonBarnett/bobiverse",
    "SimonBarnett/xai-cookbook",
    "SimonBarnett/Club-Madeira",
    "SimonBarnett/ce-priority",
    "SimonBarnett/priority-branding",  # FR #5134
)
RESYNC_REPOS_NAME = "resync-repos.txt"

# (name, method, path, status codes that count as UP)
CHECKS = (
    ("report", "GET", "/bob/v1/report", frozenset({200})),
    ("jira", "GET", "/bob/v1/jira", frozenset({200})),
    ("intake", "GET", "/bob/v1/intake/jeeves-health-probe", frozenset({200, 404})),
    ("git", "POST", "/bob/v1/git", frozenset({200, 202, 204})),
)


def targets() -> dict[str, str]:
    public = (
        os.environ.get("JEEVES_PROBE_PUBLIC")
        or os.environ.get("BOB_PUBLIC_BASE")
        or PUBLIC_BASE
    )
    return {
        "local": (os.environ.get("JEEVES_PROBE_LOCAL") or LOCAL_BASE).rstrip("/"),
        "public": public.strip().rstrip("/"),
    }


def default_http(method: str, url: str, body: bytes | None = None, headers: dict | None = None,
                 timeout: float = 10.0) -> int:
    """HTTP status, or 0 when the connection itself failed. HTTP error statuses are returned, not raised."""
    req = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp.read(256)
            return int(resp.status)
    except urllib.error.HTTPError as exc:
        return int(exc.code)
    except Exception:  # noqa: BLE001 - refused / DNS / TLS / timeout
        return 0


def _ping_body() -> bytes:
    return json.dumps({"zen": PROBE_ZEN, "repository": {"full_name": PROBE_REPO}}).encode("utf-8")


def probe_target(base: str, http=default_http) -> dict[str, int]:
    out: dict[str, int] = {}
    for name, method, path, _ok in CHECKS:
        if method == "POST":
            out[name] = http(method, base + path, _ping_body(),
                             {"Content-Type": "application/json", "X-GitHub-Event": "ping",
                              "User-Agent": "bobiverse-jeeves-health"})
        else:
            out[name] = http(method, base + path, None, {"User-Agent": "bobiverse-jeeves-health"})
    return out


def failing(codes: dict[str, int]) -> list[str]:
    ok = {name: oks for name, _m, _p, oks in CHECKS}
    return [f"{n}={codes.get(n, 0)}" for n in ok if codes.get(n, 0) not in ok[n]]


def _read_state(path: Path) -> dict:
    try:
        doc = json.loads(path.read_text(encoding="utf-8-sig"))
        return doc if isinstance(doc, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_state(path: Path, doc: dict) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _fmt_age(sec: float) -> str:
    sec = int(max(0, sec))
    if sec < 90:
        return f"{sec}s"
    if sec < 5400:
        return f"{sec // 60}m"
    return f"{sec // 3600}h{(sec % 3600) // 60:02d}m"


def probe_cycle(home: Path, *, now: float, http=default_http, sleep=time.sleep, retry_s: float = 5.0,
                bases: dict[str, str] | None = None) -> dict:
    """One probe run. Returns {"log": [lines], "announce": [lines], "state": doc}. Writes webhook-health.json."""
    bases = bases or targets()
    path = Path(home) / STATE_NAME
    state = _read_state(path)
    prev_targets = state.get("targets") if isinstance(state.get("targets"), dict) else {}
    log: list[str] = []
    announce: list[str] = []
    new_targets: dict[str, dict] = {}
    for tname, base in bases.items():
        codes = probe_target(base, http)
        bad = failing(codes)
        if bad:                                   # confirm once before calling it down (no flapping on one blip)
            sleep(retry_s)
            codes2 = probe_target(base, http)
            if len(failing(codes2)) <= len(bad):
                codes, bad = codes2, failing(codes2)
        up = not bad
        old = prev_targets.get(tname) if isinstance(prev_targets.get(tname), dict) else None
        was_up = True if old is None else bool(old.get("up"))
        since = float(old.get("since") or now) if (old and bool(old.get("up")) == up) else now
        new_targets[tname] = {"up": up, "since": since, "failing": bad, "codes": codes, "checked": now}
        summary = " ".join(f"{k}={v}" for k, v in codes.items())
        log.append(f"INFO webhook-health {tname} {'up' if up else 'DOWN'} {base} {summary}")
        if was_up and not up:
            announce.append(f"WEBHOOK DOWN {tname} ({base}): {', '.join(bad)}")
        elif (not was_up) and up:
            announce.append(f"WEBHOOK RECOVERED {tname} ({base}) after {_fmt_age(now - float(old.get('since') or now))}")
    state = {"v": 1, "last_run": now, "targets": new_targets}
    try:
        _write_state(path, state)
    except OSError as exc:
        log.append(f"WARN webhook-health state write failed: {exc}")
    return {"log": log, "announce": announce, "state": state}


# --------------------------------------------------------------------------- GitHub resync

def default_token() -> tuple[str, str]:
    """(token, source). Uses the existing gh_filer loader (config\\github.token etc.) - not changed."""
    try:
        import gh_filer
        src = gh_filer.ensure_gh_token_env()
    except Exception:  # noqa: BLE001
        return "", "none"
    tok = (os.environ.get("GH_TOKEN") or "").strip()
    return (tok, src) if tok else ("", "none")


def ensure_resync_repos_file(home: Path, *, defaults: tuple[str, ...] | None = None) -> Path:
    """Create or merge fleet defaults into ``<home>/resync-repos.txt`` (FR #4725).

    Missing file: write the default list. Existing file: append any missing defaults
    (comments and operator extras stay). Never removes a line.
    """
    import gitclaim

    home = Path(home)
    home.mkdir(parents=True, exist_ok=True)
    path = home / RESYNC_REPOS_NAME
    wanted = list(defaults if defaults is not None else DEFAULT_RESYNC_REPOS)
    wanted = [
        gitclaim.canonical_queue_repo(n)
        for n in wanted
        if gitclaim.REPO_RE.fullmatch(str(n).strip())
    ]
    wanted = list(dict.fromkeys(wanted))
    if not path.is_file():
        body = (
            "# Fleet GitHub resync list (FR #4725). One owner/repo per line.\n"
            "# Install and chair start merge DEFAULT_RESYNC_REPOS; do not delete ce-priority.\n"
            + "\n".join(wanted)
            + "\n"
        )
        path.write_text(body, encoding="utf-8")
        return path
    try:
        raw = path.read_text(encoding="utf-8-sig")
    except OSError:
        return path
    present = {
        gitclaim.canonical_queue_repo(ln.strip()).lower()
        for ln in raw.splitlines()
        if ln.strip() and not ln.strip().startswith("#") and gitclaim.REPO_RE.fullmatch(ln.strip())
    }
    missing = [n for n in wanted if n.lower() not in present]
    if not missing:
        return path
    add = ("\n" if raw and not raw.endswith("\n") else "") + "\n".join(missing) + "\n"
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(add)
    return path


def configured_repos(home: Path) -> list[str]:
    import gitclaim
    names: list[str] = []
    env = (os.environ.get("JEEVES_RESYNC_REPOS") or "").replace(";", ",")
    names += [x.strip() for x in env.split(",") if x.strip()]
    for p in (Path(home) / RESYNC_REPOS_NAME,):
        try:
            names += [ln.strip() for ln in p.read_text(encoding="utf-8-sig").splitlines()
                      if ln.strip() and not ln.strip().startswith("#")]
        except OSError:
            pass
    # FR #785: rewrite archived sources (gh-Jeeves -> bobiverse) before returning.
    out: list[str] = []
    for n in names:
        if not gitclaim.REPO_RE.fullmatch(n):
            continue
        out.append(gitclaim.canonical_queue_repo(n))
    return list(dict.fromkeys(out))


def _owner_prefix(owners: set[str]) -> str:
    """Pick a GitHub owner login for short focus keys (FR #3146)."""
    lowered = {str(o).strip().lower() for o in (owners or set()) if str(o).strip()}
    if "simonbarnett" in lowered:
        return "SimonBarnett"
    for o in sorted(lowered):
        if o:
            # Preserve common TitleCase for single-token owners when unknown.
            return o[:1].upper() + o[1:] if o.islower() else o
    return "SimonBarnett"


def focus_repos(home: Path, owners: set[str]) -> list[str]:
    """Union ``focus.repos`` into resync discovery (FR #3146).

    Short keys like ``a-search`` expand to ``{Owner}/a-search`` using ``owners``
    (SimonBarnett when that owner is allowed). Full ``owner/repo`` keys pass through
    ``gitclaim.canonical_queue_repo``.
    """
    import focus_ignore
    import gitclaim

    try:
        doc = focus_ignore.load_focus(home)
    except Exception:  # noqa: BLE001
        return []
    raw = doc.get("repos") if isinstance(doc, dict) else None
    if isinstance(raw, dict):
        keys = list(raw.keys())
    elif isinstance(raw, list):
        keys = [str(x) for x in raw]
    else:
        keys = []
    prefix = _owner_prefix(owners)
    out: list[str] = []
    for key in keys:
        token = str(key or "").strip()
        if not token:
            continue
        if "/" not in token:
            token = f"{prefix}/{token}"
        if not gitclaim.REPO_RE.fullmatch(token):
            continue
        # Owner allow-list: drop focus rows outside configured owners.
        if token.partition("/")[0].lower() not in {str(o).lower() for o in owners}:
            continue
        out.append(gitclaim.canonical_queue_repo(token))
    return list(dict.fromkeys(out))


def discover_repos(home: Path, owners: set[str], getter, ignored) -> list[str]:
    """Configured list, else queue + token repos; always union focus.repos (FR #3146)."""
    import gitclaim
    skip = {str(x).lower() for x in ignored}
    repos = configured_repos(home)
    if not repos:
        try:
            doc = gitclaim.load_queue(home)
            for row in list(doc.get("unaccepted") or []) + list(doc.get("accepted") or []):
                r = str(row.get("repo") or "")
                if gitclaim.REPO_RE.fullmatch(r):
                    # FR #785: rewrite archived queue sources to their live successor.
                    repos.append(gitclaim.canonical_queue_repo(r))
        except Exception:  # noqa: BLE001
            pass
        for page in (1, 2):
            try:
                rows = getter(f"https://api.github.com/user/repos?per_page=100&affiliation=owner&sort=pushed&page={page}")
            except Exception:  # noqa: BLE001
                break
            if not isinstance(rows, list) or not rows:
                break
            for r in rows:
                if not isinstance(r, dict) or r.get("archived") or r.get("disabled") or not r.get("has_issues", True):
                    continue
                full = str(r.get("full_name") or "")
                if full.partition("/")[0].lower() in owners:
                    repos.append(gitclaim.canonical_queue_repo(full))
    # FR #3146: never let strict focus starve when queue/config/user-repos are empty.
    repos.extend(focus_repos(home, owners))
    # FR #3817: one entry per owner/name ignoring case (prefer mixed-case spelling).
    by_key: dict[str, str] = {}
    for r in repos:
        # FR #785: never keep a known-archived source name after rewrite.
        if gitclaim.repo_archived_for_queue(r):
            continue
        if not gitclaim.REPO_RE.fullmatch(r):
            continue
        if r.lower() in skip or r.split("/", 1)[-1].lower() in skip:
            continue
        k = gitclaim._repo_key(r)
        prev = by_key.get(k)
        by_key[k] = gitclaim._prefer_repo_casing(prev or "", r) if prev else r
    out = list(by_key.values())
    return out[:MAX_REPOS]


def resync_cycle(
    home: Path,
    *,
    token: str,
    ignored,
    fetch_json=None,
    owners: set[str] | None = None,
    budget: gab.GithubApiBudget | None = None,
    essential: bool = False,
    force_refresh: bool = False,
    log=None,
) -> dict:
    import gitclaim
    if owners is None:
        owners = {"simonbarnett"}
    bud = budget or gab.GithubApiBudget(home, clock=time.time, log=log or (lambda _s: None))
    _log = log or (lambda _s: None)
    # FR #4959: startup + !resync force a full GET (no If-None-Match).
    force = bool(force_refresh or essential)
    if fetch_json is None:
        if not bud.allow("reconcile", essential=essential):
            # FR #4422: never skip silently — log why and surface retry/reset fields.
            why = bud.skip_reason("reconcile") or "budget-backoff"
            _log(f"WARN github-resync skipped: {why}")
            _log(f"WARN github-resync resync_degraded reason={why}")
            return {
                "ok": True,
                "unaccepted": len(gitclaim.load_unaccepted(home)),
                "added": 0,
                "dropped": 0,
                "repos": [],
                "failed": [],
                "unchanged": [],
                "note": "budget-backoff",
                "skip_reason": why,
                "rate_reset": bud.rate_reset,
                "pruned": 0,
                "pruned_detail": [],
                "dropped_detail": [],
                "budget": bud.status_line(),
            }
        getter = gab.make_budgeted_fetch(
            bud, token, path="reconcile", essential=essential, force_refresh=force
        )
    else:
        getter = fetch_json
    # FR #180: drop skill/harvest/safe-to-close junk before GitHub merge so they cannot be re-offered.
    pruned = gitclaim.prune_unassignable_queue(home)
    repos = discover_repos(home, owners, getter, ignored)
    if not repos:
        return {"ok": True, "unaccepted": len(gitclaim.load_unaccepted(home)), "added": 0, "dropped": 0,
                "repos": [], "failed": [], "unchanged": [], "note": "no repos",
                "pruned": pruned.get("dropped", 0),
                "pruned_detail": list(pruned.get("dropped_detail") or []),
                "dropped_detail": [], "budget": bud.status_line()}
    out = gitclaim.resync_from_github(
        home,
        repos,
        fetch_json=getter,
        token=token,
        ignored=list(ignored),
        force_refresh=force,
    )
    if isinstance(out, dict):
        out["pruned"] = int(pruned.get("dropped") or 0)
        out["pruned_detail"] = list(pruned.get("dropped_detail") or [])
        out["budget"] = bud.status_line()
        out.setdefault("unchanged", [])
    return out


class ChairJobs:
    """Owned by the chair Client. ``tick()`` is cheap and non-blocking; work runs in one daemon thread."""

    def __init__(self, home: Path, digest_home: Path, *, log, announce=None, http=default_http, fetch_json=None,
                 token_loader=default_token, ignored_loader=None, clock=time.time, sleep=time.sleep,
                 spawn: bool = True, owners: set[str] | None = None) -> None:
        self.home = Path(home)
        self.digest_home = Path(digest_home)
        self.log = log
        self.announce = announce or self._announce
        self.http = http
        self.fetch_json = fetch_json
        self.token_loader = token_loader
        self.ignored_loader = ignored_loader or (lambda: [])
        self.clock = clock
        self.sleep = sleep
        self.spawn = spawn
        self.owners = owners
        # FR #4725: seed/merge fleet resync-repos.txt on both homes (includes ce-priority).
        try:
            ensure_resync_repos_file(self.home)
            ensure_resync_repos_file(self.digest_home)
        except Exception as exc:  # noqa: BLE001
            self.log(f"WARN ensure_resync_repos_file: {type(exc).__name__}: {exc}")
        t0 = clock()
        self.next_probe = t0 + FIRST_PROBE_DELAY_S
        self.next_resync = t0 + FIRST_RESYNC_DELAY_S
        self.next_merge_on_green = t0 + FIRST_MERGE_ON_GREEN_DELAY_S
        self.next_copilot = t0 + FIRST_COPILOT_DELAY_S
        self.next_webhook_ensure = t0 + FIRST_WEBHOOK_ENSURE_DELAY_S
        self._startup_webhook_ensure_done = False
        self.next_stall = t0 + FIRST_STALL_DELAY_S
        self.next_stuck_sweep = t0 + FIRST_STUCK_SWEEP_DELAY_S
        self.next_intake_outbox = t0 + FIRST_INTAKE_OUTBOX_DELAY_S
        self._intake_backoff_s = INTAKE_OUTBOX_S
        self._intake_announced_at = 0.0
        self.resync_fail_streak = 0
        self.busy = threading.Lock()
        self.token_source = ""            # set at first resync
        self._token_logged = False
        self.last_resync: dict = {}
        self.last_resync_at = 0.0
        self._startup_resync_done = False
        # FR #4959: !resync sets this so the next cycle skips If-None-Match.
        self._force_refresh_resync = False
        self.api_budget = gab.GithubApiBudget(self.home, clock=self.clock, log=self.log)

    def _announce(self, text: str) -> None:
        import bobreport
        bobreport.enqueue_chair_fleet_privmsg(self.digest_home, text)

    def request_intake_outbox_drain(self) -> None:
        """FR #5359: GitHub is reachable again; drain the queue now."""
        self.next_intake_outbox = 0.0
        self._intake_backoff_s = INTAKE_OUTBOX_S

    def request_resync(self) -> None:
        # FR #4959: operator !resync must force-refresh (not ride stale issues ETags).
        self._force_refresh_resync = True
        self.next_resync = 0.0

    def _maybe_pull_resync_forward_after_skip(self, now: float) -> None:
        """FR #4422: after budget-backoff, schedule retry at rate-limit reset (not only +RESYNC_S)."""
        res = self.last_resync if isinstance(self.last_resync, dict) else {}
        if str(res.get("note") or "") != "budget-backoff":
            return
        reset = res.get("rate_reset")
        if reset is None:
            reset = getattr(self.api_budget, "rate_reset", None)
        try:
            reset_f = float(reset) if reset is not None else None
        except (TypeError, ValueError):
            reset_f = None
        # Prefer GitHub reset; otherwise retry in 5 min so an exhausted hourly
        # counter is not left silent until the next full hour.
        retry_at = (reset_f + 1.0) if reset_f is not None else (float(now) + 300.0)
        if retry_at < float(now):
            retry_at = float(now) + 5.0
        if retry_at < self.next_resync:
            self.next_resync = retry_at
            why = res.get("skip_reason") or "budget-backoff"
            self.log(
                f"INFO github-resync retry scheduled in "
                f"{int(max(0, retry_at - float(now)))}s reason={why}"
            )

    def tick(self) -> bool:
        now = self.clock()
        # FR #3212: gap in webhook delivery pulls reconcile forward (still one-at-a-time via busy lock).
        if now < self.next_resync and gab.webhook_gap_due(
            self.home, now=now, gap_s=WEBHOOK_GAP_S
        ):
            self.next_resync = now
        if now < min(
            self.next_probe,
            self.next_resync,
            self.next_merge_on_green,
            self.next_stall,
            self.next_stuck_sweep,
            self.next_copilot,
            self.next_webhook_ensure,
            self.next_intake_outbox,
        ):
            return False
        if not self.busy.acquire(blocking=False):
            return False
        if not self.spawn:
            try:
                self._run_due()
            finally:
                self.busy.release()
            return True
        threading.Thread(target=self._thread_main, daemon=True, name="chair-jobs").start()
        return True

    def _thread_main(self) -> None:
        try:
            self._run_due()
        finally:
            self.busy.release()

    def run_due_sync(self) -> None:
        with self.busy:
            self._run_due()

    def _run_due(self) -> None:
        now = self.clock()
        if now >= self.next_probe:
            self.next_probe = now + WEBHOOK_PROBE_S
            try:
                out = probe_cycle(self.home, now=now, http=self.http, sleep=self.sleep)
                for line in out["log"]:
                    self.log(line)
                for line in out["announce"]:
                    self.announce(line)
                    self.log("INFO webhook-health announced: " + line)
                # WEBHOOK DOWN on any target is a gap signal — pull reconcile forward.
                for tname, tdoc in (out.get("state") or {}).get("targets", {}).items():
                    if isinstance(tdoc, dict) and not tdoc.get("up"):
                        self.next_resync = min(self.next_resync, now)
                        break
            except Exception as exc:  # noqa: BLE001
                self.log(f"WARN webhook-health probe failed: {type(exc).__name__}: {exc}")
        now = self.clock()
        if now >= self.next_resync:
            self.next_resync = now + RESYNC_S
            self._resync()
            # FR #4422: when reconcile was skipped for rate-limit/budget, retry at
            # X-RateLimit-Reset (or sooner than the full hourly cadence).
            self._maybe_pull_resync_forward_after_skip(now)
        now = self.clock()
        if now >= self.next_merge_on_green:
            self.next_merge_on_green = now + MERGE_ON_GREEN_S
            try:
                import mrb_merge_on_green

                token, src = self.token_loader()
                if token and not self.token_source:
                    self.token_source = src or ""
                out = mrb_merge_on_green.process_pending(
                    self.home,
                    token=token or None,
                    log=self.log,
                    rate_remaining=mrb_merge_on_green.get_rate_remaining,
                )
                # FR #4543: when budget is low, stretch the next sweep so offers/resync keep quota.
                if out.get("backed_off"):
                    self.next_merge_on_green = now + max(MERGE_ON_GREEN_S, 300.0)
                    self.log(
                        "INFO merge-on-green back-off "
                        f"rate_remaining={out.get('rate_remaining')} "
                        f"pending={out.get('seen', 0)}"
                    )
                elif out.get("merged") or out.get("requeued") or out.get("skipped_hold") or out.get("dropped"):
                    self.log(
                        "INFO merge-on-green "
                        f"merged={out.get('merged', 0)} requeued={out.get('requeued', 0)} "
                        f"wait={out.get('wait', 0)} hold={out.get('skipped_hold', 0)} "
                        f"dropped={out.get('dropped', 0)} err={out.get('errors', 0)}"
                    )
            except Exception as exc:  # noqa: BLE001
                self.log(f"WARN merge-on-green: {type(exc).__name__}: {exc}")
        now = self.clock()
        if now >= self.next_stall:
            self.next_stall = now + STALL_S
            try:
                self._stall_scan()
            except Exception as exc:  # noqa: BLE001
                self.log(f"WARN stall-scan: {type(exc).__name__}: {exc}")
        now = self.clock()
        if now >= self.next_stuck_sweep:
            self.next_stuck_sweep = now + STUCK_SWEEP_S
            try:
                self._stuck_job_sweep()
            except Exception as exc:  # noqa: BLE001
                self.log(f"WARN stuck-sweep: {type(exc).__name__}: {exc}")
        now = self.clock()
        if now >= self.next_copilot:
            self.next_copilot = now + COPILOT_TICK_S
            try:
                self._copilot_tick()
            except Exception as exc:  # noqa: BLE001
                self.log(f"WARN copilot-dispatch: {type(exc).__name__}: {exc}")
        now = self.clock()
        if now >= self.next_webhook_ensure:
            self.next_webhook_ensure = now + WEBHOOK_ENSURE_S
            try:
                self._ensure_webhooks()
            except Exception as exc:  # noqa: BLE001
                self.log(f"WARN webhook-ensure: {type(exc).__name__}: {exc}")
        now = self.clock()
        if now >= self.next_intake_outbox:
            try:
                self._drain_intake_outbox()
            except Exception as exc:  # noqa: BLE001
                self.log(f"WARN intake-outbox-drain: {type(exc).__name__}: {exc}")
                self._intake_backoff_s = min(
                    INTAKE_OUTBOX_BACKOFF_MAX_S, max(INTAKE_OUTBOX_S, self._intake_backoff_s) * 2.0
                )
                self.next_intake_outbox = now + self._intake_backoff_s

    def _drain_intake_outbox(self) -> None:
        """FR #5359: retry the whole intake/outbox with backoff; announce queued age."""
        import intake
        import gh_filer

        now = self.clock()
        snap = intake.intake_outbox_snapshot(self.digest_home, now=now)
        count = int(snap.get("count") or 0)
        age = snap.get("oldest_age_s")
        gh_ok = bool(snap.get("gh_cli"))
        if count and (
            self._intake_announced_at <= 0.0 or (now - self._intake_announced_at) >= 900.0
        ):
            age_s = int(age) if age is not None else 0
            line = (
                f"INTAKE OUTBOX queued={count} oldest_age_s={age_s} "
                f"gh={'ok' if gh_ok else 'MISSING'}"
            )
            self.announce(line)
            self.log("INFO " + line)
            self._intake_announced_at = now
        if count == 0:
            self._intake_backoff_s = INTAKE_OUTBOX_S
            self.next_intake_outbox = now + INTAKE_OUTBOX_S
            return
        if not gh_ok:
            self._intake_backoff_s = min(INTAKE_OUTBOX_BACKOFF_MAX_S, self._intake_backoff_s * 2.0)
            self.next_intake_outbox = now + self._intake_backoff_s
            self.log("WARN intake-outbox gh MISSING; queued until gh is installed")
            return
        filer = gh_filer.default_filer()
        stats = intake.drain_intake_outbox_all(self.digest_home, filer, batch=20)
        c = stats.as_counts()
        self.log(
            "INFO intake_outbox_drain "
            f"filed={c.get('filed')} receipt={c.get('recorded_receipt')} "
            f"dup={c.get('skipped_duplicate')} deferred={c.get('deferred')}"
        )
        if c.get("deferred"):
            self._intake_backoff_s = min(INTAKE_OUTBOX_BACKOFF_MAX_S, self._intake_backoff_s * 2.0)
            self.next_intake_outbox = now + self._intake_backoff_s
            return
        self._intake_backoff_s = INTAKE_OUTBOX_S
        self.next_intake_outbox = now + INTAKE_OUTBOX_S

    def _github_json(self, method: str, url: str, body: dict | None = None) -> tuple[dict | list | None, int]:
        """Authenticated GitHub JSON helper for Copilot pool + tasks (FR #5174)."""
        import json as _json
        import urllib.error
        import urllib.request

        token, _src = self.token_loader()
        if not token:
            raise RuntimeError("no token")
        # Prefer injected fetch_json for GET-only test doubles.
        if method.upper() == "GET" and self.fetch_json is not None and body is None:
            data = self.fetch_json(url)
            return data, 200
        raw = _json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(
            url,
            data=raw,
            method=method.upper(),
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "User-Agent": "bobiverse-jeeves",
                "Content-Type": "application/json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                text = resp.read().decode("utf-8") or "null"
                code = int(resp.status)
                parsed = _json.loads(text) if text not in ("", "null") else None
                return parsed, code
        except urllib.error.HTTPError as exc:
            err_body = ""
            with contextlib.suppress(Exception):
                err_body = exc.read().decode("utf-8", errors="replace")
            parsed = None
            with contextlib.suppress(Exception):
                parsed = _json.loads(err_body) if err_body else None
            if not isinstance(parsed, dict):
                parsed = {"message": err_body or str(exc), "status": int(exc.code)}
            else:
                parsed.setdefault("status", int(exc.code))
            return parsed, int(exc.code)

    def _copilot_tick(self) -> None:
        """FR #5174: always pass fetch_user + tasks POST into copilot_dispatch.tick.

        FR #5267: release stranded accepts before any Copilot API call, including
        when there is no token (dispatch stays off).
        """
        import copilot_dispatch

        swept = copilot_dispatch.settle_stuck_accepted(self.digest_home, now=self.clock())
        if swept.get("dropped") or swept.get("released"):
            self.log(
                f"INFO copilot-queue dropped={swept.get('dropped', 0)} "
                f"released={swept.get('released', 0)}"
            )
        token, _src = self.token_loader()
        if not token:
            self.log("WARN copilot-dispatch skipped: no token")
            return

        def fetch_user() -> dict:
            data, _code = self._github_json(
                "GET", "https://api.github.com/copilot_internal/user"
            )
            return data if isinstance(data, dict) else {}

        def post(path: str, body: dict) -> dict:
            url = path if str(path).startswith("http") else (
                "https://api.github.com/" + str(path).lstrip("/")
            )
            data, code = self._github_json("POST", url, body if isinstance(body, dict) else {})
            out = dict(data) if isinstance(data, dict) else {}
            out.setdefault("status", int(code))
            return out

        def get(path: str):
            data, code = self._github_json("GET", "https://api.github.com/" + path.lstrip("/"))
            if not 200 <= code < 300:
                raise RuntimeError(f"Copilot tracking GET failed ({code})")
            return data

        # FR #5174: queue.json / unaccepted live under digest_home (BOB_DIGEST_HOME),
        # not chair home (BOB_HOME / ~/.jeeves). Allowance + jobs cache share that path.
        out = copilot_dispatch.tick(
            self.digest_home,
            fetch_user=fetch_user,
            post=post,
            get=get,
            announce=self.announce,
        )
        if out.get("dispatched") or out.get("timed_out"):
            self.log(
                f"INFO copilot-dispatch dispatched={out.get('dispatched', 0)} "
                f"timed_out={out.get('timed_out', 0)}"
            )

    def _ensure_webhooks(self) -> None:
        """FR #5172: ensure git hooks on every served repo (startup + hourly)."""
        import copilot_dispatch
        import json as _json
        import urllib.error
        import urllib.request

        repos = configured_repos(self.home)
        if not repos:
            repos = list(DEFAULT_RESYNC_REPOS)
        token, _src = self.token_loader()
        if not token:
            self.log("WARN webhook-ensure skipped: no token")
            return

        if self.fetch_json is not None:
            def list_hooks(repo: str) -> list:
                rows = self.fetch_json(f"https://api.github.com/repos/{repo}/hooks")
                return list(rows) if isinstance(rows, list) else []

            def make_create(_repo: str):
                def _c(body: dict) -> None:
                    self.log(f"INFO webhook-ensure create (dry, fetch_json) events={body.get('events')}")

                return _c

            def make_patch(_repo: str):
                def _p(hid, body: dict) -> None:
                    self.log(f"INFO webhook-ensure repair (dry, fetch_json) id={hid}")

                return _p

            for repo in list(dict.fromkeys(repos)):
                info = copilot_dispatch.ensure_repo_webhook(
                    repo,
                    list_hooks=list_hooks,
                    create=make_create(repo),
                    patch=make_patch(repo),
                    file_stall=lambda **kw: copilot_dispatch.file_webhook_stall(self.home, **kw),
                )
                act = (info or {}).get("action") or "error"
                self.log(f"INFO webhook-ensure repo={repo} action={act}")
            return

        def _gh(method: str, url: str, body: dict | None = None):
            raw = _json.dumps(body).encode("utf-8") if body is not None else None
            req = urllib.request.Request(
                url,
                data=raw,
                method=method,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "bobiverse-jeeves",
                    "Content-Type": "application/json",
                },
            )
            try:
                with urllib.request.urlopen(req, timeout=20) as resp:
                    text = resp.read().decode("utf-8") or "null"
                    return _json.loads(text) if text != "null" else None
            except urllib.error.HTTPError as exc:
                if int(exc.code) in (401, 403, 404):
                    raise PermissionError(f"hooks {exc.code}") from exc
                raise

        def list_hooks(repo: str) -> list:
            rows = _gh("GET", f"https://api.github.com/repos/{repo}/hooks")
            return list(rows) if isinstance(rows, list) else []

        def make_create(repo: str):
            def _c(body: dict) -> None:
                _gh("POST", f"https://api.github.com/repos/{repo}/hooks", body)

            return _c

        def make_patch(repo: str):
            def _p(hid, body: dict) -> None:
                _gh("PATCH", f"https://api.github.com/repos/{repo}/hooks/{hid}", body)

            return _p

        for repo in list(dict.fromkeys(repos)):
            info = copilot_dispatch.ensure_repo_webhook(
                repo,
                list_hooks=list_hooks,
                create=make_create(repo),
                patch=make_patch(repo),
                file_stall=lambda **kw: copilot_dispatch.file_webhook_stall(self.home, **kw),
            )
            act = (info or {}).get("action") or "error"
            self.log(f"INFO webhook-ensure repo={repo} action={act}")


    def _stuck_job_sweep(self) -> None:
        """FR #5510: classify open/queue work; release silent accepts; enqueue untracked."""
        import stuck_job_sweep
        import gitclaim

        live = gitclaim.live_seat_nicks(self.digest_home)
        idle = gitclaim.free_seat_nicks(self.digest_home, live)
        activity = {}
        for nick in live:
            ts = gitclaim.last_worker_activity(self.digest_home, nick)
            if ts is None:
                ts = gitclaim.last_worker_activity(self.home, nick)
            if ts is not None:
                activity[str(nick).lower()] = float(ts)
        stuck_job_sweep.run_stuck_sweep(
            self.digest_home,
            now=self.clock(),
            live=live,
            idle=idle,
            activity=activity,
            act=True,
            log=self.log,
            announce=self.announce,
        )

    def _stall_scan(self) -> None:
        """FR #5164: file one issue per distinct stall; never raise."""
        import stall_detectors
        import stall_filer
        import gitclaim

        doc = gitclaim.load_queue(self.digest_home)
        live = gitclaim.live_seat_nicks(self.digest_home)
        idle = gitclaim.free_seat_nicks(self.digest_home, live)
        healed = []
        with contextlib.suppress(Exception):
            healed = gitclaim.heal_mrb_reviewer_deadlock(
                self.digest_home, idle=idle, live=live, now=self.clock()
            )
        if healed:
            self.log("INFO stall-heal " + "; ".join(healed))
        res = self.last_resync if isinstance(self.last_resync, dict) else {}
        status = res.get("error") or (200 if res.get("ok") else None)
        last_activity = {}
        for nick in idle:
            if not nick:
                continue
            ts = gitclaim.last_worker_activity(self.digest_home, nick)
            if ts is None:
                ts = gitclaim.last_worker_activity(self.home, nick)
            if ts is not None:
                last_activity[nick] = float(ts)
        snap = {
            "now": self.clock(),
            "live": live,
            "idle": idle,
            "unaccepted": list(doc.get("unaccepted") or []),
            "accepted": list(doc.get("accepted") or []),
            "ledger": gitclaim.ledger_load(self.digest_home),
            "resync_fail_streak": self.resync_fail_streak,
            "last_resync_status": status,
            "last_bored": gitclaim.merge_last_bored(self.home, self.digest_home),
            "last_activity": last_activity,
            "deadlock_healed": bool(healed),
        }
        findings = stall_detectors.detect_all(snap)
        if not findings:
            return
        # FR #5181: park all-gave-up rows so the next scan skips them
        # (needs_human) and seats stop re-offering abandoned human work.
        with contextlib.suppress(Exception):
            n_park = stall_detectors.stamp_needs_human_for_all_gave_up(
                self.digest_home, findings
            )
            if n_park:
                self.log(f"INFO stall-park needs_human n={n_park}")
        actions = stall_filer.apply_findings(
            findings,
            home=self.home,
            now=self.clock(),
            excerpt="chair stall scan",
            create=stall_filer.default_create,
        )
        for act in actions:
            self.log(f"INFO stall-filer {act}")

    def _log_token_source_once(self, source: str) -> None:
        if self._token_logged:
            return
        self._token_logged = True
        line = f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.clock()))}\tresync token source: {source}\n"
        try:
            with (self.home / TOKEN_SOURCE_LOG).open("a", encoding="utf-8") as fh:
                fh.write(line)
        except OSError:
            pass
        self.log(f"INFO github-resync token source: {source} (value never logged)")

    def _resync(self) -> None:
        try:
            token, source = self.token_loader()
            self.token_source = source
            self._log_token_source_once(source)
            if not token:
                self.resync_fail_streak = int(self.resync_fail_streak) + 1
                self.last_resync = {"ok": False, "error": "no token"}
                return
            essential = not self._startup_resync_done
            force_refresh = bool(self._force_refresh_resync or essential)
            self._force_refresh_resync = False
            res = resync_cycle(
                self.home,
                token=token,
                ignored=list(self.ignored_loader()),
                fetch_json=self.fetch_json,
                owners=self.owners,
                budget=self.api_budget,
                essential=essential,
                force_refresh=force_refresh,
                log=self.log,
            )
            self._startup_resync_done = True
            self.last_resync, self.last_resync_at = res, self.clock()
            if res.get("ok"):
                self.resync_fail_streak = 0
                if res.get("note") != "budget-backoff":
                    self.request_intake_outbox_drain()
                note = res.get("note") or ""
                # FR #4422: budget-backoff is a skip — keep WARN visible (resync_cycle also logs).
                if note == "budget-backoff":
                    why = res.get("skip_reason") or note
                    self.log(f"WARN github-resync skipped note={note} reason={why}")
                    self.log(f"WARN github-resync resync_degraded reason={why}")
                elif (
                    res.get("failed")
                    and not res.get("repos")
                    and self.api_budget.in_backoff()
                ):
                    why = self.api_budget.skip_reason("reconcile") or "rate-limit-floor"
                    self.log(f"WARN github-resync resync_degraded reason={why}")
                else:
                    # FR #4959: surface unchanged= so repos=0 is not mistaken for "no repos".
                    self.log(
                        f"INFO github-resync ok repos={len(res.get('repos') or [])} "
                        f"failed={len(res.get('failed') or [])} "
                        f"unchanged={len(res.get('unchanged') or [])} "
                        f"added={res.get('added', 0)} dropped={res.get('dropped', 0)} "
                        f"pruned={res.get('pruned', 0)} skipped_draft={res.get('skipped_draft', 0)} "
                        f"unaccepted={res.get('unaccepted', 0)} "
                        f"fix_dup={res.get('fix_dup', 0)} "
                        f"fix_skip_main_red={res.get('fix_skip_main_red', 0)}"
                        + (f" note={note}" if note else "")
                    )
                # FR #2899: name every dropped row + reason (never only dropped=N).
                for detail in list(res.get("dropped_detail") or [])[:40]:
                    self.log(f"INFO github-resync dropped {detail}")
                for detail in list(res.get("pruned_detail") or [])[:40]:
                    self.log(f"INFO github-resync pruned {detail}")
            else:
                self.resync_fail_streak = int(self.resync_fail_streak) + 1
                self.log(f"WARN github-resync failed: {res.get('error')}")
        except Exception as exc:  # noqa: BLE001
            self.resync_fail_streak = int(self.resync_fail_streak) + 1
            self.last_resync = {"ok": False, "error": type(exc).__name__}
            self.log(f"WARN github-resync error: {type(exc).__name__}: {exc}")

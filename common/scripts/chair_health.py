"""Chair background jobs (deterministic, no LLM, no IRC I/O of their own):

* webhook health probes every 30 min  (``WEBHOOK_PROBE_S``): GET report, GET jira, GET intake/<id> (404 = up) and a
  synthetic ``ping`` to POST git, against the local receiver and the public https URL. State in
  ``webhook-health.json``; announce on #bobiverse (via chair-outbox) ONLY when a target flips up<->down.
* authenticated ``gitclaim.resync_from_github`` every 15 min (``RESYNC_S``) using the existing Jeeves token
  (``config\\github.token`` through ``gh_filer`` - token handling is NOT changed here). The token SOURCE (never the
  value) is written once per process to ``resync-token-source.log``.

Everything network/clock/disk is injectable so tests use fakes.
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

WEBHOOK_PROBE_S = 1800.0
RESYNC_S = 900.0
FIRST_RESYNC_DELAY_S = 120.0
FIRST_PROBE_DELAY_S = 45.0
STATE_NAME = "webhook-health.json"
TOKEN_SOURCE_LOG = "resync-token-source.log"
LOCAL_BASE = "http://127.0.0.1:7700"
PUBLIC_BASE = "https://irc.ntsa.uk"
PROBE_ZEN = "jeeves-health-probe"          # bobcallback acks this ping quietly (no queue, no announce)
PROBE_REPO = "SimonBarnett/bobiverse"
MAX_REPOS = 60

# (name, method, path, status codes that count as UP)
CHECKS = (
    ("report", "GET", "/bob/v1/report", frozenset({200})),
    ("jira", "GET", "/bob/v1/jira", frozenset({200})),
    ("intake", "GET", "/bob/v1/intake/jeeves-health-probe", frozenset({200, 404})),
    ("git", "POST", "/bob/v1/git", frozenset({200, 202, 204})),
)


def targets() -> dict[str, str]:
    return {
        "local": (os.environ.get("JEEVES_PROBE_LOCAL") or LOCAL_BASE).rstrip("/"),
        "public": (os.environ.get("JEEVES_PROBE_PUBLIC") or PUBLIC_BASE).rstrip("/"),
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


def configured_repos(home: Path) -> list[str]:
    import gitclaim
    names: list[str] = []
    env = (os.environ.get("JEEVES_RESYNC_REPOS") or "").replace(";", ",")
    names += [x.strip() for x in env.split(",") if x.strip()]
    for p in (Path(home) / "resync-repos.txt",):
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


def discover_repos(home: Path, owners: set[str], getter, ignored) -> list[str]:
    """Configured list, else repos already in the queue + the token's own repos (owner allow-list, not archived)."""
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
    out = []
    for r in dict.fromkeys(repos):
        # FR #785: never keep a known-archived source name after rewrite.
        if gitclaim.repo_archived_for_queue(r):
            continue
        if gitclaim.REPO_RE.fullmatch(r) and r.lower() not in skip and r.split("/", 1)[-1].lower() not in skip:
            out.append(r)
    return out[:MAX_REPOS]


def resync_cycle(home: Path, *, token: str, ignored, fetch_json=None, owners: set[str] | None = None) -> dict:
    import gitclaim
    if owners is None:
        owners = {"simonbarnett"}
    getter = fetch_json
    if getter is None:
        def getter(url, _tok=token):  # noqa: E306
            req = urllib.request.Request(url, headers={
                "Accept": "application/vnd.github+json", "User-Agent": "bobiverse-jeeves",
                "Authorization": "Bearer " + _tok})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
    # FR #180: drop skill/harvest/safe-to-close junk before GitHub merge so they cannot be re-offered.
    pruned = gitclaim.prune_unassignable_queue(home)
    repos = discover_repos(home, owners, getter, ignored)
    if not repos:
        return {"ok": True, "unaccepted": len(gitclaim.load_unaccepted(home)), "added": 0, "dropped": 0,
                "repos": [], "failed": [], "note": "no repos", "pruned": pruned.get("dropped", 0),
                "pruned_detail": list(pruned.get("dropped_detail") or []),
                "dropped_detail": []}
    out = gitclaim.resync_from_github(home, repos, fetch_json=getter, token=token, ignored=list(ignored))
    if isinstance(out, dict):
        out["pruned"] = int(pruned.get("dropped") or 0)
        out["pruned_detail"] = list(pruned.get("dropped_detail") or [])
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
        t0 = clock()
        self.next_probe = t0 + FIRST_PROBE_DELAY_S
        self.next_resync = t0 + FIRST_RESYNC_DELAY_S
        self.busy = threading.Lock()
        self.token_source = ""            # set at first resync
        self._token_logged = False
        self.last_resync: dict = {}
        self.last_resync_at = 0.0

    def _announce(self, text: str) -> None:
        import bobreport
        bobreport.enqueue_chair_fleet_privmsg(self.digest_home, text)

    def request_resync(self) -> None:
        self.next_resync = 0.0

    def tick(self) -> bool:
        now = self.clock()
        if now < min(self.next_probe, self.next_resync):
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
            except Exception as exc:  # noqa: BLE001
                self.log(f"WARN webhook-health probe failed: {type(exc).__name__}: {exc}")
        now = self.clock()
        if now >= self.next_resync:
            self.next_resync = now + RESYNC_S
            self._resync()

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
                self.last_resync = {"ok": False, "error": "no token"}
                return
            res = resync_cycle(self.home, token=token, ignored=list(self.ignored_loader()),
                               fetch_json=self.fetch_json, owners=self.owners)
            self.last_resync, self.last_resync_at = res, self.clock()
            if res.get("ok"):
                self.log(f"INFO github-resync ok repos={len(res.get('repos') or [])} failed={len(res.get('failed') or [])} "
                         f"added={res.get('added', 0)} dropped={res.get('dropped', 0)} "
                         f"pruned={res.get('pruned', 0)} skipped_draft={res.get('skipped_draft', 0)} "
                         f"unaccepted={res.get('unaccepted', 0)}")
                # FR #2899: name every dropped row + reason (never only dropped=N).
                for detail in list(res.get("dropped_detail") or [])[:40]:
                    self.log(f"INFO github-resync dropped {detail}")
                for detail in list(res.get("pruned_detail") or [])[:40]:
                    self.log(f"INFO github-resync pruned {detail}")
            else:
                self.log(f"WARN github-resync failed: {res.get('error')}")
        except Exception as exc:  # noqa: BLE001
            self.last_resync = {"ok": False, "error": type(exc).__name__}
            self.log(f"WARN github-resync error: {type(exc).__name__}: {exc}")

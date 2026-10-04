"""FR #2302 / Refs #1993 WP4: deterministic two-worker queue storm harness.

Offline / any-machine harness. Proves in-process queue RLock accounting under
concurrent synthetic GIT pings + claim/DONE traffic (two workers per machine).

Live ionos cutover checklist stays in ``jeeves/docs/jeeves-exe-self-heal.md``;
this module does not touch Ergo/BobIrcd and does not require a live :7700.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import gitclaim
import jeeves_locks

DEFAULT_PINGS = 50
DEFAULT_WORKERS_PER_MACHINE = 2
DEFAULT_MACHINES = ("marchhare", "flamingo")
REPO = "SimonBarnett/bobiverse"


@dataclass
class StormEvent:
    kind: str
    id: str
    nick: str = ""
    result: str = ""
    seq: int = 0


@dataclass
class StormSummary:
    ok: bool
    fr: int = 2302
    seed: int = 0
    pings: int = 0
    workers: int = 0
    machines: list[str] = field(default_factory=list)
    enqueue_added: int = 0
    enqueue_duplicate: int = 0
    enqueue_errors: list[str] = field(default_factory=list)
    claim_ok: int = 0
    claim_errors: list[str] = field(default_factory=list)
    done_ok: int = 0
    done_ids: list[str] = field(default_factory=list)
    event_log: list[dict[str, Any]] = field(default_factory=list)
    enqueue_schedule: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    duration_s: float = 0.0
    inproc_lock: bool = True

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


def _claim_for_ping(ping_id: str) -> gitclaim.GitClaim:
    return gitclaim.GitClaim(
        repo=REPO,
        task="MRB",
        id=ping_id,
        event="pull_request",
        action="opened",
        line=f"GIT pull_request {REPO}{ping_id} storm",
        title=f"storm ping {ping_id}",
        body="WP4 synthetic storm; not a real PR",
    )


def _worker_nicks(machines: list[str], workers_per_machine: int) -> list[str]:
    out: list[str] = []
    for m in machines:
        mid = str(m).strip().lower()
        if not mid:
            continue
        for i in range(1, workers_per_machine + 1):
            out.append(f"{mid}-{10000 + i}")
    return out


def _done_accepted(home: Path, job: dict) -> str:
    """Move one accepted row to done under the queue lock (simulates shop DONE)."""
    repo = str(job.get("repo") or "")
    task = str(job.get("task") or "")
    ident = str(job.get("id") or "")
    nick = str(job.get("nick") or "")
    try:
        with gitclaim._lock(home):
            doc = gitclaim._load_queue_unlocked(home)
            before = len(doc.get("accepted") or [])
            kept = []
            moved = None
            for row in doc.get("accepted") or []:
                if moved is None and gitclaim._same(row, repo, task, ident):
                    moved = dict(row)
                    continue
                kept.append(row)
            if moved is None:
                return "missing"
            moved["done_ts"] = gitclaim._utc_now()
            moved["done_nick"] = nick
            doc["accepted"] = kept
            doc.setdefault("done", []).append(moved)
            gitclaim._write_queue(gitclaim.queue_path(home), doc)
            if len(doc["accepted"]) != before - 1:
                return "error"
            return "ok"
    except (TimeoutError, OSError, json.JSONDecodeError, ValueError) as exc:
        return f"error:{exc.__class__.__name__}"


def run_storm(
    home: Path,
    *,
    seed: int = 1,
    pings: int = DEFAULT_PINGS,
    machines: list[str] | None = None,
    workers_per_machine: int = DEFAULT_WORKERS_PER_MACHINE,
    use_inproc_lock: bool = True,
) -> StormSummary:
    """Run a seeded storm; return a machine-readable summary.

    Same seed + parameters → same enqueue submission schedule and the same
    done-id multiset. Claim completion order across workers may interleave.
    """
    t0 = time.perf_counter()
    machines = list(machines or DEFAULT_MACHINES)
    nicks = _worker_nicks(machines, workers_per_machine)
    rng = random.Random(seed)
    # gitclaim.ID_RE requires ``#\d+``
    ping_ids = [f"#{10_000 + i}" for i in range(pings)]
    schedule = list(ping_ids)
    rng.shuffle(schedule)

    summary = StormSummary(
        ok=False,
        seed=seed,
        pings=pings,
        workers=len(nicks),
        machines=machines,
        inproc_lock=use_inproc_lock,
        enqueue_schedule=list(schedule),
    )
    log_lock = threading.Lock()
    seq = 0

    def log_event(kind: str, eid: str, nick: str = "", result: str = "") -> None:
        nonlocal seq
        with log_lock:
            seq += 1
            summary.event_log.append(
                StormEvent(kind=kind, id=eid, nick=nick, result=result, seq=seq).__dict__
            )

    jeeves_locks.disable_inproc_locks()
    if use_inproc_lock:
        jeeves_locks.enable_inproc_locks()

    prev_digest = os.environ.get("BOB_DIGEST_HOME")
    try:
        home = Path(home)
        home.mkdir(parents=True, exist_ok=True)
        # gitclaim._root uses fleet_digest_home — pin so storm stays in the temp home.
        os.environ["BOB_DIGEST_HOME"] = str(home.resolve())

        def do_enqueue(eid: str) -> str:
            result = gitclaim.enqueue_unaccepted(home, _claim_for_ping(eid))
            log_event("enqueue", eid, result=result)
            return result

        with ThreadPoolExecutor(max_workers=max(4, len(nicks))) as pool:
            futs = [pool.submit(do_enqueue, eid) for eid in schedule]
            for fut in as_completed(futs):
                r = fut.result()
                if r == "added":
                    summary.enqueue_added += 1
                elif r == "duplicate":
                    summary.enqueue_duplicate += 1
                else:
                    summary.enqueue_errors.append(r)

        stop = threading.Event()

        def worker_loop(nick: str) -> None:
            channel = f"#{nick.rsplit('-', 1)[0]}"
            while not stop.is_set():
                status, job = gitclaim.claim_top(home, nick, channel)
                if status == "empty":
                    return
                if status != "ok" or not job:
                    log_event("claim", "", nick=nick, result=status)
                    with log_lock:
                        summary.claim_errors.append(f"{nick}:{status}")
                    continue
                eid = str(job.get("id") or "")
                log_event("claim", eid, nick=nick, result="ok")
                with log_lock:
                    summary.claim_ok += 1
                done = _done_accepted(home, job)
                log_event("done", eid, nick=nick, result=done)
                with log_lock:
                    if done == "ok":
                        summary.done_ok += 1
                        summary.done_ids.append(eid)
                    else:
                        summary.failures.append(f"done:{eid}:{done}")

        with ThreadPoolExecutor(max_workers=len(nicks) or 1) as pool:
            futs = [pool.submit(worker_loop, n) for n in nicks]
            for fut in as_completed(futs):
                fut.result()
            stop.set()

        doc = gitclaim.load_queue(home)
        left_u = list(doc.get("unaccepted") or [])
        left_a = list(doc.get("accepted") or [])
        done_rows = list(doc.get("done") or [])
        done_ids = [str(r.get("id") or "") for r in done_rows]
        summary.done_ids = done_ids

        if summary.enqueue_errors:
            summary.failures.append(f"enqueue_errors={summary.enqueue_errors}")
        if summary.claim_errors:
            summary.failures.append(f"claim_errors={summary.claim_errors}")
        if summary.enqueue_added != pings:
            summary.failures.append(
                f"enqueue_added={summary.enqueue_added} want={pings}"
            )
        if summary.enqueue_duplicate:
            summary.failures.append(f"unexpected_duplicates={summary.enqueue_duplicate}")
        if left_u or left_a:
            summary.failures.append(
                f"leftover unaccepted={len(left_u)} accepted={len(left_a)}"
            )
        if len(done_ids) != pings:
            summary.failures.append(f"done_count={len(done_ids)} want={pings}")
        if len(set(done_ids)) != pings:
            summary.failures.append("done_ids not unique (duplicate/lost)")
        if sorted(done_ids) != sorted(ping_ids):
            summary.failures.append("done_ids != ping_ids (reordered account fail)")
        for r in summary.enqueue_errors:
            if str(r).startswith("error:queue"):
                summary.failures.append(f"err=queue:{r}")

        summary.ok = not summary.failures
    finally:
        jeeves_locks.disable_inproc_locks()
        if prev_digest is None:
            os.environ.pop("BOB_DIGEST_HOME", None)
        else:
            os.environ["BOB_DIGEST_HOME"] = prev_digest
        summary.duration_s = round(time.perf_counter() - t0, 4)

    return summary


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="FR #2302 WP4 queue storm harness")
    p.add_argument("--home", type=Path, required=True, help="digest home (temp ok)")
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--pings", type=int, default=DEFAULT_PINGS)
    p.add_argument("--workers-per-machine", type=int, default=DEFAULT_WORKERS_PER_MACHINE)
    p.add_argument(
        "--machines",
        default=",".join(DEFAULT_MACHINES),
        help="comma-separated machine ids",
    )
    p.add_argument("--out", type=Path, default=None, help="write JSON summary")
    p.add_argument("--no-inproc-lock", action="store_true")
    args = p.parse_args(argv)
    machines = [m.strip() for m in str(args.machines).split(",") if m.strip()]
    summary = run_storm(
        args.home,
        seed=args.seed,
        pings=args.pings,
        machines=machines,
        workers_per_machine=args.workers_per_machine,
        use_inproc_lock=not args.no_inproc_lock,
    )
    payload = summary.to_json()
    line = json.dumps(payload, ensure_ascii=False)
    print(line)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(line + "\n", encoding="utf-8")
    return 0 if summary.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

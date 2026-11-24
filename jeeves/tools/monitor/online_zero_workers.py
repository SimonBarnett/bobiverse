#!/usr/bin/env python3
"""Online shop with zero workers while fleet offerable_count > 0 (FR #9462).

Digest stuck[] already classifies ``online_zero_workers`` (FR #8429). This check
EXIT 1 on non-chair hosts reading live /report (and on chair local digest) so
monitor can escalate with fingerprint ``stall:online-zero-workers:<machine>``.
Never Start-BobWorker / auto-start seats (FR #3180) — TipForm Agents only.

FR #9503 follow-up: an **offline** ear (bob-ear dead / ircBob Running-without-child)
is ``ircbob_ear`` + ``ear_down_gate``, not this check. Do not Closes ear-down FRs
when this check alone goes quiet — require digest online + bob-ear child (+
``!startworker`` ACK) per ``ear_down_gate.py``.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from _common import (
    EXIT_FINDING,
    EXIT_OK,
    fetch_live_report,
    live_report_url,
    non_chair_overlay,
    resolve_homes,
    resolve_queue_path,
    run_check,
)

FINGERPRINT_ID = "online-zero-workers"
REMEDIATION = (
    "Operator: TipForm -> Agents to start seats on the empty online machine "
    "(FR #3180 / #9462). Do not silent auto-start."
)


def fingerprint_for(machine: str) -> str:
    mid = str(machine or "").strip().lower() or "?"
    return f"stall:{FINGERPRINT_ID}:{mid}"


def _worker_count(ent: dict) -> int | None:
    """Return live worker count when the digest/report shape is known."""
    if not isinstance(ent, dict):
        return None
    if "worker_list" in ent and ent.get("worker_list") is not None:
        wl = ent.get("worker_list")
        if isinstance(wl, (list, dict)):
            return len(wl)
        return 0
    if "workers" not in ent:
        return None
    raw = ent.get("workers")
    if isinstance(raw, dict):
        return len(raw)
    if isinstance(raw, list):
        return len(raw)
    return 0


def collect_online_zero_machines(
    machines: object,
    offerable_count: int,
) -> list[dict[str, Any]]:
    """Online machines with a known empty worker list while offerable_count > 0."""
    try:
        offerable = int(offerable_count)
    except (TypeError, ValueError):
        offerable = 0
    if offerable < 1 or not isinstance(machines, dict):
        return []
    out: list[dict[str, Any]] = []
    for mid, ent in sorted(machines.items(), key=lambda kv: str(kv[0]).lower()):
        if not isinstance(ent, dict):
            continue
        if not ent.get("online"):
            continue
        count = _worker_count(ent)
        if count is None or count > 0:
            continue
        mid_s = str(mid)
        out.append(
            {
                "machine": mid_s,
                "workers": 0,
                "offerable_count": offerable,
                "fingerprint": fingerprint_for(mid_s),
                "rule": "online_zero_workers",
            }
        )
    return out


def _offerable_from_doc(doc: dict | None) -> int:
    if not isinstance(doc, dict):
        return 0
    queue = doc.get("queue")
    if isinstance(queue, dict) and queue.get("offerable_count") is not None:
        try:
            return int(queue.get("offerable_count") or 0)
        except (TypeError, ValueError):
            return 0
    if doc.get("offerable_count") is not None:
        try:
            return int(doc.get("offerable_count") or 0)
        except (TypeError, ValueError):
            return 0
    return 0


def _load_json(path: Path):
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _payload(
    *,
    ok: bool,
    findings: list[str],
    empty: list[dict[str, Any]],
    offerable: int,
    source: str,
    notes: list[str] | None = None,
    extra: dict | None = None,
) -> dict[str, Any]:
    fps = [str(r.get("fingerprint") or "") for r in empty if r.get("fingerprint")]
    body: dict[str, Any] = {
        "ok": ok,
        "findings": findings,
        "machines": empty,
        "machine_ids": [str(r.get("machine") or "") for r in empty],
        "offerable_count": int(offerable),
        "fingerprints": fps,
        "remediation": REMEDIATION if empty else "",
        "source": source,
        "notes": list(notes or []),
    }
    if extra:
        body.update(extra)
    return body


def _check_live_report(chair: Path, digest: Path, qpath: Path):
    import _common as common

    findings: list[str] = []
    notes: list[str] = []
    doc = common.fetch_live_report()
    overlay = common.non_chair_overlay(
        chair,
        digest,
        require_missing_queue=True,
        report=doc,
        fetch=False,
    )
    url = common.live_report_url()
    if doc is None or overlay is None:
        findings.append("local queue missing; live report unavailable/stale/incomplete")
        return (
            _payload(
                ok=False,
                findings=findings,
                empty=[],
                offerable=0,
                source="live_report",
                notes=notes,
                extra={"live_report_url": url, "queue_path": str(qpath)},
            ),
            EXIT_FINDING,
        )
    if doc.get("stale") is True or not isinstance(doc.get("machines"), dict):
        findings.append("local queue missing; live report unavailable/stale/incomplete")
        return (
            _payload(
                ok=False,
                findings=findings,
                empty=[],
                offerable=0,
                source="live_report",
                notes=notes,
                extra={"live_report_url": url, "queue_path": str(qpath)},
            ),
            EXIT_FINDING,
        )
    offerable = _offerable_from_doc(doc)
    empty = collect_online_zero_machines(doc.get("machines"), offerable)
    for row in empty:
        mid = row["machine"]
        findings.append(
            f"online_zero_workers machine={mid} offerable={offerable} "
            f"fingerprint={row['fingerprint']}"
        )
    if not empty and offerable < 1:
        notes.append("offerable_count=0; no online_zero_workers escalate")
    ok = not findings
    payload = _payload(
        ok=ok,
        findings=findings,
        empty=empty,
        offerable=offerable,
        source="live_report",
        notes=notes,
        extra={"live_report_url": url, "queue_path": str(qpath)},
    )
    if isinstance(overlay, dict):
        payload.update(overlay)
    return (payload, EXIT_OK if ok else EXIT_FINDING)


def check(args):
    chair, digest = resolve_homes(args)
    qpath = resolve_queue_path(chair, digest)
    if not qpath.is_file():
        return _check_live_report(chair, digest, qpath)

    findings: list[str] = []
    notes: list[str] = []
    dig = _load_json(digest / "digest.json") or {}
    if not isinstance(dig, dict):
        dig = {}
    offerable = _offerable_from_doc(dig)
    machines = dig.get("machines") if isinstance(dig.get("machines"), dict) else {}
    empty = collect_online_zero_machines(machines, offerable)
    for row in empty:
        mid = row["machine"]
        findings.append(
            f"online_zero_workers machine={mid} offerable={offerable} "
            f"fingerprint={row['fingerprint']}"
        )
    if not empty and offerable < 1:
        notes.append("offerable_count=0; no online_zero_workers escalate")
    ok = not findings
    return (
        _payload(
            ok=ok,
            findings=findings,
            empty=empty,
            offerable=offerable,
            source="local_digest",
            notes=notes,
            extra={
                "digest_path": str(digest / "digest.json"),
                "queue_path": str(qpath),
            },
        ),
        EXIT_OK if ok else EXIT_FINDING,
    )


def main(argv=None) -> int:
    return run_check(
        "online_zero_workers",
        "Online machines with zero workers while offerable_count>0 (exit 0/1/2)",
        check,
        argv,
    )


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())

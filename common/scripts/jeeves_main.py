"""FR #1993: jeeves.exe entry — chair + BobCallback one process.

Modes:
  --self-test   offline/live checks, exit 0/1/2, optional JSON (WP2: --check)
  --heal        deterministic allowlist repairs (WP2: --dry-run / --force-orphan-busy;
                FR #2412: if still failing, start one rate-limited maintenance agent)
  --http-only   BobCallback listener (in-process path for cutover tests)
  --chair --http HOST:PORT  enable in-proc locks, start HTTP thread, then irc_agent --chair

PyInstaller pack (WP3) freezes this module as jeeves.exe.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any


SELF_TEST_CHECKS = ("imports", "locks", "http", "queue", "health", "offer")
DEFAULT_SELF_TEST = ("imports", "locks", "http", "queue", "offer")


def _print_json(payload: dict) -> None:
    print(json.dumps(payload, separators=(",", ":"), sort_keys=True), flush=True)


def monitor_tools_dir() -> Path | None:
    """Locate jeeves/tools/monitor (repo tree or composed install)."""
    here = Path(__file__).resolve().parent
    candidates = [
        here.parents[1] / "jeeves" / "tools" / "monitor",  # repo: common/scripts -> root/jeeves/...
        here.parent / "tools" / "monitor",  # install: <root>/scripts + <root>/tools
        here.parents[1] / "tools" / "monitor",
        Path(os.environ.get("JEEVES_INSTALL_ROOT") or "") / "tools" / "monitor",
    ]
    for cand in candidates:
        if cand.is_dir() and (cand / "health.py").is_file():
            return cand
    return None


def run_monitor_check(
    name: str,
    *,
    chair_home: Path,
    digest_home: Path,
    dry_run: bool = False,
) -> tuple[dict[str, Any], int]:
    """Import a monitor/*.py check as a library and run it (FR #1993 WP2)."""
    root = monitor_tools_dir()
    if root is None:
        return ({"ok": False, "error": "monitor_tools_missing", "findings": ["monitor tools dir missing"]}, 2)
    path_s = str(root)
    if path_s not in sys.path:
        sys.path.insert(0, path_s)
    try:
        mod = __import__(name)
    except Exception as exc:  # noqa: BLE001
        return (
            {
                "ok": False,
                "error": f"import:{type(exc).__name__}",
                "findings": [f"import {name}: {exc}"],
            },
            2,
        )
    args = SimpleNamespace(
        dry_run=dry_run,
        chair_home=str(chair_home),
        digest_home=str(digest_home),
    )
    if dry_run:
        return ({"ok": True, "dry_run": True, "check": name, "findings": []}, 0)
    try:
        payload, code = mod.check(args)
        if isinstance(payload, dict):
            payload.setdefault("check", name)
        return payload, int(code)
    except Exception as exc:  # noqa: BLE001
        return (
            {
                "ok": False,
                "check": name,
                "error": f"{type(exc).__name__}: {exc}",
                "findings": [str(exc)],
            },
            2,
        )


def _check_imports() -> tuple[dict[str, Any], list[str], list[str]]:
    findings: list[str] = []
    errors: list[str] = []
    for mod in ("bobcallback", "gitclaim", "bobreport", "jeeves_locks", "irc_agent", "focus_ignore"):
        try:
            __import__(mod)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"import:{mod}:{type(exc).__name__}")
    return {"ok": not errors}, findings, errors


def _check_locks(home: Path) -> tuple[dict[str, Any], list[str], list[str]]:
    findings: list[str] = []
    errors: list[str] = []
    detail: dict[str, Any] = {"home": str(home)}
    try:
        home.mkdir(parents=True, exist_ok=True)
        probe = home / f".jeeves-self-test.{os.getpid()}"
        probe.write_text("ok\n", encoding="utf-8")
        probe.unlink(missing_ok=True)
    except OSError as exc:
        errors.append(f"home_unwritable:{exc}")
    try:
        import jeeves_locks

        name = jeeves_locks.mutex_name_for_home(home)
        detail["mutex"] = name
        if "BobiverseJeeves-" not in name:
            findings.append("mutex_name_shape")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"mutex:{type(exc).__name__}")
    # Report disk git-claim.lock age (do not break in self-test).
    try:
        import gitclaim

        lock = home / gitclaim.LOCK_NAME
        if lock.is_file():
            age = time.time() - lock.stat().st_mtime
            detail["git_claim_lock_age_s"] = round(age, 1)
            thresh = max(30.0, float(getattr(gitclaim, "LOCK_WAIT_S", 30.0)))
            if age > thresh:
                findings.append(f"git-claim.lock stale age_s={int(age)}")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"lock_probe:{type(exc).__name__}")
    detail["ok"] = not errors and not findings
    return detail, findings, errors


def _check_http(host: str = "127.0.0.1", port: int = 7700) -> tuple[dict[str, Any], list[str], list[str]]:
    findings: list[str] = []
    errors: list[str] = []
    listening = False
    try:
        with socket.create_connection((host, port), timeout=1.0):
            listening = True
    except OSError:
        listening = False
    detail: dict[str, Any] = {"host": host, "port": port, "listening": listening}
    if not listening:
        findings.append(f"no LISTEN {host}:{port}")
    detail["ok"] = listening
    return detail, findings, errors


def _check_queue(home: Path, chair_home: Path | None) -> tuple[dict[str, Any], list[str], list[str]]:
    findings: list[str] = []
    errors: list[str] = []
    paths = []
    for root in (chair_home, home):
        if root is None:
            continue
        p = Path(root) / "queue.json"
        if p.is_file():
            paths.append(p)
            break
    detail: dict[str, Any] = {"path": str(paths[0]) if paths else ""}
    if not paths:
        detail["ok"] = True
        detail["missing"] = True
        return detail, findings, errors
    try:
        doc = json.loads(paths[0].read_text(encoding="utf-8-sig"))
        unacc = doc.get("unaccepted") if isinstance(doc, dict) else None
        n = len(unacc) if isinstance(unacc, list) else 0
        detail["unaccepted"] = n
        detail["ok"] = True
    except Exception as exc:  # noqa: BLE001
        errors.append(f"queue_parse:{type(exc).__name__}")
        detail["ok"] = False
    return detail, findings, errors


def _check_offer(home: Path, chair_home: Path | None) -> tuple[dict[str, Any], list[str], list[str]]:
    findings: list[str] = []
    errors: list[str] = []
    try:
        import gitclaim

        root = Path(chair_home) if chair_home and (Path(chair_home) / "queue.json").is_file() else home
        stats = gitclaim.summarize_empty_offer(root, "")
        detail = dict(stats)
        detail["ok"] = True
        # Finding when queue has rows but zero offerable under focus (operator confusion).
        # FR #2526: if every unaccepted row is require_machine-gated (and none out-of-focus),
        # keep as note only — intentional pins must not exit 1 / spawn maintenance.
        if int(stats.get("unaccepted") or 0) > 0 and int(stats.get("offerable") or 0) == 0:
            msg = (
                "0 offerable for you under focus "
                f"({stats.get('unaccepted')} unaccepted, "
                f"{stats.get('out_of_focus')} out-of-focus, "
                f"{stats.get('require_machine')} require_machine)"
            )
            unacc = int(stats.get("unaccepted") or 0)
            req = int(stats.get("require_machine") or 0)
            oof = int(stats.get("out_of_focus") or 0)
            if req >= unacc and oof == 0:
                detail["offer_note_only"] = True
                detail["offer_note"] = msg
            else:
                findings.append(msg)
                detail["ok"] = False
        return detail, findings, errors
    except Exception as exc:  # noqa: BLE001
        errors.append(f"offer:{type(exc).__name__}")
        return {"ok": False}, findings, errors


def run_self_test(
    *,
    home: Path,
    as_json: bool,
    checks: list[str] | None = None,
    chair_home: Path | None = None,
) -> int:
    """Token-free self-test. 0=ok 1=finding 2=error. WP2 wires monitor libs + --check."""
    wanted = list(checks) if checks else list(DEFAULT_SELF_TEST)
    wanted = [c.strip().lower() for c in wanted if c and c.strip()]
    for c in wanted:
        if c not in SELF_TEST_CHECKS:
            payload = {
                "ok": False,
                "exit": 2,
                "fr": 1993,
                "wp": 2,
                "errors": [f"unknown_check:{c}"],
                "findings": [],
                "checks": {},
                "home": str(home),
            }
            if as_json:
                _print_json(payload)
            else:
                print(f"ERROR unknown_check:{c}", flush=True)
            return 2

    findings: list[str] = []
    errors: list[str] = []
    check_payloads: dict[str, Any] = {}
    chair = Path(chair_home) if chair_home else home

    runners = {
        "imports": lambda: _check_imports(),
        "locks": lambda: _check_locks(home),
        "http": lambda: _check_http(),
        "queue": lambda: _check_queue(home, chair),
        "offer": lambda: _check_offer(home, chair),
    }

    for name in wanted:
        if name == "health":
            payload, code = run_monitor_check(
                "health",
                chair_home=chair,
                digest_home=home,
                dry_run=False,
            )
            check_payloads[name] = payload
            if code == 2:
                errors.extend(payload.get("findings") or [payload.get("error") or "health_error"])
            elif code == 1:
                findings.extend(payload.get("findings") or ["health_finding"])
            continue
        detail, fnd, err = runners[name]()
        check_payloads[name] = detail
        findings.extend(fnd)
        errors.extend(err)

    exit_code = 2 if errors else (1 if findings else 0)
    payload = {
        "ok": exit_code == 0,
        "exit": exit_code,
        "home": str(home),
        "chair_home": str(chair),
        "findings": findings,
        "errors": errors,
        "checks": check_payloads,
        "fr": 1993,
        "wp": 2,
    }
    if as_json:
        _print_json(payload)
    else:
        print(
            f"INFO self-test exit={exit_code} findings={len(findings)} errors={len(errors)}",
            flush=True,
        )
        for e in errors:
            print(f"ERROR {e}", flush=True)
        for f in findings:
            print(f"FINDING {f}", flush=True)
    return int(exit_code)


def _gitclaim_lock_stale(home: Path) -> tuple[Path | None, float]:
    try:
        import gitclaim

        path = home / gitclaim.LOCK_NAME
        if not path.is_file():
            return None, 0.0
        age = time.time() - path.stat().st_mtime
        thresh = max(30.0, float(getattr(gitclaim, "LOCK_WAIT_S", 30.0)))
        if age > thresh:
            return path, age
        return path, age  # present but fresh — caller checks age
    except Exception:
        return None, 0.0


def run_heal(
    *,
    home: Path,
    dry_run: bool,
    force_orphan_busy: bool,
    as_json: bool,
    chair_home: Path | None = None,
    no_maintenance_agent: bool = False,
) -> int:
    """Deterministic heal allowlist (FR #1993 WP2). Never touches BobIrcd/Ergo.

    FR #2412: when exit != 0 after heal, start ONE rate-limited maintenance agent
    in ``<drive>:\\ai\\jeeves`` (unless ``--no-maintenance-agent`` / dry-run skip path).
    """
    actions: list[str] = []
    notes: list[str] = []
    findings: list[str] = []
    errors: list[str] = []
    chair = Path(chair_home) if chair_home else home

    # 1) stale git-claim.lock
    try:
        import gitclaim

        lock = home / gitclaim.LOCK_NAME
        if lock.is_file():
            age = time.time() - lock.stat().st_mtime
            thresh = max(30.0, float(getattr(gitclaim, "LOCK_WAIT_S", 30.0)))
            if age > thresh:
                msg = f"break git-claim.lock age_s={int(age)}"
                if dry_run:
                    actions.append(f"dry-run:{msg}")
                else:
                    try:
                        lock.unlink()
                        actions.append(f"broke:{msg}")
                    except OSError as exc:
                        errors.append(f"git-claim.lock:{type(exc).__name__}")
            else:
                notes.append(f"git-claim.lock fresh age_s={int(age)}")
        else:
            notes.append("git-claim.lock absent")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"gitclaim_heal:{type(exc).__name__}")

    # 2) digest.lock via bobreport (foreign/stale only)
    try:
        import bobreport

        if dry_run:
            actions.append("dry-run:break_stale_digest_lock")
        else:
            broken = bobreport.break_stale_digest_lock(home)
            if broken:
                actions.append(f"broke:digest.lock reason={broken.get('reason')}")
            else:
                notes.append("digest.lock ok_or_absent")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"digest_heal:{type(exc).__name__}")

    # 3) http listen — report only (in-process rebind needs running service loop; WP2 foundation)
    try:
        _detail, fnd, _err = _check_http()
        if fnd:
            findings.extend(fnd)
            notes.append("http: report only (restart HTTP thread when running as service)")
        else:
            notes.append("http:7700 listening")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"http_probe:{type(exc).__name__}")

    # 4) monitor health as report
    try:
        payload, code = run_monitor_check(
            "health",
            chair_home=chair,
            digest_home=home,
            dry_run=False,
        )
        if code != 0:
            findings.extend(payload.get("findings") or [f"health exit={code}"])
            notes.append("health: report only (never restart BobIrcd)")
        else:
            notes.append("health: ok")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"health:{type(exc).__name__}")

    # 5) stuck_accepted / seats_stuck_doing — report only unless force_orphan_busy + empty accepted
    try:
        import gitclaim

        qpath = None
        for root in (chair, home):
            cand = Path(root) / "queue.json"
            if cand.is_file():
                qpath = cand
                break
        accepted_n = 0
        if qpath:
            doc = json.loads(qpath.read_text(encoding="utf-8-sig"))
            acc = doc.get("accepted") if isinstance(doc, dict) else None
            if isinstance(acc, dict):
                accepted_n = len(acc)
            elif isinstance(acc, list):
                accepted_n = len(acc)
        if force_orphan_busy:
            if accepted_n > 0:
                notes.append(
                    f"skip force-orphan-busy: accepted={accepted_n} (keep seats busy; clear only when accepted empty)"
                )
            else:
                msg = "force-orphan-busy: accepted empty — report seats_stuck_doing only in WP2 (no clear_seat_doing default)"
                if dry_run:
                    actions.append(f"dry-run:{msg}")
                else:
                    # WP2: still report-only for digest doing; MSI/service loop (WP3) owns live clear.
                    actions.append(msg)
                    sa, sc = run_monitor_check(
                        "seats_stuck_doing",
                        chair_home=chair,
                        digest_home=home,
                        dry_run=False,
                    )
                    if sc != 0:
                        findings.extend(sa.get("findings") or [])
        else:
            notes.append("seats_stuck_doing: report only (pass --force-orphan-busy when accepted empty)")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"orphan:{type(exc).__name__}")

    # 6) offer / focus empty clarity (report)
    try:
        detail, fnd, err = _check_offer(home, chair)
        findings.extend(fnd)
        errors.extend(err)
        if detail:
            notes.append(
                "offer "
                f"unaccepted={detail.get('unaccepted')} "
                f"offerable={detail.get('offerable')} "
                f"out_of_focus={detail.get('out_of_focus')} "
                f"require_machine={detail.get('require_machine')}"
            )
            if detail.get("offer_note"):
                notes.append(str(detail.get("offer_note")))
    except Exception as exc:  # noqa: BLE001
        errors.append(f"offer:{type(exc).__name__}")

    exit_code = 2 if errors else (1 if findings else 0)
    maintenance: dict[str, Any] = {"action": "skip", "reason": "not_attempted"}
    if no_maintenance_agent:
        maintenance = {"action": "skip", "reason": "no_maintenance_agent_flag"}
        notes.append("maintenance: skipped (--no-maintenance-agent)")
    else:
        try:
            import jeeves_maintenance

            mr = jeeves_maintenance.try_start_maintenance_agent(
                home=home,
                heal_exit=int(exit_code),
                heal_payload={
                    "findings": findings,
                    "errors": errors,
                    "actions": actions,
                },
                dry_run=bool(dry_run),
            )
            maintenance = {
                "action": mr.action,
                "reason": mr.reason,
                "cwd": mr.cwd,
                "pid": mr.pid,
                "log": mr.log_line,
            }
            notes.append(f"maintenance: {mr.action} {mr.reason}")
            if mr.action == "spawn":
                actions.append(f"maintenance-agent pid={mr.pid} cwd={mr.cwd}")
        except Exception as exc:  # noqa: BLE001 — heal must still return its exit
            maintenance = {"action": "skip", "reason": f"hook_error:{type(exc).__name__}"}
            notes.append(f"maintenance: hook_error:{type(exc).__name__}")

    payload = {
        "ok": exit_code == 0,
        "exit": exit_code,
        "dry_run": bool(dry_run),
        "force_orphan_busy": bool(force_orphan_busy),
        "actions": actions,
        "notes": notes,
        "findings": findings,
        "errors": errors,
        "home": str(home),
        "maintenance": maintenance,
        "fr": 1993,
        "wp": 2,
        "fr_maintenance": 2412,
    }
    if as_json:
        _print_json(payload)
    else:
        print(
            f"INFO heal exit={exit_code} actions={len(actions)} findings={len(findings)} errors={len(errors)} dry_run={int(dry_run)}",
            flush=True,
        )
        for a in actions:
            print(f"ACTION {a}", flush=True)
        for n in notes:
            print(f"NOTE {n}", flush=True)
        for e in errors:
            print(f"ERROR {e}", flush=True)
        for f in findings:
            print(f"FINDING {f}", flush=True)
        print(
            f"INFO maintenance action={maintenance.get('action')} reason={maintenance.get('reason')}",
            flush=True,
        )
    return int(exit_code)


def start_http_thread(
    home: Path,
    *,
    host: str,
    port: int,
    briefer_nick: str = "Jeeves",
) -> tuple[threading.Thread, object]:
    """Bind bobcallback and serve_forever on a daemon thread. Returns (thread, httpd)."""
    import bobcallback

    bobcallback.assert_home_usable(home)
    httpd = bobcallback.serve(home, host=host, port=port, briefer_nick=briefer_nick)
    t = threading.Thread(
        target=httpd.serve_forever,
        name="jeeves-http",
        daemon=True,
    )
    t.start()
    # Brief settle for bind
    time.sleep(0.05)
    return t, httpd



def is_ephemeral_pytest_home(path: str | Path | None) -> bool:
    """True for pytest temp homes that must not override live digest/chair (FR #2526)."""
    s = str(path or "").replace("\\", "/").lower()
    if not s:
        return False
    return ("pytest-of-" in s) or ("/pytest-current" in s) or s.rstrip("/").endswith("pytest-current")


def resolve_digest_home(*, digest_home_arg: str = "", home_arg: str = "", env: dict | None = None) -> Path:
    """Resolve digest home; refuse ephemeral pytest BOB_DIGEST_HOME (FR #2526)."""
    e = os.environ if env is None else env
    candidates = [
        (digest_home_arg or "").strip(),
        (e.get("BOB_DIGEST_HOME") or "").strip(),
        (home_arg or "").strip(),
    ]
    for c in candidates:
        if c and not is_ephemeral_pytest_home(c):
            return Path(c).expanduser()
    prof = e.get("USERPROFILE") or e.get("HOME") or "."
    return Path(prof).expanduser() / ".bobiverse"


def parse_http_bind(raw: str) -> tuple[str, int]:
    text = (raw or "").strip()
    if not text:
        return "127.0.0.1", 7700
    if ":" in text:
        host, _, port_s = text.rpartition(":")
        return (host or "127.0.0.1"), int(port_s)
    return "127.0.0.1", int(text)


def main(argv: list[str] | None = None) -> int:
    try:
        import crash_report

        crash_report.install("jeeves")
    except Exception:
        pass
    argv = list(sys.argv[1:] if argv is None else argv)
    p = argparse.ArgumentParser(description="jeeves.exe foundation (FR #1993)")
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--heal", action="store_true", help="WP2: deterministic allowlist heal")
    p.add_argument("--dry-run", action="store_true", help="with --heal: report actions only")
    p.add_argument(
        "--no-maintenance-agent",
        action="store_true",
        help="with --heal: do not spawn FR #2412 maintenance agent when still failing",
    )
    p.add_argument(
        "--force-orphan-busy",
        action="store_true",
        help="with --heal: allow orphan busy remediation when accepted empty",
    )
    p.add_argument(
        "--check",
        action="append",
        default=[],
        help="with --self-test: locks|http|queue|imports|health|offer (repeatable)",
    )
    p.add_argument("--json", action="store_true", help="with --self-test/--heal, one JSON line")
    p.add_argument("--http-only", action="store_true", help="BobCallback listener only")
    p.add_argument("--chair", action="store_true", help="run irc_agent --chair after HTTP")
    p.add_argument(
        "--http",
        default="",
        help="with --chair: HOST:PORT for in-process BobCallback (e.g. 127.0.0.1:7700)",
    )
    p.add_argument("--home", default="", help="chair home (BOB_HOME)")
    p.add_argument("--digest-home", default="", help="digest home (BOB_DIGEST_HOME)")
    p.add_argument("--bind", default="127.0.0.1")
    p.add_argument("--port", type=int, default=7700)
    p.add_argument("--nick", default="Jeeves")
    args, unknown = p.parse_known_args(argv)

    home = resolve_digest_home(digest_home_arg=args.digest_home or "", home_arg=args.home or "")
    chair_home = Path(args.home).expanduser() if args.home else None
    if chair_home and is_ephemeral_pytest_home(chair_home):
        chair_home = None

    if args.self_test:
        checks = args.check or None
        if checks:
            # allow comma-separated
            expanded: list[str] = []
            for item in checks:
                expanded.extend([x.strip() for x in str(item).split(",") if x.strip()])
            checks = expanded
        return run_self_test(
            home=home,
            as_json=bool(args.json),
            checks=checks,
            chair_home=chair_home,
        )

    if args.heal:
        return run_heal(
            home=home,
            dry_run=bool(args.dry_run),
            force_orphan_busy=bool(args.force_orphan_busy),
            as_json=bool(args.json),
            chair_home=chair_home,
            no_maintenance_agent=bool(args.no_maintenance_agent),
        )

    import jeeves_locks

    jeeves_locks.enable_inproc_locks()
    # Wire gitclaim in-proc path
    import gitclaim  # noqa: F401 — import after enable so _lock sees RLock

    if not jeeves_locks.try_acquire_instance_mutex(home):
        _print_json({"ok": False, "err": "already_running", "fr": 1993})
        return 2

    try:
        if args.http_only or (args.chair and args.http):
            host, port = (args.bind, int(args.port))
            if args.http:
                host, port = parse_http_bind(args.http)
            try:
                _t, httpd = start_http_thread(home, host=host, port=port, briefer_nick=args.nick)
            except OSError as exc:
                print(f"ERROR http bind failed {host}:{port} err={exc}", flush=True)
                return 1
            addr = httpd.server_address[:2]
            print(f"INFO jeeves http listen {addr[0]}:{addr[1]} inproc=1 fr=1993", flush=True)

            if args.http_only and not args.chair:
                try:
                    while True:
                        time.sleep(3600)
                except KeyboardInterrupt:
                    return 0

            if args.chair:
                # Delegate remaining argv to irc_agent --chair (unknown flags preserved).
                os.environ["BOB_DIGEST_HOME"] = str(home)
                if args.home:
                    os.environ["BOB_HOME"] = str(Path(args.home).expanduser())
                chair_argv = [
                    "--chair",
                    "--nick",
                    args.nick,
                    "--home",
                    str(Path(args.home).expanduser() if args.home else home),
                ] + list(unknown)
                import irc_agent

                # irc_agent.main parses sys.argv — temporarily replace.
                old = sys.argv
                try:
                    sys.argv = ["irc_agent"] + chair_argv
                    irc_agent.main()
                finally:
                    sys.argv = old
                return 0

        p.error("specify --self-test, --heal, --http-only, or --chair --http HOST:PORT")
        return 2
    finally:
        jeeves_locks.release_instance_mutex()


if __name__ == "__main__":
    raise SystemExit(main())

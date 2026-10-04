"""FR #1993: jeeves.exe entry — chair + BobCallback one process (foundation).

Modes:
  --self-test   offline checks, exit 0/1/2, optional JSON
  --http-only   BobCallback listener (in-process path for cutover tests)
  --chair --http HOST:PORT  enable in-proc locks, start HTTP thread, then irc_agent --chair

PyInstaller pack (WP3) freezes this module as jeeves.exe.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from pathlib import Path


def _print_json(payload: dict) -> None:
    print(json.dumps(payload, separators=(",", ":"), sort_keys=True), flush=True)


def run_self_test(*, home: Path, as_json: bool) -> int:
    """Token-free offline subset. 0=ok 1=finding 2=error."""
    findings: list[str] = []
    errors: list[str] = []
    try:
        home.mkdir(parents=True, exist_ok=True)
        probe = home / f".jeeves-self-test.{os.getpid()}"
        probe.write_text("ok\n", encoding="utf-8")
        probe.unlink(missing_ok=True)
    except OSError as exc:
        errors.append(f"home_unwritable:{exc}")
    # Import graph for freeze smoke
    for mod in ("bobcallback", "gitclaim", "bobreport", "jeeves_locks", "irc_agent"):
        try:
            __import__(mod)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"import:{mod}:{type(exc).__name__}")
    try:
        import jeeves_locks

        name = jeeves_locks.mutex_name_for_home(home)
        if "BobiverseJeeves-" not in name:
            findings.append("mutex_name_shape")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"mutex:{type(exc).__name__}")
    payload = {
        "ok": not errors and not findings,
        "exit": 2 if errors else (1 if findings else 0),
        "home": str(home),
        "findings": findings,
        "errors": errors,
        "fr": 1993,
    }
    if as_json:
        _print_json(payload)
    else:
        print(
            f"INFO self-test exit={payload['exit']} findings={len(findings)} errors={len(errors)}",
            flush=True,
        )
        for e in errors:
            print(f"ERROR {e}", flush=True)
        for f in findings:
            print(f"FINDING {f}", flush=True)
    return int(payload["exit"])


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


def parse_http_bind(raw: str) -> tuple[str, int]:
    text = (raw or "").strip()
    if not text:
        return "127.0.0.1", 7700
    if ":" in text:
        host, _, port_s = text.rpartition(":")
        return (host or "127.0.0.1"), int(port_s)
    return "127.0.0.1", int(text)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    p = argparse.ArgumentParser(description="jeeves.exe foundation (FR #1993)")
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--json", action="store_true", help="with --self-test, one JSON line")
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

    digest = (args.digest_home or os.environ.get("BOB_DIGEST_HOME") or args.home or "").strip()
    if not digest:
        prof = os.environ.get("USERPROFILE") or os.environ.get("HOME") or "."
        digest = str(Path(prof) / ".bobiverse")
    home = Path(digest).expanduser()

    if args.self_test:
        return run_self_test(home=home, as_json=bool(args.json))

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

        p.error("specify --self-test, --http-only, or --chair --http HOST:PORT")
        return 2
    finally:
        jeeves_locks.release_instance_mutex()


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""FR #6066: wake named Grok Bot Bob (SendGrokBotUserMessage). Not chair assign."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

from _common import EXIT_ERROR, EXIT_FINDING, EXIT_OK, emit
from wake_brief import WakeBriefError, build_wake_brief

# Wake work is pinned to Bob's Grok Bot desktop, not ionos (detection-only).
REQUIRE_MACHINE_KEY = "require_machine"
WAKE_MACHINE_ENV = "BOB_GROK_BOT_WAKE_MACHINE"

_TOKEN_RE = re.compile(r"(?i)(token|bearer|sandbox[_-]?key|api[_-]?key)\s*[:=]\s*\S+")
_SANDBOX_RE = re.compile(r"https?://[^\s]*sandbox[^\s]*", re.I)
_SAND_SECRETS_RE = re.compile(r"(?i)sand-secrets\.json")


def redact_wake_log(text: str) -> str:
    s = str(text or "")
    s = _SANDBOX_RE.sub("https://***", s)
    s = _TOKEN_RE.sub(r"\1=***", s)
    s = _SAND_SECRETS_RE.sub("***", s)
    return s


def ticket_id(item: dict[str, Any]) -> tuple[str, str]:
    repo = str(item.get("repo") or "").strip()
    num = str(item.get("number") or "").strip()
    return repo, num


def complete_ticket(item: dict[str, Any]) -> bool:
    try:
        build_wake_brief(item)
        return True
    except WakeBriefError:
        return False


def brief_text(item: dict[str, Any]) -> str:
    return build_wake_brief(item)


def grokbot_api_path() -> Path | None:
    env = (os.environ.get("GROK_BOT_API") or os.environ.get("BOB_GROK_BOT_API") or "").strip()
    if env:
        p = Path(env)
        return p if p.is_file() else None
    here = Path(__file__).resolve()
    for cand in (
        here.parents[2] / "tray" / "tools" / "GrokBotApi.py",
        here.parents[3] / "bob" / "tray" / "tools" / "GrokBotApi.py",
    ):
        if cand.is_file():
            return cand
    return None


def _default_send(*, agent: str, text: str) -> dict[str, Any]:
    script = grokbot_api_path()
    if script is None:
        raise FileNotFoundError("GrokBotApi.py missing (set GROK_BOT_API)")
    r = subprocess.run(
        [sys.executable, str(script), "send", "--agent", agent, "--text", text],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if r.returncode != 0:
        raise ConnectionError(redact_wake_log((r.stderr or r.stdout or "send failed")[:240]))
    return {"ok": True}


def wake_bob(
    item: dict[str, Any],
    *,
    send: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    try:
        text = brief_text(item)
    except WakeBriefError:
        return {
            "ok": False,
            "woke": False,
            "error": "invalid_ticket",
            "detail": "need owner/repo and issue/PR number",
            "brief": "",
        }
    sender = send or _default_send
    try:
        sender(agent="Bob", text=text)
    except Exception as e:  # noqa: BLE001
        return {
            "ok": False,
            "woke": False,
            "error": "bob_unreachable",
            "detail": redact_wake_log(str(e))[:160],
            "brief": text,
        }
    return {"ok": True, "woke": True, "brief": text, "agent": "Bob"}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="FR #6066 wake Grok Bot Bob")
    p.add_argument("--repo", default="")
    p.add_argument("--number", default="")
    p.add_argument("--event", default="closed")
    p.add_argument("--kind", default="issue")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)
    item = {
        "repo": args.repo,
        "number": args.number,
        "event": args.event,
        "kind": args.kind,
    }
    if not complete_ticket(item):
        return emit(
            {
                "check": "wake_grok_bot_bob",
                "ok": False,
                "woke": False,
                "error": "invalid_ticket",
                "detail": "need owner/repo and issue/PR number",
                "brief": "",
                REQUIRE_MACHINE_KEY: (os.environ.get(WAKE_MACHINE_ENV) or "UNKNOWN").strip(),
            },
            EXIT_ERROR,
        )
    if args.dry_run:
        return emit(
            {
                "check": "wake_grok_bot_bob",
                "ok": True,
                "dry_run": True,
                "brief": brief_text(item),
                REQUIRE_MACHINE_KEY: (os.environ.get(WAKE_MACHINE_ENV) or "UNKNOWN").strip(),
            },
            EXIT_OK,
        )
    out = wake_bob(item)
    out["check"] = "wake_grok_bot_bob"
    out[REQUIRE_MACHINE_KEY] = (os.environ.get(WAKE_MACHINE_ENV) or "UNKNOWN").strip()
    code = EXIT_OK if out.get("ok") else EXIT_FINDING
    if out.get("error") and "missing" in str(out.get("detail") or "").lower():
        code = EXIT_ERROR
    return emit(out, code)


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())

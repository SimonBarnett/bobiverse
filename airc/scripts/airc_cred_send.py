"""FR #5825: console-side CRED persist via=irc sender (seal + send).

Operator / Bob ear helper. Never accepts a password on the argv. Sources:
  - CredMan (``read_generic_credential``)
  - in-memory pass-in (callers / tests only)
  - one-line password on stdin when ``--stdin-password`` (with ``--username``)

Wire:
  1) CRED persist target=<t> via=irc  -> CRED-HELLO ...
  2) CRED-SEAL token= seq=i/N ct=...  -> cred-persisted | named error

Secrets never appear in returned result dicts, logs, or raised messages.
"""
from __future__ import annotations

import argparse
import os
import re
import secrets
import sys
import time
from typing import Any, Callable

import airc_cred_irc as circ

_HELLO_RE = re.compile(
    r"CRED-HELLO\s+token=(\S+)\s+pub=(\S+)\s+exp=(\d+)\s+alg=(\S+)\s+target=(\S+)",
    re.IGNORECASE,
)
_RESULT_RE = re.compile(
    r"\b(cred-persisted|cred-rejected-auth|cred-expired|cred-replay|"
    r"cred-target-not-allowlisted|cred-bad-payload|cred-write-failed:\S+|"
    r"cred-chunk-ok|cred-failed:\S+|cred-url-rejected)\b",
    re.IGNORECASE,
)


TransportFn = Callable[[str], str]


def new_job_id() -> str:
    return secrets.token_hex(4)


def parse_cred_hello(text: str) -> dict[str, Any] | None:
    """Extract CRED-HELLO fields from a multi-line IRC reply blob."""
    m = _HELLO_RE.search(text or "")
    if not m:
        return None
    return {
        "token": m.group(1).lower(),
        "pub": m.group(2),
        "exp": int(m.group(3)),
        "alg": m.group(4),
        "target": m.group(5),
    }


def format_persist_command(*, qid: str, target: str) -> str:
    t = (target or "").strip()
    q = (qid or "").strip().lower()
    if q:
        return f"id={q} CRED persist target={t} via=irc"
    return f"CRED persist target={t} via=irc"


def format_seal_commands(
    *, qid: str, token: str, chunks: list[str]
) -> list[str]:
    q = (qid or "").strip().lower()
    tok = (token or "").strip().lower()
    total = len(chunks)
    out: list[str] = []
    for i, ct in enumerate(chunks, start=1):
        if q:
            out.append(
                f"id={q} CRED-SEAL token={tok} seq={i}/{total} ct={ct}"
            )
        else:
            out.append(f"CRED-SEAL token={tok} seq={i}/{total} ct={ct}")
    return out


def extract_cred_result_code(text: str) -> str | None:
    """Last matching named CRED outcome token in a reply blob."""
    found = None
    for m in _RESULT_RE.finditer(text or ""):
        found = m.group(1)
    return found


def extract_account(text: str) -> str:
    m = re.search(r"\baccount=(\S+)", text or "", re.IGNORECASE)
    return m.group(1) if m else ""


def redact_secret(text: str, password: str) -> str:
    """Best-effort scrub of a known secret from operator-visible text."""
    if not password:
        return text or ""
    return (text or "").replace(password, "***")


def load_credential(
    *,
    credman_source: str = "",
    username: str = "",
    password: str = "",
    reader: Callable[[str], Any] | None = None,
) -> dict[str, str]:
    """Resolve username/password without putting secrets in exceptions.

    Prefer CredMan when ``credman_source`` is set. Pass-in pair is for tests
    and trusted in-process callers only.
    """
    src = (credman_source or "").strip()
    if src:
        read = reader
        if read is None:
            import airc_credman as cm

            read = cm.read_generic_credential
        pair = read(src)
        if pair is None:
            raise RuntimeError("credman-source-missing")
        if hasattr(pair, "username"):
            user = getattr(pair, "username", "")
            pw = getattr(pair, "password", None)
        else:
            user = (pair or {}).get("username")  # type: ignore[union-attr]
            pw = (pair or {}).get("password")  # type: ignore[union-attr]
        if not user or pw is None or pw == "":
            raise RuntimeError("credman-source-incomplete")
        return {"username": str(user), "password": str(pw)}
    user = (username or "").strip()
    if not user or password is None or password == "":
        raise RuntimeError("cred-incomplete")
    return {"username": user, "password": str(password)}


def send_cred_via_irc(
    *,
    target: str,
    username: str,
    password: str,
    transport: TransportFn,
    qid: str | None = None,
    now: Callable[[], float] | None = None,
    seal_fn: Callable[..., list[str]] | None = None,
) -> dict[str, Any]:
    """Run HELLO + SEAL over ``transport``; return one named result (no secret).

    ``transport(cmd)`` sends one console PRIVMSG body and returns the reply
    blob (possibly multi-line out/err/DONE).
    """
    clock = now or time.time
    t = (target or "").strip()
    if not t:
        return {"ok": False, "code": "cred-target-required", "target": "", "account": ""}
    job = (qid or new_job_id()).lower()
    hello_blob = transport(format_persist_command(qid=job, target=t))
    hello_blob = redact_secret(hello_blob, password)
    hello = parse_cred_hello(hello_blob)
    if hello is None:
        code = extract_cred_result_code(hello_blob) or "cred-hello-missing"
        return {"ok": False, "code": code, "target": t, "account": ""}
    if clock() > float(hello["exp"]):
        return {"ok": False, "code": "cred-expired", "target": t, "account": ""}
    sealer = seal_fn or circ.seal_cred_payload
    chunks = sealer(
        pub_b64=hello["pub"],
        token=hello["token"],
        target=hello["target"],
        exp=int(hello["exp"]),
        username=username,
        password=password,
    )
    last_blob = ""
    for cmd in format_seal_commands(qid=job, token=hello["token"], chunks=chunks):
        if clock() > float(hello["exp"]):
            return {"ok": False, "code": "cred-expired", "target": t, "account": ""}
        last_blob = transport(cmd)
        last_blob = redact_secret(last_blob, password)
        code = extract_cred_result_code(last_blob)
        if code == "cred-chunk-ok":
            continue
        if code:
            account = extract_account(last_blob) if code == "cred-persisted" else ""
            return {
                "ok": code == "cred-persisted",
                "code": code,
                "target": t if code == "cred-persisted" else t,
                "account": account,
            }
    code = extract_cred_result_code(last_blob) or "cred-no-result"
    account = extract_account(last_blob) if code == "cred-persisted" else ""
    return {
        "ok": code == "cred-persisted",
        "code": code,
        "target": t,
        "account": account,
    }


def _build_outbox_transport(
    *,
    machine_id: str,
    outbox: str,
    replies_jsonl: str,
    timeout_s: float,
) -> TransportFn:
    """Minimal outbox + airc-replies.jsonl waiter (Bob ear path)."""
    mid = re.sub(r"[^a-z0-9_-]+", "-", (machine_id or "").strip().lower()).strip("-_")
    nick = f"{mid}_console"
    out_path = outbox
    reply_path = replies_jsonl

    def _append(line: str) -> None:
        with open(out_path, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(line if line.endswith("\n") else line + "\n")

    def _wait(qid: str, start_len: int) -> str:
        deadline = time.time() + float(timeout_s)
        bodies: list[str] = []
        while time.time() < deadline:
            if not os.path.isfile(reply_path):
                time.sleep(0.2)
                continue
            try:
                with open(reply_path, "r", encoding="utf-8", errors="replace") as fh:
                    fh.seek(start_len)
                    chunk = fh.read()
            except OSError:
                time.sleep(0.2)
                continue
            for raw in chunk.splitlines():
                line = raw.strip()
                if not line:
                    continue
                # jsonl: {"body":"..."} or plain body
                body = line
                if line.startswith("{"):
                    try:
                        import json

                        obj = json.loads(line)
                        body = str(obj.get("body") or obj.get("text") or "")
                    except Exception:
                        body = line
                if qid and f"id={qid}" not in body and qid not in body:
                    # still collect DONE without id in rare paths
                    if "CRED-HELLO" not in body and "cred-" not in body.lower():
                        continue
                bodies.append(body)
                if "DONE" in body and (
                    "cred-" in body.lower() or "CRED-HELLO" in "\n".join(bodies)
                ):
                    # wait until we have HELLO or a terminal cred code
                    blob = "\n".join(bodies)
                    if parse_cred_hello(blob) or extract_cred_result_code(blob):
                        return blob
            time.sleep(0.2)
        return "\n".join(bodies) if bodies else "cred-timeout"

    def transport(cmd: str) -> str:
        qid_m = re.match(r"(?i)^id=([0-9a-f]{8})\b", (cmd or "").strip())
        qid = qid_m.group(1).lower() if qid_m else ""
        start_len = 0
        if os.path.isfile(reply_path):
            try:
                start_len = os.path.getsize(reply_path)
            except OSError:
                start_len = 0
        _append(f"PRIVMSG {nick} :{cmd}")
        return _wait(qid, start_len)

    return transport


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="FR #5825: CRED persist via=irc sender (never put password on argv)"
    )
    p.add_argument("--machine", required=True, help="target machine id (console nick)")
    p.add_argument("--target", required=True, help="CredMan target name on the remote")
    p.add_argument(
        "--credman-source",
        default="",
        help="local CredMan target to read username/password from",
    )
    p.add_argument("--username", default="", help="with --stdin-password only")
    p.add_argument(
        "--stdin-password",
        action="store_true",
        help="read one password line from stdin (never argv)",
    )
    p.add_argument("--outbox", required=True, help="Bob ear/worker outbox.txt path")
    p.add_argument(
        "--replies",
        default="",
        help="airc-replies.jsonl path (default: beside outbox)",
    )
    p.add_argument("--timeout-s", type=float, default=90.0)
    p.add_argument("--qid", default="")
    # Refuse password-looking argv flags (FR #5659 / #3304).
    check = list(argv) if argv is not None else sys.argv[1:]
    for a in check:
        low = (a or "").lower()
        if low.startswith("--password") or low.startswith("-password"):
            print("err code=usage-secrets-on-argv", file=sys.stderr)
            return 2

    args = p.parse_args(argv)

    password = ""
    username = (args.username or "").strip()
    if args.stdin_password:
        password = sys.stdin.readline().rstrip("\r\n")
    try:
        pair = load_credential(
            credman_source=args.credman_source,
            username=username,
            password=password,
        )
    except RuntimeError as exc:
        print(f"err code={exc}", file=sys.stderr)
        return 1

    replies = (args.replies or "").strip()
    if not replies:
        replies = os.path.join(os.path.dirname(args.outbox), "airc-replies.jsonl")

    transport = _build_outbox_transport(
        machine_id=args.machine,
        outbox=args.outbox,
        replies_jsonl=replies,
        timeout_s=float(args.timeout_s),
    )
    result = send_cred_via_irc(
        target=args.target,
        username=pair["username"],
        password=pair["password"],
        transport=transport,
        qid=(args.qid or "") or None,
    )
    # wipe local copies
    pair["password"] = ""
    password = ""

    code = result.get("code") or "cred-failed"
    if result.get("ok"):
        acct = result.get("account") or ""
        tgt = result.get("target") or ""
        print(f"ok code=cred-persisted target={tgt} account={acct}")
        return 0
    print(f"err code={code}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

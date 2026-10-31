"""Airc PUT/RUN/JOB/STATUS/GET protocol (FR #78).

Durable jobs under ``<ConsoleHome>/jobs/<id>/``; file sandbox under
``<ConsoleHome>/drop/``. Fail closed on traversal, secret paths, bad frames.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Literal

# Limits (IRC-safe / retention)
MAX_PUT_BYTES = 256 * 1024


def put_max_bytes(via: str = "") -> int:
    """FR #5536: IRC PUT stays 256 KiB; via=dcc uses DCC_BULK_SIZE_CAP (2 MiB)."""
    if (via or "").strip().lower() == "dcc":
        from airc_dcc_bulk import DCC_BULK_SIZE_CAP

        return int(DCC_BULK_SIZE_CAP)
    return MAX_PUT_BYTES
MAX_CHUNK_RAW = 300
MAX_JOBS_RETAINED = 64
JOB_RETENTION_S = 7 * 24 * 3600
DEFAULT_RUN_TIMEOUT_S = 120.0
# FR #5611: DCC receive + atomic write must not sit on the IRC thread forever.
JOB_IO_TIMEOUT_S = 30.0
JOB_OFFLOAD_VERBS = frozenset({"PUT", "PUTEND", "GET"})

VerbLevel = Literal["read", "write", "exec"]

# FR #5281: VERSION is STATUS-class read (allowed when shell=off / jobs=off).
CAPS_OFF_ALLOWED_VERBS = frozenset({"STATUS", "VERSION"})

VERB_LEVELS: dict[str, VerbLevel] = {
    "STATUS": "read",
    "VERSION": "read",
    "GET": "read",
    "GETCHUNK": "read",
    "JOB": "read",
    "PUT": "write",
    "CHUNK": "write",
    "PUTEND": "write",
    "RUN": "exec",
    "CANCEL": "exec",
}

_SECRET_NAMES = {
    "console.password",
    "ergo.password",
    "connect.password",
    "identity.json",
    "github.token",
    "nickserv.password",
}
_SECRET_SUFFIXES = (".password", ".token")

_KV_RE = re.compile(r"(\w+)=([^\s]+)")
_VERB_RE = re.compile(
    r"^(?P<verb>STATUS|VERSION|PUT|CHUNK|PUTEND|RUN|GETCHUNK|GET|JOB|CANCEL)(?:\s+(?P<rest>.*))?$",
    re.IGNORECASE,
)
# FR #2570: optional leading id=<8 hex> before the verb (same pin as FR #75 shell).
_ID_PREFIX_RE = re.compile(r"(?is)^id=([0-9a-f]{8})\s+(.*)$")


class JobProtocolError(Exception):
    def __init__(self, code: str, message: str, job_id: str = "") -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.job_id = job_id


def run_job_io(fn: Callable[[], object], timeout_s: float, *, job_id: str = "") -> object:
    """FR #5611: blocking job I/O with a join timeout (hung writes stay off-thread)."""
    box: dict[str, object] = {}

    def _run() -> None:
        try:
            box["r"] = fn()
        except Exception as exc:  # noqa: BLE001
            box["e"] = exc

    t = threading.Thread(target=_run, name="airc-job-io", daemon=True)
    t.start()
    t.join(max(0.05, float(timeout_s)))
    if t.is_alive():
        raise JobProtocolError("timeout", "job I/O timeout", job_id)
    if "e" in box:
        exc = box["e"]
        if isinstance(exc, JobProtocolError):
            raise exc
        raise JobProtocolError("io", type(exc).__name__, job_id) from exc  # type: ignore[misc]
    return box.get("r")


def new_job_id() -> str:
    return uuid.uuid4().hex[:8]


def parse_kv(rest: str) -> dict[str, str]:
    return {m.group(1).lower(): m.group(2) for m in _KV_RE.finditer(rest or "")}


def parse_job_verb(text: str) -> tuple[str, dict[str, str]] | None:
    """Return (VERB, kv) if ``text`` is a FR #78 verb frame; else None.

    FR #2570: accept optional leading ``id=<8 hex>`` so Invoke-AircRemote Status
    can pin the same DONE correlation id as Command/Cmd/Psb64.
    """
    raw = (text or "").strip()
    leading_id = ""
    m_id = _ID_PREFIX_RE.match(raw)
    if m_id:
        leading_id = (m_id.group(1) or "").lower()
        raw = (m_id.group(2) or "").strip()
    m = _VERB_RE.match(raw)
    if not m:
        return None
    verb = m.group("verb").upper()
    kv = parse_kv(m.group("rest") or "")
    if leading_id and "id" not in kv:
        kv["id"] = leading_id
    # PUT path= may contain '=' only in kv values; path uses path=
    if verb == "PUT" and "path" not in kv and (m.group("rest") or "").lower().startswith("path="):
        # path value may include spaces? we disallow spaces in path for IRC safety
        pass
    return verb, kv


def verb_level(verb: str) -> VerbLevel:
    return VERB_LEVELS[verb.upper()]


@dataclass
class VerbAuthPolicy:
    """Per-verb authorization matrix on top of base AuthPolicy.

    Levels: read (STATUS/GET/JOB), write (PUT*), exec (RUN/CANCEL).
    ``write_nicks`` / ``exec_nicks`` restrict those levels when non-empty;
    empty means any nick that already passed base auth.
    """

    write_nicks: set[str] = field(default_factory=set)
    exec_nicks: set[str] = field(default_factory=set)

    def allow(self, nick: str, level: VerbLevel) -> bool:
        n = (nick or "").strip().lower()
        if level == "read":
            return True
        if level == "write":
            return (not self.write_nicks) or n in self.write_nicks
        if level == "exec":
            return (not self.exec_nicks) or n in self.exec_nicks
        return False


def _is_secret_name(name: str) -> bool:
    low = name.lower()
    if low in _SECRET_NAMES:
        return True
    return any(low.endswith(suf) for suf in _SECRET_SUFFIXES)


# FR #5610: DOS/Win32 reserved devices (stem before first dot).
_WIN_RESERVED_DEVICES = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{i}" for i in range(1, 10)}
    | {f"lpt{i}" for i in range(1, 10)}
)


def _is_win_reserved_device_component(name: str) -> bool:
    """True when a path component is CON/PRN/AUX/NUL/COM1-9/LPT1-9.

    Stem is the text before the first dot after stripping trailing spaces and dots
    (``COM1.txt``, ``nul. ``, ``LPT1.log``).
    """
    s = (name or "").strip().rstrip(". ").strip()
    if not s:
        return False
    stem = s.split(".", 1)[0].rstrip(". ").strip()
    return stem.lower() in _WIN_RESERVED_DEVICES


def _reject_win_reserved_device_path(raw: str) -> None:
    parts = [x for x in raw.replace("/", "\\").split("\\") if x not in ("", ".")]
    for part in parts:
        if _is_win_reserved_device_component(part):
            raise JobProtocolError("bad_path", "reserved device name")


def resolve_sandbox_path(drop_root: Path, raw_path: str) -> Path:
    """Resolve ``raw_path`` under drop_root; reject traversal / secrets / devices / escape."""
    if not raw_path or not raw_path.strip():
        raise JobProtocolError("bad_path", "empty path")
    p = raw_path.strip().replace("/", "\\")
    _reject_win_reserved_device_path(p)
    if _is_secret_name(Path(p).name):
        raise JobProtocolError("secret_path", "refusing secret file name")
    # Disallow device paths / UNC
    if p.startswith("\\\\") or (len(p) >= 3 and p[1] == ":" and p[0].isalpha()):
        # Absolute — only allow if under drop_root
        cand = Path(p)
        try:
            resolved = cand.resolve()
            root = drop_root.resolve()
        except OSError as exc:
            raise JobProtocolError("bad_path", str(exc)) from exc
        if root != resolved and root not in resolved.parents:
            raise JobProtocolError("sandbox", "absolute path outside sandbox")
        if _is_secret_name(resolved.name):
            raise JobProtocolError("secret_path", "refusing secret file name")
        return resolved
    if ".." in Path(p).parts:
        raise JobProtocolError("traversal", "path traversal rejected")
    cand = (drop_root / p).resolve()
    root = drop_root.resolve()
    if root != cand and root not in cand.parents:
        raise JobProtocolError("sandbox", "path escapes sandbox")
    if _is_secret_name(cand.name):
        raise JobProtocolError("secret_path", "refusing secret file name")
    return cand


def atomic_place_file(dest: Path, blob: bytes, expect_sha: str = "") -> str:
    """Write blob via a temp file, verify sha256, then replace dest (FR #5194)."""
    digest = hashlib.sha256(blob).hexdigest()
    if expect_sha and digest != expect_sha.lower():
        raise JobProtocolError("checksum", "sha256 mismatch")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".airc-put.tmp")
    try:
        tmp.write_bytes(blob)
        on_disk = hashlib.sha256(tmp.read_bytes()).hexdigest()
        if on_disk != digest:
            raise JobProtocolError("checksum", "sha256 mismatch after write")
        os.replace(tmp, dest)
    except Exception:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
        raise
    return digest


@dataclass
class JobRecord:
    id: str
    state: str  # receiving|ready|running|completed|failed|cancelled
    created_ts: float
    updated_ts: float
    path: str = ""
    bytes: int = 0
    sha256: str = ""
    seqs_expected: int | None = None
    seqs_received: list[int] = field(default_factory=list)
    exit_code: int | None = None
    error: str = ""
    owner: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "state": self.state,
            "created_ts": self.created_ts,
            "updated_ts": self.updated_ts,
            "path": self.path,
            "bytes": self.bytes,
            "sha256": self.sha256,
            "seqs_expected": self.seqs_expected,
            "seqs_received": list(self.seqs_received),
            "exit_code": self.exit_code,
            "error": self.error,
            "owner": self.owner,
        }

    @classmethod
    def from_dict(cls, d: dict) -> JobRecord:
        return cls(
            id=str(d.get("id") or ""),
            state=str(d.get("state") or "failed"),
            created_ts=float(d.get("created_ts") or 0),
            updated_ts=float(d.get("updated_ts") or 0),
            path=str(d.get("path") or ""),
            bytes=int(d.get("bytes") or 0),
            sha256=str(d.get("sha256") or ""),
            seqs_expected=d.get("seqs_expected"),
            seqs_received=list(d.get("seqs_received") or []),
            exit_code=d.get("exit_code"),
            error=str(d.get("error") or ""),
            owner=str(d.get("owner") or ""),
        )


class JobStore:
    """Filesystem-backed durable job store under ConsoleHome."""

    def __init__(self, home: Path) -> None:
        self.home = Path(home)
        self.jobs_root = self.home / "jobs"
        self.drop_root = self.home / "drop"
        self.jobs_root.mkdir(parents=True, exist_ok=True)
        self.drop_root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._chunks: dict[str, dict[int, bytes]] = {}
        self._fetches: dict[str, bytes] = {}
        self._meta: dict[str, JobRecord] = {}
        self._cancel = set()
        self.job_io_timeout_s = JOB_IO_TIMEOUT_S
        self._load_and_recover()

    def _job_dir(self, job_id: str) -> Path:
        return self.jobs_root / job_id

    def _meta_path(self, job_id: str) -> Path:
        return self._job_dir(job_id) / "meta.json"

    def _payload_path(self, job_id: str) -> Path:
        return self._job_dir(job_id) / "payload.bin"

    def _save(self, rec: JobRecord) -> None:
        d = self._job_dir(rec.id)
        d.mkdir(parents=True, exist_ok=True)
        rec.updated_ts = time.time()
        self._meta_path(rec.id).write_text(json.dumps(rec.to_dict(), indent=2) + "\n", encoding="utf-8")
        self._meta[rec.id] = rec

    def _load_and_recover(self) -> None:
        now = time.time()
        for child in self.jobs_root.iterdir() if self.jobs_root.is_dir() else []:
            if not child.is_dir():
                continue
            mp = child / "meta.json"
            if not mp.is_file():
                continue
            try:
                rec = JobRecord.from_dict(json.loads(mp.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                continue
            if rec.state == "running":
                rec.state = "failed"
                rec.error = "interrupted by restart"
                rec.exit_code = 125
                try:
                    self._save(rec)
                except OSError:
                    pass
            self._meta[rec.id] = rec
        self.cleanup(now=now)

    def cleanup(self, *, now: float | None = None) -> int:
        """Bounded retention: drop old completed/failed/cancelled jobs."""
        ts = time.time() if now is None else now
        removed = 0
        with self._lock:
            ids = sorted(self._meta.keys(), key=lambda i: self._meta[i].updated_ts)
            # age-based
            for jid in list(ids):
                rec = self._meta.get(jid)
                if not rec:
                    continue
                if rec.state in {"completed", "failed", "cancelled"} and (ts - rec.updated_ts) > JOB_RETENTION_S:
                    self._purge(jid)
                    removed += 1
            # count-based
            ids = sorted(self._meta.keys(), key=lambda i: self._meta[i].updated_ts)
            while len(ids) > MAX_JOBS_RETAINED:
                victim = ids.pop(0)
                rec = self._meta.get(victim)
                if rec and rec.state == "running":
                    continue
                self._purge(victim)
                removed += 1
                ids = sorted(self._meta.keys(), key=lambda i: self._meta[i].updated_ts)
        return removed

    def _purge(self, job_id: str) -> None:
        self._meta.pop(job_id, None)
        self._chunks.pop(job_id, None)
        self._cancel.discard(job_id)
        d = self._job_dir(job_id)
        if d.is_dir():
            shutil.rmtree(d, ignore_errors=True)

    def get(self, job_id: str) -> JobRecord | None:
        with self._lock:
            return self._meta.get(job_id)

    def handle_put(self, nick: str, kv: dict[str, str]) -> list[str]:
        jid = kv.get("id") or new_job_id()
        path = kv.get("path") or ""
        try:
            nbytes = int(kv.get("bytes") or "0")
        except ValueError as exc:
            raise JobProtocolError("bad_frame", "bytes not int", jid) from exc
        sha = (kv.get("sha256") or "").lower()
        via = (kv.get("via") or "").strip().lower()
        limit = put_max_bytes(via)
        if nbytes < 0 or nbytes > limit:
            raise JobProtocolError("size", f"bytes out of range 0..{limit}", jid)
        if sha and (len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha)):
            raise JobProtocolError("bad_frame", "sha256 must be 64 hex", jid)
        dest = resolve_sandbox_path(self.drop_root, path)
        with self._lock:
            rec = JobRecord(
                id=jid,
                state="receiving",
                created_ts=time.time(),
                updated_ts=time.time(),
                path=str(dest),
                bytes=nbytes,
                sha256=sha,
                owner=nick.strip().lower(),
            )
            self._chunks[jid] = {}
            self._save(rec)
        if via == "dcc":
            recv = getattr(self, "dcc_receive", None)
            if recv is None:
                return [
                    f"ok id={jid} put path={dest.name} bytes={nbytes}",
                    f"err id={jid} dcc-put unavailable; falling back to IRC",
                ]
            io_t = float(getattr(self, "job_io_timeout_s", JOB_IO_TIMEOUT_S) or JOB_IO_TIMEOUT_S)
            try:
                pair = run_job_io(lambda: recv(jid), io_t, job_id=jid)
                blob, dig = pair  # type: ignore[misc]
            except JobProtocolError as exc:
                if exc.code == "timeout":
                    with self._lock:
                        rec.state = "failed"
                        rec.error = "job I/O timeout"
                        self._save(rec)
                    return [
                        f"err id={jid} code=timeout msg=job I/O timeout",
                        f"DONE id={jid} exit=1",
                    ]
                return [
                    f"ok id={jid} put path={dest.name} bytes={nbytes}",
                    f"err id={jid} dcc failed: {exc.message}; falling back to IRC",
                ]
            except Exception as exc:
                return [
                    f"ok id={jid} put path={dest.name} bytes={nbytes}",
                    f"err id={jid} dcc failed: {exc}; falling back to IRC",
                ]
            expect = sha or (dig or "").lower()
            try:
                if len(blob) > put_max_bytes("dcc"):
                    raise JobProtocolError("size", f"dcc payload over {put_max_bytes('dcc')}", jid)
                if nbytes and len(blob) != nbytes:
                    raise JobProtocolError("size", "dcc size != declared bytes", jid)
                digest = run_job_io(
                    lambda: atomic_place_file(dest, blob, expect),
                    io_t,
                    job_id=jid,
                )
            except JobProtocolError as exc:
                with self._lock:
                    rec.state = "failed"
                    rec.error = exc.message
                    self._save(rec)
                if dest.exists():
                    try:
                        dest.unlink()
                    except OSError:
                        pass
                if exc.code == "timeout":
                    return [
                        f"err id={jid} code=timeout msg=job I/O timeout",
                        f"DONE id={jid} exit=1",
                    ]
                raise
            with self._lock:
                rec.state = "ready"
                rec.bytes = len(blob)
                rec.sha256 = digest
                self._chunks.pop(jid, None)
                self._save(rec)
            return [f"ok id={jid} putend bytes={len(blob)} sha256={digest} via=dcc"]
        return [f"ok id={jid} put path={dest.name} bytes={nbytes}"]

    def handle_chunk(self, nick: str, kv: dict[str, str]) -> list[str]:
        import base64

        jid = kv.get("id") or ""
        if not jid:
            raise JobProtocolError("bad_frame", "CHUNK requires id=")
        try:
            seq = int(kv.get("seq") or "0")
        except ValueError as exc:
            raise JobProtocolError("bad_frame", "seq not int", jid) from exc
        data_b64 = kv.get("data") or ""
        if seq < 1:
            raise JobProtocolError("bad_frame", "seq must be >=1", jid)
        if not data_b64:
            raise JobProtocolError("bad_frame", "CHUNK requires data=", jid)
        try:
            raw = base64.b64decode(data_b64, validate=True)
        except Exception as exc:  # noqa: BLE001
            raise JobProtocolError("bad_frame", "malformed chunk base64", jid) from exc
        if len(raw) > MAX_CHUNK_RAW:
            raise JobProtocolError("size", f"chunk larger than {MAX_CHUNK_RAW}", jid)
        with self._lock:
            rec = self._meta.get(jid)
            if rec and rec.state == "ready":
                return [f"ok id={jid} chunk seq={seq} already=1"]
            if not rec or rec.state not in {"receiving"}:
                raise JobProtocolError("state", "no receiving PUT for id", jid)
            if rec.owner and rec.owner != nick.strip().lower():
                raise JobProtocolError("owner", "chunk owner mismatch", jid)
            bag = self._chunks.setdefault(jid, {})
            if seq in bag:
                # idempotent duplicate
                return [f"ok id={jid} chunk seq={seq} dup=1"]
            total = sum(len(v) for v in bag.values()) + len(raw)
            if total > MAX_PUT_BYTES or (rec.bytes and total > rec.bytes):
                raise JobProtocolError("size", "PUT exceeds declared/max size", jid)
            bag[seq] = raw
            rec.seqs_received = sorted(bag.keys())
            self._save(rec)
        return [f"ok id={jid} chunk seq={seq}"]

    def handle_putend(self, nick: str, kv: dict[str, str]) -> list[str]:
        jid = kv.get("id") or ""
        if not jid:
            raise JobProtocolError("bad_frame", "PUTEND requires id=")
        try:
            seqs = int(kv.get("seqs") or "0")
        except ValueError as exc:
            raise JobProtocolError("bad_frame", "seqs not int", jid) from exc
        sha = (kv.get("sha256") or "").lower()
        with self._lock:
            rec = self._meta.get(jid)
            if rec and rec.state == "ready":
                return [f"ok id={jid} putend already=1 sha256={rec.sha256}"]
            if not rec or rec.state != "receiving":
                raise JobProtocolError("state", "no receiving PUT for id", jid)
            if rec.owner and rec.owner != nick.strip().lower():
                raise JobProtocolError("owner", "PUTEND owner mismatch", jid)
            bag = self._chunks.get(jid) or {}
            if sorted(bag.keys()) != list(range(1, seqs + 1)):
                raise JobProtocolError(
                    "order",
                    f"chunk set incomplete/out-of-order have={sorted(bag.keys())} want=1..{seqs}",
                    jid,
                )
            blob = b"".join(bag[i] for i in range(1, seqs + 1))
            digest = hashlib.sha256(blob).hexdigest()
            expect = sha or rec.sha256
            if expect and digest != expect:
                rec.state = "failed"
                rec.error = "checksum mismatch"
                self._save(rec)
                raise JobProtocolError("checksum", "sha256 mismatch", jid)
            if rec.bytes and len(blob) != rec.bytes:
                raise JobProtocolError("size", "assembled size != declared bytes", jid)
            dest = Path(rec.path)
            # FR #5611: do not hold the store lock across blocking disk I/O.
        io_t = float(getattr(self, "job_io_timeout_s", JOB_IO_TIMEOUT_S) or JOB_IO_TIMEOUT_S)
        try:
            digest = run_job_io(
                lambda: atomic_place_file(dest, blob, expect),
                io_t,
                job_id=jid,
            )
        except JobProtocolError as exc:
            with self._lock:
                rec = self._meta.get(jid)
                if rec:
                    rec.state = "failed"
                    rec.error = exc.message
                    self._save(rec)
            if exc.code == "timeout":
                return [
                    f"err id={jid} code=timeout msg=job I/O timeout",
                    f"DONE id={jid} exit=1",
                ]
            raise
        with self._lock:
            rec = self._meta.get(jid)
            if not rec:
                raise JobProtocolError("state", "job vanished during putend", jid)
            self._payload_path(jid).write_bytes(blob)
            rec.state = "ready"
            rec.bytes = len(blob)
            rec.sha256 = digest
            rec.seqs_expected = seqs
            self._chunks.pop(jid, None)
            self._save(rec)
        return [f"ok id={jid} putend bytes={len(blob)} sha256={digest}"]

    def handle_get(self, kv: dict[str, str]) -> list[str]:
        if (kv.get("fetch") or "").lower() == "chunk":
            return self._start_fetch(kv)
        jid = kv.get("id") or ""
        path = kv.get("path") or ""
        with self._lock:
            if jid:
                rec = self._meta.get(jid)
                if not rec:
                    raise JobProtocolError("missing", "unknown job id", jid)
                return [
                    f"GET id={rec.id} state={rec.state} path={rec.path} bytes={rec.bytes} "
                    f"sha256={rec.sha256} exit={rec.exit_code if rec.exit_code is not None else '-'}"
                ]
            if not path:
                raise JobProtocolError("bad_frame", "GET requires id= or path=")
            dest = resolve_sandbox_path(self.drop_root, path)
            if not dest.is_file():
                raise JobProtocolError("missing", "file not found")
            data = dest.read_bytes()[:MAX_PUT_BYTES]
            digest = hashlib.sha256(data).hexdigest()
            head = data[:80].decode("utf-8", errors="replace").replace("\n", "\\n")
            return [f"GET path={dest} bytes={len(data)} sha256={digest} head={head}"]

    def _start_fetch(self, kv: dict[str, str]) -> list[str]:
        """FR #4795: open a pull-mode outbound fetch. No file bytes on this reply."""
        path = kv.get("path") or ""
        if not path:
            raise JobProtocolError("bad_frame", "GET fetch=chunk requires path=")
        dest = resolve_sandbox_path(self.drop_root, path)
        if not dest.is_file():
            raise JobProtocolError("missing", "file not found")
        data = dest.read_bytes()
        if len(data) > MAX_PUT_BYTES:
            raise JobProtocolError("size", f"file larger than {MAX_PUT_BYTES}")
        jid = (kv.get("id") or "").strip().lower() or new_job_id()
        digest = hashlib.sha256(data).hexdigest()
        seqs = (len(data) + MAX_CHUNK_RAW - 1) // MAX_CHUNK_RAW if data else 0
        with self._lock:
            self._fetches[jid] = data
        return [
            f"ok id={jid} get bytes={len(data)} sha256={digest} seqs={seqs} chunk={MAX_CHUNK_RAW}"
        ]

    def handle_getchunk(self, kv: dict[str, str]) -> list[str]:
        """FR #4795: one raw chunk per request. The next GETCHUNK is the ack."""
        import base64

        jid = (kv.get("id") or "").strip().lower()
        if not jid:
            raise JobProtocolError("bad_frame", "GETCHUNK requires id=")
        try:
            seq = int(kv.get("seq") or "0")
        except ValueError as exc:
            raise JobProtocolError("bad_frame", "seq not int", jid) from exc
        if seq < 1:
            raise JobProtocolError("bad_frame", "seq must be >=1", jid)
        with self._lock:
            data = self._fetches.get(jid)
            if data is None:
                raise JobProtocolError("missing", "unknown fetch id", jid)
            start = (seq - 1) * MAX_CHUNK_RAW
            if start >= len(data):
                raise JobProtocolError("bad_frame", "seq past end", jid)
            raw = data[start : start + MAX_CHUNK_RAW]
        b64 = base64.b64encode(raw).decode("ascii")
        return [f"ok id={jid} chunk seq={seq} data={b64}"]

    def handle_job(self, kv: dict[str, str]) -> list[str]:
        jid = kv.get("id") or ""
        if not jid:
            raise JobProtocolError("bad_frame", "JOB requires id=")
        with self._lock:
            rec = self._meta.get(jid)
            if not rec:
                raise JobProtocolError("missing", "unknown job id", jid)
            return [
                f"JOB id={rec.id} state={rec.state} exit={rec.exit_code if rec.exit_code is not None else '-'} "
                f"error={rec.error or '-'}"
            ]

    def request_cancel(self, job_id: str) -> list[str]:
        with self._lock:
            rec = self._meta.get(job_id)
            if not rec:
                raise JobProtocolError("missing", "unknown job id", job_id)
            if rec.state in {"completed", "failed", "cancelled"}:
                return [f"ok id={job_id} cancel state={rec.state}"]
            self._cancel.add(job_id)
            if rec.state in {"receiving", "ready"}:
                rec.state = "cancelled"
                rec.error = "cancelled"
                self._save(rec)
            return [f"ok id={job_id} cancel requested"]

    def is_cancelled(self, job_id: str) -> bool:
        with self._lock:
            return job_id in self._cancel

    def mark_running(self, job_id: str) -> JobRecord:
        with self._lock:
            rec = self._meta.get(job_id)
            if not rec:
                raise JobProtocolError("missing", "unknown job id", job_id)
            if rec.state != "ready":
                raise JobProtocolError("state", f"RUN requires ready (have {rec.state})", job_id)
            rec.state = "running"
            self._save(rec)
            return rec

    def mark_done(self, job_id: str, exit_code: int, error: str = "") -> None:
        with self._lock:
            rec = self._meta.get(job_id)
            if not rec:
                return
            if job_id in self._cancel and exit_code != 0:
                rec.state = "cancelled"
            else:
                rec.state = "completed" if exit_code == 0 else "failed"
            rec.exit_code = exit_code
            rec.error = error
            self._cancel.discard(job_id)
            self._save(rec)
            self.cleanup()


def collect_status_versions(ai_root: Path | None = None) -> dict[str, str]:
    root = Path(ai_root or os.environ.get("AI_ROOT") or r"C:\ai")
    out: dict[str, str] = {}
    for name in ("bob", "airc", "jeeves"):
        vf = root / name / "VERSION"
        try:
            out[name] = vf.read_text(encoding="utf-8").strip().splitlines()[0].strip() if vf.is_file() else "-"
        except OSError:
            out[name] = "-"
    return out


def _token(raw: str, *, max_len: int = 64) -> str:
    """Single IRC token: no spaces, no secret-shaped keys."""
    t = re.sub(r"\s+", "", str(raw or "").strip())
    if re.search(r"(?i)pass|secret|token|pwd", t):
        return ""
    return t[:max_len]


def collect_airc_build_meta(ai_root: Path | None = None) -> dict[str, str]:
    """FR #5534 / FR #5589: BUILD.json commit+built_utc; HOTPATCH overlays commit only.

    HOTPATCH.json schema: ``commit`` (or ``hotpatch_commit`` / ``sha``) and
    ``hotpatched_utc`` (legacy ``built_utc`` / ``at_utc`` is the hotpatch time,
    never the exe build time).
    """
    root = Path(ai_root or os.environ.get("AI_ROOT") or r"C:\ai") / "airc"
    meta: dict[str, str] = {}
    for name, overlay in (("BUILD.json", False), ("HOTPATCH.json", True)):
        path = root / name
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        commit = _token(
            str(
                data.get("commit")
                or data.get("hotpatch_commit")
                or data.get("sha")
                or ""
            )
        )
        built = _token(str(data.get("built_utc") or data.get("at_utc") or ""), max_len=40)
        patched = _token(
            str(
                data.get("hotpatched_utc")
                or (data.get("built_utc") if overlay else "")
                or (data.get("at_utc") if overlay else "")
                or ""
            ),
            max_len=40,
        )
        if overlay:
            meta["hotpatch"] = "1"
            if commit:
                meta["commit"] = commit
            if patched:
                meta["hotpatched_utc"] = patched
        else:
            if commit:
                meta["commit"] = commit
            if built:
                meta["built_utc"] = built
    return meta


def format_version_lines(
    *,
    versions: dict[str, str],
    machine: str,
    build: dict[str, str] | None = None,
) -> list[str]:
    """FR #5281 / #5534: airc VERSION plus optional commit/built/hotpatch.

    Version source is ``<ai root>\\airc\\VERSION``. Missing/unreadable -> ``-``.
    No ARP / registry fallback. BUILD.json / HOTPATCH.json add identity tokens.
    """
    bits = [f"VERSION machine={machine} airc_ver={versions.get('airc', '-')}"]
    info = build or {}
    commit = _token(info.get("commit") or "")
    built = _token(info.get("built_utc") or "", max_len=40)
    if commit:
        bits.append(f"commit={commit}")
    if built:
        bits.append(f"built={built}")
    patched = _token(info.get("hotpatched_utc") or "", max_len=40)
    if patched:
        bits.append(f"hotpatched={patched}")
    if str(info.get("hotpatch") or "") == "1":
        bits.append("hotpatch=1")
    return [" ".join(bits)]


def format_status_lines(*, airc_running: bool, versions: dict[str, str], machine: str) -> list[str]:
    run = "Running" if airc_running else "Stopped"
    return [
        f"STATUS machine={machine} airc={run} bob={versions.get('bob', '-')} "
        f"airc_ver={versions.get('airc', '-')} jeeves={versions.get('jeeves', '-')}"
    ]


class JobProtocol:
    """Dispatch FR #78 verbs; RUN executes via injected runner callback."""

    def __init__(
        self,
        store: JobStore,
        *,
        verb_auth: VerbAuthPolicy | None = None,
        on_reply: Callable[[str, str], None] | None = None,
        run_file: Callable[[Path, float], tuple[int, str, str]] | None = None,
        ai_root: Path | None = None,
        machine: str = "",
        airc_running: bool = True,
        run_timeout_s: float = DEFAULT_RUN_TIMEOUT_S,
        job_io_timeout_s: float = JOB_IO_TIMEOUT_S,
        inline_jobs: bool = True,
    ) -> None:
        self.store = store
        self.verb_auth = verb_auth or VerbAuthPolicy()
        self.on_reply = on_reply
        self.run_file = run_file or _default_run_ps1
        self.ai_root = ai_root
        self.machine = machine
        self.airc_running = airc_running
        self.run_timeout_s = run_timeout_s
        self.job_io_timeout_s = float(job_io_timeout_s)
        # Tests stay inline; the live console sets inline_jobs=False (FR #5611).
        self.inline_jobs = bool(inline_jobs)
        self.store.job_io_timeout_s = self.job_io_timeout_s
        self._lock = threading.Lock()
        self.dcc_receive = None  # FR #5194: (job_id) -> (bytes, sha256)

    def authorize(self, nick: str, verb: str) -> None:
        level = verb_level(verb)
        if not self.verb_auth.allow(nick, level):
            raise JobProtocolError("denied", f"verb {verb} requires {level} permission")

    def _emit(self, nick: str, line: str) -> None:
        # FR #2551: on_reply may raise ConnectionError after IRC drop; swallow so the
        # RUN worker thread does not die with an unhandled exception (crash hook).
        if self.on_reply:
            try:
                self.on_reply(nick, line)
            except ConnectionError:
                return

    def handle(self, nick: str, verb: str, kv: dict[str, str]) -> list[str]:
        try:
            self.authorize(nick, verb)
            if verb == "STATUS":
                vers = collect_status_versions(self.ai_root)
                body = format_status_lines(
                    airc_running=self.airc_running, versions=vers, machine=self.machine
                )
                # FR #2570: terminal DONE so Invoke-AircRemote -ReplyFile Wait matches id=.
                # FR #2575: frame body as out id= seq= (same as format_shell_replies) so StdOut fills.
                jid = (kv.get("id") or "").strip().lower() or new_job_id()
                lines = [
                    f"out id={jid} seq={i} {part}" for i, part in enumerate(body, start=1)
                ]
                lines.append(f"DONE id={jid} exit=0")
                return lines
            if verb == "VERSION":
                vers = collect_status_versions(self.ai_root)
                body = format_version_lines(
                    versions=vers,
                    machine=self.machine,
                    build=collect_airc_build_meta(self.ai_root),
                )
                jid = (kv.get("id") or "").strip().lower() or new_job_id()
                lines = [
                    f"out id={jid} seq={i} {part}" for i, part in enumerate(body, start=1)
                ]
                lines.append(f"DONE id={jid} exit=0")
                return lines
            if verb == "PUT":
                self.store.dcc_receive = self.dcc_receive
                self.store.job_io_timeout_s = self.job_io_timeout_s
                return self.store.handle_put(nick, kv)
            if verb == "CHUNK":
                return self.store.handle_chunk(nick, kv)
            if verb == "PUTEND":
                return self.store.handle_putend(nick, kv)
            if verb == "GET":
                return self.store.handle_get(kv)
            if verb == "GETCHUNK":
                return self.store.handle_getchunk(kv)
            if verb == "JOB":
                return self.store.handle_job(kv)
            if verb == "CANCEL":
                jid = kv.get("id") or ""
                if not jid:
                    raise JobProtocolError("bad_frame", "CANCEL requires id=")
                return self.store.request_cancel(jid)
            if verb == "RUN":
                return self._run(nick, kv)
            raise JobProtocolError("bad_frame", f"unknown verb {verb}")
        except JobProtocolError as exc:
            jid = exc.job_id or kv.get("id") or "-"
            lines = [f"err id={jid} code={exc.code} msg={exc.message}"]
            # FR #5611: I/O timeout must complete the job for callers waiting on DONE.
            if exc.code == "timeout":
                lines.append(f"DONE id={jid} exit=1")
            return lines

    def handle_async(self, nick: str, verb: str, kv: dict[str, str]) -> None:
        """Handle verb and emit replies (FR #5611: PUT/GET I/O off the IRC thread)."""
        def _emit_handle() -> None:
            lines = self.handle(nick, verb, kv)
            for ln in lines:
                self._emit(nick, ln)

        if verb == "RUN":
            _emit_handle()
            return
        if (not self.inline_jobs) and verb in JOB_OFFLOAD_VERBS:
            threading.Thread(
                target=_emit_handle,
                name=f"airc-job-{verb.lower()}",
                daemon=True,
            ).start()
            return
        _emit_handle()

    def _run(self, nick: str, kv: dict[str, str]) -> list[str]:
        jid = kv.get("id") or ""
        path = kv.get("path") or ""
        if not jid and path:
            # path-only RUN: synthesize from ready file without prior PUT id
            dest = resolve_sandbox_path(self.store.drop_root, path)
            jid = new_job_id()
            rec = JobRecord(
                id=jid,
                state="ready",
                created_ts=time.time(),
                updated_ts=time.time(),
                path=str(dest),
                owner=nick.strip().lower(),
            )
            if not dest.is_file():
                raise JobProtocolError("missing", "RUN path not found", jid)
            self.store._save(rec)  # noqa: SLF001 — intentional store API for path-only RUN
        if not jid:
            raise JobProtocolError("bad_frame", "RUN requires id= or path=")

        rec = self.store.mark_running(jid)
        script = Path(rec.path)
        if path:
            script = resolve_sandbox_path(self.store.drop_root, path)
        if not script.is_file():
            self.store.mark_done(jid, 2, "script missing")
            raise JobProtocolError("missing", "script missing", jid)

        def worker() -> None:
            try:
                if self.store.is_cancelled(jid):
                    self.store.mark_done(jid, 130, "cancelled")
                    self._emit(nick, f"DONE id={jid} exit=130")
                    return
                code, out, err = self.run_file(script, self.run_timeout_s)
                if self.store.is_cancelled(jid):
                    code = 130
                self.store.mark_done(jid, code)
                # Emit FR #75-style framing for correlation
                seq = 0
                for label, text in (("out", out), ("err", err)):
                    for part in (text.splitlines() or ([] if not text else [""])):
                        seq += 1
                        self._emit(nick, f"{label} id={jid} seq={seq} {part}")
                self._emit(nick, f"DONE id={jid} exit={code}")
            except Exception as exc:  # noqa: BLE001
                self.store.mark_done(jid, 1, str(exc))
                self._emit(nick, f"err id={jid} seq=1 {exc}")
                self._emit(nick, f"DONE id={jid} exit=1")

        t = threading.Thread(target=worker, name=f"airc-run-{jid}", daemon=True)
        t.start()
        return [f"ok id={jid} run started"]


def _default_run_ps1(path: Path, timeout_s: float) -> tuple[int, str, str]:
    import subprocess
    import shutil

    ps = shutil.which("powershell.exe") or "powershell.exe"
    proc = subprocess.run(
        [
            ps,
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(path),
        ],
        capture_output=True,
        timeout=timeout_s,
        check=False,
    )
    out = (proc.stdout or b"")[: 64 * 1024].decode("utf-8", errors="replace")
    err = (proc.stderr or b"")[: 64 * 1024].decode("utf-8", errors="replace")
    return int(proc.returncode), out, err

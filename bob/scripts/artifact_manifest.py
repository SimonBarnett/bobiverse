# -*- coding: utf-8 -*-
"""FR #8218: per-file SHA-256 artifact manifest (path, size, hash).

``manifest.txt`` lists every file that will be uploaded in a component
artifact (worker today; ear/tray can reuse the same format). The manifest
itself is excluded from the file table (self-hash chicken-egg). ``provenance.txt``
stays a separate key=value identity file and is listed like any other payload.

Header keys keep ``source_commit`` / ``workflow_commit`` and optional GitHub
run id fields at the top. File rows are tab-separated:
``relative_path\\tsize_bytes\\tsha256``.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path

MANIFEST_NAMES = frozenset({"manifest.txt", "manifest.sha256"})
DEFAULT_PRODUCT = "bob-worker"
DEFAULT_FR = "8218"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def rel_posix(stage: Path, path: Path) -> str:
    rel = path.relative_to(stage).as_posix()
    return rel


def iter_payload_files(stage: Path) -> list[Path]:
    """Every file under ``stage`` except the manifest leaf itself."""
    stage = Path(stage)
    out: list[Path] = []
    for path in sorted(stage.rglob("*")):
        if not path.is_file():
            continue
        if path.name.lower() in MANIFEST_NAMES:
            continue
        out.append(path)
    return out


def build_file_rows(stage: Path) -> list[tuple[str, int, str]]:
    rows: list[tuple[str, int, str]] = []
    for path in iter_payload_files(stage):
        rows.append((rel_posix(stage, path), path.stat().st_size, sha256_file(path)))
    return rows


def format_manifest(
    rows: list[tuple[str, int, str]],
    *,
    source_commit: str = "",
    workflow_commit: str = "",
    github_run_id: str = "",
    github_run_attempt: str = "",
    product: str = DEFAULT_PRODUCT,
    fr: str = DEFAULT_FR,
) -> str:
    lines = [
        "# bobiverse artifact manifest (FR #%s)" % fr,
        "# columns: relative_path<TAB>size_bytes<TAB>sha256",
        "product=%s" % (product or DEFAULT_PRODUCT),
        "fr=%s" % (fr or DEFAULT_FR),
        "source_commit=%s" % (source_commit or "").strip(),
        "workflow_commit=%s" % (workflow_commit or source_commit or "").strip(),
        "github_run_id=%s" % (github_run_id or "").strip(),
        "github_run_attempt=%s" % (github_run_attempt or "").strip(),
        "file_count=%d" % len(rows),
        "---",
    ]
    for rel, size, digest in rows:
        lines.append("%s\t%d\t%s" % (rel, int(size), digest.lower()))
    lines.append("")
    return "\n".join(lines)


def write_manifest(
    stage: Path,
    *,
    source_commit: str = "",
    workflow_commit: str = "",
    github_run_id: str = "",
    github_run_attempt: str = "",
    product: str = DEFAULT_PRODUCT,
    fr: str = DEFAULT_FR,
    name: str = "manifest.txt",
) -> Path:
    stage = Path(stage)
    if not stage.is_dir():
        raise SystemExit("artifact stage missing: %s" % stage)
    leaf = name if name.lower() in MANIFEST_NAMES else "manifest.txt"
    # Drop a stale alias before hashing so it is not listed as payload.
    for stale in MANIFEST_NAMES:
        p = stage / stale
        if p.is_file():
            p.unlink()
    rows = build_file_rows(stage)
    if not rows:
        raise SystemExit("artifact stage has no payload files: %s" % stage)
    text = format_manifest(
        rows,
        source_commit=source_commit,
        workflow_commit=workflow_commit,
        github_run_id=github_run_id,
        github_run_attempt=github_run_attempt,
        product=product,
        fr=fr,
    )
    out = stage / leaf
    out.write_text(text, encoding="ascii", newline="\n")
    return out


def parse_manifest(text: str) -> tuple[dict[str, str], list[tuple[str, int, str]]]:
    header: dict[str, str] = {}
    rows: list[tuple[str, int, str]] = []
    in_files = False
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line == "---":
            in_files = True
            continue
        if not in_files:
            if "=" in line:
                k, v = line.split("=", 1)
                header[k.strip()] = v.strip()
            continue
        parts = raw.split("\t")
        if len(parts) != 3:
            raise SystemExit("bad manifest row (want path<TAB>size<TAB>sha256): %r" % raw)
        rel, size_s, digest = parts
        rows.append((rel.strip().replace("\\", "/"), int(size_s), digest.strip().lower()))
    return header, rows


def verify_manifest(stage: Path, manifest_path: Path | None = None) -> dict[str, str]:
    """Raise SystemExit on missing/extra/mismatched files. Return header on ok."""
    stage = Path(stage)
    man = Path(manifest_path) if manifest_path else stage / "manifest.txt"
    if not man.is_file():
        # allow manifest.sha256 alias
        alt = stage / "manifest.sha256"
        if alt.is_file():
            man = alt
        else:
            raise SystemExit("manifest missing under %s" % stage)
    header, rows = parse_manifest(man.read_text(encoding="ascii"))
    if not rows:
        raise SystemExit("manifest has no file rows: %s" % man)
    listed = {rel: (size, digest) for rel, size, digest in rows}
    actual: dict[str, tuple[int, str]] = {}
    for path in iter_payload_files(stage):
        rel = rel_posix(stage, path)
        actual[rel] = (path.stat().st_size, sha256_file(path))
    missing = sorted(set(listed) - set(actual))
    extra = sorted(set(actual) - set(listed))
    if missing:
        raise SystemExit("manifest lists missing files: %s" % ", ".join(missing))
    if extra:
        raise SystemExit("artifact has files not in manifest: %s" % ", ".join(extra))
    bad: list[str] = []
    for rel, (size, digest) in listed.items():
        got_size, got_digest = actual[rel]
        if got_size != size or got_digest != digest:
            bad.append(
                "%s listed=%d/%s got=%d/%s" % (rel, size, digest, got_size, got_digest)
            )
    if bad:
        raise SystemExit("manifest hash/size mismatch: %s" % "; ".join(bad))
    fc = header.get("file_count")
    if fc is not None and fc != "" and int(fc) != len(rows):
        raise SystemExit("file_count=%s != rows=%d" % (fc, len(rows)))
    return header


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="FR #8218 artifact per-file SHA-256 manifest")
    sub = p.add_subparsers(dest="cmd", required=True)

    w = sub.add_parser("write", help="write manifest.txt for a staged artifact dir")
    w.add_argument("--stage", required=True)
    w.add_argument("--source-commit", default="")
    w.add_argument("--workflow-commit", default="")
    w.add_argument("--github-run-id", default="")
    w.add_argument("--github-run-attempt", default="")
    w.add_argument("--product", default=DEFAULT_PRODUCT)
    w.add_argument("--fr", default=DEFAULT_FR)
    w.add_argument("--name", default="manifest.txt")

    v = sub.add_parser("verify", help="verify stage against manifest.txt")
    v.add_argument("--stage", required=True)
    v.add_argument("--manifest", default="")

    args = p.parse_args(argv)
    if args.cmd == "write":
        # Prefer explicit flags; fall back to GHA env when unset.
        src = args.source_commit or os.environ.get("WORKFLOW_COMMIT") or ""
        wf = args.workflow_commit or src
        rid = args.github_run_id or os.environ.get("GITHUB_RUN_ID") or ""
        ratt = args.github_run_attempt or os.environ.get("GITHUB_RUN_ATTEMPT") or ""
        out = write_manifest(
            Path(args.stage),
            source_commit=src,
            workflow_commit=wf,
            github_run_id=rid,
            github_run_attempt=ratt,
            product=args.product,
            fr=args.fr,
            name=args.name,
        )
        print(str(out))
        return 0
    if args.cmd == "verify":
        man = Path(args.manifest) if args.manifest else None
        header = verify_manifest(Path(args.stage), man)
        print(
            "ok files=%s source_commit=%s"
            % (header.get("file_count"), header.get("source_commit"))
        )
        return 0
    return 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        print("artifact_manifest error: %s" % e, file=sys.stderr)
        raise SystemExit(1)

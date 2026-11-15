"""FR #7465: checks and site-kit manifest for the Jeeves IIS www bundle.

No service build. No host names. The #7460 regression is a web.config with a
duplicate staticContent, rewrite, or handlers section.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen
import xml.etree.ElementTree as ET

SECTIONS = ("staticContent", "rewrite", "handlers")
LINK_RE = re.compile(
    r"""(?:href|src)\s*=\s*['"]([^'"]+)['"]""",
    re.IGNORECASE,
)


class KitError(SystemExit):
    pass


def local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def assert_web_config(path: Path) -> None:
    """Well-formed XML and a single copy of each guarded section."""
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        raise KitError(f"web.config is not well-formed XML: {exc}") from exc
    counts = {name: 0 for name in SECTIONS}
    for el in root.iter():
        name = local_name(el.tag)
        if name in counts:
            counts[name] += 1
    dupes = {k: v for k, v in counts.items() if v > 1}
    if dupes:
        raise KitError(f"duplicate web.config sections: {dupes}")


def _asset_paths(html: str) -> list[str]:
    out: list[str] = []
    for raw in LINK_RE.findall(html):
        ref = raw.split("#", 1)[0].split("?", 1)[0].strip()
        if not ref or ref.startswith(("#", "mailto:", "javascript:")):
            continue
        if ref.startswith(("http://", "https://", "//")):
            continue
        out.append(ref)
    return out


def smoke_serve(root: Path) -> None:
    """Serve the published bundle and require 2xx for pages and local assets."""
    root = root.resolve()

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(root), **kwargs)

        def log_message(self, fmt: str, *args) -> None:
            return

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    try:
        pages = [p for p in root.rglob("*.html")]
        if not pages:
            raise KitError(f"no html pages under {root}")
        seen: set[str] = set()
        for page in pages:
            rel = page.relative_to(root).as_posix()
            _get(base, "/" + rel)
            html = page.read_text(encoding="utf-8", errors="replace")
            for ref in _asset_paths(html):
                if ref.startswith("/"):
                    url_path = ref
                else:
                    parent = page.parent.relative_to(root).as_posix()
                    url_path = "/" + (parent + "/" if parent != "." else "") + ref
                url_path = re.sub(r"/+", "/", url_path)
                if url_path in seen:
                    continue
                seen.add(url_path)
                target = (root / url_path.lstrip("/")).resolve()
                if not str(target).startswith(str(root)):
                    continue
                if target.is_file():
                    _get(base, url_path)
    finally:
        httpd.shutdown()
        thread.join(timeout=5)


def _get(base: str, path: str) -> None:
    url = base + path
    try:
        with urlopen(url, timeout=10) as resp:
            code = getattr(resp, "status", 200)
            if code >= 500:
                raise KitError(f"{url} returned {code}")
            resp.read()
    except HTTPError as exc:
        if exc.code >= 500:
            raise KitError(f"{url} returned {exc.code}") from exc
        if exc.code == 404:
            raise KitError(f"missing linked asset {url}") from exc
        raise


def file_matches(pattern: str, path: str) -> bool:
    pat = pattern.replace("\\", "/").lstrip("./")
    rel = path.replace("\\", "/").lstrip("./")
    if pat.startswith("!"):
        pat = pat[1:]
    rx = re.escape(pat).replace(r"\*\*", ".*").replace(r"\*", "[^/]*")
    if re.fullmatch(rx, rel):
        return True
    if pat.endswith("/**") and (rel == pat[:-3] or rel.startswith(pat[:-3] + "/")):
        return True
    return False


def workflow_paths(text: str, event: str) -> list[str]:
    """Return the paths: list under pull_request or push. Ignores paths-ignore."""
    lines = text.splitlines()
    in_event = False
    in_paths = False
    out: list[str] = []
    for line in lines:
        if re.match(rf"^  {event}:\s*$", line):
            in_event = True
            in_paths = False
            continue
        if in_event and re.match(r"^  [A-Za-z0-9_]+:\s*$", line):
            break
        if in_event and re.match(r"^    paths:\s*$", line):
            in_paths = True
            continue
        if in_paths:
            if line.startswith("      - "):
                raw = line.strip()[2:].strip()
                if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "'\"":
                    raw = raw[1:-1]
                out.append(raw)
                continue
            if line.startswith("    ") and not line.startswith("      "):
                in_paths = False
    return out


def file_selected(patterns: list[str], path: str) -> bool:
    included = False
    for pat in patterns:
        neg = pat.startswith("!")
        if file_matches(pat, path):
            included = not neg
    return included


def workflow_runs(patterns: list[str], changed: list[str]) -> bool:
    return any(file_selected(patterns, p) for p in changed)


def write_site_kit(www: Path, installer: Path, out_dir: Path, commit: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    bundle = out_dir / "www"
    if bundle.exists():
        shutil.rmtree(bundle)
    shutil.copytree(www, bundle)
    inst_dest = out_dir / installer.name
    shutil.copy2(installer, inst_dest)
    files = [p for p in out_dir.rglob("*") if p.is_file() and p.name != "MANIFEST.json"]
    entries = []
    for p in sorted(files):
        rel = p.relative_to(out_dir).as_posix()
        digest = hashlib.sha256(p.read_bytes()).hexdigest()
        entries.append({"path": rel, "sha256": digest})
    manifest = {
        "kit": "jeeves-webhooks",
        "commit": commit,
        "files": entries,
    }
    dest = out_dir / "MANIFEST.json"
    dest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return dest


def run_site_kit(repo: Path, physical: Path, out_dir: Path, commit: str) -> None:
    www = repo / "jeeves" / "www" / "irc-ntsa"
    installer = repo / "jeeves" / "scripts" / "Install-BobWebhooks.ps1"
    ps = shutil.which("powershell") or shutil.which("pwsh")
    if not ps:
        raise KitError("powershell or pwsh required")
    proc = subprocess.run(
        [
            ps,
            "-NoProfile",
            "-File",
            str(installer),
            "-SiteKit",
            "-PhysicalPath",
            str(physical),
            "-Backend",
            "http://127.0.0.1:7700",
            "-WwwSource",
            str(www),
        ],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    if proc.returncode != 0:
        raise KitError(proc.stdout + "\n" + proc.stderr)
    cfg = physical / "web.config"
    assert_web_config(cfg)
    raw = cfg.read_bytes()
    again = subprocess.run(
        [
            ps,
            "-NoProfile",
            "-File",
            str(installer),
            "-SiteKit",
            "-PhysicalPath",
            str(physical),
            "-Backend",
            "http://127.0.0.1:7700",
            "-WwwSource",
            str(www),
        ],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    if again.returncode != 0:
        raise KitError(again.stdout + "\n" + again.stderr)
    if (physical / "web.config").read_bytes() != raw:
        raise KitError("second site-kit install changed web.config bytes")
    smoke_serve(physical)
    write_site_kit(www, installer, out_dir, commit)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--repo-root", default=".")
    p.add_argument("--physical", default="")
    p.add_argument("--out", required=True)
    p.add_argument("--commit", default="")
    args = p.parse_args(argv)
    repo = Path(args.repo_root).resolve()
    physical = Path(args.physical) if args.physical else Path(args.out) / "published"
    import os

    commit = args.commit or os.environ.get("WORKFLOW_COMMIT") or "unknown"
    try:
        run_site_kit(repo, physical, Path(args.out), commit)
    except KitError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

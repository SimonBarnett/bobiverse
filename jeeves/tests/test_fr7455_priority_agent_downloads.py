"""FR #7455: /downloads Priority Agent card from priority-mcp releases (page-time)."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

from repo_layout import REPO

WWW = REPO / "jeeves" / "www" / "irc-ntsa"
PAGE = WWW / "downloads" / "index.html"
SCRIPT = WWW / "downloads" / "priority-agent.js"
INSTALL = REPO / "jeeves" / "scripts" / "Install-BobWebhooks.ps1"
PACK = REPO / "common" / "scripts" / "Pack-BobiverseRelease.ps1"
SYNC = REPO / "common" / "scripts" / "Sync-BobiverseFromRepo.ps1"

HARDCODED_VER = re.compile(r"Priority Agent v\d+\.\d+\.\d+")


def test_fr7455_page_has_priority_card_and_external_script():
    html = PAGE.read_text(encoding="utf-8")
    assert 'data-product="priority-agent"' in html
    assert "Priority Agent" in html
    assert 'src="/downloads/priority-agent.js"' in html
    assert not HARDCODED_VER.search(html), "page must not hardcode a Priority Agent version"


def test_fr7455_script_file_exists_and_has_no_hardcoded_version():
    assert SCRIPT.is_file(), "downloads/priority-agent.js must ship beside the page"
    js = SCRIPT.read_text(encoding="utf-8")
    assert "SimonBarnett/priority-mcp" in js
    assert "per_page=100" in js
    assert "draft" in js and "prerelease" in js
    assert "textContent" in js
    assert "browser_download_url" not in js
    assert not HARDCODED_VER.search(js)
    assert "innerHTML" not in js


def test_fr7455_pack_and_sync_stage_www_beside_scripts():
    pack = PACK.read_text(encoding="utf-8-sig")
    sync = SYNC.read_text(encoding="utf-8-sig")
    assert "jeeves\\www" in pack or "jeeves/www" in pack
    assert "www" in pack and "Copy-Item" in pack
    assert "jeeves\\www" in sync or "jeeves/www" in sync
    install = INSTALL.read_text(encoding="utf-8-sig")
    assert "..\\www\\irc-ntsa" in install or "../www/irc-ntsa" in install


def test_fr7455_node_fake_releases_picks_numeric_latest(tmp_path: Path):
    node = shutil.which("node")
    assert SCRIPT.is_file()
    if not node:
        # Static gates above already fail before the change; Node proves the resolver.
        return
    releases = [
        {
            "name": "Priority Agent v1.0.0",
            "tag_name": "v1.0.0",
            "draft": False,
            "prerelease": False,
            "assets": [
                {"name": "PriorityAgent-1.0.0.exe"},
                {"name": "PriorityAgent-1.0.0.exe.sha256"},
            ],
        },
        {
            "name": "Priority Agent v1.2.0",
            "tag_name": "v1.2.0",
            "draft": False,
            "prerelease": False,
            "assets": [
                {"name": "PriorityAgent-1.2.0.exe"},
                {"name": "PriorityAgent-1.2.0.exe.sha256"},
            ],
        },
        {
            "name": "Priority Agent v9.9.9",
            "tag_name": "v9.9.9",
            "draft": True,
            "prerelease": False,
            "assets": [{"name": "skip.exe"}],
        },
        {
            "name": "Other Tool v3.0.0",
            "tag_name": "v3.0.0",
            "draft": False,
            "prerelease": False,
            "assets": [{"name": "other.exe"}],
        },
        {
            "name": "Priority Agent v1.1.9",
            "tag_name": "v1.1.9",
            "draft": False,
            "prerelease": True,
            "assets": [{"name": "pre.exe"}],
        },
    ]
    runner = tmp_path / "run_pa.js"
    runner.write_text(
        """
const fs = require('fs');
const vm = require('vm');
const path = process.argv[2];
const payload = JSON.parse(process.argv[3]);
const js = fs.readFileSync(path, 'utf8');
const versionEl = { textContent: '' };
const assetsEl = {
  children: [],
  firstChild: null,
  textContent: '',
  appendChild(c) {
    this.children.push(c);
    this.firstChild = this.children[0];
    return c;
  },
  removeChild(c) {
    this.children = this.children.filter(function (x) { return x !== c; });
    this.firstChild = this.children[0] || null;
    return c;
  }
};
const card = {
  querySelector(sel) {
    if (sel.indexOf('version') !== -1) return versionEl;
    if (sel.indexOf('assets') !== -1) return assetsEl;
    return null;
  }
};
function el(tag) {
  return { tagName: tag, className: '', href: '', textContent: '', setAttribute() {} };
}
const ctx = {
  console: console,
  document: { createElement: el, querySelector() { return card; } },
  fetch() {
    return Promise.resolve({ ok: true, json() { return Promise.resolve(payload); } });
  },
  globalThis: null
};
ctx.globalThis = ctx;
vm.createContext(ctx);
vm.runInContext(js, ctx);
const api = ctx.BobiversePriorityAgentDownloads;
if (!api) { console.error('missing export'); process.exit(2); }
api.refresh(card, ctx.fetch).then(function () {
  const out = {
    version: versionEl.textContent,
    hrefs: assetsEl.children.map(function (c) { return c.href; }),
    labels: assetsEl.children.map(function (c) { return c.textContent; }),
    classes: assetsEl.children.map(function (c) { return c.className; })
  };
  process.stdout.write(JSON.stringify(out));
}).catch(function (e) { console.error(e); process.exit(1); });
""",
        encoding="utf-8",
    )
    r = subprocess.run(
        [node, str(runner), str(SCRIPT), json.dumps(releases)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert "1.2.0" in out["version"]
    assert "1.0.0" not in out["version"]
    assert "9.9.9" not in out["version"]
    hrefs = " ".join(out["hrefs"])
    assert "priority-mcp/releases/download/v1.2.0/PriorityAgent-1.2.0.exe" in hrefs
    assert "PriorityAgent-1.2.0.exe.sha256" in hrefs
    assert "browser_download_url" not in hrefs
    assert any("btn-gold" in c for c in out["classes"])
    assert any("btn-ghost" in c for c in out["classes"])

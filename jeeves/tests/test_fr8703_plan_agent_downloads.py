"""FR #8703: Plan Agent card on /downloads from plan-v* releases."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from repo_layout import REPO

WWW = REPO / "jeeves" / "www" / "irc-ntsa"
PAGE = WWW / "downloads" / "index.html"
SCRIPT = WWW / "downloads" / "plan-agent.js"
MSI = "https://github.com/SimonBarnett/skills-visionary/releases/latest/download/PlanAgent.msi"


def test_fr8703_card_before_airc_and_no_static_msi():
    html = PAGE.read_text(encoding="utf-8")
    assert 'data-product="plan-agent"' in html
    assert "Plan Agent" in html
    assert "not yet released" in html
    assert 'src="/downloads/plan-agent.js"' in html
    plan_at = html.index('data-product="plan-agent"')
    airc_at = html.index('data-product="airc"')
    assert plan_at < airc_at
    # No broken installer link until a plan-v* release exists.
    assert "PlanAgent.msi" not in html
    assert "skills-visionary" not in html


def test_fr8703_script_pins_exact_latest_msi():
    js = SCRIPT.read_text(encoding="utf-8")
    assert MSI in js
    assert "MSI_HREF + '.sha256'" in js
    assert "plan-v" in js
    assert "not yet released" in js
    assert "innerHTML" not in js
    assert "published_at" in js


def _run(node: str, tmp_path: Path, payload: list, name: str) -> dict:
    runner = tmp_path / name
    runner.write_text(
        """
const fs = require('fs');
const vm = require('vm');
const path = process.argv[2];
const payload = JSON.parse(process.argv[3]);
const js = fs.readFileSync(path, 'utf8');
const versionEl = { textContent: 'not yet released' };
const assetsEl = {
  children: [], firstChild: null,
  appendChild(c) { this.children.push(c); this.firstChild = this.children[0]; return c; },
  removeChild(c) {
    this.children = this.children.filter(function (x) { return x !== c; });
    this.firstChild = this.children[0] || null;
    return c;
  }
};
const card = {
  nodes: [],
  querySelector(sel) {
    if (sel.indexOf('version') !== -1) return versionEl;
    if (sel.indexOf('assets') !== -1) return assetsEl;
    return null;
  },
  appendChild(c) { this.nodes.push(c); return c; }
};
function el() {
  return { className: '', href: '', textContent: '', attrs: {}, setAttribute(k, v) { this.attrs[k] = v; } };
}
const ctx = {
  console: console,
  document: {
    createElement: el,
    querySelector() { return card; },
    readyState: 'complete',
    addEventListener() {}
  },
  fetch() {
    return Promise.resolve({ ok: true, json() { return Promise.resolve(payload); } });
  }
};
ctx.globalThis = ctx;
vm.createContext(ctx);
vm.runInContext(js, ctx);
const api = ctx.BobiversePlanAgentDownloads;
if (!api) { console.error('missing export'); process.exit(2); }
api.refresh(card, ctx.fetch).then(function () {
  const notes = card.nodes.filter(function (n) {
    return n.attrs && n.attrs['data-role'] === 'release-notes';
  })[0];
  process.stdout.write(JSON.stringify({
    version: versionEl.textContent,
    hrefs: assetsEl.children.map(function (c) { return c.href; }),
    labels: assetsEl.children.map(function (c) { return c.textContent; }),
    notes: notes ? notes.href : ''
  }));
}).catch(function (e) { console.error(e); process.exit(1); });
""",
        encoding="utf-8",
    )
    r = subprocess.run(
        [node, str(runner), str(SCRIPT), json.dumps(payload)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_fr8703_release_sets_exact_msi_href(tmp_path: Path):
    node = shutil.which("node")
    if not node:
        return
    payload = [
        {
            "tag_name": "plan-v1.2.0",
            "draft": False,
            "prerelease": False,
            "published_at": "2026-11-21T12:00:00Z",
            "assets": [{"name": "PlanAgent.msi"}],
        },
        {
            "tag_name": "v9.9.9",
            "draft": False,
            "prerelease": False,
            "published_at": "2026-11-20T00:00:00Z",
            "assets": [],
        },
    ]
    out = _run(node, tmp_path, payload, "run_plan.js")
    assert out["version"] == "plan-v1.2.0 · 2026-11-21"
    assert MSI in out["hrefs"]
    assert MSI + ".sha256" in out["hrefs"]
    assert out["notes"].endswith("/releases/latest")


def test_fr8703_no_plan_release_has_no_link(tmp_path: Path):
    node = shutil.which("node")
    if not node:
        return
    payload = [
        {
            "tag_name": "v1.0.0",
            "draft": False,
            "prerelease": False,
            "published_at": "2026-01-01T00:00:00Z",
            "assets": [{"name": "Other.msi"}],
        },
        {
            "tag_name": "plan-v0.1.0",
            "draft": True,
            "prerelease": False,
            "published_at": "2026-01-02T00:00:00Z",
            "assets": [],
        },
    ]
    out = _run(node, tmp_path, payload, "run_plan_empty.js")
    assert out["version"] == "not yet released"
    assert out["hrefs"] == []
    assert out["notes"] == ""

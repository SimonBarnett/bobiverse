"""Generate jeeves/www/irc-ntsa static HTML from bob_webhook_docs registry (FR #6453)."""
from __future__ import annotations

from html import escape
from pathlib import Path

import bob_webhook_docs as d

CSS = """
body{font-family:system-ui,Segoe UI,sans-serif;margin:2rem;max-width:52rem;line-height:1.45;color:#122}
header{margin-bottom:1.5rem}
h1{font-size:1.6rem;margin:0 0 .4rem}
h2{font-size:1.2rem;margin-top:1.6rem;border-bottom:1px solid #ccd;padding-bottom:.2rem}
a{color:#0645ad}
.meta{color:#456;font-size:.95rem}
pre{background:#f4f6f8;padding:.8rem;overflow:auto;border:1px solid #dde}
table{border-collapse:collapse;width:100%}
td,th{border:1px solid #ccd;padding:.4rem .55rem;text-align:left;vertical-align:top}
.nav{margin:.8rem 0 1.2rem}
.badge{display:inline-block;background:#e8eef7;border:1px solid #b9c7dd;border-radius:4px;padding:0 .35rem;font-size:.85rem}
"""


def page(title: str, body: str, *, crumbs_html: str = "") -> str:
    crumb = f" · {crumbs_html}" if crumbs_html else ""
    return (
        "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n"
        "<meta charset=\"utf-8\"/>\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"/>\n"
        f"<title>{escape(title)} — bob.ntsa.uk</title>\n"
        f"<style>{CSS}</style>\n</head>\n<body>\n<header>\n"
        f"<p class=\"meta\"><a href=\"/\">bob.ntsa.uk</a>{crumb}</p>\n"
        f"<h1>{escape(title)}</h1>\n</header>\n{body}\n"
        "<footer class=\"meta\" style=\"margin-top:2.5rem\">"
        "FR #6453 · static read-only docs · no secrets</footer>\n"
        "</body>\n</html>\n"
    )


def render_entries(entries: list[d.DocEntry]) -> str:
    parts: list[str] = []
    for e in entries:
        parts.append(
            f"<section id=\"{escape(e.slug)}\">\n"
            f"<h2>{escape(e.title)} <span class=\"badge\">{escape(e.method)} "
            f"{escape(e.path)}</span></h2>\n"
            f"<p><strong>Direction:</strong> {escape(e.direction)} · "
            f"<strong>Purpose:</strong> {escape(e.purpose)}</p>\n"
            f"<p><strong>Who calls it:</strong> {escape(e.callers)}</p>\n"
            f"<p><strong>Auth (named only):</strong> {escape(e.auth)}</p>\n"
            f"<p><strong>Request schema:</strong> {escape(e.request_schema)}</p>\n"
            f"<p><strong>Response schema:</strong> {escape(e.response_schema)}</p>\n"
            f"<p><strong>Status codes:</strong> {escape(e.status_codes)}</p>\n"
            f"<p><strong>Retry / idempotency:</strong> {escape(e.retry_idempotency)}</p>\n"
            f"<p><strong>Rate limits:</strong> {escape(e.rate_limits)}</p>\n"
            f"<p><strong>Reachability:</strong> {escape(e.reachability)}</p>\n"
            f"<p><strong>Source:</strong> <code>{escape(e.source)}</code> · "
            f"<strong>Related:</strong> {escape(e.fr)}</p>\n"
            "<p><strong>Redacted example</strong></p>\n"
            f"<pre>{escape(e.example_request)}</pre>\n"
            "</section>\n"
        )
    return "\n".join(parts)


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    www = d.www_root(root)
    (www / "docs" / "webhooks").mkdir(parents=True, exist_ok=True)

    titles = {
        "docs/webhooks/report.html": "Report / digest webhook",
        "docs/webhooks/hours.html": "Hours API",
        "docs/webhooks/intake.html": "Intake webhook",
        "docs/webhooks/jira.html": "Jira webhook",
        "docs/webhooks/git.html": "GitHub git webhook",
        "docs/webhooks/digest-local.html": "Local digest alias",
        "docs/webhooks/health-local.html": "BobCallback health",
        "docs/webhooks/outbound-stall-wake.html": "Outbound stall / ticket-closure wake",
    }

    for rel, entries in d.entries_by_html().items():
        title = titles.get(rel, entries[0].title)
        body = (
            '<p class="nav"><a href="index.html">Webhooks &amp; API index</a></p>\n'
            + render_entries(entries)
        )
        path = www / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            page(
                title,
                body,
                crumbs_html='<a href="index.html">Webhooks</a> · ' + escape(title),
            ),
            encoding="utf-8",
        )
        print("wrote", rel)

    rows: list[str] = []
    for e in d.all_entries():
        rows.append(
            "<tr>"
            f"<td>{escape(e.direction)}</td>"
            f"<td><code>{escape(e.method)}</code></td>"
            f'<td><a href="{escape(Path(e.html_rel).name)}"><code>{escape(e.path)}</code></a></td>'
            f"<td>{escape(e.title)}</td>"
            "</tr>"
        )
    hub_body = (
        "<p>Human-readable documentation for inbound BobCallback routes on "
        "<code>bob.ntsa.uk</code>, local-only aliases, and outbound Jeeves wake/stall "
        "callbacks. Tested against route constants in <code>bobcallback</code> / "
        "<code>bobhours</code> (FR #6453).</p>\n"
        "<p class=\"meta\">Public HTTP base: <code>https://bob.ntsa.uk</code>. "
        "IRC stays on <code>irc.ntsa.uk</code>. No route requires a shared password; "
        "protection is schema, size, rate, roster, and owner allow-lists.</p>\n"
        "<table>\n<thead><tr><th>Dir</th><th>Method</th><th>Path</th><th>Doc</th>"
        "</tr></thead>\n<tbody>\n"
        + "".join(rows)
        + "</tbody>\n</table>\n"
        "<p>Operator markdown twin: <code>jeeves/docs/webhooks.md</code> in the "
        "bobiverse repo.</p>\n"
    )
    (www / "docs" / "webhooks" / "index.html").write_text(
        page("Webhooks & API", hub_body, crumbs_html="Webhooks &amp; API"),
        encoding="utf-8",
    )
    print("wrote docs/webhooks/index.html")

    index_body = """
<p><strong>bobiverse acme</strong></p>
<p>Public HTTP front door for Bobiverse fleet webhooks (IIS + Cloudflare).
API JSON lives under <code>/bob/v1/*</code>.</p>
<h2>Webhooks &amp; API</h2>
<p>Read-only documentation for each inbound and outbound webhook:</p>
<ul>
<li><a href="docs/webhooks/index.html">Webhooks &amp; API index</a></li>
<li><a href="docs/webhooks/report.html">Report / digest</a> — <code>GET|POST /bob/v1/report</code></li>
<li><a href="docs/webhooks/git.html">GitHub git</a> — <code>POST /bob/v1/git</code></li>
<li><a href="docs/webhooks/intake.html">Intake / harvest</a> — <code>POST /bob/v1/intake</code></li>
<li><a href="docs/webhooks/jira.html">Jira</a> — <code>GET|POST /bob/v1/jira</code></li>
<li><a href="docs/webhooks/hours.html">Hours</a> — <code>GET|POST /bob/v1/hours</code></li>
<li><a href="docs/webhooks/outbound-stall-wake.html">Outbound stall / ticket-closure wake</a> (FR #6391 / #6439)</li>
<li><a href="docs/webhooks/digest-local.html">Local digest alias</a> · <a href="docs/webhooks/health-local.html">Local /health</a></li>
</ul>
<p class="meta">Live digest JSON: <a href="/bob/v1/report"><code>/bob/v1/report</code></a></p>
"""
    (www / "index.html").write_text(page("bobiverse acme", index_body), encoding="utf-8")
    print("wrote index.html")
    text = (www / "index.html").read_text(encoding="utf-8")
    if "bobiverse acme" not in text.lower():
        raise SystemExit("index missing bobiverse acme marker")
    print("ok", www)


if __name__ == "__main__":
    main()

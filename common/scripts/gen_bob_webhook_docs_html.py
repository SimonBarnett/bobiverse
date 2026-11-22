"""Generate jeeves/www/irc-ntsa static HTML from bob_webhook_docs registry (FR #6453).

FR #7478: webhook docs pages emit the NTSA logo brand anchor (href=/) and favicon.
Does not overwrite the redesigned home (jeeves/www/irc-ntsa/index.html).
"""
from __future__ import annotations

from html import escape
from pathlib import Path

import bob_webhook_docs as d

CSS = """
body{font-family:system-ui,Segoe UI,sans-serif;margin:2rem;max-width:52rem;line-height:1.45;color:#122}
header{margin-bottom:1.5rem;display:flex;flex-wrap:wrap;align-items:center;gap:.75rem 1rem}
h1{font-size:1.6rem;margin:0 0 .4rem;flex:1 1 100%}
h2{font-size:1.2rem;margin-top:1.6rem;border-bottom:1px solid #ccd;padding-bottom:.2rem}
a{color:#0645ad}
.meta{color:#456;font-size:.95rem}
pre{background:#f4f6f8;padding:.8rem;overflow:auto;border:1px solid #dde}
table{border-collapse:collapse;width:100%}
td,th{border:1px solid #ccd;padding:.4rem .55rem;text-align:left;vertical-align:top}
.nav{margin:.8rem 0 1.2rem}
.badge{display:inline-block;background:#e8eef7;border:1px solid #b9c7dd;border-radius:4px;padding:0 .35rem;font-size:.85rem}
a.brand{display:inline-flex;align-items:center;gap:.55rem;text-decoration:none;color:inherit}
a.brand:focus{outline:2px solid #0645ad;outline-offset:2px}
.brand-logo{display:block;flex:0 0 auto}
.brand-text{display:flex;flex-direction:column;line-height:1.2;font-size:.92rem}
.brand-text strong{font-size:1rem}
@media (max-width:400px){header{gap:.5rem}.brand-text{font-size:.85rem}}
"""


def _write_utf8_lf(path: Path, text: str) -> None:
    """UTF-8 without BOM, LF newlines (checked-in pages are LF)."""
    data = text.replace("\r\n", "\n").replace("\r", "\n")
    if not data.endswith("\n"):
        data += "\n"
    path.write_bytes(data.encode("utf-8"))


def page(title: str, body: str, *, crumbs_html: str = "") -> str:
    crumb = f' <span class="meta">· {crumbs_html}</span>' if crumbs_html else ""
    brand = (
        '<a class="brand" href="/">'
        '<img class="brand-logo" src="/jeeves/assets/ntsa-gut-logo.png" '
        'alt="NTSA" width="36" height="36"/>'
        '<span class="brand-text"><strong>bob.ntsa.uk</strong>'
        "<span>Webhooks</span></span>"
        f"</a>{crumb}"
    )
    return (
        "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n"
        "<meta charset=\"utf-8\"/>\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"/>\n"
        f"<title>{escape(title)} — bob.ntsa.uk</title>\n"
        '<link rel="icon" href="/favicon.ico" type="image/x-icon"/>\n'
        f"<style>{CSS}</style>\n</head>\n<body>\n<header>\n"
        f"{brand}\n"
        f"<h1>{escape(title)}</h1>\n</header>\n{body}\n"
        "<footer class=\"meta\" style=\"margin-top:2.5rem\">"
        "FR #6453 · static read-only docs · no secrets</footer>\n"
        "</body>\n</html>\n"
    )


def render_entries(entries: list[d.DocEntry]) -> str:
    parts: list[str] = []
    for e in entries:
        coming = getattr(e, "status", "live") == "coming"
        status_badge = (
            ' <span class="badge">Coming — not served</span>' if coming else ""
        )
        parts.append(
            f"<section id=\"{escape(e.slug)}\">\n"
            f"<h2>{escape(e.title)} <span class=\"badge\">{escape(e.method)} "
            f"{escape(e.path)}</span>{status_badge}</h2>\n"
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
        "docs/webhooks/models.html": "Models webhook",
        "docs/webhooks/builds.html": "Builds catalog",
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
        _write_utf8_lf(
            path,
            page(
                title,
                body,
                crumbs_html='<a href="index.html">Webhooks</a> · ' + escape(title),
            ),
        )
        print("wrote", rel)

    rows: list[str] = []
    for e in d.all_entries():
        coming = getattr(e, "status", "live") == "coming"
        title_cell = escape(e.title) + (
            ' <span class="badge">Coming — not served</span>' if coming else ""
        )
        rows.append(
            "<tr>"
            f"<td>{escape(e.direction)}</td>"
            f"<td><code>{escape(e.method)}</code></td>"
            f'<td><a href="{escape(Path(e.html_rel).name)}"><code>{escape(e.path)}</code></a></td>'
            f"<td>{title_cell}</td>"
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
    _write_utf8_lf(
        www / "docs" / "webhooks" / "index.html",
        page("Webhooks & API", hub_body, crumbs_html="Webhooks &amp; API"),
    )
    print("wrote docs/webhooks/index.html")

    # FR #7467 / #7478 / #7488: never write or clobber the redesigned home
    # (jeeves/www/irc-ntsa/index.html). Cards live in that hand-edited file;
    # this generator only owns docs/webhooks/*.html.
    site_index = www / "index.html"
    if site_index.is_file():
        print("kept existing front-page index.html")
    else:
        print("skipped front-page index.html (no seed; redesigned home is hand-edited)")
    print("ok", www)


if __name__ == "__main__":
    main()

"""FR #6453: registry of bob.ntsa.uk webhook/API docs (tested against live routes).

Static HTML lives under ``jeeves/www/irc-ntsa/`` and is copied to the IIS site
physical path by ``Install-BobWebhooks.ps1``. Docs are read-only; they do not
change route behaviour.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import bobcallback
import bobhours


@dataclass(frozen=True)
class DocEntry:
    slug: str
    title: str
    method: str
    path: str
    direction: str  # in | out | local
    purpose: str
    callers: str
    auth: str
    request_schema: str
    response_schema: str
    example_request: str
    status_codes: str
    retry_idempotency: str
    rate_limits: str
    reachability: str
    source: str
    fr: str
    html_rel: str


def www_root(repo_root: Path | None = None) -> Path:
    root = repo_root or Path(__file__).resolve().parents[2]
    return root / "jeeves" / "www" / "irc-ntsa"


def _inbound() -> list[DocEntry]:
    return [
        DocEntry(
            slug="report-get",
            title="Fleet digest (GET report)",
            method="GET",
            path=bobcallback.REPORT_PATH,
            direction="in",
            purpose="Public fleet digest JSON for TipForm, UAT, and operators.",
            callers="Browsers, TipForm, chair health probes, fleet scripts.",
            auth="None. Open GET on Cloudflare front-door.",
            request_schema="No body. Optional query unused.",
            response_schema="JSON object: machines, jobs, fuels, chair fields (shape evolves; treat unknown keys as opaque).",
            example_request='GET https://bob.ntsa.uk/bob/v1/report\nAccept: application/json',
            status_codes="200 OK; 503 when digest.lock is wedged (retry).",
            retry_idempotency="Safe to retry. Idempotent read.",
            rate_limits="Cloudflare + reverse proxy only (no app per-IP GET quota).",
            reachability="Public via https://bob.ntsa.uk (Cloudflare). Local :7700 also serves aliases.",
            source="common/scripts/bobcallback.py, bobreport.py",
            fr="FR #149 / #174 / #2458",
            html_rel="docs/webhooks/report.html",
        ),
        DocEntry(
            slug="report-post",
            title="Status callback (POST report)",
            method="POST",
            path=bobcallback.REPORT_PATH,
            direction="in",
            purpose="TipForm / ear status merge, worker ops, shop-down.",
            callers="Fleet TipForm and ears on registered machines.",
            auth="None. Machine id must appear on the Jeeves-published ChanServ roster (registered-machines.json). Stray X-Bob-Secret ignored.",
            request_schema='JSON object with op in {merge, delete-worker, shop-down, worker-*} plus machine fields. Legacy bodies without op are normalized.',
            response_schema="JSON ok / error; empty 204 on some ops.",
            example_request=(
                "POST https://bob.ntsa.uk/bob/v1/report\n"
                "Content-Type: application/json\n\n"
                '{"op":"merge","machine":"example-host","pcent":12}'
            ),
            status_codes="200/204 success; 400 schema; 403 not on roster; 413 too large; 429 rate; 503 lock.",
            retry_idempotency="merge is upsert-style; callers may retry on 503/429 with backoff.",
            rate_limits=f"Default {bobcallback.DEFAULT_REPORT_RATE_PER_MIN}/min per machine (env {bobcallback.REPORT_RATE_ENV}).",
            reachability="Public Cloudflare POST to bob.ntsa.uk; rewritten to BobCallback :7700.",
            source="common/scripts/bobcallback.py",
            fr="FR #174 / roster gate",
            html_rel="docs/webhooks/report.html",
        ),
        DocEntry(
            slug="git",
            title="GitHub git webhook",
            method="POST",
            path=bobcallback.GIT_WEBHOOK_PATH,
            direction="in",
            purpose="GitHub delivery into the digest job queue (issues, PRs, checks, comments).",
            callers="GitHub repository webhooks (allow-listed owners).",
            auth="None shared secret. Owner allow-list via BOB_GIT_OWNERS (default SimonBarnett). Event must be accepted.",
            request_schema="GitHub webhook JSON + X-GitHub-Event / X-GitHub-Delivery headers.",
            response_schema="204/202 accepted; 403 owner/event; 429 rate.",
            example_request=(
                "POST https://bob.ntsa.uk/bob/v1/git\n"
                "Content-Type: application/json\n"
                "X-GitHub-Event: issues\n\n"
                '{"action":"opened","repository":{"full_name":"SimonBarnett/example"},'
                '"issue":{"number":1,"title":"example"}}'
            ),
            status_codes="202/204 accepted; 400 bad JSON; 403 owner/event; 413; 429.",
            retry_idempotency="GitHub retries deliveries; chair also !resync / hourly github-resync fallback.",
            rate_limits=f"{bobcallback.GIT_RATE_PER_MIN}/min per repository.",
            reachability="Public Cloudflare. Never post git events to /bob/v1/report.",
            source="common/scripts/bobcallback.py, gitclaim.py",
            fr="FR #5170 / #4711 / #4955",
            html_rel="docs/webhooks/git.html",
        ),
        DocEntry(
            slug="intake",
            title="Intake / harvest",
            method="POST",
            path=bobcallback.INTAKE_PATH,
            direction="in",
            purpose="File issues/FRs/skills/harvest lessons without gh on the box.",
            callers="Report-BobiverseIntakeIssue.ps1, harvest, MONITORING, crash reporters.",
            auth="None. Open endpoint; schema + size + rate gates. repo=owner/name required.",
            request_schema='JSON: kind in {issue,fr,skill,harvest}, title, body, repo (owner/name required), optional idempotency_key.',
            response_schema="HTTP 202 with intake receipt JSON (id, queued flags). Never returns secrets.",
            example_request=(
                "POST https://bob.ntsa.uk/bob/v1/intake\n"
                "Content-Type: application/json\n\n"
                '{"kind":"issue","repo":"SimonBarnett/bobiverse","title":"example",'
                '"body":"what / where / evidence","idempotency_key":"example-key-1"}'
            ),
            status_codes="202 accepted; 400 schema/missing repo; 413; 429. Offline clients queue locally and Flush.",
            retry_idempotency="idempotency_key + existing intake/<id> PR dedupe. Safe to retry.",
            rate_limits="Per-source intake rate limiter (see intake.py).",
            reachability="Public Cloudflare. Path is /bob/v1/intake (not /bob/v1/harvest).",
            source="common/scripts/intake.py, bobcallback.py",
            fr="FR #3135 / #2595",
            html_rel="docs/webhooks/intake.html",
        ),
        DocEntry(
            slug="intake-get",
            title="Intake receipt probe (GET)",
            method="GET",
            path=bobcallback.INTAKE_PATH + "/{id}",
            direction="in",
            purpose="Lookup a prior intake id / health probe path.",
            callers="Chair webhook health (jeeves-health-probe), operators.",
            auth="None.",
            request_schema="Path id only.",
            response_schema="200/404 JSON or empty depending on id.",
            example_request="GET https://bob.ntsa.uk/bob/v1/intake/jeeves-health-probe",
            status_codes="200 or 404.",
            retry_idempotency="Safe GET.",
            rate_limits="Proxy only.",
            reachability="Public Cloudflare (ARR rewrite of /bob/v1/intake*).",
            source="common/scripts/bobcallback.py",
            fr="FR #1014 health probe",
            html_rel="docs/webhooks/intake.html",
        ),
        DocEntry(
            slug="jira",
            title="Jira-style intake",
            method="POST",
            path=bobcallback.JIRA_PATH,
            direction="in",
            purpose="Customer Jira webhooks into fleet intake/announce path.",
            callers="Jira Cloud/Data Center webhooks.",
            auth="None shared Bob secret. Schema + size + rate gates.",
            request_schema="Jira webhook JSON (issue events). See jira_webhook.py.",
            response_schema="202/200 JSON ok; 400 bad body.",
            example_request=(
                "POST https://bob.ntsa.uk/bob/v1/jira\n"
                "Content-Type: application/json\n\n"
                '{"webhookEvent":"jira:issue_updated","issue":{"key":"EX-1"}}'
            ),
            status_codes="200/202; 400; 413; 429.",
            retry_idempotency="Jira retries; receiver validates schema.",
            rate_limits="Per-source limiter in jira_webhook / bobcallback.",
            reachability="Public Cloudflare.",
            source="common/scripts/jira_webhook.py",
            fr="FR #190",
            html_rel="docs/webhooks/jira.html",
        ),
        DocEntry(
            slug="jira-get",
            title="Jira health (GET)",
            method="GET",
            path=bobcallback.JIRA_PATH,
            direction="in",
            purpose="Liveness for chair webhook health probes.",
            callers="ChairJobs webhook health.",
            auth="None.",
            request_schema="No body.",
            response_schema="200 JSON ok.",
            example_request="GET https://bob.ntsa.uk/bob/v1/jira",
            status_codes="200.",
            retry_idempotency="Safe GET.",
            rate_limits="Proxy only.",
            reachability="Public Cloudflare.",
            source="common/scripts/jira_webhook.py",
            fr="FR #190",
            html_rel="docs/webhooks/jira.html",
        ),
        DocEntry(
            slug="hours-post",
            title="Hours create",
            method="POST",
            path=bobhours.HOURS_PATH,
            direction="in",
            purpose="Create a work-time entry for timesheet drafting.",
            callers="Agents / operators posting partial work logs.",
            auth="None. Rejects obvious credential fields; never logs request bodies.",
            request_schema="JSON with idempotency_key, user, timing fields (see bobhours.py).",
            response_schema="JSON entry id / status.",
            example_request=(
                "POST https://bob.ntsa.uk/bob/v1/hours\n"
                "Content-Type: application/json\n\n"
                '{"idempotency_key":"example-hours-1","user":"ExampleUser",'
                '"minutes":30,"note":"example"}'
            ),
            status_codes="200/201; 400 schema/credentials; 413; 429.",
            retry_idempotency="idempotency_key required for create; safe retry.",
            rate_limits=f"Default {bobhours.DEFAULT_HOURS_RATE_PER_MIN}/min (env {bobhours.HOURS_RATE_ENV}).",
            reachability="Public Cloudflare.",
            source="common/scripts/bobhours.py",
            fr="FR #3450",
            html_rel="docs/webhooks/hours.html",
        ),
        DocEntry(
            slug="hours-get",
            title="Hours list / summary / export",
            method="GET",
            path=bobhours.HOURS_PATH,
            direction="in",
            purpose="List, day summary, or export hours entries.",
            callers="Operators and timesheet tools.",
            auth="None.",
            request_schema="Query: user, from, to, date, format=csv|json, optional filters.",
            response_schema="JSON list/summary or CSV export.",
            example_request=(
                "GET https://bob.ntsa.uk/bob/v1/hours?user=ExampleUser&from=2026-01-01&to=2026-01-02\n"
                "GET https://bob.ntsa.uk/bob/v1/hours/summary?user=ExampleUser&date=2026-01-01\n"
                "GET https://bob.ntsa.uk/bob/v1/hours/export?user=ExampleUser&format=csv"
            ),
            status_codes="200; 400 bad query.",
            retry_idempotency="Safe GET.",
            rate_limits="Proxy only for GET.",
            reachability="Public Cloudflare.",
            source="common/scripts/bobhours.py",
            fr="FR #3450",
            html_rel="docs/webhooks/hours.html",
        ),
        DocEntry(
            slug="hours-actions",
            title="Hours heartbeat / close / withdraw",
            method="POST",
            path=bobhours.HOURS_PATH + "/{id}/heartbeat|close|withdraw",
            direction="in",
            purpose="Heartbeat an open entry, close it, or soft-withdraw.",
            callers="Agents holding an open hours id.",
            auth="None. Schema + rate gates.",
            request_schema="JSON body (close may include note); id in path.",
            response_schema="JSON status.",
            example_request=(
                "POST https://bob.ntsa.uk/bob/v1/hours/example-id/heartbeat\n"
                "Content-Type: application/json\n\n{}"
            ),
            status_codes="200; 400; 404; 429.",
            retry_idempotency="heartbeat safe; close/withdraw are state transitions (retry carefully).",
            rate_limits=f"Shares hours write rate ({bobhours.DEFAULT_HOURS_RATE_PER_MIN}/min default).",
            reachability="Public Cloudflare.",
            source="common/scripts/bobhours.py",
            fr="FR #3450",
            html_rel="docs/webhooks/hours.html",
        ),
    ]


def _local() -> list[DocEntry]:
    return [
        DocEntry(
            slug="digest-local",
            title="Local digest alias",
            method="GET",
            path=bobcallback.DIGEST_PATH,
            direction="local",
            purpose="Same JSON as GET report; local BobCallback only.",
            callers="Local tools on the chair host.",
            auth="None.",
            request_schema="No body.",
            response_schema="Same as GET /bob/v1/report.",
            example_request="GET http://127.0.0.1:7700/bob/v1/digest",
            status_codes="200 local; public IIS historically 404 for /bob/v1/digest unless rewrite present.",
            retry_idempotency="Safe GET.",
            rate_limits="n/a",
            reachability="Loopback / LAN to :7700. Prefer public /bob/v1/report on bob.ntsa.uk.",
            source="common/scripts/bobcallback.py",
            fr="FR #149 / #354",
            html_rel="docs/webhooks/digest-local.html",
        ),
        DocEntry(
            slug="health-local",
            title="BobCallback health",
            method="GET",
            path=bobcallback.HEALTH_PATH,
            direction="local",
            purpose="Liveness + digest.lock age for watchdog.",
            callers="Local watchdog thread, ops on chair host.",
            auth="None.",
            request_schema="No body.",
            response_schema="JSON ok, lock_age_s, last_digest_write, pid fields.",
            example_request="GET http://127.0.0.1:7700/health",
            status_codes="200.",
            retry_idempotency="Safe GET.",
            rate_limits="n/a",
            reachability="Not published on IIS front-door (404 on bob.ntsa.uk).",
            source="common/scripts/bobcallback.py",
            fr="FR #1136",
            html_rel="docs/webhooks/health-local.html",
        ),
    ]


def _outbound() -> list[DocEntry]:
    return [
        DocEntry(
            slug="outbound-stall-wake",
            title="Jeeves stall / ticket-closure wake (outbound)",
            method="POST",
            path="https://<operator-configured-wake-host>/ (JEEVES_TICKET_CLOSURE_WAKE_URL)",
            direction="out",
            purpose="HTTPS wake callbacks when MONITORING detects stalls or ticket-closure events (same transport as FR #6391).",
            callers="jeeves/tools/monitor/ticket_closure.py and common/scripts/stall_callbacks.py on the chair.",
            auth="Named only: whatever the wake URL operator configured (Bearer or shared header). Never documented as a literal secret here.",
            request_schema="JSON wake brief (event, subject, summary). No passwords.",
            response_schema="2xx accepted; non-2xx retried with backoff.",
            example_request=(
                "POST https://example-wake.example/hook\n"
                "Authorization: Bearer REDACTED\n"
                "Content-Type: application/json\n\n"
                '{"event":"stall","subject":"example","summary":"redacted"}'
            ),
            status_codes="2xx ok; connection errors queued/debounced.",
            retry_idempotency="Debounced per event/subject; drain_pending retries.",
            rate_limits="Internal backoff (WAKE_BACKOFF_S .. WAKE_BACKOFF_MAX_S).",
            reachability="Outbound from chair only. Not an inbound bob.ntsa.uk route.",
            source="common/scripts/stall_callbacks.py, jeeves/tools/monitor/ticket_closure.py",
            fr="FR #6391 / #6439",
            html_rel="docs/webhooks/outbound-stall-wake.html",
        ),
    ]


def inbound_entries() -> list[DocEntry]:
    return list(_inbound())


def all_entries() -> list[DocEntry]:
    return _inbound() + _local() + _outbound()


def entries_by_html() -> dict[str, list[DocEntry]]:
    out: dict[str, list[DocEntry]] = {}
    for e in all_entries():
        out.setdefault(e.html_rel, []).append(e)
    return out


def iter_slugs() -> Iterable[str]:
    for e in all_entries():
        yield e.slug

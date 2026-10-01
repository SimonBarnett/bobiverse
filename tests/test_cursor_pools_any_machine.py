"""#60: cursor pools readable on any machine; bob reports pools/overspend/grok to the digest per machine.

Fixture shapes are scrubbed copies of what ionos (win-mpre8vi4u6u, works) and MarchHare (no groups) hold.
No secrets: tokens are fake, the AES key is random per test.
"""
from __future__ import annotations

import base64
import importlib.util
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

import bobreport
import registered_machines as rm

ROOT = Path(__file__).resolve().parents[1]
TRAY = ROOT / "third_party" / "bob-tray"
USAGE_PY = TRAY / "tools" / "Get-CursorAgentUsage.py"
PS = shutil.which("powershell") or shutil.which("pwsh")
needs_ps = pytest.mark.skipif(not PS or os.name != "nt", reason="needs Windows PowerShell")

# ionos: GetCurrentPeriodUsage + GetSandUsageStatus bodies (values scrubbed to the same magnitudes).
IONOS_FIXTURE = {
    "period": {
        "billingCycleEnd": "1792171381000",  # 2026-10-16T17:23:01Z
        "planUsage": {"autoPercentUsed": 100, "apiPercentUsed": 100, "bonusSpend": 285224, "remainingBonus": False},
        "spendLimitUsage": {"individualUsed": 20011, "individualLimit": 20000},
    },
    "sand": {"usagePercent": 0.06, "nextResetTimestampUtc": "2026-10-07T17:23:58.025Z",
             "onDemandSettings": {"enabled": True}},
}
# MarchHare: cursor-account.json has ONLY label + period end, nothing about groups.
MARCHHARE_ACCOUNT_FILE = {"label": "0%", "period_end": "2026-10-16T17:23:01Z", "updated_at": "2026-10-01T10:00:00Z"}


def load_usage_module():
    spec = importlib.util.spec_from_file_location("get_cursor_agent_usage", USAGE_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def usage():
    return load_usage_module()


@pytest.fixture(autouse=True)
def _fx_rate(monkeypatch):
    monkeypatch.setenv("BOB_CURSOR_USD_GBP_RATE", "0.7538")


# ------------------------------------------------------------------ reader (python)
def test_reader_is_shipped_with_the_tray():
    assert USAGE_PY.is_file(), "marchhare had no tools\\Get-CursorAgentUsage.py -> no groups"
    sync = (ROOT / "scripts" / "Sync-BobTrayFromAgenticBuild.ps1").read_text(encoding="utf-8-sig")
    assert "Get-CursorAgentUsage.py" in sync  # preserved across re-sync


def test_ionos_shape_gives_groups_overspend_and_periods(usage):
    d = usage.build_usage_doc(IONOS_FIXTURE["period"], IONOS_FIXTURE["sand"])
    g = {x["id"]: x for x in d["cursor_spending_groups"]}
    assert g["grok-chat"]["remaining_pct"] == 94
    assert g["high-cost-models"]["remaining_pct"] == 0 and g["auto"]["remaining_pct"] == 0
    assert d["overage_usd"] == 200.11 and d["overage_gbp"] == 150.84
    assert d["overspend_state"] == "at-limit"
    assert d["on_demand_limit_cents"] == 20000 and d["on_demand_remaining_pct"] == 0
    assert d["period_end"] == "2026-10-16T17:23:01Z"
    assert d["sand_period_end"] == "2026-10-07T17:23:58.025Z"


def test_overspend_states(usage):
    assert usage.overspend_state(0, 20000) == "none"
    assert usage.overspend_state(500, 20000) == "over"
    assert usage.overspend_state(20000, 20000) == "at-limit"
    assert usage.overspend_state(None, None) == "unknown"


def test_fixture_env_runs_end_to_end(tmp_path):
    fx = tmp_path / "f.json"
    fx.write_text(json.dumps(IONOS_FIXTURE))
    env = dict(os.environ, BOB_CURSOR_AGENT_FIXTURE=str(fx), BOB_CURSOR_USD_GBP_RATE="0.7538")
    out = subprocess.run([shutil.which("python") or "python", str(USAGE_PY)], env=env, capture_output=True, text=True)
    assert out.returncode == 0
    assert json.loads(out.stdout)["overage_gbp"] == 150.84


def _secrets(tmp_path, accounts_value):
    app = tmp_path / "Grok Bot"
    app.mkdir()
    (app / "sand-secrets.json").write_text(json.dumps({"cursor-accounts": accounts_value}))
    return app


def test_account_layouts_are_tolerated(usage):
    rec = {"cursor-access-token": "x"}
    as_string = json.dumps({"active": "a", "accounts": {"a": rec}})
    assert usage._account_records({"cursor-accounts": as_string})[0] is not None
    assert usage._account_records({"cursor-accounts": {"active": "a", "accounts": {"a": rec}}})[0] == rec
    assert usage._account_records({"cursor-accounts": {"active": "gone", "accounts": {"b": rec}}})[0] == rec  # stale active
    assert usage._account_records({"cursor-accounts": {"accounts": [rec]}})[0] == rec
    assert usage._account_records({"cursor-access-token": "x"})[0] == {"cursor-access-token": "x"}
    assert usage._account_records({}) == []


def test_marchhare_shape_fails_with_a_stage_not_a_crash(tmp_path):
    """Account with label + period only (no token): the reader says WHY instead of returning nothing."""
    app = _secrets(tmp_path, {"active": "a", "accounts": {"a": dict(MARCHHARE_ACCOUNT_FILE)}})
    env = dict(os.environ, BOB_CURSOR_APP_DIR=str(app))
    env.pop("BOB_CURSOR_AGENT_FIXTURE", None)
    out = subprocess.run([shutil.which("python") or "python", str(USAGE_PY)], env=env, capture_output=True, text=True)
    j = json.loads(out.stdout)
    assert j["ok"] is False and j["error"] in ("token-missing", "key-unprotect", "local-state")
    # and: no secrets file at all
    env["BOB_CURSOR_APP_DIR"] = str(tmp_path / "nope")
    j = json.loads(subprocess.run([shutil.which("python") or "python", str(USAGE_PY)], env=env,
                                  capture_output=True, text=True).stdout)
    assert j == {"ok": False, "error": "secrets-file", "detail": j["detail"]}


def test_v10_token_roundtrip_and_plain_token(usage):
    crypt = pytest.importorskip("cryptography.hazmat.primitives.ciphers.aead")
    key = os.urandom(32)
    nonce = os.urandom(12)
    blob = base64.b64encode(b"v10" + nonce + crypt.AESGCM(key).encrypt(nonce, b"fake-token", None)).decode()
    assert usage._decrypt_v10(key, blob) == "fake-token"
    assert usage._decrypt_v10(key, "short") == "short"  # plain token layout


def test_token_found_in_alternate_key_names(usage, tmp_path):
    app = _secrets(tmp_path, {"active": "a", "accounts": {"a": {"access_token": "plain-fake-token-value-0123456789abcdef"}}})
    # no key available + undecodable layout must raise a stage, never a traceback
    with pytest.raises(usage.FetchError):
        usage._access_token(None, app / "sand-secrets.json")


# ------------------------------------------------------------------ python discovery / wiring (static)
def test_python_discovery_is_not_hardcoded_to_c_python():
    src = (TRAY / "src" / "Public" / "Get-BobTrayHover.ps1").read_text(encoding="utf-8-sig")
    i = src.index("function Resolve-BobCursorPython")
    body = src[i:i + 1800]
    for needle in ("Get-Command python.exe", "py.exe", "$env:ProgramFiles", "LOCALAPPDATA", "BOB_CURSOR_PYTHON", "WindowsApps"):
        assert needle in body, needle
    assert "Resolve-BobCursorUsageScript" in src and "Resolve-BobCursorPython" in src
    assert "cursor-agent-usage.error.json" in src  # the reason a machine has no groups is recorded


# ------------------------------------------------------------------ bob -> digest -> tray (end to end)
def _run_ps(script: str, env: dict, tmp_path: Path) -> str:
    f = tmp_path / "run.ps1"
    f.write_text(script, encoding="utf-8")
    full = dict(os.environ, **env)
    r = subprocess.run([PS, "-NoProfile", "-File", str(f)], env=full, capture_output=True, text=True, timeout=180)
    assert r.returncode == 0, r.stderr[-800:]
    return r.stdout


def _bob_post(tmp_path: Path, fixture: dict, machine: str = "MarchHare") -> dict:
    fx = tmp_path / "fix.json"
    fx.write_text(json.dumps(fixture), encoding="utf-8")
    bridge, irc = tmp_path / "bridge", tmp_path / "irc"
    bridge.mkdir(); irc.mkdir()
    cfg = tmp_path / "bobiverse.json"
    cfg.write_text('{"nicks":{},"mootId":"x"}')
    cap = tmp_path / "cap.jsonl"
    _run_ps(
        "$ErrorActionPreference='Stop'\n"
        f"Import-Module '{TRAY / 'src' / 'BobBridge.psd1'}' -Force -DisableNameChecking\n"
        "& (Get-Module BobBridge) { Write-BobIrcStatus | Out-Null }\n",
        {"BOB_MACHINE_ID": machine, "BOB_BRIDGE_HOME": str(bridge), "BOB_IRC_HOME": str(irc),
         "BOB_IRC_CONFIG": str(cfg), "BOB_CURSOR_AGENT_FIXTURE": str(fx),
         "BOB_DIGEST_WEBHOOK_CAPTURE": str(cap), "BOB_CURSOR_USD_GBP_RATE": "0.7538"},
        tmp_path,
    )
    lines = [ln for ln in cap.read_text(encoding="utf-8-sig").splitlines() if ln.strip()]
    assert lines, "Write-BobIrcStatus posted nothing"
    return json.loads(lines[-1])


@needs_ps
def test_bob_posts_cursor_pools_overspend_and_grok_keyed_by_machine(tmp_path):
    p = _bob_post(tmp_path, IONOS_FIXTURE)
    assert p["op"] == "merge" and p["machine"] == "marchhare"  # Get-ThisMachineId, lowercase
    rows = {r["group_id"]: r for r in p["cursor_pools"]}
    assert set(rows) == {"grok-chat", "high-cost-models", "auto"}
    assert rows["grok-chat"]["remaining_pct"] == 94 and rows["grok-chat"]["period_end"] == "2026-10-07T17:23:58.025Z"
    assert rows["high-cost-models"]["period_end"] == "2026-10-16T17:23:01Z"
    assert rows["auto"]["remaining_pct"] == 0
    assert p["overage_gbp"] == 150.84 and p["overage_usd"] == 200.11 and p["overspend_state"] == "at-limit"
    assert p["on_demand_limit_cents"] == 20000
    assert p["sand_period_end"] == "2026-10-07T17:23:58.025Z" and p["cursor_period_end"] == "2026-10-16T17:23:01Z"
    assert p["pcent"]["grok-chat"] == 94
    blob = json.dumps(p).lower()
    for bad in ("password", "token", "secret"):
        assert bad not in blob


@needs_ps
def test_server_stores_under_machines_id_and_tray_summary_reads_it(tmp_path):
    p = _bob_post(tmp_path, IONOS_FIXTURE)
    home = tmp_path / "home"
    home.mkdir()
    rm.save_registered(home, {"marchhare", "win-mpre8vi4u6u"})
    out = bobreport.apply_callback(home, p, "Jeeves")
    assert out.ok, out.err
    doc = bobreport.load_digest(home)
    ent = doc["machines"]["marchhare"]
    assert ent["overage_gbp"] == 150.84 and ent["overspend_state"] == "at-limit"
    assert ent["overage_usd"] == 200.11 and ent["on_demand_limit_cents"] == 20000
    assert ent["sand_period_end"] == "2026-10-07T17:23:58.025Z"
    pools = {r["id"]: r for r in ent["cursor_pools"]}
    assert pools["grok-weekly"]["remaining"] == 94 and pools["grok-weekly"]["period_end"] == "2026-10-07T17:23:58.025Z"
    assert pools["other-models"]["period_end"] == "2026-10-16T17:23:01Z"
    # the exported digest machine row (what the tray GETs) keeps all of it
    exp = bobreport.export_machine_for_tray(home, "marchhare", ent, now=datetime(2026, 10, 1, 12, tzinfo=timezone.utc))
    for k in ("overage_gbp", "overage_usd", "overspend_state", "sand_period_end", "cursor_pools"):
        assert exp.get(k) not in (None, [], ""), k
    # tray side: digest machines.<id> -> Grok accounts row data
    dj = tmp_path / "digest.json"
    dj.write_text(json.dumps({"machines": {"marchhare": exp}}), encoding="utf-8")
    out = _run_ps(
        "$ErrorActionPreference='Stop'\n"
        f"Import-Module '{TRAY / 'src' / 'BobBridge.psd1'}' -Force -DisableNameChecking\n"
        f"$d = Get-Content -Raw '{dj}' | ConvertFrom-Json\n"
        "& (Get-Module BobBridge) { param($d) Get-BobTrayDigestMachineSummary -Digest $d -MachineId 'MARCHHARE' | ConvertTo-Json -Depth 6 -Compress } $d\n",
        {}, tmp_path,
    )
    s = json.loads(out.strip().splitlines()[-1])
    grok = s["grok_pools"] if isinstance(s["grok_pools"], list) else [s["grok_pools"]]
    assert grok[0]["id"] == "grok-weekly" and grok[0]["remaining_pct"] == 94
    assert grok[0]["period_end"] == "2026-10-07T17:23:58.025Z"
    assert {r["id"] for r in s["cursor_pools"]} >= {"other-models", "cursor-models"}
    assert s["overspend_gbp"] == 150.84 and s["overspend_state"] == "at-limit"


@needs_ps
def test_marchhare_shape_without_groups_still_posts_what_it_has(tmp_path):
    """Account file = label+period only -> no groups available: payload must still be valid, not crash."""
    fx = {"period": {"billingCycleEnd": "1792171381000", "planUsage": {"autoPercentUsed": 100}}, "sand": {}}
    p = _bob_post(tmp_path, fx)
    assert p["machine"] == "marchhare" and p["cursor_period_end"] == "2026-10-16T17:23:01Z"
    assert "overage_gbp" not in p or p["overage_gbp"] is None
    assert p.get("overspend_state") in (None, "unknown")


def test_tray_renders_per_machine_grok_accounts_section():
    w = (TRAY / "tools" / "Watch-BobTray.ps1").read_text(encoding="utf-8-sig")
    i = w.index("-Title 'Grok accounts'")
    sec = w[i:i + 4500]
    for needle in ("$m.grok_pools", "$m.cursor_pools", "$m.overspend_gbp", "Format-BobTrayCursorOverspendLine"):
        assert needle in sec, needle
    h = (TRAY / "src" / "Public" / "Get-BobTrayHover.ps1").read_text(encoding="utf-8-sig")
    assert "Get-BobTrayDigestMachineSummary -Digest $reportDigest -MachineId $mid" in h
    for key in ("grok_pools", "cursor_pools", "overspend_gbp", "overspend_state"):
        assert key + " " in h


def test_server_whitelists_overspend_fields_for_merge_and_export():
    for k in ("overage_usd", "overspend_state", "on_demand_used_cents", "on_demand_limit_cents", "sand_period_end"):
        assert k in bobreport._MERGE_PEER_FIELDS and k in bobreport._TRAY_MACHINE_EXPORT_KEYS, k

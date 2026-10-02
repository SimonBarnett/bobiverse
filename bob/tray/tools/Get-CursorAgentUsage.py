#!/usr/bin/env python3
r"""Read Cursor Spending (grok chat / high cost / auto) + Sand + on-demand overspend. Prints JSON only.

Works on ANY machine that has Grok Bot signed in to Cursor (``%APPDATA%\Grok Bot``):
the access token is read from ``sand-secrets.json`` (``cursor-accounts``), decrypted with the
DPAPI-protected AES key in ``Local State`` (v10 AES-GCM, needs the ``cryptography`` package), and
used for the two Cursor dashboard calls. Layout differences between machines are tolerated:

* ``cursor-accounts`` may be a JSON *string* (ionos) or an already-parsed object;
* ``active`` may be missing/stale -> first account that carries a token;
* the token may be a ``v10`` blob, a bare base64 blob, or plain text;
* an account record may hold the token under ``cursor-access-token`` / ``access_token`` / ``token``.

On failure it prints ``{"ok": false, "error": "<stage>", ...}`` (stage names only, never secrets) so
callers/tests can tell *why* a machine has no groups (token-missing, key-unprotect,
cryptography-missing, http-401, network, ...).

Env: ``BOB_CURSOR_AGENT_FIXTURE`` (fixture JSON {period, sand}), ``BOB_CURSOR_APP_DIR`` (override the
Grok Bot dir), ``BOB_CURSOR_USD_GBP_RATE`` (skip the FX lookup).
"""
from __future__ import annotations

import base64
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


class FetchError(Exception):
    def __init__(self, stage: str, detail: str = "") -> None:
        super().__init__(stage)
        self.stage = stage
        self.detail = detail


def app_dir() -> Path:
    env = (os.environ.get("BOB_CURSOR_APP_DIR") or "").strip()
    if env:
        return Path(env)
    return Path(os.environ.get("APPDATA", "")) / "Grok Bot"


# ----------------------------------------------------------------------------- DPAPI / AES-GCM
def _dpapi_unprotect(raw: bytes) -> bytes:
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    buf = ctypes.create_string_buffer(raw)
    blob_in = DATA_BLOB(len(raw), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    blob_out = DATA_BLOB()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    if not crypt32.CryptUnprotectData(ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)):
        raise OSError("CryptUnprotectData failed")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)


def _chrome_key(local_state: Path) -> bytes:
    try:
        wrap = json.loads(local_state.read_text(encoding="utf-8-sig"))
        enc = base64.b64decode(wrap["os_crypt"]["encrypted_key"])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise FetchError("local-state", type(exc).__name__) from exc
    if enc.startswith(b"DPAPI"):
        enc = enc[5:]
    try:
        return _dpapi_unprotect(enc)
    except (OSError, AttributeError) as exc:
        raise FetchError("key-unprotect", type(exc).__name__) from exc


def _decrypt_v10(key: bytes, blob_b64: str) -> str:
    try:
        raw = base64.b64decode(blob_b64, validate=False)
    except ValueError:
        return blob_b64  # not base64 at all: treat as a plain token
    if not raw.startswith(b"v10") and not raw.startswith(b"v11"):
        # bare base64 AES-GCM blob (nonce|ct|tag) or a plain token that happens to be base64
        if len(raw) < 12 + 16 + 1:
            return blob_b64
    else:
        raw = raw[3:]
    nonce, ct_tag = raw[:12], raw[12:]
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError as exc:
        raise FetchError("cryptography-missing", "pip install cryptography") from exc
    try:
        return AESGCM(key).decrypt(nonce, ct_tag, None).decode("utf-8")
    except Exception as exc:  # InvalidTag etc.
        raise FetchError("token-decrypt", type(exc).__name__) from exc


_TOKEN_KEYS = ("cursor-access-token", "access_token", "accessToken", "token")


def _account_records(secrets: dict) -> list[dict]:
    """All account records (active first) from any known ``cursor-accounts`` layout."""
    raw = secrets.get("cursor-accounts")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw or "{}")
        except ValueError:
            raw = {}
    recs: list[dict] = []
    if isinstance(raw, dict):
        accounts = raw.get("accounts")
        active = raw.get("active")
        if isinstance(accounts, dict):
            if active in accounts and isinstance(accounts[active], dict):
                recs.append(accounts[active])
            for k, v in accounts.items():
                if k != active and isinstance(v, dict):
                    recs.append(v)
        elif isinstance(accounts, list):
            recs.extend(a for a in accounts if isinstance(a, dict))
        elif any(k in raw for k in _TOKEN_KEYS):
            recs.append(raw)
    if any(k in secrets for k in _TOKEN_KEYS):
        recs.append(secrets)
    return recs


def _access_token(key: bytes | None, secrets_path: Path) -> str:
    try:
        secrets = json.loads(secrets_path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise FetchError("secrets-file", type(exc).__name__) from exc
    for rec in _account_records(secrets):
        for k in _TOKEN_KEYS:
            blob = rec.get(k)
            if isinstance(blob, str) and blob.strip():
                if key is None:
                    raise FetchError("key-unprotect", "no key")
                return _decrypt_v10(key, blob.strip())
    raise FetchError("token-missing", "no account carries an access token")


def _fetch_json(token: str, path: str) -> dict:
    req = urllib.request.Request(
        "https://api2.cursor.sh/" + path,
        data=b"{}",
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Connect-Protocol-Version": "1",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise FetchError(f"http-{exc.code}", path.rsplit("/", 1)[-1]) from exc
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise FetchError("network", type(exc).__name__) from exc


# ----------------------------------------------------------------------------- numbers
def _usd_to_gbp(usd: float) -> float | None:
    rate_env = os.environ.get("BOB_CURSOR_USD_GBP_RATE", "").strip()
    if rate_env:
        try:
            rate = float(rate_env)
            if rate > 0:
                return round(usd * rate, 2)
        except (TypeError, ValueError):
            pass
    endpoints = (
        ("https://open.er-api.com/v6/latest/USD", lambda b: float((b.get("rates") or {}).get("GBP") or 0)),
        (
            "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/usd.json",
            lambda b: float(((b.get("usd") or {}).get("gbp") or 0)),
        ),
    )
    for url, pick in endpoints:
        try:
            req = urllib.request.Request(url, method="GET", headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=4) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            rate = pick(body)
            if rate and rate > 0:
                return round(usd * rate, 2)
        except Exception:
            continue
    return None


def _num_cents(v) -> int | None:
    if v is None or v == "":
        return None
    try:
        c = int(round(float(v)))
    except (TypeError, ValueError):
        return None
    return c if c >= 0 else None


def _on_demand_usd_cents(period: dict | None) -> tuple[int | None, str | None]:
    if not period:
        return None, None
    slu = period.get("spendLimitUsage") or {}
    for key in ("individualUsed", "totalSpend"):
        c = _num_cents(slu.get(key))
        if c is not None:
            return c, f"period.spendLimitUsage.{key}"
    pu = period.get("planUsage") or {}
    try:
        over = int(round(float(pu.get("totalSpend")) - float(pu.get("includedSpend"))))
        if over > 0:
            return over, "period.planUsage.totalSpend-includedSpend"
    except (TypeError, ValueError):
        pass
    return None, None


def _on_demand_limit_cents(period: dict | None) -> int | None:
    if not period:
        return None
    slu = period.get("spendLimitUsage") or {}
    for key in ("individualLimit", "limit"):
        c = _num_cents(slu.get(key))
        if c is not None:
            return c
    return None


def _on_demand_remain_pct(used_cents: int | None, limit_cents: int | None) -> tuple[int | None, int | None]:
    if used_cents is None or limit_cents is None or limit_cents <= 0:
        return None, None
    used_pct = max(0, min(100, int(round(100.0 * used_cents / limit_cents))))
    remain = max(0, min(100, int(round(100.0 - 100.0 * used_cents / limit_cents))))
    return used_pct, remain


def _bonus_fields(period: dict | None) -> dict:
    out: dict = {}
    if not period:
        return out
    pu = period.get("planUsage") or {}
    try:
        if pu.get("bonusSpend") is not None and pu.get("bonusSpend") != "":
            out["bonus_spend_cents"] = int(round(float(pu.get("bonusSpend"))))
    except (TypeError, ValueError):
        pass
    if "remainingBonus" in pu:
        out["remaining_bonus"] = bool(pu.get("remainingBonus"))
    if pu.get("bonusTooltip"):
        out["bonus_tooltip"] = str(pu.get("bonusTooltip"))
    return out


def _parse_pct_points(raw) -> tuple[int | None, int | None]:
    """autoPercentUsed / apiPercentUsed are already percentage points (1 => 1% used)."""
    if raw is None or raw == "":
        return None, None
    try:
        used_f = float(raw)
    except (TypeError, ValueError):
        return None, None
    return int(round(used_f)), int(round(100.0 - used_f))


def _parse_used_remain(raw) -> tuple[int | None, int | None]:
    """Sand usagePercent may be a 0-1 fraction or 0-100 points."""
    if raw is None or raw == "":
        return None, None
    try:
        used_f = float(raw)
    except (TypeError, ValueError):
        return None, None
    if 0.0 <= used_f <= 1.0:
        used_f *= 100.0
    return int(round(used_f)), int(round(100.0 - used_f))


def _group_row(group_id: str, label: str, used, remain, source: str) -> dict:
    row: dict = {"id": group_id, "label": label, "source": source}
    if used is not None:
        row["used_pct"] = used
    if remain is not None:
        row["remaining_pct"] = remain
    return row


def build_spending_groups(period: dict | None, sand: dict | None) -> list[dict]:
    sand_used = sand_remain = None
    if sand:
        raw = sand.get("usagePercent")
        if raw is None:
            raw = sand.get("percentUsed")
        sand_used, sand_remain = _parse_used_remain(raw)
    api_used = api_remain = auto_used = auto_remain = None
    if period:
        pu = period.get("planUsage") or {}
        raw = pu.get("apiPercentUsed")
        if raw is None:
            raw = period.get("apiPercentUsed")
        api_used, api_remain = _parse_pct_points(raw)
        raw = pu.get("autoPercentUsed")
        if raw is None:
            raw = period.get("autoPercentUsed")
        auto_used, auto_remain = _parse_pct_points(raw)
    return [
        _group_row("grok-chat", "grok chat", sand_used, sand_remain, "GetSandUsageStatus.usagePercent"),
        _group_row("high-cost-models", "high cost models", api_used, api_remain, "GetCurrentPeriodUsage.planUsage.apiPercentUsed"),
        _group_row("auto", "Low cost models", auto_used, auto_remain, "GetCurrentPeriodUsage.planUsage.autoPercentUsed"),
    ]


def overspend_state(cents, limit_cents, enabled=None) -> str:
    """none | over (spent on-demand) | at-limit (limit reached) | unknown."""
    if cents is None:
        return "unknown"
    if cents <= 0:
        return "none"
    if limit_cents is not None and limit_cents > 0 and cents >= limit_cents:
        return "at-limit"
    return "over"


def _period_end_iso(period: dict | None) -> str | None:
    if not period:
        return None
    for key in ("billingCycleEnd", "periodEnd", "endDate", "end"):
        v = period.get(key)
        if v is None or v == "":
            continue
        try:
            ms = int(float(v))
            if ms > 10_000_000_000:
                return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except (TypeError, ValueError):
            pass
        return str(v)
    return None


def build_usage_doc(period: dict | None, sand: dict | None) -> dict:
    cursor_used = cursor_remain = None
    if period:
        pu = period.get("planUsage") or {}
        auto = pu.get("autoPercentUsed")
        if auto is None or auto == "":
            auto = period.get("autoPercentUsed")
        cursor_used, cursor_remain = _parse_pct_points(auto)
    sand_used = sand_remain = None
    if sand:
        raw = sand.get("usagePercent")
        if raw is None:
            raw = sand.get("percentUsed")
        sand_used, sand_remain = _parse_used_remain(raw)

    cents, cents_src = _on_demand_usd_cents(period)
    limit_cents = _on_demand_limit_cents(period)
    od_used, od_remain = _on_demand_remain_pct(cents, limit_cents)
    overage_gbp = overage_usd = fx_rate = None
    if cents is not None:
        overage_usd = round(cents / 100.0, 2)
        gbp = _usd_to_gbp(overage_usd)
        if gbp is not None:
            overage_gbp = gbp
            if overage_usd > 0:
                fx_rate = round(overage_gbp / overage_usd, 6)

    out: dict = {"ok": True, "source": "cursor-agent", "kind": "weekly"}
    if cursor_used is not None:
        out["used_pct"] = cursor_used
        out["remaining_pct"] = cursor_remain
        out["cursor_models_source"] = "GetCurrentPeriodUsage.planUsage.autoPercentUsed"
    if sand_used is not None:
        out["sand_used_pct"] = sand_used
        out["sand_remaining_pct"] = sand_remain
        if sand_remain is not None and sand_remain <= 0:
            out["sand_exhausted"] = True
    if overage_usd is not None:
        out["overage_usd"] = overage_usd
        out["on_demand_used_cents"] = cents
    if limit_cents is not None:
        out["on_demand_limit_cents"] = limit_cents
    if od_remain is not None:
        out["on_demand_remaining_pct"] = od_remain
        out["on_demand_used_pct"] = od_used
    if overage_gbp is not None:
        out["overage_gbp"] = overage_gbp
    if cents_src:
        out["overage_source"] = cents_src
    if fx_rate is not None:
        out["usd_gbp_rate"] = fx_rate
    out["overspend_state"] = overspend_state(cents, limit_cents)
    out.update(_bonus_fields(period))
    pe = _period_end_iso(period)
    if pe:
        out["period_end"] = pe
    out["ts"] = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    out["cursor_spending_groups"] = build_spending_groups(period, sand)
    if sand:
        sand_end = sand.get("nextResetTimestampUtc") or sand.get("period_end")
        if sand_end:
            out["sand_period_end"] = str(sand_end)
        ods = sand.get("onDemandSettings") or {}
        if "enabled" in ods:
            out["on_demand_enabled"] = bool(ods.get("enabled"))
    return out


def _has_data(out: dict) -> bool:
    return any(out.get(k) is not None for k in ("used_pct", "sand_used_pct", "overage_gbp", "overage_usd"))


def collect() -> dict:
    """Fixture, else live. Raises FetchError(stage)."""
    fixture_path = os.environ.get("BOB_CURSOR_AGENT_FIXTURE", "").strip()
    if fixture_path:
        fix = json.loads(Path(fixture_path).read_text(encoding="utf-8-sig"))
        out = build_usage_doc(fix.get("period"), fix.get("sand") or {})
        if fix.get("cursor_spending_groups"):
            out["cursor_spending_groups"] = fix["cursor_spending_groups"]
        return out
    app = app_dir()
    key = None
    secrets_path = app / "sand-secrets.json"
    if not secrets_path.is_file():
        raise FetchError("secrets-file", "sand-secrets.json not found under " + str(app.name))
    try:
        key = _chrome_key(app / "Local State")
    except FetchError:
        # a plain-text token layout needs no key; defer the error to the decrypt step
        key = None
    token = _access_token(key, secrets_path)
    sand = _fetch_json(token, "aiserver.v1.DashboardService/GetSandUsageStatus")
    try:
        period = _fetch_json(token, "aiserver.v1.DashboardService/GetCurrentPeriodUsage")
    except FetchError:
        period = None
    return build_usage_doc(period, sand)


def main() -> int:
    try:
        out = collect()
    except FetchError as exc:
        print(json.dumps({"ok": False, "error": exc.stage, "detail": exc.detail}))
        return 1
    except Exception as exc:
        print(json.dumps({"ok": False, "error": type(exc).__name__}))
        return 1
    if not _has_data(out):
        print(json.dumps({"ok": False, "error": "no-usage-data"}))
        return 1
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())

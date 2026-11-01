"""FR #5737: install-time PsExec deploy + offline LEGION ensure (pinned hash).

Sysinternals license forbids redistributing PsExec inside the MSI (no publish /
transfer). airc downloads the official PSTools.zip at install/UPDATE with pinned
SHA-256, caches it under %ProgramData%\\bobiverse\\tools\\cache\\, and LEGION only
verifies / redeploys from that local cache (no network at verb time).
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import zipfile
from pathlib import Path
from typing import Any, Callable, Optional

PSEXEC_ZIP_URL = "https://download.sysinternals.com/files/PSTools.zip"
# Defaults match psexec_pin.json (overridden when the pin file is present).
PSEXEC_ZIP_SHA256 = "c26c6ba44997e650a733df257c8feb83898d3faef2d2e391869d107e40863553"
PSEXEC_EXE_SHA256 = "078163d5c16f64caa5a14784323fd51451b8c831c73396b967b4e35e6879937b"

_PIN_NAME = "psexec_pin.json"


def _pin_path() -> Path:
    return Path(__file__).resolve().parent / _PIN_NAME


def load_psexec_pin() -> dict[str, str]:
    """Load pinned URL + SHA-256 values (FR #5737)."""
    out = {
        "zip_url": PSEXEC_ZIP_URL,
        "zip_sha256": PSEXEC_ZIP_SHA256,
        "psexec_sha256": PSEXEC_EXE_SHA256,
    }
    path = _pin_path()
    if not path.is_file():
        return out
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return out
    if not isinstance(raw, dict):
        return out
    for key in ("zip_url", "zip_sha256", "psexec_sha256"):
        val = str(raw.get(key) or "").strip()
        if val:
            out[key] = val.lower() if key.endswith("sha256") else val
    if out["zip_sha256"]:
        out["zip_sha256"] = out["zip_sha256"].lower()
    if out["psexec_sha256"]:
        out["psexec_sha256"] = out["psexec_sha256"].lower()
    return out


def tools_dir(*, dest: Optional[Path] = None) -> Path:
    return psexec_dest(dest=dest).parent


def psexec_dest(*, dest: Optional[Path] = None) -> Path:
    """AIRC_PSEXEC_PATH -> dest arg -> %ProgramData%\\bobiverse\\tools\\PsExec.exe."""
    explicit_dest = (os.environ.get("AIRC_PSEXEC_PATH") or "").strip()
    if explicit_dest:
        return Path(explicit_dest)
    if dest is not None:
        return Path(dest)
    pd = os.environ.get("ProgramData") or r"C:\ProgramData"
    return Path(pd) / "bobiverse" / "tools" / "PsExec.exe"


def cache_zip_path(*, dest: Optional[Path] = None) -> Path:
    return tools_dir(dest=dest) / "cache" / "PSTools.zip"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def psexec_hash_ok(path: Path, *, expected: str = "") -> bool:
    if not path.is_file():
        return False
    want = (expected or load_psexec_pin()["psexec_sha256"]).strip().lower()
    if not want:
        return path.is_file()
    try:
        return sha256_file(path) == want
    except OSError:
        return False


def cache_zip_ok(path: Path, *, expected: str = "") -> bool:
    if not path.is_file():
        return False
    want = (expected or load_psexec_pin()["zip_sha256"]).strip().lower()
    if not want:
        return True
    try:
        return sha256_file(path) == want
    except OSError:
        return False


def _deploy_opted_out() -> bool:
    return (os.environ.get("AIRC_NO_PSEXEC_DEPLOY") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def extract_psexec_from_zip(zip_path: Path, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        for name in zf.namelist():
            if name.lower().endswith("psexec.exe"):
                # Extract to a temp name under dest.parent then replace.
                tmp_dir = dest.parent / ".psexec-extract"
                if tmp_dir.exists():
                    shutil.rmtree(tmp_dir, ignore_errors=True)
                tmp_dir.mkdir(parents=True, exist_ok=True)
                zf.extract(name, tmp_dir)
                src = tmp_dir / name
                # zip members may include subdirs
                if not src.is_file():
                    matches = list(tmp_dir.rglob("PsExec.exe")) + list(
                        tmp_dir.rglob("psexec.exe")
                    )
                    if not matches:
                        raise RuntimeError("PsExec.exe not found after extract")
                    src = matches[0]
                shutil.copy2(src, dest)
                shutil.rmtree(tmp_dir, ignore_errors=True)
                return dest
    raise RuntimeError("PsExec.exe not found inside PSTools.zip")


def redeploy_psexec_from_cache(
    *,
    dest: Optional[Path] = None,
    pin: Optional[dict[str, str]] = None,
) -> Optional[str]:
    """FR #5737: extract PsExec from the local install cache (no network)."""
    if _deploy_opted_out():
        return None
    pin = pin or load_psexec_pin()
    target = psexec_dest(dest=dest)
    zpath = cache_zip_path(dest=dest)
    if not cache_zip_ok(zpath, expected=pin["zip_sha256"]):
        return None
    try:
        extract_psexec_from_zip(zpath, target)
    except Exception:
        return None
    if not psexec_hash_ok(target, expected=pin["psexec_sha256"]):
        try:
            target.unlink(missing_ok=True)  # type: ignore[call-arg]
        except TypeError:
            if target.is_file():
                target.unlink()
        except OSError:
            pass
        return None
    return str(target.resolve())


def deploy_psexec(
    *,
    dest: Optional[Path] = None,
    allow_network: bool = True,
    zip_path: Optional[Path] = None,
    urlretrieve: Optional[Callable[..., Any]] = None,
    pin: Optional[dict[str, str]] = None,
) -> dict[str, Any]:
    """Install/UPDATE-time deploy: download (optional) + verify + cache + extract.

    Returns ``{ok, path, cache, reason}``. Never used by LEGION verb path with
    ``allow_network=True`` (FR #5737: no network at verb time).
    """
    if _deploy_opted_out():
        return {"ok": False, "path": "", "cache": "", "reason": "deploy-opted-out"}
    pin = pin or load_psexec_pin()
    target = psexec_dest(dest=dest)
    cache = cache_zip_path(dest=dest)
    cache.parent.mkdir(parents=True, exist_ok=True)
    target.parent.mkdir(parents=True, exist_ok=True)

    src_zip: Optional[Path] = None
    if zip_path is not None and Path(zip_path).is_file():
        src_zip = Path(zip_path)
    elif cache_zip_ok(cache, expected=pin["zip_sha256"]):
        src_zip = cache
    elif allow_network:
        import urllib.request

        retrieve = urlretrieve or urllib.request.urlretrieve
        tmp = cache.with_suffix(".download")
        try:
            retrieve(pin["zip_url"], str(tmp))
            if not cache_zip_ok(tmp, expected=pin["zip_sha256"]):
                tmp.unlink(missing_ok=True) if hasattr(tmp, "unlink") else None
                return {
                    "ok": False,
                    "path": "",
                    "cache": "",
                    "reason": "zip-hash-mismatch",
                }
            if cache.exists():
                cache.unlink()
            tmp.replace(cache)
            src_zip = cache
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "path": "",
                "cache": "",
                "reason": f"download:{type(exc).__name__}",
            }
    else:
        return {"ok": False, "path": "", "cache": "", "reason": "cache-missing"}

    assert src_zip is not None
    if src_zip.resolve() != cache.resolve():
        shutil.copy2(src_zip, cache)
    if not cache_zip_ok(cache, expected=pin["zip_sha256"]):
        return {"ok": False, "path": "", "cache": str(cache), "reason": "zip-hash-mismatch"}

    try:
        extract_psexec_from_zip(cache, target)
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "path": "",
            "cache": str(cache),
            "reason": f"extract:{type(exc).__name__}",
        }
    if not psexec_hash_ok(target, expected=pin["psexec_sha256"]):
        return {
            "ok": False,
            "path": str(target),
            "cache": str(cache),
            "reason": "exe-hash-mismatch",
        }
    return {
        "ok": True,
        "path": str(target.resolve()),
        "cache": str(cache.resolve()),
        "reason": "ok",
    }


def find_psexec(explicit: str = "") -> Optional[str]:
    if explicit:
        p = Path(explicit)
        if p.is_file():
            return str(p.resolve())
    found = shutil.which("psexec") or shutil.which("PsExec.exe") or shutil.which(
        "psexec.exe"
    )
    return found


def ensure_psexec(explicit: str = "", *, dest: Optional[Path] = None) -> Optional[str]:
    """FR #5737: return airc-owned PsExec (hash-ok), redeploying from local cache only.

    Never downloads from the network (install/UPDATE owns that). Explicit path wins
    when present. PATH copies are ignored so LEGION stays on the pinned airc deploy.
    """
    pin = load_psexec_pin()
    if explicit:
        p = Path(explicit)
        if p.is_file():
            # Explicit operator override: trust path presence (hash optional).
            return str(p.resolve())
    if _psexec_download_opted_out():
        target = psexec_dest(dest=dest)
        if psexec_hash_ok(target, expected=pin["psexec_sha256"]):
            return str(target.resolve())
        return None
    target = psexec_dest(dest=dest)
    if psexec_hash_ok(target, expected=pin["psexec_sha256"]):
        return str(target.resolve())
    return redeploy_psexec_from_cache(dest=dest, pin=pin)


def plan_psexec(
    explicit: str = "",
    *,
    dest: Optional[Path] = None,
    probe: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """FR #5737: read-only prediction of ``ensure_psexec`` (no download / no writes).

    States: found | deployed | would-redeploy | undeployed | missing.
    ``probe`` is accepted for back-compat with FR #5712 callers and ignored
    (verb-time network probes are retired).
    """
    _ = probe
    pin = load_psexec_pin()
    if explicit:
        p = Path(explicit)
        if p.is_file():
            return {"state": "found", "path": str(p.resolve())}
    if _psexec_download_opted_out():
        return {"state": "missing", "reason": "deploy-opted-out"}
    target = psexec_dest(dest=dest)
    dest_s = str(target)
    if psexec_hash_ok(target, expected=pin["psexec_sha256"]):
        return {"state": "deployed", "path": str(target.resolve()), "dest": dest_s}
    zpath = cache_zip_path(dest=dest)
    if cache_zip_ok(zpath, expected=pin["zip_sha256"]):
        return {
            "state": "would-redeploy",
            "dest": dest_s,
            "cache": str(zpath.resolve()),
            "reason": "exe-missing-or-hash-mismatch",
        }
    return {
        "state": "undeployed",
        "dest": dest_s,
        "reason": "run-airc-install-or-update",
    }


# Back-compat aliases used by older callers / tests.
def offer_download_psexec(dest: Path) -> Path:
    """Install-time helper: network deploy into ``dest`` (FR #5737)."""
    hit = deploy_psexec(dest=dest, allow_network=True)
    if not hit.get("ok"):
        raise RuntimeError(hit.get("reason") or "deploy-failed")
    return Path(str(hit["path"]))


def _psexec_download_opted_out() -> bool:
    """Legacy name: maps to AIRC_NO_PSEXEC_DEPLOY or AIRC_LEGION_NO_PSEXEC_DOWNLOAD."""
    if _deploy_opted_out():
        return True
    return (os.environ.get("AIRC_LEGION_NO_PSEXEC_DOWNLOAD") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )

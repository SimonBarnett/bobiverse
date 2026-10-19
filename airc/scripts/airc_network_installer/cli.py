"""CLI entry for airc-network-installer (FR #3991)."""

from __future__ import annotations

import argparse
import getpass
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .core import (
    DEFAULT_PROFILE,
    SERVICE_NAME,
    AIRC_PROFILE_PROPERTY,
    HostResult,
    dedupe_hosts,
    hosts_from_cidr,
    parse_hosts_csv,
    parse_hosts_file,
    parse_version,
    write_summary_csv,
)
from .github_msi import download_latest_airc_msi, sha256_file
from .install import (
    find_psexec,
    install_local,
    install_remote,
    offer_download_psexec,
    read_local_version,
    socket_hostname,
)


def _candidate_version_from_msi_name(msi: Path) -> str:
    # airc-1.0.2.msi -> 1.0.2
    name = msi.stem
    if name.lower().startswith("airc-"):
        return name[5:]
    return name


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Elevated network-wide airc MSI install via PsExec (FR #3991). "
            f"MSI public property {AIRC_PROFILE_PROPERTY}=fleet|client|workstation; "
            f"Windows service name {SERVICE_NAME}."
        )
    )
    p.add_argument(
        "--msi",
        help="Testing-only local MSI override (default: always download Latest release airc MSI)",
    )
    p.add_argument(
        "--profile",
        choices=("fleet", "client", "workstation"),
        default=DEFAULT_PROFILE,
        help=f"Passed to msiexec as {AIRC_PROFILE_PROPERTY}=... (default client)",
    )
    p.add_argument("--hosts", help="Comma-separated hostnames")
    p.add_argument("--hosts-file", help="File with one host per line")
    p.add_argument("--network", help="CIDR fallback scan for SMB/445")
    p.add_argument(
        "--domain-ad",
        action="store_true",
        help="Enumerate enabled AD computer objects (default when domain-joined and no hosts given)",
    )
    p.add_argument("--no-ad", action="store_true", help="Never query AD")
    p.add_argument("--force", action="store_true", help="Reinstall even if same/newer")
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--timeout", type=float, default=900.0, help="Per-host timeout seconds")
    p.add_argument("-u", "--username", default="", help="Domain user; password prompted (no echo)")
    p.add_argument("--psexec", default="", help="Path to PsExec.exe")
    p.add_argument(
        "--download-psexec",
        action="store_true",
        help="Download PsExec from official Microsoft Sysinternals URL if missing",
    )
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--no-local", action="store_true", help="Exclude the machine running this exe")
    p.add_argument(
        "--log-dir",
        default="airc-install-logs",
        help="Directory for per-host msiexec logs + summary.csv",
    )
    p.add_argument("--download-dir", default=".", help="Where to save downloaded MSI")
    p.add_argument("--selftest", action="store_true", help="Smoke: import + version parse")
    return p


def enumerate_ad_computers() -> list[str]:
    """Enabled AD computer objects via PowerShell AD module when available."""
    import subprocess

    ps = (
        "Get-ADComputer -Filter 'Enabled -eq $true' -ErrorAction Stop "
        "| Select-Object -ExpandProperty Name"
    )
    r = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            ps,
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout or "Get-ADComputer failed").strip())
    return [ln.strip() for ln in (r.stdout or "").splitlines() if ln.strip()]


def is_domain_joined() -> bool:
    import subprocess

    r = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", "(Get-WmiObject Win32_ComputerSystem).PartOfDomain"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    return (r.stdout or "").strip().lower() in ("true", "1")


def resolve_targets(args: argparse.Namespace) -> list[str]:
    hosts: list[str] = []
    if args.hosts:
        hosts.extend(parse_hosts_csv(args.hosts))
    if args.hosts_file:
        hosts.extend(parse_hosts_file(Path(args.hosts_file)))
    use_ad = False
    if args.domain_ad:
        use_ad = True
    elif not args.no_ad and not hosts and not args.network and is_domain_joined():
        use_ad = True
    if use_ad:
        hosts.extend(enumerate_ad_computers())
    if args.network:
        hosts.extend(hosts_from_cidr(args.network, workers=max(8, args.workers * 4)))
    local = socket_hostname()
    local_aliases = {local, local.lower(), f"{local}.", "localhost", "127.0.0.1"}
    if not args.no_local:
        hosts = [local] + hosts
    return dedupe_hosts(hosts, local_names=local_aliases)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    # CAST IRON: never accept password on argv
    for i, tok in enumerate(argv):
        if tok in ("-p", "--password"):
            print("[-] Refusing -p/--password on argv (FR #3991); use -u and getpass", file=sys.stderr)
            return 2
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.selftest:
        assert parse_version("1.0.2") == (1, 0, 2)
        print("airc-network-installer selftest ok")
        return 0

    password = ""
    if args.username:
        password = getpass.getpass(f"Password for {args.username}: ")

    download_dir = Path(args.download_dir)
    if args.msi:
        msi_path = Path(args.msi).resolve()
        if not msi_path.is_file():
            print(f"[-] MSI not found: {msi_path}", file=sys.stderr)
            return 1
        print(f"[*] Testing override MSI: {msi_path}")
    else:
        print("[*] Downloading latest airc MSI from GitHub Releases (Latest)...")
        try:
            msi_path, tag = download_latest_airc_msi(download_dir)
        except Exception as exc:
            print(f"[-] Download failed: {exc}", file=sys.stderr)
            return 1
        print(f"[+] {msi_path.name} from {tag} sha256={sha256_file(msi_path)}")

    candidate = _candidate_version_from_msi_name(msi_path)
    print(f"[*] Candidate version {candidate}; profile {AIRC_PROFILE_PROPERTY}={args.profile}")
    print(f"[*] Service name {SERVICE_NAME}")

    psexec = find_psexec(args.psexec)
    if not psexec:
        if args.download_psexec:
            dest = Path.cwd() / "PsExec.exe"
            print("[*] Downloading PsExec from Microsoft Sysinternals...")
            psexec = str(offer_download_psexec(dest))
        else:
            print(
                "[-] PsExec not found on PATH (Sysinternals licence forbids bundling). "
                "Pass --psexec or --download-psexec.",
                file=sys.stderr,
            )
            return 1
    print(f"[*] PsExec: {psexec}")

    try:
        targets = resolve_targets(args)
    except Exception as exc:
        print(f"[-] Target resolution failed: {exc}", file=sys.stderr)
        return 1
    if not targets:
        print("[-] No targets")
        return 1
    print(f"[*] Targets ({len(targets)}): {', '.join(targets)}")

    log_dir = Path(args.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    local_name = socket_hostname().lower()
    results: list[HostResult] = []

    def _one(host: str) -> HostResult:
        if host.lower() == local_name or host.lower() in ("localhost", "127.0.0.1"):
            return install_local(
                msi_path=msi_path,
                candidate_version=candidate,
                profile=args.profile,
                force=args.force,
                log_dir=log_dir,
                dry_run=args.dry_run,
            )
        return install_remote(
            host=host,
            msi_path=msi_path,
            candidate_version=candidate,
            profile=args.profile,
            force=args.force,
            psexec=psexec,
            username=args.username,
            password=password,
            log_dir=log_dir,
            dry_run=args.dry_run,
            timeout_s=args.timeout,
        )

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futs = {pool.submit(_one, h): h for h in targets}
        for fut in as_completed(futs):
            host = futs[fut]
            try:
                row = fut.result()
            except Exception as exc:
                row = HostResult(host=host, status="failed", detail=str(exc), action="install")
            results.append(row)
            flag = row.status.upper()
            print(f"[{flag}] {row.host}: action={row.action} prev={row.previous_version or '-'} {row.detail}")

    summary = log_dir / "summary.csv"
    write_summary_csv(summary, results)
    print(f"[*] Summary {summary}")

    failed = [r for r in results if r.status == "failed"]
    skipped = [r for r in results if r.status == "skipped"]
    ok = [r for r in results if r.status in ("success", "reboot_required", "dry-run")]
    print(
        f"[+] done ok={len(ok)} skipped={len(skipped)} failed={len(failed)} "
        f"(local version now {read_local_version() or 'n/a'})"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

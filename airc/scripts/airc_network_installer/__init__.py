"""FR #3991: elevated network-wide airc MSI install via PsExec."""

from .core import (
    AIRC_PROFILE_PROPERTY,
    DEFAULT_PROFILE,
    SERVICE_NAME,
    HostResult,
    classify_msiexec_exit,
    compare_versions,
    dedupe_hosts,
    msiexec_install_args,
    parse_hosts_csv,
    parse_version,
    planned_action,
)

__all__ = [
    "AIRC_PROFILE_PROPERTY",
    "DEFAULT_PROFILE",
    "SERVICE_NAME",
    "HostResult",
    "classify_msiexec_exit",
    "compare_versions",
    "dedupe_hosts",
    "msiexec_install_args",
    "parse_hosts_csv",
    "parse_version",
    "planned_action",
]

"""Deterministic UAT PASS release title/tag (FR #7122).

Workers call this helper instead of inventing ``UAT PASS {date}`` titles.
Repos listed in ``PRODUCT_UAT_RELEASE`` get ``{product} vX.Y.Z`` / ``vX.Y.Z``.
Others keep the legacy date title/tag unless they add a config row.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

# owner/name lower -> product title used in GitHub release name (FR #7122).
# FR #9416: this map is title/tag metadata only — it does **not** grant UAT
# enqueue/offer. Priority Agent / priority-customer products stay off the
# default offer allowlist until an operator opts in via env or chair file.
PRODUCT_UAT_RELEASE: dict[str, str] = {
    "simonbarnett/priority-mcp": "Priority Agent",
    "simonbarnett/agentic_fomprep": "Priority Agent",
}

# FR #9382 CAST IRON + FR #9416: only these fleet repos (plus env and optional
# chair-home uat_release_repos.txt) may enqueue / offer / assign UAT #0.
# Customer / plan-only / priority-customer repos (wetherby, obw, ce-priority,
# priority-mcp, …) stay out of the default set.
DEFAULT_UAT_RELEASE_REPOS: frozenset[str] = frozenset(
    {
        "simonbarnett/bobiverse",
        "simonbarnett/a-search",
        "simonbarnett/skills-visionary",
    }
)

UAT_RELEASE_REPOS_FILE = "uat_release_repos.txt"
UAT_RELEASE_REPOS_ENV = "BOB_UAT_RELEASE_REPOS"
NO_RELEASE_TO_BUILD = "no-release-to-build"

_SEMVER = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")
_ANY_SEMVER = re.compile(r"v?(\d+)\.(\d+)\.(\d+)$")


class UatReleaseError(ValueError):
    """Refuse the release (existing tag, version not increasing, bad VERSION)."""


@dataclass(frozen=True)
class UatReleasePlan:
    title: str
    tag: str
    version: str
    notes: str
    product: str | None
    gh_args: tuple[str, ...]


def parse_semver(raw: str) -> tuple[int, int, int]:
    m = _SEMVER.match(str(raw or "").strip())
    if not m:
        raise UatReleaseError(f"VERSION is not X.Y.Z: {raw!r}")
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def bump_patch(raw: str) -> str:
    a, b, c = parse_semver(raw)
    return f"{a}.{b}.{c + 1}"


def format_semver(parts: tuple[int, int, int]) -> str:
    return f"{parts[0]}.{parts[1]}.{parts[2]}"


def semver_from_tag(tag: str) -> tuple[int, int, int] | None:
    s = str(tag or "").strip()
    if not s:
        return None
    m = _SEMVER.match(s) or _ANY_SEMVER.search(s)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def highest_semver(tags: Iterable[str]) -> tuple[int, int, int] | None:
    best: tuple[int, int, int] | None = None
    for t in tags:
        cur = semver_from_tag(t)
        if cur is None:
            continue
        if best is None or cur > best:
            best = cur
    return best


def _repo_key(repo: str) -> str:
    return str(repo or "").strip().strip("/").lower()


def _product_for(repo: str) -> str | None:
    return PRODUCT_UAT_RELEASE.get(_repo_key(repo))


def _parse_repo_lines(text: str) -> set[str]:
    out: set[str] = set()
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # allow "owner/name" or trailing comments
        line = line.split("#", 1)[0].strip()
        key = _repo_key(line)
        if key and "/" in key:
            out.add(key)
    return out


def load_uat_release_repos(*, home: Path | None = None) -> frozenset[str]:
    """Built-in allowlist + env + optional chair file (FR #9382 / #9416).

    ``PRODUCT_UAT_RELEASE`` is **not** merged here (FR #9416): product title
    rows must not auto-enable UAT offer for priority-customer repos.
    """
    names: set[str] = set(DEFAULT_UAT_RELEASE_REPOS)
    import os

    env_raw = (os.environ.get(UAT_RELEASE_REPOS_ENV) or "").strip()
    if env_raw:
        for part in env_raw.replace(";", ",").split(","):
            key = _repo_key(part)
            if key and "/" in key:
                names.add(key)
    if home is not None:
        path = Path(home) / UAT_RELEASE_REPOS_FILE
        try:
            if path.is_file():
                names |= _parse_repo_lines(path.read_text(encoding="utf-8-sig"))
        except OSError:
            pass
    return frozenset(names)


def repo_has_release_to_build(repo: str, *, home: Path | None = None) -> bool:
    """True when UAT PASS for this repo is expected to build/publish a release (FR #9382)."""
    key = _repo_key(repo)
    if not key or "/" not in key:
        return False
    return key in load_uat_release_repos(home=home)


def plan_uat_pass_release(
    *,
    repo: str,
    version: str,
    existing_tags: Iterable[str],
    date: str,
    notes_body: str = "",
) -> UatReleasePlan:
    """Return title, tag, notes. Raises UatReleaseError instead of publishing a bad tag."""
    tags = tuple(str(t).strip() for t in existing_tags if str(t).strip())
    product = _product_for(repo)
    day = str(date or "").strip() or "undated"
    extra = (notes_body or "").strip()
    if product:
        nxt = bump_patch(version)
        tag = f"v{nxt}"
        if tag in tags or nxt in tags:
            raise UatReleaseError(f"tag already exists: {tag}")
        hi = highest_semver(tags)
        parsed = parse_semver(nxt)
        if hi is not None and parsed <= hi:
            raise UatReleaseError(
                f"version {nxt} is not greater than highest existing v* {format_semver(hi)}"
            )
        title = f"{product} v{nxt}"
        notes = "\n".join(
            x
            for x in (
                f"UAT PASS {day}",
                extra,
            )
            if x
        )
        gh = ("release", "create", tag, "--title", title, "--notes", notes)
        return UatReleasePlan(
            title=title, tag=tag, version=nxt, notes=notes, product=product, gh_args=gh
        )

    tag = f"uat-{day}"
    if tag in tags:
        raise UatReleaseError(f"tag already exists: {tag}")
    title = f"UAT PASS {day}"
    notes = extra or title
    gh = ("release", "create", tag, "--title", title, "--notes", notes)
    return UatReleasePlan(
        title=title, tag=tag, version=str(version).strip(), notes=notes, product=None, gh_args=gh
    )


def read_version_file(path: Path) -> str:
    text = path.read_text(encoding="utf-8").splitlines()
    line = next((ln.strip() for ln in text if ln.strip() and not ln.strip().startswith("#")), "")
    if not line:
        raise UatReleaseError(f"empty VERSION file: {path}")
    return line


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="FR #7122 UAT PASS release title/tag helper")
    p.add_argument("--repo", required=True)
    p.add_argument("--version-file", default="")
    p.add_argument("--version", default="")
    p.add_argument("--existing-tags", default="")
    p.add_argument("--date", required=True)
    p.add_argument("--notes", default="")
    p.add_argument("--write-version", action="store_true")
    args = p.parse_args(argv)
    ver = (args.version or "").strip()
    vf = Path(args.version_file) if args.version_file else None
    if vf:
        ver = read_version_file(vf)
    if not ver:
        print("need --version or --version-file", file=sys.stderr)
        return 2
    tags = [t.strip() for t in str(args.existing_tags).split(",") if t.strip()]
    try:
        plan = plan_uat_pass_release(
            repo=args.repo,
            version=ver,
            existing_tags=tags,
            date=args.date,
            notes_body=args.notes,
        )
    except UatReleaseError as e:
        print(str(e), file=sys.stderr)
        return 1
    if args.write_version and vf and plan.product:
        vf.write_text(plan.version + "\n", encoding="utf-8")
    payload = asdict(plan)
    payload["gh_args"] = list(plan.gh_args)
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""FR #4025: drain one BUILD queue job or run BuildRunner from CLI (no agent tokens).

Chair enqueues `home/build-queue/*.json` on BUILD v1 and spawns this process for the
job. With ``--checkout`` the runner clones the repo at the requested ref into a clean
work dir, checks out the baseline (last ``vX.Y.Z`` tag, pre-release tags excluded) in a
second worktree, runs suites/pack, and publishes a GitHub pre-release (never Latest).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import bobiverse_build as bb  # noqa: E402


def _load_job(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _rmtree(path: Path) -> None:
    def _onerr(func, p, _exc):
        try:
            os.chmod(p, stat.S_IWRITE)
            func(p)
        except Exception:
            pass

    if path.exists():
        shutil.rmtree(path, onerror=_onerr)


def _git(args: list[str], cwd: Path | None, log: list[str], timeout: float = 1800) -> str:
    cp = subprocess.run(
        ["git", *args], cwd=str(cwd) if cwd else None, capture_output=True, text=True,
        timeout=timeout, check=False,
    )
    log.append(f"$ git {' '.join(args)}\nrc={cp.returncode}\n{cp.stdout}{cp.stderr}")
    if cp.returncode != 0:
        err = (cp.stderr or cp.stdout or "").strip().replace("\n", " ")[:800]
        raise RuntimeError(f"git {args[0]} failed rc={cp.returncode}: {err}")
    return cp.stdout.strip()


def checkout(repo: str, ref: str, work: Path, log: list[str]) -> tuple[Path, Path | None, str, str]:
    """Clean clone at ref + baseline worktree. Returns (src, baseline_dir, sha, baseline_tag)."""
    src = work / "src"
    base = work / "baseline"
    work.mkdir(parents=True, exist_ok=True)
    lock = work / ".runner.lock"
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    try:
        fd = os.open(str(lock), flags)
    except FileExistsError:
        raise RuntimeError(f"work lock held: {lock}") from None
    try:
        os.write(fd, f"{os.getpid()}\n".encode("ascii"))
    finally:
        os.close(fd)
    _rmtree(base)
    _rmtree(src)
    if src.exists() or base.exists():
        raise RuntimeError(f"checkout refuse: leftover {src if src.exists() else base}")
    _git(["clone", "--quiet", "--filter=blob:none", f"https://github.com/{repo}.git", str(src)], None, log)
    if ref and ref != "HEAD":
        _git(["checkout", "--quiet", "--detach", ref], src, log)
    sha = _git(["rev-parse", "HEAD"], src, log)
    tag = ""
    try:
        tag = _git(["describe", "--tags", "--abbrev=0", "--match", "v[0-9]*", "--exclude", "*-*", "HEAD"], src, log)
    except RuntimeError:
        tag = ""
    if tag:
        _git(["worktree", "add", "--quiet", "--detach", str(base), tag], src, log)
        return src, base, sha, tag
    return src, None, sha, ""


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="FR #4025 bobiverse BUILD runner")
    p.add_argument("--repo-root", default=".", help="git / install root with .bobiverse/build.yml")
    p.add_argument("--repo", default="", help="owner/repo (default from job or SimonBarnett/bobiverse)")
    p.add_argument("--version", default="")
    p.add_argument("--ref", default="HEAD")
    p.add_argument("--job", default="", help="path to build-queue JSON from chair")
    p.add_argument("--queue-dir", default="", help="drain oldest *.json from this dir")
    p.add_argument("--work-dir", default="", help="default: %ProgramData%/Bobiverse/build-work")
    p.add_argument("--fake-filer", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--checkout", action="store_true", help="clean clone at ref + baseline worktree")
    p.add_argument("--lock-file", default="", help="BuildLock json to release when done")
    p.add_argument("--result-file", default="", help="write the JSON result here")
    p.add_argument("--local-machine", default=os.environ.get("BOB_MACHINE_ID", ""))
    args = p.parse_args(argv)

    job = {}
    job_path = None
    if args.job:
        job_path = Path(args.job)
        job = _load_job(job_path)
    elif args.queue_dir:
        q = Path(args.queue_dir)
        files = sorted(q.glob("*.json"))
        if not files:
            print("build: queue empty")
            return 0
        job_path = files[0]
        job = _load_job(job_path)

    repo = (args.repo or job.get("repo") or "SimonBarnett/bobiverse").strip()
    if "," in repo:
        repo = repo.split(",")[0].strip()
    if job.get("repos"):
        repos = job["repos"]
        if isinstance(repos, str):
            repo = repos.split(",")[0].strip()
        elif isinstance(repos, list) and repos:
            repo = str(repos[0]).strip()
    version = (args.version or job.get("version") or "").strip()
    ref = ((job.get("ref") if args.ref == "HEAD" else args.ref) or "HEAD").strip()
    if not version:
        print("build: need --version or job.version", file=sys.stderr)
        return 2

    gh_src = "none"
    try:
        import gh_filer

        gh_src = gh_filer.ensure_gh_token_env()  # source tag only; never the value
    except Exception:
        pass

    result: dict = {"repo": repo, "version": version, "ref": ref, "ok": False}
    if not args.fake_filer and not args.dry_run:
        # #4188: fail at preflight, not 2h later at step:release.
        why = bb.gh_auth_preflight()
        result["gh_auth"] = "ok" if why is None else "missing"
        result["gh_auth_source"] = gh_src.split(":", 1)[0]
        if why:
            result["errors"] = [why]
            result["announce"] = [f"BUILD refused {repo} version={version}: {why}"]
            print(json.dumps(result, indent=2, default=str))
            if args.result_file:
                Path(args.result_file).write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
            if args.lock_file:
                try:
                    bb.BuildLock(Path(args.lock_file), max_parallel=1).release(repo)
                except Exception:
                    pass
            if job_path is not None:
                try:
                    job_path.rename(job_path.with_suffix(".json.failed"))
                except Exception:
                    pass
            return 4
    rc = 1
    filer = None
    try:
        work = Path(args.work_dir) if args.work_dir else Path(os.environ.get("ProgramData", "C:/ProgramData")) / "Bobiverse" / "build-work" / version
        log_dir = work / "logs"
        root = Path(args.repo_root).resolve()
        baseline_root = None
        sha, tag = "", ""
        if args.checkout and not args.dry_run:
            ck_log: list[str] = []
            try:
                root, baseline_root, sha, tag = checkout(repo, ref, work, ck_log)
            finally:
                log_dir.mkdir(parents=True, exist_ok=True)
                (log_dir / "checkout.log").write_text("\n".join(ck_log), encoding="utf-8")
        recipe = bb.load_recipe(root)
        local = (args.local_machine or "").strip()
        if local and not bb.is_recipe_build_machine(recipe.machine, local):
            print(f"build: refused machine local={local} recipe={recipe.machine}")
            result["errors"] = ["wrong machine"]
            return 3

        filer = bb.FakeGitHubFiler() if args.fake_filer else bb.GitHubFiler()
        release_fn = None
        if not args.fake_filer and not args.dry_run and sha:
            subprocess.run(
                ["gh", "label", "create", bb.RELEASE_BLOCKER_LABEL, "--repo", repo,
                 "--color", "B60205", "--description", "Auto-filed by !build (FR #4006)", "--force"],
                capture_output=True, text=True, check=False,
            )
            # FR #4316: guard/runner abort blockers carry machine:any.
            subprocess.run(
                ["gh", "label", "create", bb.MACHINE_ANY_LABEL, "--repo", repo,
                 "--color", "cccccc", "--description", "Jeeves: no machine pin (require_machine=any)", "--force"],
                capture_output=True, text=True, check=False,
            )
            release_fn = bb.make_github_prerelease_fn(
                repo,
                target_sha=sha,
                title=f"v{version} (pre-release, deterministic !build)",
                notes=(
                    f"Deterministic `!build` pre-release (FR #4006). **Not Latest.**\n\n"
                    f"- ref: `{ref}` = `{sha}`\n- baseline: `{tag or 'none'}`\n"
                    f"- build logs: `build-logs-{version}.zip`\n"
                ),
            )
        live_homes = [
            Path(os.environ.get("BOB_DIGEST_HOME") or (Path.home() / ".bobiverse")),
            Path(os.environ.get("BOB_HOME") or (Path.home() / ".jeeves")),
            Path(r"C:\Users\Administrator\.bobiverse"),
            Path(r"C:\Users\Administrator\.jeeves"),
        ]
        # #4183 belt-and-braces: copy live chair state aside before any suite runs.
        bk = work / "live-state-backup"
        for h in live_homes:
            for name in bb.LIVE_STATE_FILES:
                src_f = h / name
                if src_f.is_file():
                    dst = bk / h.name / name
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src_f, dst)
        runner = bb.BuildRunner(
            root, repo, version, ref, recipe, filer,
            run_command_fn=bb.guarded_run_command(work, live_homes),
            work_dir=work, log_dir=log_dir, local_machine=local or recipe.machine,
            release_fn=release_fn, baseline_root=baseline_root,
            baseline_resolver=(lambda *_a: tag or "baseline"),
        )
        t0 = time.time()
        report = runner.run(dry_run=bool(args.dry_run))
        result.update({
            "ok": report.ok,
            "sha": sha,
            "baseline": tag,
            "blockers": getattr(report, "blockers_filed", None) or [],
            "pack_ok": report.pack_ok,
            "release_ok": report.release_ok,
            "announce": report.announce_lines,
            "errors": report.errors,
            "log_zip": getattr(report, "log_zip", ""),
            "suites": [
                {"name": r.name, "at": r.ref_or_baseline, "rc": r.exit_code,
                 "timed_out": r.timed_out, "s": round(r.duration_s)}
                for r in report.suite_results
            ],
            "duration_s": round(time.time() - t0),
        })
        tag_name = f"v{version}"
        if report.release_ok and release_fn is not None:
            lz = getattr(report, "log_zip", "")
            if lz and Path(lz).is_file():
                subprocess.run(["gh", "release", "upload", tag_name, lz, "--repo", repo, "--clobber"],
                               capture_output=True, text=True, check=False)
            table = "\n".join(
                f"| {s['name']} | {s['at']} | {s['rc']} | {s['timed_out']} | {s['s']} |"
                for s in result["suites"]
            )
            notes = (
                f"Deterministic `!build` pre-release (FR #4006). **Not Latest.**\n\n"
                f"- ref: `{ref}` = `{sha}`\n- baseline: `{tag or 'none'}`\n\n"
                f"| step | at | rc | timed out | seconds |\n|---|---|---|---|---|\n{table}\n"
            )
            subprocess.run(["gh", "release", "edit", tag_name, "--repo", repo, "--notes", notes,
                            "--prerelease", "--latest=false"],
                           capture_output=True, text=True, check=False)
            cp = subprocess.run(["gh", "release", "view", tag_name, "--repo", repo, "--json", "url"],
                                capture_output=True, text=True, check=False)
            try:
                result["release_url"] = json.loads(cp.stdout or "{}").get("url", "")
            except Exception:
                pass
        rc = 0 if report.ok else 1
    except Exception as exc:
        # FR #4316: outer abort (e.g. LiveStateTouched escaping BuildRunner) must still
        # auto-file a release-blocker; suite-regression path alone left these untracked.
        result.setdefault("errors", []).append(f"{type(exc).__name__}: {exc}")
        announce = f"BUILD fail {repo} version={version}: {type(exc).__name__}: {str(exc)[:200]}"
        if filer is not None:
            try:
                filed = bb.file_runner_abort_blocker(
                    filer,
                    repo=repo,
                    version=version,
                    ref=ref,
                    exc=exc,
                    suite_name="",
                )
                result.setdefault("blockers", []).append(filed)
                url = str(filed.get("url") or "").strip()
                if url:
                    announce = f"{announce} blocker={url}"
                    print(f"build: filed release-blocker {url}", flush=True)
            except Exception as file_exc:
                result.setdefault("errors", []).append(
                    f"blocker_file_failed: {type(file_exc).__name__}: {file_exc}"
                )
        result["announce"] = [announce]
        rc = 1
    finally:
        if args.lock_file:
            try:
                bb.BuildLock(Path(args.lock_file), max_parallel=1).release(repo)
            except Exception:
                pass
        if job_path is not None:
            try:
                job_path.rename(job_path.with_suffix(".json.done" if rc == 0 else ".json.failed"))
            except Exception:
                pass
        text = json.dumps(result, indent=2, default=str)
        print(text)
        if args.result_file:
            Path(args.result_file).write_text(text, encoding="utf-8")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""FR #4608: assert a built jeeves PyInstaller tree embeds MRB exact-seat gitclaim.

Looks for ``PYZ-00.pyz`` under a build work dir (or a direct ``gitclaim*.pyc``),
reads it with PyInstaller's own ``ZlibArchiveReader`` (a PYZ is NOT a zip file,
see the follow-up to #4608), and inspects the frozen ``gitclaim`` *code object*.

Source-text markers such as ``if task == "MRB":`` do not survive compilation, so
the check is structural on bytecode of ``review_blocked_for_author``:

* its docstring carries ``FR #2604 / #4606``;
* it compares ``task`` with the constant ``"MRB"`` (``==``) and that compare comes
  *before* the first load of ``nick_inherits_dead_seat`` (MRB continues before the
  dead-seat inheritance, FR #2604 / #4606).

Exit 0 on pass, 1 on fail, 2 when no archive is present and --allow-missing.
"""

from __future__ import annotations

import argparse
import dis
import marshal
import sys
import types
from pathlib import Path

FUNC = "review_blocked_for_author"
DOC_MARKER = "FR #2604 / #4606"
INHERIT = "nick_inherits_dead_seat"
MODULE = "gitclaim"


def find_pyz(root: Path) -> Path | None:
    hits = sorted(root.rglob("PYZ-00.pyz"))
    return hits[0] if hits else None


def iter_code(co: types.CodeType):
    yield co
    for c in co.co_consts:
        if isinstance(c, types.CodeType):
            yield from iter_code(c)


def find_func(module_code: types.CodeType, name: str = FUNC) -> types.CodeType | None:
    for co in iter_code(module_code):
        if co.co_name == name:
            return co
    return None


def problems_in_module_code(module_code: types.CodeType) -> list[str]:
    """Return a list of reasons the frozen gitclaim lacks the fix ([] = OK)."""
    fn = find_func(module_code)
    if fn is None:
        return [f"function {FUNC} not found"]
    out: list[str] = []
    doc = fn.co_consts[0] if fn.co_consts and isinstance(fn.co_consts[0], str) else ""
    if DOC_MARKER not in doc:
        out.append(f"{FUNC} docstring lacks {DOC_MARKER!r}")
    instrs = list(dis.get_instructions(fn))
    mrb_eq: list[int] = []
    inherit_at: list[int] = []
    for i, ins in enumerate(instrs):
        if ins.opname == "LOAD_CONST" and ins.argval == "MRB":
            for nxt in instrs[i + 1 : i + 4]:
                if nxt.opname == "COMPARE_OP" and "==" in str(nxt.argrepr):
                    mrb_eq.append(ins.offset)
                    break
        if ins.argval == INHERIT and ins.opname.startswith("LOAD_"):
            inherit_at.append(ins.offset)
    if not mrb_eq:
        out.append(f'{FUNC} has no task == "MRB" compare')
    if not inherit_at:
        out.append(f"{FUNC} never calls {INHERIT}")
    if mrb_eq and inherit_at and min(mrb_eq) > min(inherit_at):
        out.append(f'{FUNC}: "MRB" check comes after {INHERIT} (stale embed)')
    return out


def _fail(msg: str) -> None:
    raise SystemExit(f"FR #4608: {msg}")


def read_pyz_module(pyz: Path, name: str = MODULE) -> types.CodeType:
    try:
        from PyInstaller.archive.readers import ZlibArchiveReader
    except Exception as exc:  # pragma: no cover - build box always has PyInstaller
        _fail(f"PyInstaller not importable to read {pyz}: {exc}")
    arch = ZlibArchiveReader(str(pyz))
    if name not in arch.toc:
        _fail(f"no {name} module in {pyz} (hidden-import missing?)")
    co = arch.extract(name)
    if isinstance(co, (bytes, bytearray)):
        co = marshal.loads(co)
    if not isinstance(co, types.CodeType):
        _fail(f"{name} in {pyz} is not a code object ({type(co).__name__})")
    return co


def check_module_code(co: types.CodeType, where: str) -> None:
    probs = problems_in_module_code(co)
    if probs:
        _fail(f"embedded gitclaim in {where} stale: " + "; ".join(probs))
    print(f"OK FR #4608: {where} embeds gitclaim with MRB exact-seat rule")


def check_pyz(pyz: Path) -> None:
    check_module_code(read_pyz_module(pyz), str(pyz))


def check_pyc_file(path: Path) -> None:
    data = path.read_bytes()
    check_module_code(marshal.loads(data[16:]), str(path))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("root", type=Path, help="Build work dir (contains PYZ-00.pyz) or a gitclaim.pyc path")
    p.add_argument("--allow-missing", action="store_true", help="Exit 2 (not 1) when no PYZ/gitclaim is found")
    args = p.parse_args(argv)
    root = args.root
    if not root.exists():
        if args.allow_missing:
            print(f"FR #4608: missing path {root} (allow-missing)", file=sys.stderr)
            return 2
        print(f"FR #4608: path not found: {root}", file=sys.stderr)
        return 1
    if root.is_file():
        check_pyc_file(root)
        return 0
    pyz = find_pyz(root)
    if pyz is None:
        loose = sorted(root.rglob("gitclaim*.pyc"))
        if loose:
            check_pyc_file(loose[0])
            return 0
        msg = f"FR #4608: no PYZ-00.pyz under {root}"
        if args.allow_missing:
            print(msg + " (allow-missing)", file=sys.stderr)
            return 2
        print(msg, file=sys.stderr)
        return 1
    check_pyz(pyz)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

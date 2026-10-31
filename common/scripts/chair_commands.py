"""Jeeves chair command surface (bobiverse#39 gaps: every gh-Jeeves @8d76d9a command).

Deterministic, token-less, no secrets. Pure functions (no sockets / no clock unless injected) so the
fake-IRC tests drive them exactly like the live chair does. ``irc_agent.Client`` is the thin glue.

gh-Jeeves reference commands restored here: !help !list (+ !filter alias) !status !stuck !resync !sweep !ignore
!ignored !unignore !focus !unfocus !recycle !build (FR #4006) !installtest (FR #4026) and the bare ``ping`` -> ``pong``. The shop wire (``!bored``,
``ACK``/``DONE``/``NACK``) lives in gitclaim / shop_listen and is not a PM command.

AUTHORIZATION MATRIX (see docs/jeeves-commands.md)::

    principal                        read cmds  !ignore !unignore !focus !unfocus !sweep !resync !recycle
    ------------------------------   ---------  ------- --------- ------ -------- ------ ------- --------
    owner: services account simon*   yes        yes     yes       yes    yes      yes    yes     yes
    ear: bob-<registered machine>**  yes        yes     yes       yes    yes      yes    yes     yes
    allowlist (JEEVES_FOCUS_MUT*)    yes        no      no        yes    yes      no     no      no
    anyone else                      yes        no      no        no     no       no     no      no

    *  The account must come from the server (account-tag / extended-join / account-notify / WHOIS 330).
       A nick alone ("simon") is never enough.
    ** Nick ``bob-<machine>`` of a machine in the ChanServ roster - the same trust root that earns the ear
       its +o/+h (chan_privs). If the server told us the nick is logged in to a DIFFERENT, non-owner
       account it is refused (someone else holding a look-alike nick).
"""
from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

ROLE_WORKER = "worker"
ROLE_BOB = "bob"
ROLE_SIMON = "simon"
ALL_ROLES = frozenset({ROLE_WORKER, ROLE_BOB, ROLE_SIMON})
OPS_ROLES = frozenset({ROLE_BOB, ROLE_SIMON})

HELP_LINE_MAX = 400
HELP_DETAIL_MAX_LINES = 5
HELP_RATE_S = 30.0
DEFAULT_RECYCLE_COOLDOWN_S = 120.0
DENIED_UNKNOWN = "unknown command; try !help"

SHOP_POINTER = (
    "note: !bored -> Jeeves assign, ACK/DONE/NACK in #{machine} are shop wire, not Jeeves PM - see README"
)


@dataclass(frozen=True)
class CommandSpec:
    name: str
    syntax: str
    summary: str
    roles: frozenset
    example: str = ""
    details: str = ""
    related: tuple = ()


COMMANDS: tuple = (
    CommandSpec("help", "!help [cmd]", "list commands or detail one command (PM only)", ALL_ROLES,
                "!help list", "Replies by private message only. Bare !help is one line per visible command.",
                ("list", "status")),
    CommandSpec("list", "!list [all|<repo>|fr|mrb|uat]", "queue by PM: one line per job (type in channel; reply is PM)",
                ALL_ROLES, "!list SimonBarnett/bobiverse",
                "In-channel or PM. !list all includes the whole queue; !list <repo> / fr / mrb / uat filter it.",
                ("filter", "help", "status", "resync")),
    CommandSpec("filter", "!filter [all|<repo>|fr|mrb|uat]", "alias of !list with a filter (PM reply)", ALL_ROLES,
                "!filter fr", "Same as !list <filter>: replies by PM, honours focus order and the ignore list.",
                ("list", "focus")),
    CommandSpec("status", "!status", "Jeeves version, uptime, queue counts, roster, last roster/queue refresh",
                ALL_ROLES, "!status", "Read-only snapshot from the digest home (queue.json / roster).",
                ("list", "resync", "help")),
    CommandSpec("register", "!register <#channel|machine>", "ChanServ REGISTER shop channel and add to roster (+o/+h gate)", OPS_ROLES,
                "!register ionos",
                "Chair-only. Authorised by live +o/+h in #bobiverse (FR #4008); operators.txt ignored. Bob ears never self-REGISTER.",
                ("unregister", "status")),
    CommandSpec("unregister", "!unregister <#channel|machine> [confirm]|dry-run <..>",
                "inverse of !register: ChanServ UNREGISTER, drop roster, PART shop (+o/+h gate)", OPS_ROLES,
                "!unregister dry-run ionos",
                "Chair-only. Dry-run prints the plan; real run needs confirm or a repeat within 60s. "
                "Core #bobiverse/#wonderland refused. Airc clients fall back to #wonderland (FR #3834). "
                "FR #5161: unregister is final locally (tombstone); a lagging ChanServ LIST cannot "
                "re-add or rejoin the shop until LIST confirms it is gone.",
                ("register", "status")),
    CommandSpec("resync", "!resync", "refresh the roster (ChanServ) now and re-sync open FR/MRB from GitHub with the Jeeves token (also automatic hourly / on webhook gap, FR #3212); purges ignored repos", OPS_ROLES, "!resync",
                "Restricted to simon and bob-* nicks. Webhook model: no GitHub token; the roster mirror is "
                "re-read from ChanServ and ignored repos are purged from the queue.", ("list", "status")),
    CommandSpec("sweep", "!sweep [channel]", "re-apply +h/+o grants in a channel", OPS_ROLES, "!sweep #bobiverse",
                "Jeeves auto-grants +h/+o to ears and +o to the verified owner; !sweep re-runs the plan. "
                "No channel text.", ("help", "status")),
    CommandSpec("ignore", "!ignore {repo}", "suppress a repo from the whole Jeeves process (simon/ops)", OPS_ROLES,
                "!ignore SimonBarnett/old-sandbox",
                "Adds owner/name or bare name to ignored.json. Ignored repos get no queue rows, no !list rows, "
                "no assign. Also purges already-queued items for that repo.", ("ignored", "unignore", "list")),
    CommandSpec("ignored", "!ignored", "list ignored repos by PM (open to anyone)", ALL_ROLES, "!ignored",
                "Replies by PM with the current ignore list (or ignored: (none)).", ("ignore", "unignore")),
    CommandSpec("unignore", "!unignore {repo}", "resume handling a previously ignored repo (simon/ops)", OPS_ROLES,
                "!unignore old-sandbox", "Removes the repo from ignored.json; new events are handled again.",
                ("ignore", "ignored")),
    CommandSpec("focus", "!focus [strict on|off]|[n|high|medium|low] {repo|owner/repo#N}",
                "priority-sort !list and assign-on-!bored (simon/ops)", OPS_ROLES, "!focus strict on",
                "focus.json beside the queue. Items (owner/repo#N) rank ahead of repo focus. Lower number first. "
                "Bare !focus lists strict flag, items, repos (read is open). !focus strict on|off: when on, "
                "!list and !bored only use focused work. Repos with GitHub topic priority-customer sort "
                "after non-customer work (refreshed on resync). Tag: "
                "gh repo edit SimonBarnett/<repo> --add-topic priority-customer. "
                "Explicit !focus / item focus on a customer repo still wins.", ("unfocus", "list")),
    CommandSpec("unfocus", "!unfocus {repo|owner/repo#N}|all", "remove repo/item focus or clear all (simon/ops)",
                OPS_ROLES, "!unfocus SimonBarnett/bobiverse#110", "Drops focus entries; !unfocus all clears all.",
                ("focus", "list")),
    CommandSpec("assign", "!assign {worker-nick} {repo} {FR|MRB|UAT|FIX} {num}",
                "Jeeves posts the normal assign line to one idle seat (simon/ops)", OPS_ROLES,
                "!assign marchhare-41928 SimonBarnett/bobiverse MRB 637",
                "Chair stamps that queued row offered to the seat and posts the usual assign line in its shop "
                "channel as Jeeves; the seat's ACK accepts it. Same checks as !bored: seat must be idle, no "
                "self-MRB/UAT, row unaccepted and not cooldown/given-up. FIX (FR #4652) enqueues a red open PR from GitHub when missing; needs_human FIX rows are refused. UAT is per repo: use num 0. Reply by PM.",
                ("focus", "list")),
    CommandSpec(
        "cleargiveup",
        "!cleargiveup owner/repo#N [seat]",
        "ops: clear queue giveup stamps and seat-ledger giveup for a job (FR #5135)",
        OPS_ROLES,
        "!cleargiveup SimonBarnett/bobiverse#5134 flamingo-9",
        "Under the queue lock: drop giveup_seats / cooldown_until / giveup_ts / giveup_count / "
        "needs_human on matching rows, or only the named seat from giveup_seats. Also clears "
        "seat-ledger.json giveup[owner/repo#n] for that seat or the whole key. Reply by PM.",
        ("assign", "list"),
    ),
    CommandSpec("recycle", "!recycle [machine|all|dry-run [machine|all]]",
                "route recycle to bob seats: bare/all = fleet; machine = one box; dry-run = plan only", OPS_ROLES,
                "!recycle marchhare",
                "Jeeves routes only. Bare !recycle or !recycle all = every roster seat. !recycle <machine> = that "
                "machine only. !recycle dry-run [..] authorises and plans but sends nothing. Local bob-* "
                "announces restarting then executes. Duplicates are cooldown-blocked.", ("help", "status")),
    CommandSpec(
        "build",
        "!build <owner/repo>[,owner/repo...] <version> [ref] | !build status|cancel|dry-run ...",
        "queue a deterministic repo BUILD (no agent); failures become release-blocker issues (FR #4006)",
        OPS_ROLES,
        "!build SimonBarnett/bobiverse 0.1.32",
        "Ops only (simon / bob-* / +o/+h). Runs the in-repo .bobiverse/build.yml on the recipe machine. "
        "<version> must be numeric x.y.z or x.y.z.w (digits only, e.g. 0.1.32 / 0.1.32.1); "
        "anything else (v0.1.32, 0.1.32-test2) is refused. "
        "Subcommands: status, cancel, dry-run. Per-repo single-flight; no recipe => refuse.",
        ("status", "list", "focus", "installtest"),
    ),
    CommandSpec(
        "installtest",
        "!installtest <owner/repo> <version> [tag] | !installtest dry-run <owner/repo> <version> [tag]",
        "msiexec install-test pre-release MSIs + post-checks; failures become release-blocker issues (FR #4026 WP3)",
        OPS_ROLES,
        "!installtest SimonBarnett/bobiverse 0.1.32",
        "Ops only (simon / bob-* / +o/+h). Optional follow-on after BUILD: msiexec /i /qn /l*v each product MSI "
        "from recipe install_test, post-check service/SASL/channels/seat ACK, file release-blocker on fail. "
        "Requires install_test in .bobiverse/build.yml; runs on recipe install_test.machine (fold-aware).",
        ("build", "status"),
    ),
    CommandSpec(
        "stuck",
        "!stuck",
        "list stuck/held open jobs from the stuck-job sweep (FR #5510)",
        ALL_ROLES,
        "!stuck",
        "Read-only. Shows silent accepted rows, untracked offerable opens, and held items with the rule. "
        "The sweep runs every 10 min in the chair (no agent).",
        ("status", "list", "resync"),
    ),
    CommandSpec("ping", "ping [nick-glob]", "channel or PM: reply pong (bare word, no !)", ALL_ROLES, "ping",
                "Jeeves answers pong to a bare ping, or to ping <glob> when the glob matches its nick.", ("help",)),
)
COMMAND_BY_NAME = {c.name: c for c in COMMANDS}


def get_command(name: str):
    return COMMAND_BY_NAME.get((name or "").strip().lstrip("!").lower())


def validate_registry() -> list:
    errs, seen = [], set()
    for c in COMMANDS:
        if c.name in seen:
            errs.append(f"duplicate:{c.name}")
        seen.add(c.name)
        if not c.syntax.strip() or not c.summary.strip() or not c.roles:
            errs.append(f"incomplete:{c.name}")
    return errs


# ------------------------------------------------------------------ nick / principal
_JUNK = dict.fromkeys(map(ord, "\ufeff\u200b\u200c\u200d\u2060\u00a0\x00"))


def _clean(s) -> str:
    return str(s if s is not None else "").translate(_JUNK).strip().lstrip(":").strip()


def owner_account() -> str:
    return (os.environ.get("JEEVES_OWNER_ACCOUNT") or "simon").strip().lower() or "simon"


def owner_accounts() -> set:
    out = {owner_account()}
    try:
        import chan_privs

        out |= {a.lower() for a in chan_privs.op_accounts()[0]}
    except Exception:
        pass
    return out


def _csv_env(name: str) -> set:
    return {p.strip().lower() for p in (os.environ.get(name) or "").split(",") if p.strip()}


@dataclass(frozen=True)
class Principal:
    kind: str                     # owner | ear | allowlist | none
    nick: str = ""
    account: str = ""
    machine: str = ""             # ear: roster machine id

    @property
    def ops(self) -> bool:
        return self.kind in ("owner", "ear")

    @property
    def roles(self) -> frozenset:
        if self.kind == "owner":
            return ALL_ROLES
        if self.kind == "ear":
            return frozenset({ROLE_BOB, ROLE_WORKER})
        return frozenset({ROLE_WORKER})


def classify(nick, account=None, *, ear_machine: Callable = lambda n: None) -> Principal:
    """Who is this? ``ear_machine(nick)`` -> roster machine id for ``bob-<machine>``, else None."""
    n = _clean(nick)
    low = n.lower()
    acct = _clean(account).lower()
    if acct and acct in owner_accounts():
        return Principal("owner", n, acct)
    mid = ear_machine(n) if low.startswith("bob-") else None
    if mid:
        if acct and acct not in (low, low.rstrip("_")) and not acct.startswith("bob-"):
            return Principal("none", n, acct)          # look-alike nick under someone else's account
        return Principal("ear", n, acct, mid)
    if acct and acct in _csv_env("JEEVES_FOCUS_MUTATOR_ACCOUNTS"):
        return Principal("allowlist", n, acct)
    if low and low in _csv_env("JEEVES_FOCUS_MUTATORS"):
        return Principal("allowlist", n, acct)
    return Principal("none", n, acct)


MATRIX = {
    # command -> who may run it
    "help": "any", "list": "any", "filter": "any", "status": "any", "ignored": "any", "stuck": "any", "ping": "any",
    "focus-read": "any",
    "ignore": "ops", "unignore": "ops", "sweep": "ops", "resync": "ops", "recycle": "ops", "build": "ops",
    "installtest": "ops", "assign": "ops", "cleargiveup": "ops",
    "focus": "ops+allow", "unfocus": "ops+allow",
}


def may(cmd: str, who: Principal) -> bool:
    rule = MATRIX.get(cmd, "ops")
    if rule == "any":
        return True
    if rule == "ops+allow":
        return who.kind in ("owner", "ear", "allowlist")
    return who.ops


def denied_line(cmd: str) -> str:
    return {
        "ignore": "ignore: denied (simon or bob-* ops only)",
        "unignore": "unignore: denied (simon or bob-* ops only)",
        "focus": "focus: denied (owner account required)",
        "unfocus": "unfocus: denied (owner account required)",
        "recycle": "recycle: denied (authorised operator + services account required)",
        "resync": "resync: denied (simon or bob-* ops only)",
        "sweep": "sweep: denied (simon or bob-* ops only)",
        "build": "build: denied (simon or bob-* ops only)",
        "installtest": "installtest: denied (simon or bob-* ops only)",
        "assign": "assign: denied (simon or bob-* ops only)",
        "cleargiveup": "cleargiveup: denied (simon or bob-* ops only)",
    }.get(cmd, f"{cmd}: denied")


# ------------------------------------------------------------------ parsing
_HELP_RE = re.compile(r"^!+\s*help(?:\s+(\S+))?\s*$", re.I)
_STATUS_RE = re.compile(r"^!+\s*status\s*$", re.I)
_STUCK_RE = re.compile(r"^!+\s*stuck\s*$", re.I)
_RESYNC_RE = re.compile(r"^!+\s*resync\s*$", re.I)
_SWEEP_RE = re.compile(r"^!+\s*sweep(?:\s+(#?\S+))?\s*$", re.I)
_FILTER_RE = re.compile(r"^!+\s*filter\b(.*)$", re.I)
_RECYCLE_RE = re.compile(r"^!+\s*recycle(?:\s+(.*))?$", re.I)
_PING_RE = re.compile(r"^ping(?:\s+(\S+))?\s*$", re.I)


def parse_help(body: str):
    m = _HELP_RE.match((body or "").strip())
    if not m:
        return False, None
    arg = m.group(1)
    return True, (arg.lstrip("!").lower() if arg else None)


def is_status(body: str) -> bool:
    return bool(_STATUS_RE.match((body or "").strip()))


def is_stuck(body: str) -> bool:
    return bool(_STUCK_RE.match((body or "").strip()))


def stuck_lines(home: Path) -> list:
    import stuck_job_sweep
    return stuck_job_sweep.format_stuck_lines(home)


def is_resync(body: str) -> bool:
    return bool(_RESYNC_RE.match((body or "").strip()))


def parse_sweep(body: str):
    """None = not a sweep; '' = bare; '#chan' otherwise."""
    m = _SWEEP_RE.match((body or "").strip())
    if not m:
        return None
    ch = m.group(1)
    if not ch:
        return ""
    return ch if ch.startswith("#") else "#" + ch


def filter_to_list(body: str):
    """``!filter fr`` -> ``!list fr`` (alias); anything else -> None."""
    m = _FILTER_RE.match((body or "").strip())
    if not m:
        return None
    rest = m.group(1).strip()
    return ("!list " + rest).strip()


def parse_ping(body: str):
    m = _PING_RE.match((body or "").strip())
    if not m:
        return False, None
    return True, m.group(1)


def ping_matches(pattern, nick: str) -> bool:
    if pattern is None:
        return True
    esc = re.escape(pattern)
    return bool(re.fullmatch(esc.replace(r"\*", ".*").replace(r"\?", "."), nick or "", re.I))


def parse_recycle(body: str):
    """-> (is_recycle, dry_run, arg|None). ``!recycle dry-run marchhare`` -> (True, True, 'marchhare')."""
    m = _RECYCLE_RE.match((body or "").strip())
    if not m:
        return False, False, None
    toks = (m.group(1) or "").split()
    dry = False
    if toks and toks[0].lower() in ("dry-run", "dryrun", "dry", "plan", "check"):
        dry, toks = True, toks[1:]
    return True, dry, (toks[0].lower() if toks else None)


# ------------------------------------------------------------------ !help
def _clip(line: str, n: int = HELP_LINE_MAX) -> str:
    line = re.sub(r"\s+", " ", (line or "").replace("\r", " ").replace("\n", " ")).strip()
    b = line.encode("utf-8")
    if len(b) <= n:
        return line
    return b[: n - 3].decode("utf-8", "ignore") + "..."


def commands_for(roles) -> list:
    want = set(roles)
    return [c for c in COMMANDS if c.roles & want]


@dataclass
class HelpRate:
    interval_s: float = HELP_RATE_S
    _last: dict = field(default_factory=dict)

    def allow(self, nick: str, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        key = (nick or "").lower()
        prev = self._last.get(key)
        if prev is not None and now - prev < self.interval_s:
            return False
        self._last[key] = now
        return True

    def remaining(self, nick: str, now: float | None = None) -> float:
        now = time.time() if now is None else now
        prev = self._last.get((nick or "").lower())
        return 0.0 if prev is None else max(0.0, self.interval_s - (now - prev))


def index_line(c: CommandSpec) -> str:
    return _clip(f"{c.syntax} - {c.summary} [{','.join(sorted(c.roles))}]")


def detail_lines(c: CommandSpec) -> list:
    lines = [_clip(f"syntax: {c.syntax}"),
             _clip(f"what: {c.summary}" + (f" - {c.details}" if c.details else "")),
             _clip(f"who: {', '.join(sorted(c.roles))}")]
    if c.example:
        lines.append(_clip(f"example: {c.example}"))
    if c.related:
        lines.append(_clip("related: " + " ".join("!" + r for r in c.related)))
    return lines[:HELP_DETAIL_MAX_LINES]


def build_help(who: Principal, arg=None, *, rate: HelpRate | None = None, now: float | None = None) -> list:
    if rate is not None and not rate.allow(who.nick, now):
        return [_clip(f"rate limit: wait {int(rate.remaining(who.nick, now) + 0.999)}s before !help again")]
    roles = who.roles
    if arg:
        spec = get_command(arg)
        if spec is None or not (spec.roles & roles):
            return [DENIED_UNKNOWN]
        return detail_lines(spec)
    return [index_line(c) for c in commands_for(roles)] + [_clip(SHOP_POINTER)]


# ------------------------------------------------------------------ !status
def resolve_jeeves_install_root(
    *,
    env: dict | None = None,
    frozen: bool | None = None,
    executable: str | Path | None = None,
    file_path: str | Path | None = None,
    explicit: str | Path | None = None,
) -> Path:
    """Install root for chair VERSION (FR #2728; same frozen family as FR #2666).

    Priority: ``explicit`` → ``JEEVES_INSTALL_ROOT`` → ``BOB_INSTALL_ROOT`` →
    frozen ``sys.executable`` layout (``<root>\\jeeves\\jeeves.exe`` or
    ``<root>\\jeeves.exe``) → source ``common/`` parent of ``chair_commands.py``.
    """
    import sys

    if explicit is not None and str(explicit).strip():
        return Path(str(explicit).strip()).resolve()
    e = os.environ if env is None else env
    for key in ("JEEVES_INSTALL_ROOT", "BOB_INSTALL_ROOT"):
        override = (e.get(key) or "").strip()
        if override:
            return Path(override).resolve()
    is_frozen = (
        bool(getattr(sys, "frozen", False)) or hasattr(sys, "_MEIPASS")
        if frozen is None
        else bool(frozen)
    )
    if is_frozen:
        exe = Path(sys.executable if executable is None else executable).resolve()
        # Pack stages jeeves\\jeeves.exe under InstallRoot (Install-Jeeves.ps1).
        if exe.parent.name.lower() == "jeeves":
            return exe.parent.parent
        return exe.parent
    here = Path(__file__ if file_path is None else file_path).resolve().parent
    return here.parent


def _version_from_file(path: Path) -> str | None:
    try:
        v = path.read_text(encoding="utf-8-sig").strip()
    except OSError:
        return None
    if not v:
        return None
    return v.splitlines()[0].strip() or None


def read_version(
    root: Path | None = None,
    *,
    env: dict | None = None,
    frozen: bool | None = None,
    executable: str | Path | None = None,
    file_path: str | Path | None = None,
    meipass: str | Path | None = None,
) -> str:
    """Resolve chair VERSION; prefer install root over PyInstaller ``_MEIPASS`` (FR #2728)."""
    import sys

    e = os.environ if env is None else env
    for key in ("BOBIVERSE_VERSION", "BOB_VERSION", "JEEVES_VERSION"):
        env_ver = (e.get(key) or "").strip()
        if env_ver:
            return env_ver.splitlines()[0].strip()[:64]

    roots: list[Path] = []
    if root is not None:
        roots.append(Path(root))
    try:
        roots.append(
            resolve_jeeves_install_root(
                env=e, frozen=frozen, executable=executable, file_path=file_path
            )
        )
    except Exception:
        pass
    # Source layout: common/VERSION beside scripts/, and repo root VERSION.
    here = Path(__file__ if file_path is None else file_path).resolve().parent
    roots.extend([here.parent, here.parent.parent])

    seen: set[str] = set()
    for base in roots:
        key = str(base.resolve()) if base.exists() else str(base)
        if key in seen:
            continue
        seen.add(key)
        for p in (base / "VERSION", base / "src" / "VERSION", base / "common" / "VERSION"):
            got = _version_from_file(p)
            if got:
                return got

    # Bundled PyInstaller data last (Build-Jeeves --add-data VERSION).
    mei = meipass
    if mei is None:
        mei = getattr(sys, "_MEIPASS", None)
    if mei:
        got = _version_from_file(Path(mei) / "VERSION")
        if got:
            return got
    return "?"


def count_digest_doing_seats(home: Path) -> int:
    """Count digest ``worker_list`` rows with ``state=doing`` (FR #2728)."""
    import bobreport

    try:
        doc = bobreport.load_digest(Path(home))
    except Exception:
        return 0
    machines = doc.get("machines") if isinstance(doc, dict) else None
    if not isinstance(machines, dict):
        return 0
    n = 0
    for ent in machines.values():
        if not isinstance(ent, dict):
            continue
        try:
            rows = bobreport._coerce_worker_list(ent.get("worker_list"))
        except Exception:
            continue
        for row in rows:
            if str(row.get("state") or "").lower() == "doing":
                n += 1
    return n


def status_lines(home: Path, *, started: float, now: float | None = None, version: str | None = None) -> list:
    import bobreport
    import gitclaim
    import registered_machines

    now = time.time() if now is None else now
    un = acc = 0
    try:
        un = len(gitclaim.load_unaccepted(home))
        acc = len(gitclaim.load_accepted(home))
    except Exception:
        pass
    busy = 0
    try:
        busy = count_digest_doing_seats(home)
    except Exception:
        busy = 0
    try:
        mids = list(bobreport.roster_machine_ids(Path(home)))
    except Exception:
        mids = []
    age = None
    try:
        age = registered_machines.registry_age_s(Path(bobreport.fleet_digest_home(Path(home))), now)
    except Exception:
        pass
    return [
        f"Jeeves status: version={version or read_version()} uptime_s={int(max(0, now - started))}",
        f"queue: unaccepted={un} accepted={acc}",
        f"workers: busy={busy}",
        f"roster: machines={len(mids)} ({', '.join(mids)})" if mids else "roster: machines=0",
        f"last_resync: roster {('%ds ago' % int(age)) if age is not None else 'n/a'}",
    ]


# ------------------------------------------------------------------ !recycle (decision only)
RECYCLE_STEPS = ("stop_managed_workers", "cleanup_owned_orphans", "git_ff_only", "reload_skills", "restart_workers")


@dataclass
class RecycleGate:
    cooldown_s: float = DEFAULT_RECYCLE_COOLDOWN_S
    _last: dict = field(default_factory=dict)

    def allow(self, key: str, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        prev = self._last.get(key)
        if prev is not None and now - prev < self.cooldown_s:
            return False
        self._last[key] = now
        return True

    def remaining(self, key: str, now: float | None = None) -> float:
        now = time.time() if now is None else now
        prev = self._last.get(key)
        return 0.0 if prev is None else max(0.0, self.cooldown_s - (now - prev))


@dataclass
class RecycleDecision:
    ok: bool
    reason: str = ""
    pm_lines: list = field(default_factory=list)
    machine: str = ""            # roster id | 'fleet' | 'jeeves'
    scope: str = "local"         # local | fleet
    dry_run: bool = False
    route: str = ""              # wire line to post in #bobiverse (empty for dry-run / chair-local / jeeves)


def decide_recycle(*, who: Principal, arg, dry_run: bool, roster: tuple, resolve: Callable,
                   gate: RecycleGate, now: float | None = None) -> RecycleDecision:
    if not may("recycle", who):
        return RecycleDecision(False, "denied", [denied_line("recycle")])
    raw = (arg or "").strip().lower() or None
    if raw in (None, "all", "fleet"):
        mid, scope = "fleet", "fleet"
    elif raw in ("jeeves", "ircjeeves"):
        mid, scope = "jeeves", "local"
    else:
        mid, scope = resolve(raw) or "", "local"
        if not mid:
            return RecycleDecision(False, "unknown_machine",
                                   [f"recycle: unknown machine {raw} (want: {', '.join(roster)}, all)"],
                                   dry_run=dry_run)
    key = "fleet" if scope == "fleet" else mid
    if not dry_run and not gate.allow(key, now):
        return RecycleDecision(False, "cooldown",
                               [f"recycle: cooldown {int(gate.remaining(key, now) + 0.999)}s (duplicate prevented)"],
                               mid, scope)
    steps = ", ".join(RECYCLE_STEPS)
    route = f"RECYCLE machine={mid} by={who.nick or '-'} scope={scope} exec=local-bob-seat"
    ack = f"Recycling all seats ({', '.join(roster)})." if scope == "fleet" else f"Recycling {mid}."
    if dry_run:
        return RecycleDecision(True, "dry_run", [
            f"recycle dry-run: would recycle {mid} ({scope}) as {who.kind}; nothing sent",
            f"recycle dry-run: route={route}",
            f"recycle dry-run: steps={steps}",
        ], mid, scope, True, "")
    return RecycleDecision(True, "ok", [
        ack,
        f"recycle: routed to bob seat(s) ({scope} {mid}); Jeeves runs no host ops",
        f"recycle: steps={steps}",
        "recycle: bob must announce restarting then execute (deterministic)",
    ], mid, scope, False, route)

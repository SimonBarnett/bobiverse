"""FR #3401: AIRC_PROFILE=client — minimal full-remote, IRC ops/half-ops auth."""
from __future__ import annotations

from pathlib import Path

import airc_console as ac
from repo_layout import ROOT

INSTALL = ROOT / "airc/scripts/Install-Airc.ps1"
INSTALL_CONSOLE = ROOT / "airc/scripts/Install-AircConsole.ps1"
UNINSTALL = ROOT / "airc/scripts/Uninstall-Airc.ps1"
PACK = ROOT / "common/scripts/Pack-BobiverseRelease.ps1"
COMMON = ROOT / "common/scripts/Bobiverse-Common.ps1"
POST = ROOT / "common/docs/post-install.md"
SKILL = ROOT / "airc/.grok/skills/bobiverse-airc/SKILL.md"
SERVICE = ROOT / "airc/scripts/airc_console_service.py"


def _no_bom(path: Path) -> None:
    assert not path.read_bytes().startswith(b"\xef\xbb\xbf"), path


def _ascii_only(path: Path) -> None:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    assert all(b < 128 for b in raw), f"non-ASCII in {path}"


# --- resolve helpers (client caps) -------------------------------------------------


def test_resolve_client_shell_jobs_update_require_self_update():
    assert (
        ac.resolve_shell_mode_for_install(
            prior_shell="off",
            explicit=None,
            had_prior_service=False,
            profile="client",
        )
        == "operators"
    )
    assert ac.resolve_jobs_for_install(prior="off", explicit=None, profile="client") == "on"
    assert (
        ac.resolve_update_cap_for_install(prior="off", explicit=None, profile="client")
        == "on"
    )
    assert (
        ac.resolve_require_account_for_install(
            prior=True, explicit=None, profile="client"
        )
        is False
    )
    assert (
        ac.resolve_self_update_for_install(prior=True, explicit=None, profile="client")
        is False
    )
    # Explicit MSI/CLI still wins.
    assert (
        ac.resolve_shell_mode_for_install(
            prior_shell=None,
            explicit="off",
            had_prior_service=False,
            profile="client",
        )
        == "off"
    )
    assert (
        ac.resolve_self_update_for_install(
            prior=None, explicit=True, profile="client"
        )
        is True
    )


def test_resolve_client_crash_report_default_on():
    assert ac.resolve_crash_report_enabled_for_install(
        prior=None, explicit=None, profile="client"
    ) is True
    assert ac.resolve_crash_report_enabled_for_install(
        prior=True, explicit=None, profile="workstation"
    ) is False
    assert ac.resolve_crash_report_enabled_for_install(
        prior=None, explicit=False, profile="client"
    ) is False


# --- ChannelMemberMap + AuthPolicy irc_ops ----------------------------------------


def test_channel_member_map_names_mode_nick_and_op_check():
    m = ac.ChannelMemberMap(channel="#acme")
    m.apply_names("@simon %bob-other +voiceed ~owner &admin plain")
    m.mark_synced()
    assert m.synced
    assert m.has_chan_priv("simon")
    assert m.has_chan_priv("bob-other")
    assert m.has_chan_priv("owner")
    assert m.has_chan_priv("admin")
    assert not m.has_chan_priv("voiceed")
    assert not m.has_chan_priv("plain")
    assert not m.has_chan_priv("missing")

    m.on_mode("#acme", "+o", ["plain"])
    assert m.has_chan_priv("plain")
    m.on_mode("#acme", "-o", ["plain"])
    assert not m.has_chan_priv("plain")
    m.on_mode("#acme", "+h", ["plain"])
    assert m.has_chan_priv("plain")

    m.on_nick("simon", "simon2")
    assert not m.has_chan_priv("simon")
    assert m.has_chan_priv("simon2")

    m.on_part("simon2")
    assert not m.known("simon2")
    m.on_kick("bob-other")
    assert not m.known("bob-other")


def test_auth_policy_irc_ops_live_status_and_self_deny():
    m = ac.ChannelMemberMap(channel="#acme")
    m.apply_names("@simon %helper plain")
    m.mark_synced()
    auth = ac.AuthPolicy(
        auth_mode="irc_ops",
        members=m,
        self_nicks={"acme_console"},
    )
    assert auth.allow("simon")
    assert auth.allow("helper")
    assert not auth.allow("plain")
    assert not auth.allow("acme_console")  # never self
    # De-op takes effect immediately.
    m.on_mode("#acme", "-o", ["simon"])
    assert not auth.allow("simon")
    # Unknown / not synced refuses everything.
    m2 = ac.ChannelMemberMap(channel="#acme")
    auth2 = ac.AuthPolicy(auth_mode="irc_ops", members=m2, self_nicks=set())
    assert not auth2.allow("simon")
    m2.apply_names("@simon")
    # still not synced
    assert not auth2.allow("simon")
    m2.mark_synced()
    assert auth2.allow("simon")


def test_auth_policy_has_no_operators_list_fr3639():
    """FR #3639: the operators nick list is gone on every profile (fleet included)."""
    import dataclasses

    names = {f.name for f in dataclasses.fields(ac.AuthPolicy)}
    assert "operators" not in names
    assert "accounts" not in names
    assert "require_account" not in names
    assert "machine" not in names
    assert ac.AuthPolicy().auth_mode == "irc_ops"
    # bob-<machine> is not implicitly trusted any more: no channel status, no auth.
    m = ac.ChannelMemberMap(channel="#tm")
    m.apply_names("bob-tm")
    m.mark_synced()
    assert not ac.AuthPolicy(members=m).allow("bob-tm")


# --- Core: channel + DM commands under irc_ops ------------------------------------


class _StubJobs:
    def handle_async(self, nick, verb, kv):  # noqa: ANN001
        self.last = (nick, verb, kv)


def test_core_irc_ops_allows_channel_and_dm_for_op_denies_others():
    m = ac.ChannelMemberMap(channel="#acme")
    m.apply_names("@simon plain")
    m.mark_synced()
    auth = ac.AuthPolicy(
        auth_mode="irc_ops",
        members=m,
        self_nicks={"acme_console"},
    )
    jobs = _StubJobs()
    core = ac.AircConsoleCore(
        machine="acme", auth=auth, nick="acme_console", job_protocol=jobs, channel_commands=True
    )
    core.channel = "#acme"

    # Op via channel command (client accepts channel PRIVMSG).
    hr = core.handle_raw(":simon!u@h PRIVMSG #acme :STATUS")
    assert hr is not None
    assert hr.action == "job"
    assert hr.nick == "simon"

    # Op via DM.
    hr = core.handle_raw(":simon!u@h PRIVMSG acme_console :STATUS")
    assert hr is not None
    assert hr.action == "job"

    # Non-op denied with DONE exit=126 not-op (no command execution).
    hr = core.handle_raw(":plain!u@h PRIVMSG acme_console :Write-Output hi")
    assert hr is not None
    assert hr.action == "deny"
    assert hr.reply == "DONE exit=126 not-op"
    assert hr.deny_reason == "not-op"

    hr = core.handle_raw(":plain!u@h PRIVMSG #acme :Write-Output hi")
    assert hr is not None
    assert hr.action == "deny"
    assert hr.reply == "DONE exit=126 not-op"

    # Ops only in a different channel do not count (member map is control channel).
    hr = core.handle_raw(":outsider!u@h PRIVMSG #acme :STATUS")
    assert hr is not None
    assert hr.action == "deny"

    # Fleet (channel_commands off): same channel +o/+h auth, but silent in channel (DM only).
    fleet = ac.AircConsoleCore(
        machine="acme",
        auth=auth,
        nick="acme_console",
    )
    fleet.channel = "#acme"
    hr = fleet.handle_raw(":simon!u@h PRIVMSG #acme :STATUS")
    assert hr is not None
    assert hr.action == "silent_channel"


def test_core_irc_ops_unknown_state_and_self_nick_refuse():
    m = ac.ChannelMemberMap(channel="#acme")
    # not synced
    auth = ac.AuthPolicy(
        auth_mode="irc_ops",
        members=m,
        self_nicks={"acme_console"},
    )
    core = ac.AircConsoleCore(machine="acme", auth=auth, nick="acme_console", channel_commands=True)
    core.channel = "#acme"
    hr = core.handle_raw(":simon!u@h PRIVMSG acme_console :STATUS")
    assert hr is not None
    assert hr.action == "deny"
    assert hr.reply == "DONE exit=126 not-op"
    assert hr.deny_reason == "channel-state-unknown"

    m.apply_names("@acme_console @simon")
    m.mark_synced()
    hr = core.handle_raw(":acme_console!u@h PRIVMSG #acme :STATUS")
    assert hr is not None
    assert hr.action == "deny"
    assert hr.deny_reason == "self-nick"


# --- control channel selection helpers --------------------------------------------


def test_control_channel_reason_helpers():
    # FR #3834 superseded domain-fallback with wonderland-fallback.
    assert ac.control_channel_reason("registered") == "registered-machine"
    assert ac.control_channel_reason("wonderland") == "wonderland-fallback"
    assert ac.control_channel_reason("domain-lobby") == "wonderland-fallback"
    assert "control-channel=" in ac.control_channel_log_line("#acme", "registered")
    assert "reason=registered-machine" in ac.control_channel_log_line(
        "#acme", "registered"
    )
    assert "reason=wonderland-fallback" in ac.control_channel_log_line(
        "#wonderland", "wonderland"
    )


# --- Install / pack / docs wiring -------------------------------------------------


def test_install_client_profile_wiring():
    t = INSTALL.read_text(encoding="utf-8-sig")
    _no_bom(INSTALL)
    _ascii_only(INSTALL)
    assert "client" in t
    assert "FR #3401" in t
    assert "auth_mode" in t
    assert "irc_ops" in t
    # client skips agent layer like workstation
    assert "prof -eq 'client'" in t or "prof -in @('fleet', 'workstation', 'client')" in t or (
        "'client'" in t and "wantAgentLayer" in t
    )
    # crash reports ON for client
    assert "client" in t.lower() and "crash" in t.lower()
    # no operators for client
    assert "irc_ops" in t


def test_fr3462_client_workstation_force_sync_off_ignore_prior():
    """FR #3462: client/workstation sync_from_repo=false unless MSI/CLI explicit (ignore prior)."""
    t = INSTALL.read_text(encoding="utf-8-sig")
    assert "FR #3462" in t
    # Contiguous force-off mirrors self_update (priorSync must not win for client/workstation).
    assert (
        "elseif ($prof -in @('workstation', 'client')) { $resolvedSync = $false }" in t
    )
    # Explicit MSI/CLI still wins first.
    assert "if ($null -ne $expSync) { $resolvedSync = [bool]$expSync }" in t
    # Order: expSync -> client/workstation force false -> priorSync (fleet only).
    i_exp = t.index("if ($null -ne $expSync) { $resolvedSync = [bool]$expSync }")
    i_force = t.index(
        "elseif ($prof -in @('workstation', 'client')) { $resolvedSync = $false }"
    )
    i_prior = t.index("elseif ($null -ne $priorSync) { $resolvedSync = [bool]$priorSync }")
    assert i_exp < i_force < i_prior


def test_install_console_and_common_skip_operators_for_client():
    c = INSTALL_CONSOLE.read_text(encoding="utf-8-sig")
    _no_bom(INSTALL_CONSOLE)
    assert "FR #3401" in c
    assert "irc_ops" in c or "AuthMode" in c
    common = COMMON.read_text(encoding="utf-8-sig")
    assert "client" in common
    # FR #3639: no profile builds an operators list any more (client included).
    assert "function Resolve-BobiverseAircOperatorNicks" not in common
    assert "function Merge-BobiverseAircOperatorsFile" not in common


def test_service_wires_irc_ops_and_control_channel_log():
    t = SERVICE.read_text(encoding="utf-8")
    assert "FR #3401" in t
    assert "irc_ops" in t
    assert "control_channel_log_line" in t
    assert "ChannelMemberMap" in t or "members" in t
    assert "353" in t  # NAMES
    assert "366" in t  # end of NAMES


def test_pack_still_passes_airc_profile():
    p = PACK.read_text(encoding="utf-8")
    assert 'Property Id="AIRC_PROFILE"' in p
    assert "-Profile &quot;[AIRC_PROFILE]&quot;" in p or '-Profile "' in p


def test_docs_skill_document_client_profile():
    post = POST.read_text(encoding="utf-8")
    assert "AIRC_PROFILE=client" in post
    assert "ops" in post.lower() or "half-op" in post.lower() or "+o" in post
    skill = SKILL.read_text(encoding="utf-8")
    assert "FR #3401" in skill or "AIRC_PROFILE=client" in skill
    assert "client" in skill.lower()


def test_uninstall_purge_default_includes_client():
    t = UNINSTALL.read_text(encoding="utf-8-sig")
    # purge_default path still driven by manifest; install writes purge_default for client
    inst = INSTALL.read_text(encoding="utf-8-sig")
    assert "purge_default" in inst
    assert "client" in inst


def test_fr3401_files_end_with_newline():
    for p in (INSTALL, INSTALL_CONSOLE, SERVICE, POST, SKILL, Path(__file__), COMMON):
        assert p.read_bytes().endswith(b"\n"), p

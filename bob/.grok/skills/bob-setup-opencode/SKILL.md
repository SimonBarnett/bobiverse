---
name: setup-bob-opencode
description: >
  Install or repair OpenCode on a Bob Fleet Windows seat, put opencode.exe on
  PATH, configure the opencode-go provider key from the session env/secret store,
  bring up fuel ids opencode-free and opencode-go, or when Bob must start an
  OpenCode worker seat without Simon pasting secrets. Use when winget install
  fails, opencode is not recognized, auth is missing, or /setup-bob-opencode.
github: https://github.com/SimonBarnett/bobiverse
---

# Setup Bob OpenCode (Windows seat)

Home: `SimonBarnett/bobiverse` `bob/.grok/skills/bob-setup-opencode`. Honesty box:
using this skill obliges a harvest PR/issue back here (see `harvest-agent-skills`).
Fuel ids: `opencode-free`, `opencode-go`.

## Why OpenCode

Low-cost CLI coding agent for routine FR/fix PRs, docs PRs and harvest work when
Cursor Models / Grok seats are thin or capped. Hostile MRB stays on a stronger
seat (Grok first, then Cursor). CodeRabbit stays advisory, never required.

## CAST IRON — never put API keys in code, tests, logs, argv, IRC or docs

Keys live only in `%USERPROFILE%\.local\share\opencode\auth.json` (written by
`/connect` or `opencode auth login`) and the User env / secret store. Restrict
ACL to the seat user. Never read a key into agent context or paste it into chat.

## Install (winget)

```powershell
# 1) Install / update OpenCode CLI
winget install -e --id SST.opencode
# Verified MarchHare: 1.19.5 lands opencode.exe on PATH via
# %LOCALAPPDATA%\Microsoft\WinGet\Links\opencode.exe

# 2) Verify
opencode --version
opencode models opencode-go
```

If winget is blocked, download the portable Windows binary from opencode.ai, place
it under `%LOCALAPPDATA%\Programs\opencode\opencode.exe`, and add that folder to
the User PATH.

## Auth (session env / secret store only)

### 1) Check seat first

```powershell
Test-Path "$env:USERPROFILE\.local\share\opencode\auth.json"
# Provider id should be "opencode-go"
```

If `auth.json` exists and the provider key is populated, skip create — go to
smoke.

### 2) Authenticate without exposing the key

1. Box browser → `https://opencode.ai` sign-in / API key page.
2. Use `request_user_form` for typed steps; captcha / passkey / device approval →
   `request_box_help`. Host fills; Bob never sees values.
3. Create/copy the provider key for `opencode-go`.
4. Build or copy the **complete** `auth.json` body for provider `opencode-go`
   (a bare key is not a valid auth document). Write **only** that JSON body to box
   `/workspace/secrets/opencode-auth-<machine>.json`, mode `600`. Report **path +
   byte length only** — never the key, never the token in Task reports, screenshots
   captions, or chat. Alternatively, run `opencode auth login` on the seat to
   create the file before restricting its ACL.
5. CopyFromBox to an allowed local-exec path, then move to
   `%USERPROFILE%\.local\share\opencode\auth.json`. Reset inherited or stale
   explicit ACEs, then restrict ACL to the seat user and verify it succeeded:

```powershell
$authDir = Join-Path $env:USERPROFILE '.local\share\opencode'
New-Item -ItemType Directory -Force -Path $authDir | Out-Null
# Move the box-landed file into place; do NOT Read it into agent context.
$authFile = Join-Path $authDir 'auth.json'
icacls $authFile /reset
if ($LASTEXITCODE -ne 0) { throw "failed to reset auth.json ACL" }
icacls $authFile /inheritance:r /grant:r "$($env:USERNAME):(R)"
if ($LASTEXITCODE -ne 0) { throw "failed to restrict auth.json ACL" }
```

Delete the box secret file after a successful seat install.

## Smoke (headless)

Re-apply the ACL on the existing `auth.json` before the smoke test so every
install path restricts access:

```powershell
$authFile = Join-Path $env:USERPROFILE '.local\share\opencode\auth.json'
icacls $authFile /reset
if ($LASTEXITCODE -ne 0) { throw "failed to reset auth.json ACL" }
icacls $authFile /inheritance:r /grant:r "$($env:USERNAME):(R)"
if ($LASTEXITCODE -ne 0) { throw "failed to restrict auth.json ACL" }
```

```powershell
# Free model (no account)
opencode run -m opencode-free/beam-free "Reply with pong only"

# Go model (subscription)
opencode run -m opencode-go/glm-5.3 "Reply with pong only"
```

Verified MarchHare: `glm-5.3`, `glm-5.3-flash`, `kimi-k2.7-code`, `longcat-2.0`
all reply `pong`. `opencode models opencode-go` lists ~30 models. There is no
`kimi-k2.6` in the Go catalog. The worker picks the first fallback model that
has positive per-model fuel; it will not fall back to another capped model.

## Fleet wire-up

1. Fuel ids `opencode-free` and `opencode-go` on the digest webhook. Remaining %
   is estimated from local `opencode stats` cost vs the per-model monthly caps
   (e.g. glm-5.3 $15, kimi-k2.7-code $60); `n/a` when unknown, like other pools.
2. Worker loop: join `#{machine}`, `!bored` **after the agent is ready** and after
   DONE / NACK / GIVEUP / 2m idle, ACK/DONE to Jeeves. The program posts `!bored`;
   the model must never post it.
3. Out-of-fuel: the worker refuses offers when the current model's cap is hit.
   It then picks the first Go model in fallback order with positive remaining fuel
   (using per-model readings from the digest), then the free model, else goes idle.

## Model / plan notes

| Plan | Models | Typical flag |
|------|--------|--------------|
| Free (no account) | `beam-free`, `iceman-contributor-free` | `opencode run -m opencode-free/beam-free ...` |
| Go ($10/mo) | `glm-5.3`, `glm-5.3-flash`, `glm-5.2`, `kimi-k3`, `kimi-k2.7-code`, `longcat-2.0`, `deepseek-v4.1-flash`, `qwen3.8-flash` | `opencode run -m opencode-go/<model> ...` |

Go limits are per-model dollar allowances with rolling caps: 20% per 5h, 50% per
week, 100% per month. `opencode stats` shows local cost only; there is no public
remaining-quota API.

## Troubleshoot

| Symptom | Fix |
|---------|-----|
| `opencode : The term 'opencode' is not recognized` | WinGet install incomplete or Links folder not on PATH; use full path or add `%LOCALAPPDATA%\Microsoft\WinGet\Links` to User PATH |
| Auth errors / 401 | Re-run `opencode auth login`; verify `auth.json` provider id is `opencode-go` |
| Model 429 / cap hit | Seat falls back to another Go model or free model; digest fuel reflects 0% for that model |
| npm route fails on old Node | Use winget route only |

## Do not

- Put API keys in SKILL.md, IRC, PRs, Task reports, chat, argv, or git.
- Ask Simon to paste a key when box browser + form/handoff can create/store it.
- Use OpenCode for hostile MRB (keep Grok/Cursor first).
- Stamp UAT from OpenCode.

## Related

- `harvest-agent-skills`
- Bob digest webhook fuel / worker activity webhook
- `opencode_fuel.py` (shared cap/fallback logic)

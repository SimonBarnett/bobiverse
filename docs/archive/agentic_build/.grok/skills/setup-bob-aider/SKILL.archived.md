<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path .grok/skills/setup-bob-aider/SKILL.md, last changed 2026-09-24. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
---
name: setup-bob-aider
description: >
  Install or repair Aider (aider-chat) on a Bob Fleet Windows seat, fix
  WinError 5 / PATH after pip, wire free OpenRouter/Groq/Gemini models, bring
  up fuel id aider-free, or when Bob must obtain an API key and start Aider
  without asking Simon to paste secrets. Use when pip install aider-chat fails,
  aider is not recognized, cffi Access is denied, or /setup-bob-aider.
github: https://github.com/SimonBarnett/agentic_build
---

# Setup Bob Aider (Windows seat)

Home: `SimonBarnett/agentic_build` `.grok/skills/setup-bob-aider`. Honesty box:
using this skill obliges a harvest PR/issue back here (see `harvest-agent-skills`).
Fuel id: `aider-free`.

## Why Aider

CLI coding agent for PR/MRB when Cursor Models / Grok seats are thin. Prefer
free backends (OpenRouter free, Groq, Gemini). Same fleet rules as Cursor/Grok:
IRC watch seat, digest webhook activity with **agent** + **model**, clear when idle.

## CAST IRON — do not system-pip into Program Files

MarchHare lesson 2026-09-24:

1. Never `pip install aider-chat` into `C:\Program Files\Python312` while other
   Python processes run.
2. Bare install failed mid-way with `OSError: [WinError 5] Access is denied` on
   `_cffi_backend.cp312-win_amd64.pyd` under Roaming/AppData
   `Python\Python312\site-packages`. Then `aider` was not on PATH
   (`CommandNotFoundException`).
3. Lock holders include `irc_agent.py` (`bob-*` ears) and other long-lived
   Python (e.g. open_tts). Stop them to unlock pip; **restart the ear after**.

## Preferred install (dedicated venv)

```powershell
# 1) Optional: free the lock only if uninstall of cffi fails
Get-CimInstance Win32_Process -Filter "name='python.exe'" |
  Select-Object ProcessId, CommandLine
# Stop only processes holding the locked pyd; then restart bob-<machine> ear.

# 2) Dedicated venv (avoids Program Files + roaming fights)
$venv = Join-Path $env:USERPROFILE 'venvs\aider'
# MarchHare example: D:\Users\Administrator\venvs\aider
python -m venv $venv
& "$venv\Scripts\python.exe" -m pip install --upgrade pip
& "$venv\Scripts\pip.exe" install aider-chat

# 3) User PATH (permanent) + this session
$scripts = "$venv\Scripts"
$env:Path = "$scripts;" + $env:Path
$cur = [Environment]::GetEnvironmentVariable('Path','User')
if ($cur -notlike "*$scripts*") {
  [Environment]::SetEnvironmentVariable('Path', ($scripts + ';' + $cur), 'User')
}

# 4) Verify
& "$scripts\aider.exe" --version
# Expect aider-chat 0.86.x (or newer)
```

Fallback: `pip install --user aider-chat`, then add
`%APPDATA%\Python\Python312\Scripts` to User PATH. Still stop lockers first.

## Known install noise (safe)

- `WARNING: Failed to remove contents in a temporary directory
  '...site-packages\~aml'` (PyYAML) / `~il` (pillow) / `~harset_normalizer` —
  remove leftover dirs when idle.
- Scripts under Roaming `...\Python312\Scripts` "which is not on PATH" — add
  that folder or use the venv Scripts path above.

## CAST IRON — Bob obtains the key (never ask Simon to paste)

Bob must get a free API key and start Aider without Simon pasting secrets into
chat. Prefer **OpenRouter free** (`OPENROUTER_API_KEY`, fuel id `aider-free`).
Groq / Gemini use the same pattern.

### 1) Check seat first

```powershell
$names = 'OPENROUTER_API_KEY','GROQ_API_KEY','GEMINI_API_KEY'
foreach ($n in $names) {
  $u = [Environment]::GetEnvironmentVariable($n,'User')
  if ($u) { Write-Output "ENV User $n present len=$($u.Length)" }  # length only
}
Test-Path "$env:USERPROFILE\.grok\aider.env"
```

If User env or `~\.grok\aider.env` already has a key, skip create — go to start.

### 2) Create key in box browser (no key in chat / reports)

1. Box browser → `https://openrouter.ai/settings/keys` (or `/keys`).
2. Prefer GitHub SSO (Google also works). Sign-in: `request_user_form` for typed
   steps (domain from the bar); captcha / passkey / device approval →
   `request_box_help`. Host fills; Bob never sees values.
3. Create key named `bob-<machine>-aider` (e.g. `bob-marchhare-aider`). Free tier.
4. When the key is revealed once: write **only** the raw key (trimmed, single
   line) to box `/workspace/secrets/openrouter-<machine>.key`, mode `600`.
   Report **path + byte length only** — never the key, never `sk-or-…` in Task
   reports, screenshots captions, or chat.
5. Groq / Google AI Studio only if OpenRouter is blocked; same file pattern.

### 3) Install key on the seat (never Read the secret into agent context)

```powershell
# CopyFromBox /workspace/secrets/openrouter-<machine>.key
#   → seat (allowed local-exec path first, e.g. USERPROFILE\aider.env),
#   then move to $env:USERPROFILE\.grok\aider.env (and D:\Users\...\.\grok if used).
# Do NOT land the file inside a git worktree. Do NOT Read it into agent context.

$envFile = Join-Path $env:USERPROFILE '.grok\aider.env'
# MarchHare also mirrors D:\Users\Administrator\.grok\aider.env when that profile exists
New-Item -ItemType Directory -Force -Path (Split-Path $envFile) | Out-Null
$key = (Get-Content -Raw $envFile).Trim()
if ($key -match '(?m)^OPENROUTER_API_KEY=(.+)$') { $key = $Matches[1].Trim() }
[Environment]::SetEnvironmentVariable('OPENROUTER_API_KEY', $key, 'User')
$env:OPENROUTER_API_KEY = $key
Set-Content -Path $envFile -Value "OPENROUTER_API_KEY=$key" -NoNewline -Encoding ascii
Remove-Variable key
Write-Output "OPENROUTER_API_KEY User env set; aider.env present=$([bool](Test-Path $envFile))"
```

Delete the box secret file after a successful seat install.

### 4) Start / smoke Aider

```powershell
$aider = Join-Path $env:USERPROFILE 'venvs\aider\Scripts\aider.exe'
# MarchHare: D:\Users\Administrator\venvs\aider\Scripts\aider.exe
if (-not $env:OPENROUTER_API_KEY) {
  Get-Content (Join-Path $env:USERPROFILE '.grok\aider.env') | ForEach-Object {
    if ($_ -match '^([^#=]+)=(.*)$') { Set-Item -Path "Env:$($Matches[1])" -Value $Matches[2] }
  }
}
& $aider --version
# Smoke (throwaway dir; --no-git ok for pong):
& $aider --model openrouter/openrouter/free --yes --no-git --message "Reply with pong only"
# If that slug 404s, try a listed :free model from openrouter.ai/models?q=free
```

Verified 2026-09-24 MarchHare: `aider 0.86.2` + `openrouter/openrouter/free` → `pong`.

Report activity to `https://irc.ntsa.uk/bob/v1/report` with **agent=`aider`** and
**model=`openrouter/...`** while working; clear when idle.

## Model / API keys (free-first)

| Backend | Env | Typical model flag |
|---------|-----|--------------------|
| OpenRouter free | `OPENROUTER_API_KEY` | `aider --model openrouter/openrouter/free` or `openrouter/<slug>:free` |
| Groq | `GROQ_API_KEY` | `aider --model groq/...` |
| Gemini | `GEMINI_API_KEY` | `aider --model gemini/...` |
| OpenAI-compatible | `OPENAI_API_KEY` + `OPENAI_API_BASE` | per provider |

Store keys in User env + `~\.grok\aider.env` on the seat, not in git.

## Fleet wire-up (when systray / recruit-fuel lands)

1. Fuel id `aider-free` in digest / TipForm Agents (same IRC watcher + webhook
   rules as Cursor/Grok).
2. On start: report `https://irc.ntsa.uk/bob/v1/report` with **agent=`aider`**
   and **model=`<backend/model>`**.
3. On finish/fail/idle: clear jobs (worker activity webhook).
4. Launch via venv `aider.exe`, not system Python.
5. AgentMonitor / Watch-AgentHealth: free worker seat once start-code exists.

## Troubleshoot (MarchHare transcript)

| Symptom | Fix |
|---------|-----|
| `WinError 5` on `_cffi_backend*.pyd` | Stop python holding the file; prefer venv; rename/delete locked pyd only after stop |
| `aider : The term 'aider' is not recognized` | Install incomplete or Scripts not on PATH; use full venv `Scripts\aider.exe` and fix User PATH |
| Partial Program Files install | Abandon system site-packages; use `$HOME\venvs\aider` |
| Ear killed to unlock pip | Restart `bob-<machine>` before leaving the seat |
| No API key / auth errors from Aider | Run **Bob obtains the key**; confirm User env length > 0 without printing |
| OpenRouter / GitHub login wall | `request_user_form` or `request_box_help`; never paste keys into chat |
| CopyFromBox refused outside local-exec root | Land under allowed path (e.g. `%USERPROFILE%\aider.env`), then move to `~\.grok\aider.env` |

## Do not

- `pip install` into Program Files while bob-* / TTS / other Python is running.
- Put API keys in SKILL.md, IRC, PRs, Task reports, or chat.
- Ask Simon to paste an API key into chat when box browser + form/handoff can create/store it.
- Stamp UAT from Aider.
- Use Copilot CCA as the Aider backend until CCA is live.
- Burn Bob chat tokens implementing PRs — Aider is the worker; Bob starts/assigns.

## Related

- `harvest-agent-skills`
- Bob digest webhook fuel / token-efficient handoff / worker activity webhook
- recruit-fuel / free Agents systray (when merged)

---
name: Bob setup Aider
description: >-
  Use when installing or repairing Aider (aider-chat) on a Bob Fleet Windows
  seat, fixing WinError 5 / PATH after pip install, wiring free
  OpenRouter/Groq/Gemini models, bringing up fuel id aider-free, or when Bob
  must obtain an API key and start Aider without asking Simon to paste secrets.
---
# Setup Bob Aider (Windows seat)

Home skill book: `https://github.com/SimonBarnett/agentic_build` (`.grok/skills/setup-bob-aider`). Using this skill binds the honesty-box harvest back to that repo (see harvest-agent-skills). Fuel id: `aider-free`.

## Why Aider
CLI coding agent for PR/MRB when Cursor Models / Grok seats are thin. Prefer free model backends (OpenRouter free, Groq, Gemini) over paid. Same fleet rules as Cursor/Grok: IRC watch seat, digest webhook activity with **agent** + **model**, clear when idle.

## CAST IRON — harvest MRB + free-agent setup
When standing up Aider (or any free agent), copy/link [Bob MRB worker](sand-workflow:bob-mrb-worker) into the seat instruction pack (`AIDER_IRC_INSTRUCTION.md` or equivalent). MRB is: add new tests for the PR before running tests; PASS → merge to main; FAIL → exactly one fix PR then merge both; Jeeves announces. Harvest gaps back to agentic_build (honesty box).


## CAST IRON — do not system-pip into Program Files

On Windows seats (MarchHare lesson 2026-09-24):

1. **Never** `pip install aider-chat` into `C:\Program Files\Python312` while other Python processes run.
2. A bare install failed mid-way with `OSError: [WinError 5] Access is denied` on `_cffi_backend.cp312-win_amd64.pyd` under `%APPDATA%\Python\Python312\site-packages` (or Roaming under `D:\Users\...`). Then `aider` was not on PATH (`CommandNotFoundException`).
3. Holders that lock `.pyd` files include `irc_agent.py` (`bob-*` ears) and other long-lived Python (e.g. open_tts). Killing them unlocks pip but **must** restart the ear afterward.

## Preferred install (dedicated venv)

```powershell
# 1) Optional: free the lock only if uninstall of cffi fails
Get-CimInstance Win32_Process -Filter "name='python.exe'" |
  Select-Object ProcessId, CommandLine
# Stop only processes holding the locked pyd; then restart bob-<machine> ear.

# 2) Dedicated venv (avoids Program Files + roaming fights)
$venv = "$env:USERPROFILE\venvs\aider"
# On MarchHare: D:\Users\Administrator\venvs\aider
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

Fallback if you insist on user site-packages: `pip install --user aider-chat`, then add `%APPDATA%\Python\Python312\Scripts` to User PATH. Still stop lockers first.

## Known install noise (safe)

During uninstall of older wheels you may see:

- `WARNING: Failed to remove contents in a temporary directory '...site-packages\~aml'` (PyYAML) or `~il` (pillow) or `~harset_normalizer` — remove those leftover dirs manually when idle.
- Scripts installed under Roaming `...\Python312\Scripts` "which is not on PATH" — add that folder or use the venv Scripts path above.

## CAST IRON — Bob obtains the key (never ask Simon to paste)

Bob must be able to get a free API key and start Aider without Simon pasting secrets into chat. Prefer **OpenRouter free** (`OPENROUTER_API_KEY`, fuel id `aider-free`). Groq / Gemini are fallbacks with the same pattern.

### 1) Check seat first

On the target Windows seat (machineId):

```powershell
$names = 'OPENROUTER_API_KEY','GROQ_API_KEY','GEMINI_API_KEY'
foreach ($n in $names) {
  $u = [Environment]::GetEnvironmentVariable($n,'User')
  if ($u) { Write-Output "ENV User $n present len=$($u.Length)" }  # length only
}
Test-Path "$env:USERPROFILE\.grok\aider.env"
```

If User env or `~\.grok\aider.env` already has a key, skip create — go to **Start Aider**.

### 2) Create key in box browser (no key in chat / reports)

1. Dispatch **computerUse** to `https://openrouter.ai/settings/keys` (or `/keys`).
2. Prefer GitHub SSO (Google also works). If sign-in is required: `request_user_form` (auth, domain from the bar) for typed steps — host fills the live page; Bob never sees the values. Captcha / passkey / device approval → `request_box_help`.
3. Create key named `bob-<machine>-aider` (e.g. `bob-marchhare-aider`). Free tier / no credit limit.
4. When the key is revealed once: write **only** the raw key (trimmed, single line) to box path `/workspace/secrets/openrouter-<machine>.key`, mode `600`. Report **file path + byte length only** — never the key, never `sk-or-…` in Task results, screenshots captions, or SendToUser.
5. Prefer Groq (`console.groq.com`) or Google AI Studio only if OpenRouter is blocked; same file pattern (`groq-<machine>.key` / `gemini-<machine>.key`).

### 3) Install key on the seat (never Read the secret file)

```powershell
# Parent: CopyFromBox /workspace/secrets/openrouter-<machine>.key
#   → allowed local-exec path first (e.g. %USERPROFILE%\aider.env),
#   then move to $env:USERPROFILE\.grok\aider.env (mirror D:\Users\...\.grok if used).
# Do NOT land inside a git worktree. Do NOT Read the file into agent context.

$envFile = "$env:USERPROFILE\.grok\aider.env"
New-Item -ItemType Directory -Force -Path (Split-Path $envFile) | Out-Null
$key = (Get-Content -Raw $envFile).Trim()
if ($key -match '(?m)^OPENROUTER_API_KEY=(.+)$') { $key = $Matches[1].Trim() }
[Environment]::SetEnvironmentVariable('OPENROUTER_API_KEY', $key, 'User')
$env:OPENROUTER_API_KEY = $key
Set-Content -Path $envFile -Value "OPENROUTER_API_KEY=$key" -NoNewline -Encoding ascii
Remove-Variable key
Write-Output "OPENROUTER_API_KEY User env set; aider.env present=$([bool](Test-Path $envFile))"
```

Optional: delete the box secret file after a successful seat install.

### 4) Start / smoke Aider

```powershell
$aider = "$env:USERPROFILE\venvs\aider\Scripts\aider.exe"
# MarchHare: D:\Users\Administrator\venvs\aider\Scripts\aider.exe
if (-not $env:OPENROUTER_API_KEY) {
  Get-Content "$env:USERPROFILE\.grok\aider.env" | ForEach-Object {
    if ($_ -match '^([^#=]+)=(.*)$') { Set-Item -Path "Env:$($Matches[1])" -Value $Matches[2] }
  }
}
& $aider --version
& $aider --model openrouter/cohere/north-mini-code:free --yes --no-git --message "Reply with pong only"
# Prefer live :free from openrouter.ai/models?q=free — NOT google/gemini-2.0-flash-exp:free (404)
```

Verified 2026-09-24 MarchHare: OpenRouter chat/completions 200 on `cohere/north-mini-code:free`; Aider default set to `openrouter/cohere/north-mini-code:free`. Do not use `google/gemini-2.0-flash-exp:free` (404).

Report activity to `https://irc.ntsa.uk/bob/v1/report` with **agent=`aider`** and **model=`openrouter/...`** while working; clear when idle.

## Model / API keys (free-first)

| Backend | Env | Typical model flag |
|---------|-----|--------------------|
| OpenRouter free | `OPENROUTER_API_KEY` | `aider --model openrouter/cohere/north-mini-code:free` (coding) or other live `openrouter/<slug>:free` |
| Groq | `GROQ_API_KEY` | `aider --model groq/...` |
| Gemini | `GEMINI_API_KEY` / Google AI | `aider --model gemini/...` |
| OpenAI-compatible | `OPENAI_API_KEY` + `OPENAI_API_BASE` | per provider |

Store keys in User env + `~\.grok\aider.env` on the seat, not in git. Prefer OpenRouter free quota for Bob Fleet `aider-free` fuel.

## Fleet wire-up (when systray/recruit-fuel lands)

1. Fuel id `aider-free` in digest / TipForm Agents (same IRC watcher + webhook rules as Cursor/Grok).
2. On start: report activity to `https://irc.ntsa.uk/bob/v1/report` with **agent=`aider`** and **model=`<backend/model>`**.
3. On finish/fail/idle: clear jobs (see Bob worker activity webhook).
4. Launch via dedicated venv `aider.exe`, not system Python.
5. AgentMonitor / Watch-AgentHealth: treat as a free worker seat once start-code exists; until then operators start from this skill.

## Troubleshoot (MarchHare transcript)

| Symptom | Fix |
|---------|-----|
| `WinError 5` on `_cffi_backend*.pyd` | Stop python holding the file; prefer venv install; rename/delete locked pyd only after stop |
| `aider : The term 'aider' is not recognized` | Install incomplete or Scripts not on PATH; use full path to venv `Scripts\aider.exe` and fix User PATH |
| Partial Program Files install | Abandon system site-packages; use `$HOME\venvs\aider` |
| Ear killed to unlock pip | Restart `bob-<machine>` (`irc_agent.py` / Start-BobEar / Watch-Bobiverse) before leaving the seat |
| No API key / auth errors from Aider | Run **Bob obtains the key**; confirm User env length &gt; 0 without printing; reload shell after SetEnvironmentVariable |
| OpenRouter login wall | `request_user_form` or `request_box_help`; never paste keys into Grok Bot chat |
| CopyFromBox refused outside local-exec root | Land under allowed path (e.g. `%USERPROFILE%\aider.env`), then move to `~\.grok\aider.env` |

## Do not

- `pip install` into Program Files while bob-* / TTS / other Python is running.
- Put API keys in SKILL.md, IRC, PRs, Task reports, or chat.
- Ask Simon to paste an API key into chat when box browser + `request_user_form` can create/store it.
- Stamp UAT from Aider.
- Use Copilot CCA as the Aider backend until CCA is live.
- Burn Bob chat tokens implementing PRs — Aider is the worker; Bob only starts/assigns.

## Related

- harvest-agent-skills (honesty box → agentic_build)
- [Bob MRB worker](sand-workflow:bob-mrb-worker) (standard for all MRB seats)
- Bob digest webhook fuel / Bob token-efficient handoff / Bob worker activity webhook
- recruit-fuel / free Agents systray (when merged)

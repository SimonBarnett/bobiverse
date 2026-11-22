# FR #8718 / BOB-25 evidence

S1: Workers > Cursor harvest goes to SimonBarnett/bobiverse.

- `bob/agents/worker/AGENTS.md` cites `-Repo SimonBarnett/bobiverse` for tray, worker, and Cursor-start lessons. It says not to file them on a-search.
- `bob/.grok/skills/bobiverse-bob-worker/SKILL.md` carries the same sentence.
- The worker launch prompt in `bob/scripts/bob_worker.py` (`_worker_prompt_builtin`) carries the same sentence, so a Cursor seat sees the intake target without opening another repo.

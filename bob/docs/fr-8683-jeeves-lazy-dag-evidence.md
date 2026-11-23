# FR #8683 / BOB-39 evidence

Agents > Jeeves uses a **lazy** skill DAG on `J:\.grok\skills` (J: mapped to Ergo `ai\jeeves`).

- Dry-run / tray log: `jeeves-dag lazy root=J:\.grok\skills` before Grok start (CS + PS).
- Smoke: `python bob/scripts/jeeves_lazy_dag.py --skills-root <path>` indexes frontmatter via `skill_dag_index.scan_skills` and checks `depends_on` cycles. It does **not** eagerly concatenate SKILL.md bodies.
- Fail-when avoided: eager full load only / no DAG.

`python -m pytest -q bob/tests/test_fr8683_jeeves_lazy_dag.py`

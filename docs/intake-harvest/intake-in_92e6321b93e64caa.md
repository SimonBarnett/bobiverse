Lesson (FR #7908): skill_dag_mcp get_skill closed stdio (MCP -32000 Connection closed) because it wrote a SKILL.md body with ensure_ascii=False to the locale cp1252 stdout pipe; bobiverse-bob-job-fr/SKILL.md contains U+2265 and U+2194, so outf.write raised UnicodeEncodeError outside the per-call guard and the process exited. Fix: reconfigure stdio to UTF-8, fall back to ensure_ascii, wrap the write, and report the exception via crash_report.report_exception. Playbook: an MCP stdio server must never assume UTF-8 pipes on Windows; configure sys.std* and keep the reply write inside the exception guard.
---
_via-intake id=`in_92e6321b93e64caa` ts=`2026-11-16T12:28:46Z`_
_source machine=`redqueen` agent=`Report-BobiverseIntakeIssue` book=`harvest` ver=`-`_

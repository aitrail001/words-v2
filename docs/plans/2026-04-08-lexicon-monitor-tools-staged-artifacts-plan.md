# Lexicon Monitor Tools Staged Artifacts Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Update the lexicon monitor/operator scripts so snapshot directories created by `enrich`, `enrich-core`, and `enrich-translations` are all inspectable without manual file-path juggling.

**Architecture:** Keep the current shell/python script surface, but make directory resolution auto-detect the staged `core` and `translations` ledgers alongside the legacy unified ledgers. Add a one-pass monitor mode so the shell script can be verified under pytest.

**Tech Stack:** zsh operator scripts in `tools/lexicon/scripts`, Python helper scripts, pytest.

---

### Task 1: Add failing script behavior tests

**Files:**
- Create: `tools/lexicon/tests/test_scripts.py`

- [ ] **Step 1: Write failing tests for staged failure/discard auto-resolution and one-pass monitor output**

```python
class ScriptTests(unittest.TestCase):
    def test_show_failures_reads_staged_ledgers_from_snapshot_dir(self) -> None:
        ...
```

- [ ] **Step 2: Run the focused test file and confirm it fails for the missing staged-monitor behavior**

Run: `.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_scripts.py -q`
Expected: FAIL because the scripts still only target legacy `enrich.*` filenames or lack `--once`.

### Task 2: Patch the monitor/operator scripts

**Files:**
- Modify: `tools/lexicon/scripts/monitor-enrich.zsh`
- Modify: `tools/lexicon/scripts/show-failures.py`
- Modify: `tools/lexicon/scripts/show-discarded.py`

- [ ] **Step 1: Add `--once` and staged file sections to `monitor-enrich.zsh`**

```zsh
case "$1" in
  --once)
    ONCE=1
    shift
    ;;
esac
```

- [ ] **Step 2: Add staged/legacy snapshot-dir auto-resolution to the Python helper scripts**

```python
def _resolve_failure_paths(path_arg: str) -> list[tuple[str, Path]]:
    ...
```

- [ ] **Step 3: Keep direct file-path inputs working exactly as before**

Run: same focused pytest file
Expected: PASS

### Task 3: Update concise operator docs/status evidence

**Files:**
- Modify: `docs/status/project-status.md`

- [ ] **Step 1: Add a short status-log entry documenting that operator monitor scripts now understand staged enrichment ledgers**

```markdown
| 2026-04-08 | No project-state change. Updated lexicon monitor scripts to auto-detect staged enrichment ledgers and added focused script regression tests. | Codex | `...pytest tools/lexicon/tests/test_scripts.py -q` |
```

- [ ] **Step 2: Run the relevant combined verification**

Run: `.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_scripts.py tools/lexicon/tests/test_cli.py tools/lexicon/tests/test_enrich.py -q`
Expected: PASS

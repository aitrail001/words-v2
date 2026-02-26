# Lesson: Skill Discipline in Phase 0

**Date**: 2026-02-26
**Phase**: Phase 0 (Foundation)

## What Happened

During Phase 0 scaffolding, no skills were invoked before writing code. The rationale was "this is just boilerplate, skills are overkill." Code was written implementation-first (not TDD), and code review was only run after the user pointed out the omission.

The Python code review came back with a BLOCK verdict: 2 CRITICAL issues (hardcoded credentials with no production guard, CORS misconfiguration) and 6 HIGH issues (info disclosure in health check, Redis lifecycle, auto-commit on reads, no test isolation, etc.).

## Why It Failed

Rationalizing: "Phase 0 is just scaffolding, TDD doesn't apply, skills are overkill for boilerplate." This is exactly the anti-pattern the using-superpowers skill warns about. Every one of the CRITICAL/HIGH issues would have been caught by invoking `security-review` or `python-patterns` before writing the code.

The cost of invoking a skill that turns out to be unnecessary is ~5 seconds. The cost of not invoking one that was needed is a full rewrite after code review.

## What To Do

1. Invoke skills BEFORE writing code, every time, no exceptions
2. The CLAUDE.md "Development Process (MANDATORY)" section now enforces this
3. For this project specifically, the minimum skill set per task type is documented in CLAUDE.md
4. "Simple" and "boilerplate" are not valid reasons to skip skills — those are where unexamined assumptions cause the most damage

## Files Affected

- `backend/app/core/config.py` — hardcoded credentials (CRITICAL)
- `backend/app/main.py` — CORS misconfiguration (CRITICAL)
- `backend/app/api/health.py` — info disclosure (HIGH)
- `backend/app/core/redis.py` — lifecycle management (HIGH)
- `backend/app/core/database.py` — auto-commit pattern (HIGH)
- `backend/tests/conftest.py` — no test isolation (HIGH)

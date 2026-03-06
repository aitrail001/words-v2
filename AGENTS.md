# Agent Operating Contract (Repository Scope)

This file defines how coding agents should operate in this repository.

## Purpose and Ownership

1. `AGENTS.md` is the operational source of truth for agent behavior.
2. `CLAUDE.md` remains product/domain context source of truth.
3. If rules conflict:
   - system/developer instructions override repository files
   - `AGENTS.md` overrides process sections duplicated elsewhere in repo docs

## Session Kickoff Checklist (Reusable)

Use this checklist at the start of every new task/session.

1. Confirm runtime context (repo path, branch, target slice).
2. Perform skill applicability check and invoke all relevant skills before implementation.
3. Use a git worktree for non-trivial work.
4. Require verification evidence before any completion claim.
5. Update `docs/status/project-status.md` when feature/gate/release state changes.

Shortcut prompt users can paste:

`Follow AGENTS kickoff checklist: skill-check first, use relevant skills, worktree for non-trivial changes, verify before done, and update docs/status/project-status.md with evidence.`

## Canonical Project Status

1. Live status source of truth: `docs/status/project-status.md`.
2. Do not treat plan files as live status.
3. Any meaningful feature/gate/release state change must update `docs/status/project-status.md`.

## Mandatory Workflow (Every Implementation Task)

1. Determine applicable skills before acting.
2. For behavior/feature changes, perform brief design alignment first.
3. For multi-step work, produce/update a written plan in `docs/plans/`.
4. Use an isolated git worktree by default for non-trivial slices.
5. Write/adjust tests first where practical; run verification before claiming success.
6. Update docs/status as part of the same change set.

Hard gate:

- No implementation starts until a skill check is completed and relevant skills are invoked.

## Skill Invocation Policy

Use the smallest required set, but do not skip relevant skills.

1. Process:
   - `using-superpowers` at task start
   - `brainstorming` before behavior-changing implementation
   - `writing-plans` for multi-step tasks
   - `using-git-worktrees` for non-trivial feature slices
2. Build/debug quality:
   - `test-driven-development` or `tdd-workflow` for features/bugfixes
   - `systematic-debugging` for failures/flakes
   - `verification-before-completion` before any "done/fixed/passing" claim
3. Domain:
   - `backend-patterns` for backend architecture/API/data changes
   - `frontend-patterns` for frontend behavior/state/UI changes
   - `api-design` for endpoint contract changes
   - `security-review` for auth, secrets, input-handling, permissions
   - `e2e-testing` for user-flow and CI gate changes
4. Collaboration:
   - `dispatching-parallel-agents` and `subagent-driven-development` for parallelizable work
   - `requesting-code-review` before merge on substantial changes
   - `receiving-code-review` when applying review feedback
   - `finishing-a-development-branch` when implementation is complete

## Branching, Worktrees, and Commits

1. Use feature branches and worktrees for isolated tasks.
2. Keep commits focused and reversible.
3. Do not include unrelated local changes in commits.
4. Never use destructive git operations unless explicitly requested.

## Verification Standard

Before claiming completion:

1. Run relevant backend/frontend/tests/e2e checks for the changed scope.
2. Confirm results from fresh command output.
3. Report what was verified and what was not run.

## CI/Release Governance

1. PR required checks are mandatory merge gates.
2. Release promotion must follow `docs/runbooks/release-promotion.md`.
3. Rollback procedure is `docs/runbooks/rollback.md`.
4. Pre-prod readiness gate is `docs/runbooks/preprod-readiness-checklist.md`.

## Documentation Update Rules

When changing behavior or governance:

1. Update relevant plan/runbook/docs.
2. Update `docs/status/project-status.md`.
3. If a significant technical decision is made, add/update an ADR in `docs/decisions/`.

## Practical Defaults

1. Prefer clarity over novelty.
2. Keep implementation scope tight to requested outcome.
3. Surface risks early; do not hide uncertainty.
4. Minimize "policy drift" by linking to canonical docs rather than duplicating long guidance.

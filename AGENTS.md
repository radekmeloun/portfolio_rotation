# AGENTS.md

This file defines project-specific instructions for coding agents working in this repository.

## Scope

- Applies to the entire repository from this directory downward.
- When changing tests or behavior covered by tests, follow `TESTING_GUIDELINES.md`.

## Agent Roles

Use these roles distinctly when an orchestrator coordinates work:

1. Coding agent
- implements code changes
- updates the owning tests when behavior changes

2. Documentation agent
- checks whether code, config, setup, workflow, or script changes require documentation updates
- updates the relevant documentation files before commit
- follows `DOCUMENTATION_AGENT_WORKFLOW.md`

3. Testing agent
- validates the change with targeted tests, full suite, smoke checks, and test report refresh
- follows `TESTING_GUIDELINES.md`

4. Security agent
- runs a lightweight pre-commit sanity check before local commit
- runs the full security review before any push to GitHub
- follows `SECURITY_AGENT_WORKFLOW.md`

5. GitHub workflow agent
- manages branch creation, local commits, push, and pull request creation
- follows `GITHUB_AGENT_WORKFLOW.md`

## Required Workflow

For changes that are intended to be committed or pushed, the orchestrator should use this order:

1. GitHub workflow agent
- create or select the working branch
- never work directly on `main`

2. Coding agent
- make code changes
- update/add tests in the owning test module

3. Documentation agent
- review whether documentation is affected
- update docs if behavior, setup, commands, workflows, or structure changed

4. Testing agent
- run targeted tests for touched modules
- run full test suite
- run smoke checks
- refresh test reports

5. Security agent, lightweight pre-commit gate
- run the fast sanity check on staged or changed files
- block commit if secrets, tracked runtime artifacts, or obvious dangerous patterns are found

6. GitHub workflow agent
- create the local commit only if steps 4 and 5 passed

7. Security agent, full pre-push gate
- run the full repository security review before any push
- block push if the review fails or is incomplete

8. GitHub workflow agent
- push only when the user explicitly says to push
- create PR only when the user explicitly says to create a PR

If the task is local-only and no commit is requested, stop after the testing and security checks relevant to the change.

## Commands (Required After Changes)

```bash
venv/bin/python -m pytest -q tests/test_<module>.py
venv/bin/python -m pytest -q
venv/bin/python -c "import app"
./scripts/test_report.sh
```

If `venv` is missing:

```bash
./scripts/bootstrap.sh
```

## Commit And Push Dependency Rules

- No local commit until:
  - code changes are complete
  - documentation review is complete
  - owning tests are updated when needed
  - targeted tests pass
  - full suite passes
  - smoke check passes
  - lightweight pre-commit security check passes

- No push until:
  - local commit exists
  - full pre-push security review passes
  - user explicitly approves push

- No PR until:
  - branch is already pushed
  - user explicitly approves PR creation

- No merge until:
  - human review is complete
  - user explicitly requests merge

## Test Design Rules

- Prefer parameterized tests over many near-duplicate single-case tests.
- Avoid overlap: test each behavior once in its owning module unless it is a cross-module contract.
- Keep tests deterministic (fixed seeds, no network).
- Do not write tests that only re-derive formulas without calling production code.
- For critical flows (especially backtest), keep parity/regression coverage.

## Backtest Guardrail

- Refactors must not change backtest behavior unless explicitly requested.
- For backtest-related changes, ensure parity/regression tests pass before finalizing.

## Reference

- Detailed policy and examples: `TESTING_GUIDELINES.md`
- Git/GitHub workflow for branch, commit, push, and PR handling: `GITHUB_AGENT_WORKFLOW.md`
- Security pre-commit review workflow: `SECURITY_AGENT_WORKFLOW.md`
- Documentation update workflow: `DOCUMENTATION_AGENT_WORKFLOW.md`
- Developer setup and agent usage guide: `DEVELOPMENT_GUIDE.md`

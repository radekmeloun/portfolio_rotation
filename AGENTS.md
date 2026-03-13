# AGENTS.md

This file defines project-specific instructions for coding agents working in this repository.

## Scope

- Applies to the entire repository from this directory downward.
- When changing tests or behavior covered by tests, follow `TESTING_GUIDELINES.md`.

## Required Workflow

1. Make code changes.
2. Update/add tests in the owning test module (see `TESTING_GUIDELINES.md`).
3. Run targeted tests for touched modules.
4. Run full test suite.
5. Run smoke checks.

## Commands (Required After Changes)

```bash
.venv/bin/python -m pytest -q tests/test_<module>.py
.venv/bin/python -m pytest -q
bash scripts/test_and_smoke.sh
./scripts/test_report.sh
```

If `.venv` is missing:

```bash
./scripts/bootstrap.sh
```

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

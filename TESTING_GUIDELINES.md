# Testing Guidelines

This document defines how tests should be structured and maintained for future code changes in this project.

## Goals

- Keep tests fast, deterministic, and readable.
- Cover behavior once in the right layer (avoid duplicate assertions across modules).
- Make refactors safe without locking implementation details.

## Test Layers

Use these layers consistently:

1. Unit tests
- Scope: pure functions and local logic (formatting, ranking, metrics formulas, date helpers).
- Inputs: synthetic in-memory data only.
- No network and no real filesystem writes outside `tmp_path`.

2. Contract tests
- Scope: boundaries between modules (for example, fetch fallback + cache shape).
- Use mocks/stubs for external providers (`stooq`, `yahoo`).
- Assert data/status contracts, not private implementation internals.

3. Integration tests
- Scope: one end-to-end slice inside the app domain (for example, signal generation + backtest run).
- Keep fixture size small but realistic.

4. Parity regression tests (when relevant)
- Scope: critical pipelines (especially backtest).
- Use fixed seed / fixed synthetic dataset.
- Assert stable outputs on key checkpoints to prevent behavior drift.

## Ownership Matrix (Avoid Overlap)

Each behavior should have one primary test owner:

- `src/calc.py`: formulas, ranking, allocation.
- `src/presentation.py`: sorting and display formatting.
- `src/fetch.py`: symbol normalization, fallback order, cache keying/invalidation.
- `src/history.py`: universe/profile parsing, coverage window, price matrix alignment.
- `src/backtest.py`: signal dates, execution dates, execution gate, costs, equity evolution.
- `src/perf.py`: portfolio metrics formulas.

Do not re-test the same behavior in multiple files unless:
- It is a cross-module contract, or
- It is a critical invariant (for example, total allocation sum or backtest parity).

## Structure Rules

- Prefer `pytest.mark.parametrize` for multi-case behavior.
- Keep one assertion theme per test function.
- Name tests by behavior, not implementation detail.
- Reuse fixtures from `tests/conftest.py` (seeded and deterministic).
- Keep random data deterministic (fixed RNG seed).
- Keep tests independent (no ordering assumptions).

## Anti-Patterns to Avoid

- Repeating the same edge case in multiple modules.
- Tests that only recompute formulas locally without calling production code.
- Over-mocking internal helpers when public function behavior can be asserted directly.
- Snapshotting large full DataFrames when 3-8 key values are enough.
- Network-dependent tests in CI.

## Refactoring Tests Safely

When changing code:

1. Identify behavior changes vs implementation-only changes.
2. Update tests in the owning module first.
3. Remove/merge duplicate tests if they validate the same branch.
4. Add one integration/parity guard if change touches critical flow (for example, backtest execution).
5. Keep old public behavior unchanged unless explicitly requested.

## Backtest Safety Contract

When refactoring around backtest:

- Do not change formulas, trading calendar logic, or cost mechanics unless requested.
- Keep one parity test with fixed dataset that checks:
  - final portfolio value,
  - number of rebalances,
  - total costs,
  - selected tickers on key signal dates.
- Block merge if parity fails without approved behavior change.

## Minimal Test Set per Change

After each code change, run:

1. Targeted tests for touched module(s)
```bash
.venv/bin/python -m pytest -q tests/test_<module>.py
```

2. Full suite
```bash
.venv/bin/python -m pytest -q
```

3. Smoke check
```bash
bash scripts/test_and_smoke.sh
```

4. Persist latest report files
```bash
./scripts/test_report.sh
```

If `.venv` does not exist:
```bash
./scripts/bootstrap.sh
```

## PR Checklist for Agents

- [ ] Tests added/updated in the owning test module.
- [ ] No obvious overlap introduced (or overlap justified in PR notes).
- [ ] Deterministic fixtures only.
- [ ] Targeted tests pass.
- [ ] Full suite passes.
- [ ] Smoke check passes.
- [ ] Latest report files updated in `reports/tests/` when required by workflow.
- [ ] For backtest-related changes: parity guard updated/passing.

## Suggested Test Count Discipline

Test count is not a goal by itself. Aim for:

- Fewer, higher-signal tests.
- Parameterized coverage over copy-pasted single-case tests.
- Clear mapping between production behavior and test intent.

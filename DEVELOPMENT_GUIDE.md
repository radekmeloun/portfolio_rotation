# Development Guide

This document explains how developers and specialized agents should work in the `portfolio_rotation` repository.

## Purpose

Use this guide as the developer-facing entrypoint for:

- environment setup
- local tooling
- agent workflows
- Git/GitHub workflow expectations
- test and security preconditions

## Repository Preconditions

Before starting development, make sure:

1. The repository is cloned locally and is a valid Git worktree.
2. `origin` points to the correct GitHub repository.
3. Local Git identity is configured:
```bash
git config user.name
git config user.email
```
4. The Python virtual environment exists at `venv/`.
5. GitHub authentication is working for push operations.

## Python Environment Setup

Preferred setup:

```bash
./scripts/bootstrap.sh
```

Manual setup:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Development Tooling

Security and development tools are installed from:

```bash
venv/bin/python -m pip install -r requirements-dev.txt
```

Current security tooling expected by the repository:

- `bandit`
- `pip-audit`
- `detect-secrets`

Optional GitHub tooling:

- `gh` for PR creation

## Manual External Preconditions

Some parts of the workflow require manual setup outside the repository:

1. GitHub repository must exist and be configured as `origin`.
2. GitHub SSH key or HTTPS credentials must be configured for push access.
3. If PR creation should be automated, `gh` must be installed and authenticated.
4. Network access to PyPI is needed when installing or updating development tools.

## Standard Development Flow

The normal workflow for code changes is:

1. create or switch to a non-`main` branch
2. implement the change
3. update tests as needed
4. update documentation as needed
5. run targeted tests
6. run full suite
7. run smoke check
8. run security checks
9. commit locally
10. push only when explicitly approved
11. create PR only when explicitly approved

## Agent Usage

The repository supports multiple specialized agents.

### Coding Agent

Use for:

- code changes
- config changes
- implementation refactors
- test updates tied to code changes

### Documentation Agent

Use for:

- checking whether docs need updates after code/config/workflow changes
- updating developer and workflow docs

Workflow reference:

- `DOCUMENTATION_AGENT_WORKFLOW.md`

### Testing Agent

Use for:

- targeted test validation
- full-suite validation
- smoke checks
- test report refresh

Workflow reference:

- `TESTING_GUIDELINES.md`

### Security Agent

Use for:

- lightweight pre-commit sanity checks
- full pre-push security review

Workflow reference:

- `SECURITY_AGENT_WORKFLOW.md`

### GitHub Workflow Agent

Use for:

- branch creation
- local commit management
- push on explicit instruction
- PR creation on explicit instruction

Workflow reference:

- `GITHUB_AGENT_WORKFLOW.md`

## Recommended Orchestration Order

If an orchestrator coordinates multiple agents, use this order:

1. GitHub workflow agent
2. Coding agent
3. Documentation agent
4. Testing agent
5. Security agent, lightweight pre-commit gate
6. GitHub workflow agent for local commit
7. Security agent, full pre-push gate
8. GitHub workflow agent for push
9. GitHub workflow agent for PR creation

## Commands Used In This Repository

Targeted tests:

```bash
venv/bin/python -m pytest -q tests/test_<module>.py
```

Full test suite:

```bash
venv/bin/python -m pytest -q
```

Smoke check:

```bash
venv/bin/python -c "import app"
```

Refresh test report:

```bash
./scripts/test_report.sh
```

## Important Repository Notes

- `venv/`, caches, test reports, and runtime-generated files must not be committed.
- Backtest behavior must not be changed unintentionally.
- Documentation should be updated whenever user-facing behavior, setup, or workflows change.
- Pushes and PR creation should remain explicit user decisions.

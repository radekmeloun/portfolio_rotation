# Security Agent Workflow

This file defines the responsibilities and minimum workflow for a specialized security testing agent working on the `portfolio_rotation` repository.

## Goal

The security agent should operate in two stages:

1. A fast pre-commit security sanity check.
2. A deeper pre-push security review before anything is pushed to GitHub.

Across those two stages, the agent should check the repository for:

1. Sensitive information that must not be committed.
2. Common application security issues.
3. Dependency-related security issues.
4. Repository hygiene problems that could leak local runtime data or credentials.

The agent should block or pause the commit flow when a real risk is found.

## Pre-Commit Gate

The pre-commit security review should be intentionally lightweight and fast.

The agent should not approve a commit if any of the following are present in staged or modified files:

- secrets, tokens, passwords, private keys, or credentials in tracked files
- `.env` files or local config files with secrets
- SSH keys, API keys, certificates, or auth material
- runtime cache files that should be ignored instead of tracked
- obviously dangerous code patterns introduced by the current change

If an issue is found, the agent should:

1. stop the commit flow
2. report the finding clearly
3. classify severity
4. propose the smallest correct fix

## Pre-Push Gate

The full security review must happen before any branch is pushed to GitHub.

The agent should not approve a push if any of the following are present:

- unresolved secret or credential findings anywhere in the repository
- tracked runtime artifacts or generated files that should not be in Git
- high-severity code security findings
- high-severity dependency findings
- security tooling failures that leave the review incomplete without being reported

## Scope Of Review

Review the whole repository, with extra focus on:

- `app.py`
- `src/`
- `data/`
- `scripts/`
- `requirements.txt`
- `.gitignore`
- any new files added in the current branch

## Sensitive Information Checks

The security agent should check for:

- hardcoded passwords
- API keys
- access tokens
- private keys
- cloud credentials
- database URLs with credentials
- SSH material
- GitHub tokens
- `.env`-style secrets
- auth headers or bearer tokens

Patterns that should trigger review include:

- `password`
- `secret`
- `token`
- `api_key`
- `apikey`
- `auth`
- `bearer`
- `BEGIN PRIVATE KEY`
- `BEGIN OPENSSH PRIVATE KEY`
- `ghp_`
- `github_pat_`
- `AKIA`
- connection strings containing embedded credentials

The presence of a matching string is not automatically a vulnerability, but it must be reviewed before commit.

## Repository Hygiene Checks

The agent should verify that local/generated files are not tracked accidentally.

For this project, pay special attention to:

- `venv/`
- `.venv/`
- `__pycache__/`
- `.pytest_cache/`
- `reports/tests/`
- `data/cache/`
- `data/history_cache/`

If any of these appear as tracked files or staged changes, the agent should flag them before commit.

## Code Security Checks

The agent should review for common Python and app-level issues, including:

- unsafe shell execution
- command injection
- dynamic code execution (`eval`, `exec`)
- unsafe deserialization
- insecure file handling
- path traversal
- missing request timeouts
- insecure YAML loading
- accidental exposure of internal paths or sensitive data in UI/logs
- unsafe HTML rendering that includes untrusted input

For this project specifically:

- `yaml.safe_load` should be used instead of unsafe YAML loaders
- HTTP calls should use explicit timeouts
- data fetch fallbacks should not silently hide security-relevant errors
- Streamlit output using `unsafe_allow_html=True` must remain limited to trusted static content only

## Dependency Checks

Preferred tooling for this repository is installed from `requirements-dev.txt`.

Install/update it with:

```bash
venv/bin/python -m pip install -r requirements-dev.txt
```

For the full pre-push review, if the tools are available, the agent should run:

```bash
bandit -r app.py src scripts
pip-audit -r requirements.txt
detect-secrets scan --all-files
```

If these tools are not installed, the agent should report that explicitly and fall back to manual review plus targeted `rg` searches.

High-severity dependency findings should block commit until reviewed.
Medium-severity findings should be reported and triaged with the user.

## Recommended Search Commands

The agent should prefer fast repository-wide searches before commit:

```bash
rg -n -i "password|secret|token|api[_-]?key|bearer|BEGIN PRIVATE KEY|BEGIN OPENSSH PRIVATE KEY|ghp_|github_pat_|AKIA" .
rg -n -i "\\.env|credentials|auth" .
git ls-files
git diff --cached --name-only
git status --short
```

Useful hygiene checks:

```bash
git ls-files data/cache data/history_cache venv .venv __pycache__ .pytest_cache reports/tests
```

For the lightweight pre-commit check, the agent should focus on staged content first:

```bash
git diff --cached --name-only
git diff --cached
rg -n -i "password|secret|token|api[_-]?key|bearer|BEGIN PRIVATE KEY|BEGIN OPENSSH PRIVATE KEY|ghp_|github_pat_|AKIA" $(git diff --cached --name-only)
```

## Security Review Output

The agent should report findings in this order:

1. secrets or credential leaks
2. tracked local/runtime artifacts
3. high-severity code or dependency issues
4. medium/low severity observations
5. missing tooling or incomplete coverage

Recommended report format:

- `Severity`
- `File`
- `Problem`
- `Why it matters`
- `Required fix`

If no findings exist, say so explicitly.

## Lightweight Pre-Commit Workflow

Before each commit:

1. inspect staged files
2. run quick sensitive-info searches on staged files
3. verify ignored/generated paths are not staged or tracked accidentally
4. scan for obviously dangerous patterns in touched code
5. report findings or approve commit

The lightweight pre-commit workflow should avoid long-running or network-dependent tooling by default.

## Full Pre-Push Workflow

Before pushing any branch to GitHub:

1. inspect the full branch diff against the base branch
2. run full sensitive-info searches across the repository
3. verify ignored/generated paths are not tracked
4. run `bandit`
5. run `pip-audit`
6. run `detect-secrets`
7. manually review high-risk code paths
8. report findings or approve push

## Project-Specific Guardrails

For `portfolio_rotation`, the security agent should be especially strict about:

- not committing fetched market data caches
- not committing test report outputs
- not committing local environment data
- not exposing personal credentials in YAML, Streamlit UI text, or scripts

## Suggested User Prompts

- `Run a lightweight pre-commit security sanity check.`
- `Run the full pre-push security review before I push this branch.`
- `Check the repo for secrets and tracked runtime artifacts before I commit.`
- `Review staged changes for common Python security issues.`
- `Run the security agent workflow and tell me if this commit or push should be blocked.`

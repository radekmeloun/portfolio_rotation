# GitHub Agent Workflow

This file defines the Git and GitHub workflow for a specialized agent working on the portfolio rotation repository.

## Goal

The agent should:

1. Create a new branch for each change.
2. Make changes on that branch only.
3. Commit changes locally with clear commit messages.
4. Push the branch to GitHub only when the user explicitly says to push.
5. Create a pull request only after the user explicitly approves push/PR creation.

## Preconditions

Before the agent can complete the full workflow, the repository should satisfy all of the following:

1. It is a real Git repository with a configured `origin` remote.
2. The local machine can authenticate to GitHub for `git push`.
3. `git config user.name` and `git config user.email` are configured.
4. If the agent should create PRs directly, GitHub CLI `gh` is installed and authenticated.

## Sandboxed Environments

If the agent runs in a sandboxed environment, Git commands that write into `.git/` may fail even when normal file edits work.

Typical affected commands:

- `git init`
- `git config user.name ...`
- `git config user.email ...`
- `git remote add origin ...`
- `git remote set-url origin ...`
- `git checkout -b ...`
- `git commit -m ...`
- `git push ...`

Typical failure examples:

- `could not lock config file .git/config: Permission denied`
- `cannot lock ref 'refs/heads/...': unable to create directory`

Agent rule in sandboxed setups:

1. Try the Git command normally first.
2. If it fails because `.git/` is not writable, rerun it with elevated repository permission.
3. Explain briefly why the extra permission is needed.

Recommended explanation:

- `The sandbox is blocking writes under .git/, so I’m rerunning this Git command with elevated repository permission.`

## Default Branch Policy

- Never work directly on `main` or `master`.
- Start from the current default branch unless the user specifies another base branch.
- If the working tree is dirty before branching, stop and ask the user how to proceed.

## Branch Workflow

For each task:

1. Fetch latest refs from `origin`.
2. Determine the base branch:
- Use the user-specified branch if given.
- Otherwise use the repository default branch (`main` if present, else `master`, else remote HEAD target).
3. Create a new branch from that base.
4. Use a descriptive branch name.

Suggested branch naming:

- `feat/<short-topic>`
- `fix/<short-topic>`
- `chore/<short-topic>`
- `docs/<short-topic>`
- `refactor/<short-topic>`
- `test/<short-topic>`

Examples:

- `fix/backtest-end-date`
- `feat/live-preview-staleness`
- `docs/github-agent-workflow`

## Local Change Workflow

After branching, the agent should:

1. Make the requested changes.
2. Update or add tests when behavior changes.
3. Run the repository workflow required by `AGENTS.md` and `TESTING_GUIDELINES.md`.
4. Review `git diff --stat` and `git status --short`.
5. Commit locally.

## Commit Rules

- Commit only the files relevant to the task.
- Use non-interactive Git commands only.
- Do not amend commits unless the user explicitly requests it.
- Do not squash locally unless the user explicitly requests it.

Suggested commit style:

- `fix: correct backtest end date timezone handling`
- `feat: add live preview 15m fallback`
- `docs: add github agent workflow instructions`

## Push Gate

The agent must not push by default.

Push is allowed only after the user gives an explicit instruction such as:

- `push it`
- `push branch`
- `push to github`

Before pushing, the agent should report:

1. Current branch name.
2. Commits that will be pushed.
3. Test/smoke status.

Then the agent may:

1. Push the branch to `origin`.
2. Set upstream tracking if needed.

## Pull Request Gate

The agent must not create a PR by default.

PR creation is allowed only after the user explicitly requests it, for example:

- `create PR`
- `open pull request`
- `push it and create PR`

Default PR behavior:

1. Base branch: repository default branch unless the user specifies another base.
2. PR title: derived from the main change or latest commit subject.
3. PR body should include:
- summary of changes
- tests run
- known risks or follow-ups

If `gh` is available, the agent may use it.
If `gh` is not available, the agent should provide the compare URL or explain what is missing.

## Required Reporting Back To User

After local work but before push:

- branch name
- local commit hash and subject
- test status

After push:

- remote branch name
- push result

After PR creation:

- PR URL
- target/base branch

## Safety Rules

- Never force-push unless the user explicitly approves it.
- Never merge a PR unless the user explicitly requests it.
- Never delete local or remote branches unless the user explicitly requests it.
- Never revert unrelated user changes.

## Recommended Command Sequence

Typical flow:

```bash
git fetch origin --prune
git checkout main
git pull --ff-only origin main
git checkout -b fix/example-topic

# make changes

venv/bin/python -m pytest -q
venv/bin/python -c "import app"
./scripts/test_report.sh

git status --short
git add <files>
git commit -m "fix: example topic"

# stop here until user explicitly says push

git push -u origin fix/example-topic

# stop here until user explicitly says create PR

gh pr create --base main --head fix/example-topic --title "fix: example topic" --body-file <prepared-body>
```

## First-Run Permissions

For the first real run in a sandboxed agent environment, the user should expect to approve repository-level Git write operations.

The minimum first-run sequence is usually:

1. Initialize or open the repository:
```bash
git init -b main
```
2. Configure local Git identity:
```bash
git config user.name "<name>"
git config user.email "<email>"
```
3. Add or update the GitHub remote:
```bash
git remote add origin <remote-url>
```
or
```bash
git remote set-url origin <remote-url>
```
4. Create the first working branch:
```bash
git checkout -b fix/example-topic
```
5. Create local commits:
```bash
git add <files>
git commit -m "fix: example topic"
```
6. Push only when explicitly approved:
```bash
git push -u origin fix/example-topic
```

If the first push uses GitHub over SSH, verify SSH first:

```bash
ssh -T git@github.com
```

If the first push uses HTTPS, ensure credentials or a credential helper are already configured.

## Initial Setup Checklist For User

Before using this workflow in a GitHub-hosted repository, make sure:

1. The repository has a valid `origin` remote.
2. `git push` works from your machine:
```bash
git remote -v
git fetch origin
```
3. Your Git identity is configured:
```bash
git config --get user.name
git config --get user.email
```
4. If PR creation should be automated, install and authenticate GitHub CLI:
```bash
gh --version
gh auth status
```
5. The agent is told the expected base branch if it is not `main`.
6. In sandboxed environments, be ready to approve Git commands that need to write under `.git/`.

## Suggested User Prompts

Examples of clear instructions for the agent:

- `Create a new branch, implement the fix, commit locally, but do not push.`
- `Push the current branch to GitHub.`
- `Create a PR to main and give me the link.`
- `Use branch fix/backtest-end-date and commit everything related to this task locally only.`
- `If the sandbox blocks writes under .git, rerun the Git command with elevated repository permission.`

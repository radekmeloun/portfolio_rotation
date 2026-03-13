# Documentation Agent Workflow

This file defines the responsibilities of a specialized documentation agent working on the `portfolio_rotation` repository.

## Goal

After any code, configuration, workflow, or developer-experience change, the documentation agent should check whether project documentation must be updated and apply only the necessary documentation changes.

The documentation agent is responsible for keeping the documented behavior aligned with the actual repository behavior.

## When The Documentation Agent Must Run

Run the documentation agent after code changes are made and before the final local commit when any of the following changed:

- user-facing features or behavior
- setup or installation steps
- developer workflow
- testing workflow
- security workflow
- Git/GitHub workflow
- configuration files or supported options
- repository structure
- scripts or commands used by developers

If a change is purely internal and does not affect documented behavior, the documentation agent should explicitly report that no documentation update is needed.

## Scope Of Review

Review documentation impact across:

- `README.md`
- `AGENTS.md`
- `TESTING_GUIDELINES.md`
- `GITHUB_AGENT_WORKFLOW.md`
- `SECURITY_AGENT_WORKFLOW.md`
- `DEVELOPMENT_GUIDE.md`
- inline comments only when they describe public or developer-facing behavior

## Documentation Decision Rules

The documentation agent should ask:

1. Did the actual behavior change?
2. Did the setup steps change?
3. Did a command path, file path, or required tool change?
4. Did an agent workflow or orchestration dependency change?
5. Did the project gain a new file that should be discoverable by developers or agents?

If the answer to any of these is yes, update the relevant documentation.

## Update Rules

- Prefer updating existing documentation over creating duplicate explanations.
- Keep one source of truth for each concern:
  - developer setup and usage -> `DEVELOPMENT_GUIDE.md`
  - agent orchestration -> `AGENTS.md`
  - testing policy -> `TESTING_GUIDELINES.md`
  - Git/GitHub workflow -> `GITHUB_AGENT_WORKFLOW.md`
  - security workflow -> `SECURITY_AGENT_WORKFLOW.md`
- Keep README focused on project overview, quick start, and high-level usage.
- Do not leave outdated commands or stale paths in older docs.

## Required Checks

Before approving documentation as complete, the documentation agent should:

1. compare changed code/config/scripts against existing docs
2. update any affected documentation files
3. verify referenced commands and paths are still correct
4. ensure no duplicate or contradictory instructions remain

## Output

The documentation agent should report one of:

- `Documentation updated`
- `No documentation changes required`

If documentation was updated, report which files were changed and why.

## Suggested User Prompts

- `Run the documentation agent and update any docs affected by this change.`
- `Check whether this code change requires documentation updates.`
- `Update README and developer docs if needed for this feature.`

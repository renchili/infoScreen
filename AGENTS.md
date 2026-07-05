# Agent Execution Bootstrap

This file is the repository entry point for agents working on `renchili/infoScreen`.

It does not replace the project-specific rules in `AGENT.md` and it does not replace the reusable workflow rules in `skills/SKILL.md`. It only defines the read order and the safe operating boundary for this repository.

## Required reading order

Before planning, editing, reviewing, validating, or reporting repository work, read these files in order:

1. `AGENTS.md` — this bootstrap entrypoint.
2. `AGENT.md` — InfoScreen project-specific rules.
3. `skills/SKILL.md` — repository workflow, evidence, validation, and delivery rules.
4. `skills/full-project-acceptance-hard-gates/SKILL.md` — full-project acceptance rules when the task is validation, acceptance, or release readiness.
5. `README.md` — operator-facing project overview and verification commands.
6. `metadata.json` — compact product metadata and natural-language product prompt.
7. `docs/design.md`, `docs/api-spec.md`, and `docs/questions.md` when relevant.
8. Relevant source, scripts, deployment files, CI workflows, and configuration files.

If a required rule source cannot be read, stop and ask the user. Do not continue from memory or guess missing rules.

## Project identity

InfoScreen is a local-first personal information screen for an always-on Surface or Ubuntu display. The repository root is `~/infoscreen`.

Do not create another project root, duplicate app, placeholder implementation, unrelated demo, or generated runtime output in source control.

## Output boundaries

Agents may create or update only files required by the current request and consistent with the repository layout:

- project documentation and metadata at the repository root or under `docs/`.
- project skills under `skills/`.
- dashboard backend, frontend, configuration, and runtime-job source under `surface/`.
- deployment and operator scripts under `deploy/`, `mac/`, or `scripts/` when the task is operational.
- CI workflows under `.github/workflows/` when the task requires automated validation.

Runtime JSON, local environment files, logs, local photos, generated photo outputs, caches, and compiled files must stay out of source control.

## Evidence rules

Every repository-work response must distinguish:

- code changed.
- static inspection performed.
- local commands executed.
- CI or workflow evidence available.
- checks not run.
- remaining gaps or risks.

Do not claim full acceptance, CI success, browser validation, deployment success, or runtime correctness unless there is direct evidence for the exact commit being discussed.

## Final response requirements

For repository work, include:

- branch name.
- commit SHA or PR number when applicable.
- exact files changed.
- checks run.
- checks not run.
- remaining evidence gaps or risks.

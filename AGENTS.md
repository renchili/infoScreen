# Agent Execution Bootstrap

This file is the repository entry point for agents working on InfoScreen. It tells agents what to read first, what rule sources must be respected, what may be generated or updated, and how to continue safely after context loss.

`AGENTS.md` does not replace `AGENT.md` and does not replace `skills/SKILL.md`.

## Rule source roles

The rule sources have different jobs:

- `AGENT.md` is the InfoScreen project-specific agent file. It is generated from the current repository structure, project constraints, user corrections, and the Skill workflow. It controls InfoScreen-specific architecture, source ownership, and implementation boundaries.
- `skills/SKILL.md` is the reusable workflow Skill. It controls how agents must perform repository work, including repository hygiene, documentation output, evidence, validation, branch/PR behaviour, final responses, and compact-safe working records.
- `AGENTS.md` is only the bootstrap entrypoint. It tells agents to read and obey `AGENT.md`, then apply the Skill workflow. It must not duplicate the full project specification or copy the full Skill.

## Required reading order

Before planning, editing, generating files, reviewing, or reporting completion, agents must read and apply these files in order:

1. `AGENTS.md` — this bootstrap entrypoint.
2. `AGENT.md` — InfoScreen project rules, including source layout, Python role classification, frontend boundaries, runtime boundaries, job boundaries, documentation rules, validation, and final response requirements.
3. `skills/SKILL.md` — agent workflow rules for repository hygiene, documentation output, evidence, validation, branch/PR behaviour, and compact-safe working records.
4. `README.md`, when present.
5. Existing `docs/` files, when present.
6. Existing source layout, tests, scripts, CI, Docker/deployment files, migrations, and configuration files.

If `AGENT.md` is missing in this repository, generate it from the current project structure, `AGENTS.md`, `skills/SKILL.md`, `README.md`, docs, and source layout before making other repository changes.

If any other required rule source cannot be read, stop and ask the user. Do not continue from memory or guess missing rules.

## What agents must generate or update

For repository work, generate or update only the artefacts required by the current user request, `AGENT.md`, the Skill, and existing repository conventions.

Allowed output categories are:

- production code in the existing source layout.
- tests in the existing test layout.
- migrations or schema files when data shape changes.
- configuration files when runtime behaviour requires configuration.
- scripts only when they fit the existing repository workflow or are required for validation.
- `docs/api-spec.md` when API usage or behaviour changes.
- `docs/design.md` when architecture, implementation strategy, runtime behaviour, configuration, logging, validation, or requirement mapping changes.
- `docs/questions.md` only for clarification answers about unclear process, acceptance, testing, runtime, delivery, usage, or verification points.
- PR notes and final responses containing evidence, checks run, checks not run, and remaining gaps.

Do not generate duplicate project roots, sample applications, placeholder files, noop files, arbitrary reports, unrelated demos, or artefacts outside the repository convention.

## What agents must obey

- Respect `AGENT.md` as the project-specific controlling rule source.
- Use the Skill as the controlling workflow rule source.
- Use existing repository structure to decide where files belong.
- Treat the latest user feedback as the current correction or narrowed scope.

If these sources appear to conflict, stop and ask the user which rule controls. Do not silently choose one.

## Boundary requirements

Agents must keep implementation, tests, demos, fixtures, and acceptance aids separate.

- Production code must not depend on test helpers, mocks, random sample data, or demo-only configuration.
- Tests, fixtures, mocks, and sample data must stay in test, fixture, example, or docs paths.
- Acceptance probing aids must be documented as testing aids, not product frontend scope.
- Documentation must describe implemented behaviour and verified evidence, not desired behaviour without code or proof.

## Context continuation

After compaction, model switch, long pause, or a new continuation, agents must re-read `AGENT.md` and the Skill before continuing repository work.

A compact working record must preserve:

- current branch and base branch.
- files changed.
- user corrections that changed the requirement.
- checks run.
- checks not run.
- open risks or evidence gaps.
- user-local commands given and whether results were received.

## Final response requirements

Every final response for repository work must include:

- exact files changed.
- branch name and PR number when created.
- checks run.
- checks not run.
- remaining evidence gaps or risks.

Do not present generated artifacts or documentation under names different from their actual file paths.

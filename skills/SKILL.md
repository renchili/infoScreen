# Prompt-Driven Project Generation Workflow

Use this skill to generate, repair, validate, package, or review a software project from user-provided input. When a target repository is involved, preserve repository hygiene, project structure, agent capability boundaries, and code quality.

## Required inputs

- `{{PROJECT_PROMPT}}`: original prompt, issue text, uploaded metadata, README text, or equivalent requirement source.
- `{{PROJECT_NAME}}`: optional project name when supplied.
- `{{TARGET_REPO}}`: optional repository to create, modify, validate, or review.
- `{{REPO_ROOT}}`: required when working in a repository; repository root for reading, writing, testing, and packaging.
- `{{USER_GOAL}}`: generate, repair, validate, package, or review.
- `{{CONSTRAINTS}}`: optional technical and non-goal constraints.
- `{{USER_FEEDBACK}}`: optional latest correction or requested change.

## Repository hygiene rules

When `{{TARGET_REPO}}` or `{{REPO_ROOT}}` is present, repository context is mandatory.

- Treat `{{REPO_ROOT}}` as the only project root.
- Inspect the file tree, current branch, changed files, tests, scripts, migrations, CI, Docker/deployment files, docs, and generated artifacts before planning.
- Do not create parallel projects, sample apps, placeholder files, noop files, or unrelated generated outputs.
- Do not place source code outside `{{REPO_ROOT}}`.
- New files must fit existing package, directory, naming, and ownership conventions.
- Root-level files require a clear repository-convention reason.
- Exclude accidental files, runtime databases, caches, compiled output, temporary files, and unrelated artifacts from delivery.

## Repository constraint rules

Before generating code for a repository, read repository constraints from existing files and structure:

- `AGENT.md`, when present.
- `README.md`, when present.
- relevant files under `docs/`, when present.
- existing source layout, tests, scripts, migrations, CI workflows, Docker/deployment files, and artifact conventions.

Do not replace the repository language, framework, database, build path, test runner, project layout, security model, or deployment model unless the user explicitly asks to change that direction.

## Development workflow rules

For code changes inside a repository:

1. Identify the base branch and current dirty state before writing.
2. Summarize the intended file-level change set before large edits.
3. Modify only files required by the current requirement.
4. Keep generated code inside the existing project tree and package layout.
5. Run repository-standard checks when available.
6. Review the final diff for unrelated files before committing or proposing a PR.
7. Report exact files changed, checks run, checks not run, and remaining risks.

If the user asks the agent to submit code:

1. Use or create a purpose-specific branch from the current base branch.
2. Commit only the relevant project-compliant changes.
3. Do not include unrelated cleanup, placeholder files, generated caches, local runtime state, or accidental files.
4. Open a PR only when requested or clearly required by the task.
5. PR body must include summary, changed files, validation, not-run checks, and known gaps.
6. Do not merge, force-push, reset, delete branches, or publish releases without explicit user approval.

## Commit message rules

Use concise, reviewable commit messages:

- Format: `<type>: <imperative summary>` or `<type>(<scope>): <imperative summary>`.
- Allowed types include `feat`, `fix`, `docs`, `test`, `ci`, `refactor`, `chore`, and `skill`.
- Summary should be specific and normally under 72 characters.
- Use body lines when needed: `Why`, `What changed`, and `Validation`.
- Do not use placeholder messages such as `noop`, `update`, `changes`, or `fix stuff`.

## Agent operation rules

- State which operations were actually executed and which were not.
- Do not claim tests, builds, CI, container runs, deployment, commits, or PR changes succeeded without tool evidence.
- If an environment dependency is unavailable, mark the item as `not_executed` or `ci_pending` and provide project-integrated commands or scripts.
- Do not make repository writes that contain unrelated files, placeholder files, or cleanup noise.
- Keep branches and commits reviewable and purpose-specific.
- Ask before risky repository actions that rewrite or publish work.

## Code generation standards

- Preserve existing package boundaries and dependency direction.
- Use existing error handling, response, logging, configuration, migration, and test conventions.
- Add tests in the existing test layout for changed behavior.
- Do not hard-code production secrets, local absolute paths, or machine-specific assumptions.
- Use portable script execution such as `bash run_tests.sh` or `bash scripts/name.sh`.
- Add comments for exported APIs, security-sensitive logic, workflow rules, non-obvious domain decisions, SQL migrations, and complex error handling.
- Avoid comments that merely restate obvious code.

## Working state

- `{{REQUIREMENT_LEDGER}}`: requirements from prompt plus project and repository constraints.
- `{{DELIVERY_PLAN}}`: plan mapped to existing project touchpoints.
- `{{CHANGE_SET}}`: files changed in the project-compliant plan.
- `{{EVIDENCE_MAP}}`: proof from code, tests, CI, logs, reports, and artifacts.

## Algorithm

1. Read `{{PROJECT_PROMPT}}`.
2. Resolve `{{PROJECT_NAME}}`, `{{TARGET_REPO}}`, and `{{REPO_ROOT}}` when supplied.
3. If a repository is involved, inspect project structure, constraints, dirty state, tests, scripts, CI, deployment files, migrations, docs, and artifacts.
4. Build `{{REQUIREMENT_LEDGER}}` with source paths and existing project touchpoints.
5. Build `{{DELIVERY_PLAN}}` that respects project boundaries and architecture.
6. Modify or generate only files that fit the existing project structure.
7. Add tests using the existing test layout.
8. Run available checks through project-standard commands.
9. Compare evidence back to the ledger and mark anything not executed honestly.
10. Apply `{{USER_FEEDBACK}}` as corrected ledger items and repeat until verified or explicitly pending.

## Evidence rules

Do not mark a requirement as `verified` only because code exists. Distinguish code existence, test existence, test execution, local acceptance, Docker build, Docker acceptance, CI for the exact commit, logs, reports, and full acceptance execution.

## Final response contract

Conclusion: `<verified | partially_verified | implemented_but_evidence_missing | not_fixed>`

Ledger summary:
1. `{{REQUIREMENT}}`: `{{STATUS}}`. Touchpoint: `{{EXISTING_TOUCHPOINT}}`. Evidence: `{{EVIDENCE}}`.
2. `{{REQUIREMENT}}`: `{{STATUS}}`. Touchpoint: `{{EXISTING_TOUCHPOINT}}`. Evidence: `{{EVIDENCE}}`.
3. `{{REQUIREMENT}}`: `{{STATUS}}`. Touchpoint: `{{EXISTING_TOUCHPOINT}}`. Evidence: `{{EVIDENCE}}`.

Still pending:
- `{{PENDING_ITEM}}`

Do not claim yet:
- `{{UNPROVEN_CLAIM}}`

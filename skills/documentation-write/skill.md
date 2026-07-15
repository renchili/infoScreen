---
name: documentation-writing
description: Write or update repository documentation with evidence, safety, and gate alignment. Use this skill for README files, project docs, API docs, design docs, usage docs, bilingual docs, and documentation repair.
---

# Documentation Writing Workflow

Use this skill to create, update, repair, or review repository documentation. This is a reusable documentation workflow. Product-specific rules belong in `AGENT.md`; repository workflow rules belong in other loaded Skills.

## Gate alignment

This skill must not be used before repository gates are loaded.

Before writing documentation, the agent must follow `AGENTS.md` and load:

1. `AGENTS.md`.
2. `AGENT.md`.
3. relevant `skills/**/SKILL.md` files, including this one and any broader project-generation or repository workflow Skill.
4. `README.md`, existing docs, source layout, tests, scripts, CI, deployment files, and configuration conventions needed for the task.

The working record must include rule metadata for loaded, missing, unreadable, skipped, or blocked rule sources:

- path.
- role.
- required status.
- read status.
- stable identifier when available, such as blob SHA, commit SHA, checksum, branch, or ref.
- reason the rule source applies to the documentation task.

If `AGENT.md` is missing or unreadable during ordinary documentation work, stop before editing files and report the exact path and failed operation. Do not generate a replacement `AGENT.md` unless the user explicitly asks to create or modify it.

If the task requires a Skill and no relevant Skill under `skills/**/SKILL.md` can be found, stop before editing files. Report the searched pattern, list candidate Skill files if any, and ask which Skill applies. Do not fall back to `.chatgpt/skills/...` and do not invent a Skill path.

## Documentation scope

Use this skill for:

- README files.
- API usage documentation.
- design or architecture documentation.
- security, privacy, backup, restore, deployment, testing, and operation notes.
- clarification-answer documentation such as `docs/questions.md` when a loaded Skill defines that target.
- bilingual Chinese and English documentation.
- documentation review and repair.

Do not use this skill to invent product requirements, implementation status, roadmap, security posture, license terms, deployment topology, API behavior, or architecture.

## Evidence rules

Documentation must be evidence-backed.

- Every feature, command, API endpoint, dependency, architecture statement, security claim, deployment claim, and test claim must be traceable to repository files, user-provided requirements, tool output, CI output, logs, reports, or generated artifacts.
- If evidence is absent, omit the claim or mark it as pending. Do not fill gaps with assumptions.
- Commit titles and branch names may provide weak context only. Do not treat them as implementation proof.
- Do not claim code, tests, Docker, CI, deployment, or acceptance checks ran unless they actually ran and evidence was captured.
- Documentation must distinguish implemented behavior, intended requirement, validation evidence, checks not run, pending items, and risks.

## Documentation evidence ledger

Before writing or updating documentation, build a documentation evidence ledger. The ledger may be a working record, PR body section, or document-internal evidence section depending on the task.

Each substantive documentation claim must map to evidence. A substantive claim is any statement that describes project capability, behavior, architecture, API behavior, security posture, deployment, configuration, test status, operational status, supported language, supported platform, or generated artifact status.

For each substantive claim, track:

- claim or section.
- evidence source path, user input, command output, CI output, log, report, or artifact.
- stable identifier when available: blob SHA, commit SHA, checksum, branch, ref, command, or run ID.
- confidence status: verified, partially verified, not executed, unavailable, or pending user input.
- notes about any limitation, dynamic behavior, generated source, or missing proof.

Headings, table-of-contents entries, cross-links, and neutral labels do not need individual evidence entries unless they imply project capability or implementation status.

Do not publish broad claims such as `secure`, `production-ready`, `fully tested`, `cloud-native`, `offline`, `encrypted`, or `role-based` unless the evidence ledger contains proof from project rules, implementation, tests, and validation output.

## Safe scan rules

Scan only files needed for the documentation task.

Do not read, grep, summarize, quote, or list sensitive content from:

- version control internals.
- dependency directories and package caches.
- virtual environments.
- build output, generated output, coverage output, compiled output, and caches.
- logs, dumps, database snapshots, and runtime state.
- local-only environment files and private runtime profiles.
- credential, key, token, service-account, or kube configuration material.

Safe example files may be read when they are clearly examples, templates, or samples.

When private files are discovered by name, do not expose exact private paths in documentation. Use a general note such as: private configuration files are intentionally excluded from documentation.

## Target resolution

Before writing, determine the exact documentation target.

Use the target path from the user request, loaded Skill, existing documentation home, or repository convention. Do not invent arbitrary document names.

When a broader loaded Skill defines fixed targets, preserve them. For example, a project-generation Skill may require:

- `docs/api-spec.md` for API usage and behavior.
- `docs/design.md` for design, architecture, implementation strategy, runtime behavior, configuration, logging, validation, and requirement mapping.
- `docs/questions.md` only for project clarification answers.

If a target path cannot be resolved, ask the user for the path before writing.

If a target file already exists:

- update it in place when the task is an explicit repair, merge, or repository-maintenance task and the loaded Skill says to update existing documentation.
- ask before overwriting when the user asks to generate a standalone README or replacement document and has not granted overwrite permission.
- preserve the file name and path unless the user explicitly requests a rename.

## README target selection

For README-specific work, resolve the target explicitly before writing.

- Chinese only: use `README.md` when the repository uses Chinese as the primary README, unless the user requests `README.zh-CN.md`.
- English only: use `README.md` when the repository uses English as the primary README, unless the user requests `README.en.md`.
- Bilingual: use separate files such as `README.zh-CN.md` and `README.en.md`; create a short `README.md` index only when the repository convention supports it or the user approves.
- Existing README: do not overwrite a standalone README generation target without permission. For repair or maintenance work, update the existing target in place when the user request and loaded Skills require it.

## README reader onboarding contract

A README is not a school-outline summary. It is the first-run guide for a stranger who just cloned the repository.

A generated README must optimize for reader onboarding. It must answer, in order:

1. What is this repository?
2. What is it not?
3. Who is expected to use it?
4. What can a new reader do in the first 10 minutes?
5. What must be installed before running it?
6. What configuration is required, and where are safe examples?
7. Which command starts the smallest useful local path?
8. What output, URL, file, process, screen, or test result proves that startup worked?
9. Where are the main entry points and component boundaries?
10. How does a maintainer run tests, builds, lint, formatting, migrations, or packaging?
11. Where should a maintainer look first when startup, tests, configuration, or build fails?
12. Where should a maintainer start when changing code or documentation?

Do not write a README that only lists headings such as `Overview`, `Features`, `Tech Stack`, and `Getting Started` without a runnable path, expected success signal, repository entry points, and maintenance workflow.

If repository evidence cannot prove a first-run path, write a clear `Current runnable path` or `Local startup status` section that states what is known, what is missing, and which files or commands would be needed. Do not invent a working quick start.

## README structure contract

Use a reader-flow structure instead of a generic section list. Adapt section names to the project, but preserve the purpose and order.

A normal README should include these onboarding blocks when evidence exists:

1. `What this is`: one short paragraph grounded in project rules, manifests, and source layout.
2. `What this is not`: scope boundaries, especially when a repository has demos, acceptance aids, generated files, test harnesses, or intentionally missing runtime pieces.
3. `First 10 minutes`: the shortest safe path from clone to useful result.
4. `Prerequisites`: runtime, package manager, platform, toolchain, database, services, or device requirements proven by repository evidence.
5. `Configuration`: required, optional, and example-only configuration. Do not expose private configuration values.
6. `Run locally`: exact commands and working directory, with expected success output or URL when evidence supports it.
7. `Validate`: tests, smoke checks, health checks, CLI checks, build checks, screenshot checks, or artifact checks that prove the setup works.
8. `Repository map`: compact tree plus explanations of the files or directories a newcomer should open first.
9. `Development workflow`: how to edit, test, format, lint, build, package, migrate, or regenerate docs in the repository's actual workflow.
10. `API, CLI, UI, data, or library usage`: only the usage surfaces proven by code, schemas, tests, examples, or docs.
11. `Operations or deployment`: only when deployment or operation evidence exists.
12. `Troubleshooting`: evidence-backed failure checks such as missing configuration, dependency install failure, port conflict, database unavailable, migration not run, platform mismatch, or unsupported local mode.
13. `Security, privacy, and license`: only claims supported by project files, rules, or explicit user input.

If a block has no evidence and is not required to understand first use, omit it. If omitting it would leave the reader unable to start or validate the project, include a `Missing evidence` or `Pending setup information` note instead of pretending the path is complete.

## README short examples

Use short examples to force concrete, useful documentation. Examples should be adapted from loaded project rules and repository evidence; do not copy these examples into unrelated projects.

These examples use IronPage Vault only because this repository is the current rule-development context. They are examples, not reusable product requirements for other repositories.

Good project summary example:

```markdown
IronPage Vault is an offline Go/Echo backend for managing legal PDF lifecycle records, including document intake, version records, redaction workflow metadata, annotations, Bates numbering, audit logs, notifications, and local backup metadata.
```

Bad project summary example:

```markdown
This is a powerful document management platform with many useful features.
```

Good scope boundary example:

```markdown
This repository is a backend project. Any browser pages under `public/` are acceptance-testing aids for manually probing API behavior; they are not a product frontend.
```

Good first-run status example when startup evidence is incomplete:

```markdown
Current runnable path: the repository defines a Go backend and Docker deployment target, but this README does not claim a verified local startup command until the command has been run and captured in validation evidence.
```

Good validation example:

```markdown
A local run is considered successful only after the backend process starts, the configured database connection succeeds, and a documented health or API smoke check returns the expected response shape.
```

Good repository map example:

```markdown
Start with `cmd/server/` for process startup, `internal/app/` for HTTP routes and middleware, `internal/core/` for domain rules, `internal/service/` for orchestration, `internal/platform/` for PDF/backup adapters, `migrations/` for PostgreSQL shape, and `docs/api-spec.md` for endpoint behavior. Do not treat acceptance-probing pages as frontend product scope.
```

Bad repository map example:

```markdown
The project has many folders such as src, docs, tests, and config.
```

Good status wording example:

```markdown
Current status: backend API and Docker acceptance evidence exists for major document lifecycle flows, but the project must not be documented as fully accepted while security defaults, documentation consistency, and current-HEAD regression evidence remain unresolved.
```

Bad status wording example:

```markdown
The project is complete and production-ready.
```

Good documentation consistency example:

```markdown
If `docs/questions.md` says redaction is marker-only but the current service and Docker evidence show strict burn-in with text removal, rewrite the stale document. Do not keep both claims.
```

Good security wording example:

```markdown
For secure deployment, the README must say that secrets and credentials must be supplied externally and that acceptance/demo defaults are not production defaults. Do not publish real passwords or present predictable defaults as safe.
```

Good evidence-boundary example:

```markdown
A historical full-regression run may support behavior-equivalent evidence, but it is not the same as a current-HEAD full regression. State the exact SHA and run ID instead of claiming fresh verification.
```

## README handling

README files must be useful, concise, and grounded in repository evidence.

For README work:

1. detect the implementation languages, data languages, configuration languages, platforms, and project type before writing.
2. choose commands from manifests, build files, scripts, existing docs, or clear framework conventions.
3. include only sections with meaningful evidence.
4. keep the README focused on the onboarding path instead of cataloging every file.
5. use maintainer voice for security, privacy, and license notes.

Skip empty sections and placeholders such as `TODO`, `TBD`, or `coming soon`.

## Language, platform, and project-type detection

Documentation must support polyglot repositories. Do not reduce the repository to one primary language when multiple languages have different roles.

Detect and document each language or technology by role:

- application runtime language.
- library or SDK language.
- mobile application language.
- systems or embedded language.
- scripting or automation language.
- data, query, migration, or analytics language.
- template, markup, stylesheet, or UI language.
- infrastructure, packaging, or workflow language.
- test-only, fixture-only, example-only, or generated-code language.

For every detected language, record evidence and avoid overstating its role. A few isolated files, generated files, examples, or fixtures must not be described as a core implementation language unless repository structure proves that role.

Use ecosystem evidence, including but not limited to:

- JavaScript or TypeScript: package manifests, lockfiles, workspace files, framework configs, browser or server entry points, routes, test configs, bundler configs.
- Python: dependency manifests, package metadata, framework entry points, CLI entry points, notebooks when they are project sources, test configs.
- Java or Kotlin: Maven or Gradle files, source layout, Android or JVM configs, framework annotations, resource layout.
- Go: module files, workspace files, main packages, internal packages, public packages, test files.
- Swift or Objective-C: Xcode projects or workspaces, package manifests, app targets, framework targets, source files, plist files, test targets.
- C, C++, or Objective-C++: CMake, Make, Meson, Bazel, Ninja, autotools, compiler configs, headers, source files, bindings, embedded targets, native extension folders.
- Rust: Cargo manifests, workspace files, crates, binaries, libraries, examples, benches, feature flags, build scripts.
- PHP: Composer manifests, framework entry points, public web roots, route definitions, migrations, templates, test configs.
- Ruby: gemspecs, Gemfiles, Rails or Rack entry points, tasks, migrations, tests.
- C# or F#: solution files, project files, NuGet metadata, ASP.NET entry points, Unity or desktop project layout, tests.
- SQL and database code: schema files, migrations, seed files, stored procedures, query files, analytics SQL, test fixtures, ORM migration folders.
- Shell and PowerShell: repository scripts, installer scripts, CI helpers, operational runbooks, local developer tooling.
- HTML, CSS, Sass, templates, and static assets: frontend UI, docs site, server-rendered templates, examples, or generated output.
- Infrastructure and configuration: Dockerfiles, compose files, CI workflows, IaC files, deployment manifests, package manager files, config templates.

Language documentation rules:

- Describe each language by its actual repository role, such as `Swift iOS app`, `Rust CLI`, `C native library`, `PHP backend`, `SQL migrations`, or `Shell developer scripts`.
- Do not infer framework, platform, package manager, build command, deployment target, or database engine from file extensions alone.
- Document install, build, run, test, and lint commands only when supported by manifests, scripts, CI, docs, or clear ecosystem conventions.
- For polyglot repositories, separate commands by component or directory.
- For generated or vendored code, mention it only if it materially affects usage, build, licensing, or repository layout; otherwise omit it.
- For SQL, distinguish schema, migrations, seed data, stored procedures, query examples, analytics/reporting SQL, and test fixtures. Do not claim runtime database support unless config, code, or project rules prove it.
- For native or mobile code, distinguish application targets, library targets, bindings, platform-specific code, and tests.

Project type classification must be role-based, not language-list-based:

- frontend.
- backend service.
- full-stack application.
- mobile application.
- CLI tool.
- library or SDK.
- data or analytics project.
- infrastructure or deployment project.
- database or migration package.
- documentation-only project.
- mixed or monorepo project.

Do not replace or reinterpret the repository's language, framework, database, build path, test runner, project layout, security model, or deployment model.

## API documentation rules

Only include API documentation when API evidence exists.

Accepted evidence includes:

- OpenAPI or Swagger files.
- route or controller definitions.
- request or response schemas, DTOs, validation models, or typed handlers.
- existing docs or tests that explicitly call endpoints.

Rules:

- extract method and path only when both are explicit.
- include handler, controller, or source file when obvious.
- do not infer request or response bodies unless schema, type, validation model, or docs define them.
- do not guess authentication, roles, rate limits, side effects, status codes, or error codes.
- if routes are dynamic or unclear, document only directly confirmable entries and state that runtime assembly prevents complete static listing.
- if endpoints are numerous, group them and point to the source or OpenAPI file.

Preferred compact table:

```markdown
| Method | Path | Source | Notes |
|--------|------|--------|-------|
| GET | `/api/users` | `src/routes/users.ts` | User list endpoint |
```

## Structure and diagrams

Structure documentation must help the reader choose the next file to open. It is not a full filesystem dump.

A directory tree should:

- include only paths needed for onboarding, running, validating, developing, or operating the project.
- explain why each shown path matters.
- omit dependencies, build output, generated code, caches, private config, and unrelated artifacts.
- group large areas by purpose instead of listing every directory.

Include Mermaid only when repository evidence shows multiple components or flows that are easier to understand visually.

- Do not draw databases, queues, cloud services, external APIs, model providers, or microservices unless explicitly present in code, config, dependencies, or docs.
- Prefer request-flow, lifecycle-flow, or module-relationship diagrams over broad architecture maps.
- Omit diagrams when they would repeat the text or require guessing.
- Keep diagrams small enough that a maintainer can verify every node against repository evidence.

## Documentation density and usefulness control

Do not control documentation quality by fixed line counts, table row counts, feature counts, or command counts. Control it by reader usefulness and evidence density.

A README section is useful only if it helps a new reader do at least one of these tasks:

- decide whether the repository is relevant to them.
- install the correct tools.
- configure the smallest safe local environment.
- start the smallest useful runtime path.
- verify that startup, tests, build, migration, or packaging worked.
- find the correct source entry point.
- understand component boundaries.
- run the repository's actual development workflow.
- avoid a known wrong assumption.
- troubleshoot a likely first-run failure.
- find deeper documentation without duplicating it.

Remove or rewrite sections that only restate generic facts, marketing language, folder names without purpose, dependency names without role, feature names without behavior, or commands without expected results.

Use progressive disclosure:

- keep README focused on orientation, first-run path, validation, entry points, and next-step links.
- move detailed API behavior to `docs/api-spec.md` or the repository's API documentation home.
- move architecture rationale, requirement mapping, workflow details, and validation strategy to `docs/design.md` or the repository's design documentation home.
- move unresolved clarification answers to `docs/questions.md` when the loaded workflow Skill defines that target.
- link to deeper docs instead of duplicating long tables or long explanations in README.

A long README is acceptable when it is necessary for first use and every section has evidence. A short README is unacceptable when it hides required setup, validation, entry points, or failure modes.

Do not paste long generated documents into chat unless the user explicitly asks.

## Bilingual documentation

When generating both Chinese and English:

- create separate files such as `README.zh-CN.md` and `README.en.md`, unless the user requests different names.
- keep the two versions equivalent in structure and facts.
- localize section names and explanatory text naturally.
- avoid mixing languages in one paragraph except for commands, code, paths, package names, API names, and standard technical terms.
- if `README.md` is used as an index, keep it short and link to both language files.

## Documentation quality checklist

Before finalizing, verify:

- rule metadata was captured according to `AGENTS.md`.
- no excluded private files were read, summarized, or exposed.
- target paths were resolved and existing-file handling was respected.
- README target language and overwrite behavior were resolved when relevant.
- README explains the reader onboarding path from clone to first useful validation.
- README includes expected success signals for startup, tests, build, or smoke checks when evidence exists.
- README identifies main entry points and component boundaries.
- README includes troubleshooting or missing-evidence notes when the first-run path is incomplete.
- README avoids fixed-size filler and keeps only sections with reader-task value.
- README uses short examples to clarify the correct documentation style.
- languages, data languages, platforms, and project type were detected before generation.
- Each detected language or technology is described by its actual role, not its file extension alone.
- commands come from manifests, scripts, docs, CI, or clear framework conventions.
- SQL content is classified as schema, migration, seed, query, analytics, stored procedure, or fixture when present.
- API entries are backed by explicit route, schema, OpenAPI, docs, or test evidence.
- Architecture and deployment claims are backed by repository evidence.
- directory tree matches real files and excludes generated, private, dependency, and build output.
- Documentation evidence ledger covers substantive claims.
- security and license notes avoid invented claims and use the maintainer's voice.
- bilingual documents are factually aligned when both are generated.
- Documentation contains no placeholders.
- final response lists exact files changed, loaded rules with identifiers when available, checks run, checks not run, and remaining evidence gaps.

## Final response for documentation tasks

Every documentation task final response must include:

- exact documentation files created or updated.
- branch name and PR number when created.
- loaded rule files and metadata identifiers when available.
- source evidence used.
- checks run.
- checks not run.
- pending items, missing evidence, or risks.

Do not paste long generated documents into chat unless the user explicitly asks. Summarize the changed files and key sections instead.

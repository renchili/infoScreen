# Quality gates

The repository runs the same checks at three points. The checks are deliberately separate so a failure identifies the category instead of reporting one opaque combined result.

## 1. Before opening a pull request

Run the local pre-PR runner from any directory inside the repository:

```bash
repo_root="$(git rev-parse --show-toplevel)"
bash "$repo_root/scripts/ci/run_pre_pr.sh"
```

It compares the branch and any uncommitted work against `origin/main`. Fetch the baseline first when necessary:

```bash
git fetch origin main
```

Local checks run independently in this order:

```text
paths       runtime files, backups, obsolete Local Event overlays
content     conflict markers, private IPs, home paths, tokens, blocked UI text
structure   JSON parsing and index.html document structure
python      Python compile checks
shell       bash syntax checks
javascript  external and inline JavaScript syntax checks
```

## 2. Pull request gate

`Pull Request Gate` runs when a PR targets `main`. It exposes the same six checks as separate GitHub Actions statuses:

```text
pr-paths
pr-content
pr-structure
pr-python
pr-shell
pr-javascript
```

Configure these statuses as required checks in the branch ruleset for `main`.

## 3. Post-merge verification

`Post Merge Verification` runs after a commit reaches `main`. It reruns the six checks against the newly merged delta and adds:

```text
post-merge-http-smoke
```

The smoke test serves the dashboard through a local HTTP server, requests the entry page, and verifies that the response contains the dashboard HTML and title marker. It does not deploy or restart the Surface.

## Test ownership

| Test | Purpose | When it runs |
| --- | --- | --- |
| paths | Keep generated data, backups and obsolete overlays out of reviews | local, branch push, PR, post-merge |
| content | Prevent private data, secrets, merge markers and forbidden UI content | local, branch push, PR, post-merge |
| structure | Catch invalid JSON and malformed dashboard document structure | local, branch push, PR, post-merge |
| python | Catch Python syntax errors | local, branch push, PR, post-merge |
| shell | Catch shell syntax errors | local, branch push, PR, post-merge |
| javascript | Catch external and inline JavaScript syntax errors | local, branch push, PR, post-merge |
| HTTP smoke | Verify that the static dashboard can be served and fetched | post-merge only |

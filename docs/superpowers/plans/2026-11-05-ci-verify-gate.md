# Plan: No CI or branch protection: the six verifiers never gate what deploys to Pages (issue #35)

Risk tier: Medium. The change adds rather than alters site behavior and touches three files, but
its real effect (a check that runs on GitHub and fails a PR) cannot be exercised by a local unit
test, only replayed locally and then observed on the PR's own run. It touches CI permissions, so
least privilege is reviewed explicitly; it grants nothing, which is why it is not forced High.

Domain skills: none apply. No framework, UI, API, data, payments, or email code changes. The
site's HTML, CSS, and JavaScript are untouched. context7 is not needed: action major versions
were read from the GitHub releases API on 2026-11-05 (`actions/checkout` v7.0.1,
`actions/setup-python` v7.1.0, `actions/setup-node` v7.1.0).

## Scope

In scope: the workflow file, a drift check in an existing verifier, and CLAUDE.md.

Out of scope, by the orchestrator's instruction on behalf of the owner:

- Branch protection on `main` (issue step 2). A repo setting, not part of this diff. The owner
  approved it (require the `verify` check, require PRs, admin enforcement off), and the
  orchestrator applies it once this PR's `verify` run exists and is green, before merging, so
  this PR merges through the protection it creates. This run changes no repo setting.
- Switching Pages to an Actions deploy (issue step 3, optional). Not done. Pages keeps its
  `legacy` build from `main`.
- `--check-links`. Stays a manual, networked check, as CLAUDE.md intends.

Consequence for the issue's criteria: criteria 1 ("cannot be merged") and 2 ("direct push
blocked, or deploy gated") are met by this diff together with that settings step. The PR says
`Closes #35`.

## Acceptance criteria

1. `.github/workflows/verify.yml` exists and runs on `pull_request` and on `push` to `main`.
2. It has one job with id `verify` and no `name:` override, so the check name GitHub reports is
   exactly `verify`. That name is what branch protection will require, so it must stay stable.
3. The job sets up Python 3 and Node, then runs exactly the six commands
   `python3 tools/verify_{assets,security,content,interactivity,seo_a11y,portfolio}.py`, none
   with `--check-links`.
4. All six run even when an earlier one fails (each step after the first verifier carries
   `if: ${{ !cancelled() }}`), and the job fails if any one does.
5. No secrets: the file references no `secrets.` context and no `GITHUB_TOKEN`; checkout uses
   `persist-credentials: false`. Least privilege: top-level `permissions: contents: read` and
   nothing granted write.
6. No network beyond checkout and toolchain setup: no `--check-links`, no `pip install`, no
   `npm install`, no `curl`/`wget`. The verifiers are standard library only.
7. Every `uses:` is pinned to at least a major version tag (`@v7`), never a branch.
8. A PR that breaks a verifier (for example a removed `alt`) makes the replayed command
   sequence exit non-zero; the clean tree exits zero. Shown locally, then by the PR's own run.
9. `verify_security.py` gains `check_ci_workflow()`, standard library only, which fails when:
   the workflow is missing; the set of `tools/verify_*.py` it runs differs from the set on disk
   (a seventh verifier added, or one dropped); any is run twice or with `--check-links`;
   `permissions: contents: read` is absent or any `write` permission appears; a `secrets.`
   reference appears; a `uses:` is unpinned or pinned to a branch; `setup-node` is missing (the
   inline-script and `js/main.js` `node --check` gates skip silently without node); the job id
   `verify` is missing; either trigger is missing.
10. CLAUDE.md describes how the gate runs: the "Important Notes" bullet no longer says the
    verifiers are only run by hand, and a section explains the workflow, the stable `verify`
    check name, and the branch protection as configured (required check `verify`, PRs
    required, admin bypass allowed). It also says Pages is still the legacy build from `main`,
    so an admin direct push still publishes without waiting for the gate.

## Files that change

- `.github/workflows/verify.yml` (new)
- `tools/verify_security.py`: new `check_ci_workflow()`, called from `main()`, plus a
  `WORKFLOW` path constant and a docstring note that issue 35 added one check here.
- `CLAUDE.md`: "Important Notes" bullet, a new "### Continuous integration" subsection under
  Development Workflow, the "Verifying the security criteria" paragraph naming the new check,
  and one line in "Deployment".
- This plan.

## Order of work

1. Commit this plan alone.
2. TDD the drift check: write `check_ci_workflow()` first, run `verify_security.py` with no
   workflow present, and record the FAIL (red). Then mutation-test it against scratch workflow
   texts (missing verifier, extra verifier, `--check-links`, `contents: write`, `secrets.X`,
   `@main`, no setup-node) and record each FAIL.
3. Add `.github/workflows/verify.yml`; `verify_security.py` goes green.
4. Validate the YAML with the system PyYAML 6.0.1 (`yaml.safe_load`), dev-time only and never
   imported by a verifier, and assert the parsed structure (triggers, permissions, job id,
   step list). `actionlint` is not installed; GitHub's own parse on the PR run is the final
   word.
5. Replay: a script in scratch that runs the workflow's six `run:` commands, extracted from
   the YAML, with the same continue-on-failure semantics, and exits non-zero if any failed.
   Run it on the clean tree (exit 0) and on a scratch copy of the tree with one `alt`
   attribute removed from `index.html` (exit non-zero, `verify_seo_a11y.py` FAIL).
6. CLAUDE.md edits.
7. Full gate: all six verifiers.

## Risks

- Riskiest step: the drift check becoming a regex that passes vacuously. Guarded by the
  mutation runs in step 2: every rule must be seen failing at least once.
- A brittle check that fails on harmless reformatting of the YAML (quotes, ordering). Keep the
  regexes line-oriented and tolerant of quoting; document the expected shape in the docstring.
- `ubuntu-latest` image drift. The verifiers need only Python 3 and node, both set up
  explicitly, so the image only supplies git and a shell.
- Pinning to a major tag is not pinning to a SHA; a compromised tag could change. Accepted per
  the issue's "major version at minimum"; noted in the PR body.
- Renaming the job later silently disables a required check. The verifier asserts the job id,
  and CLAUDE.md says why.
- Pages legacy build runs Jekyll, which excludes dot-directories, so `.github/` is not
  published. No `.nojekyll` exists.

## Proof

- Criteria 1 to 7, 9: `check_ci_workflow()` in `verify_security.py`, shown red without the
  workflow and under each mutation, green with it.
- Criterion 8: the local replay output (clean exit 0, broken `alt` exit non-zero), then the PR's
  own `verify` run going green on GitHub.
- Criterion 10: the CLAUDE.md diff, reviewed by the doc finder.
- YAML validity: parser output from step 4.
- Live drive, green path: the workflow run on the PR itself (`gh pr checks --watch`).
- Live drive, red path on GitHub: after the real PR is green, a throwaway branch
  `issue-35-red-demo`, cut from the issue branch, carries one commit removing an `alt`
  attribute and opens as a draft PR titled "DO NOT MERGE: issue 35 gate demo". Its `verify`
  run must fail at the `verify_seo_a11y.py` step. Record the run URL and the failing step in
  the real PR's Test evidence, then close the draft PR and delete the remote and local branch.

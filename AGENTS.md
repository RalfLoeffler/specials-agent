# Repository instructions for Codex

## Purpose

Use this file as the stable operating contract for Codex and its subagents in
this Python repository. Prefer evidence from repository files over assumptions.
Keep changes narrow, reviewable, and reproducible.

## Agent workflow

For non-trivial work, use staged delegation:

1. Run `repo_explorer` and `test_planner` in parallel for read-only analysis.
2. Wait for both summaries before deciding on an implementation.
3. For a significant feature, refactor, migration, or multi-file change, create
   or update an ExecPlan under `.agent/plans/` using `.agent/PLANS.md`.
4. Delegate source changes to exactly one `implementer` agent.
5. After implementation, run `test_runner` and `reviewer`. They may run in
   parallel only when the implementation has stopped changing.
6. Use `docs_maintainer` after user-visible behavior, configuration, workflows,
   interfaces, or architecture change.

Do not run multiple write-capable agents at the same time. Parallelize
exploration, review, triage, and test planning; serialize implementation and
documentation changes.

## Repository discovery

Before editing, identify and cite the files that define:

- package layout and runtime entry points;
- dependency and environment management;
- canonical test commands;
- Ruff, Black, type-checking, build, and packaging configuration;
- CI and release workflows;
- repository-specific documentation rules.

Do not assume that every Python repository uses the same commands. Prefer the
commands already defined in `pyproject.toml`, `tox.ini`, `noxfile.py`,
`pytest.ini`, `environment.yml`, task runners, scripts, or CI configuration.

## Python environment and dependencies

- Prefer Mamba over Conda.
- Reuse the repository's existing environment and dependency-management method.
- Do not mix Poetry, pip, uv, Mamba, or requirements files unless the repository
  already does so intentionally.
- Do not add or upgrade production dependencies without explicit approval.
- Record any dependency or lockfile change and update all required lockfiles in
  the same change.

## Editing rules

- Make the smallest change that fully addresses the task.
- Preserve public APIs and behavior unless a change is explicitly requested.
- Preserve useful comments, docstrings, logging, and error context.
- Avoid unrelated refactoring and formatting churn.
- Follow existing naming, typing, import, and module-boundary conventions.
- Use Ruff and Black when the repository configures them.
- Never silence a lint or type error without a specific justification.
- Do not modify generated files directly unless the repository documents that
  workflow.

## Testing and validation

- Start with focused tests for the changed behavior.
- Add regression tests for fixed defects.
- Run broader tests when the affected execution path justifies them.
- Run configured linting, formatting checks, and type checks.
- Report exact commands and results.
- Distinguish new failures from known or pre-existing failures.
- Do not claim validation that was not run.

## Documentation

Update the closest relevant README or documentation as part of the same change
when a major milestone, architectural decision, interface, configuration option,
workflow, dependency, or user-visible behavior changes. Mermaid diagrams for
GitHub must use quoted node labels.

## Git safety

- Inspect `git status` and the relevant diff before and after editing.
- Do not discard unrelated local work.
- Do not commit, push, rebase, reset, or rewrite history unless explicitly asked.
- Do not change branches while another agent is writing.

## Final report

Summarize:

- what changed and why;
- files changed;
- tests and quality checks run, with outcomes;
- remaining risks, assumptions, and unverified environments;
- documentation updates or why none were required.

---
name: python-repo-workflow
description: Use for non-trivial Python repository work that requires staged exploration, implementation, tests, review, and documentation with Codex subagents.
---

# Python repository workflow

Use the repo-local custom agents when they are available.

1. Ask `repo_explorer` and `test_planner` to work in parallel. Wait for both.
2. If the task is significant, create or update an ExecPlan under
   `.agent/plans/` using `.agent/PLANS.md`.
3. Give one bounded implementation task to `implementer`. Never run two
   write-capable agents concurrently.
4. After writes stop, ask `test_runner` to validate and `reviewer` to inspect the
   diff. These two may run in parallel.
5. Use `docs_maintainer` when behavior, configuration, workflows, interfaces, or
   architecture changed.
6. Consolidate evidence into one final report with file paths, commands, results,
   remaining risks, and unverified environments.

Keep no more than two subagent threads active on this workstation unless the
user has measured that additional concurrency is beneficial. Read-heavy work is
the preferred use of parallelism.

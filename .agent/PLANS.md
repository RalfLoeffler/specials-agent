# Codex execution plans

An ExecPlan is a living implementation document for work that is too large or
risky to execute safely from a single short prompt.

Use an ExecPlan for:

- multi-file features or refactors;
- changes to architecture, packaging, interfaces, or data formats;
- migrations and compatibility work;
- tasks involving hardware, external systems, deployment, or difficult rollback;
- work expected to require several exploration, implementation, and validation
  cycles.

Store plans under `.agent/plans/<short-task-name>.md`.

## Required plan structure

### Goal

State the user-visible outcome and the problem being solved.

### Scope

List included and explicitly excluded work.

### Repository evidence

Cite the files, symbols, configuration, tests, and workflows that define the
current behavior.

### Constraints and invariants

List compatibility requirements, public APIs, data contracts, performance or
hardware constraints, and behavior that must not regress.

### Proposed approach

Describe the intended design and why it is preferable to the alternatives.

### Implementation steps

Use ordered, independently verifiable steps. Name likely files without treating
unverified assumptions as facts.

### Validation plan

List focused tests first, then linting, formatting, typing, broader tests, and
manual or hardware-specific validation.

### Risks and rollback

Describe failure modes, detection, mitigations, and how to revert safely.

### Progress log

Maintain a dated checklist as work proceeds. Record discoveries that changed the
plan.

### Outcome

At completion, summarize changes, validation evidence, deviations from the plan,
and remaining work.

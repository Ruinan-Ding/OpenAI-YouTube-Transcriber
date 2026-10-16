# Scrum backlog

Updated 15 Oct 2026. The human Product Owner orders product work and owns product decisions.
[SCRUM_WORKFLOW.md](SCRUM_WORKFLOW.md) defines the process; [AGENTS.md](AGENTS.md) owns
repo constraints/decisions, [PUNCHLIST.md](PUNCHLIST.md) owns implementation checkpoints,
and [the handoff](docs/CODEX_HANDOFF.md) owns source/environment evidence. Link those records
rather than copying their history or creating a second subtitle/setting specification.

## Product Goal

Proposed for confirmation at first planning: make downloading, transcribing and processing
media reliable and understandable across interactive/profile sessions, preserving user data
and verifying Windows behavior. This restates the existing app's purpose; it approves no
new features, defaults or subtitle integration.

## Current Sprint

No Sprint dates, duration or Sprint Goal have been agreed. Work is unscheduled; no Sprint
or Scrum event is claimed to have occurred. At first planning, agree the goal/timebox and
select achievable stories with verification capacity. A two-week cadence is an option,
not an already scheduled commitment.

## Current authorized story

### WF-001 — Adapt the ChessPlusPlus Claude Scrum workflow

- **Request/outcome:** owner's 15 Oct request for a complete cross-functional team working
  to senior standards, using TDD/BDD with possible specification-driven development later.
- **Scope:** project agent profiles, `/scrum`, native team settings, shared accountabilities,
  goals/events/backlog, BDD/TDD evidence, integration/review, Definition of Done and repo docs.
  Adapt the specialties to this Python/media/AI CLI. No app behavior or subtitle integration.
- **Owner:** current implementing conversation; one writer for workflow/shared metadata.
- **Status:** Review; configuration written, verification evidence recorded below. No live
  team trial or independent agent review is claimed.
- **Source/ownership:** setup began on the existing `fix/pre-subtitle-media-safety` dirty
  tree at `8d0b2d1`; retain its safety fixes and subtitle-plan correction. Workflow changes
  do not modify the application, prototype, tests, shipped profiles, package/dependency files
  or CI jobs.
- **Dependencies:** an available Claude Code account for actual plugin/model/team execution;
  installed Ponytail for code work. Project settings do not enable account access or grant
  new permissions. Other runtimes retain their own delegation rules.

| Example | Given / When / Then | Verification |
|---|---|---|
| WF-001-A | Given a fresh project session, when `/scrum` is used, then relevant senior role profiles follow the shared process and inherit the lead's model without permission overrides. | YAML/JSON/link checks and native discovery where available; state runtime limits. |
| WF-001-B | Given a behavior change, when the team refines and implements it, then product/development/quality agree observable examples and record meaningful Red/Green/Refactor evidence. | Workflow/role/skill instruction walkthrough; actual behavior-story trial remains separate. |
| WF-001-C | Given dirty source and overlapping one-script work, when tasks are delegated, then the intended source is preserved and each file has one writer. | Source hashes and ownership/handoff scenario review. |
| WF-001-D | Given missing product decisions, unavailable teammates or documentation-only work, when delivery proceeds, then dependent changes stay gated, verification is truthful and checks fit the change. | Subtitle-gate, structural-check and missing-runtime scenario review. |
| WF-001-E | Given later SDD consideration or changed scope, when the team adapts its plan, then accepted examples/decisions remain authoritative and no framework, Sprint, acceptance or new product policy is invented. | SDD, scope-change, defect and retrospective instruction review. |

Verification: Windows YAML/JSON, local-link, profile/tool/model and structural checks pass.
Claude Code 2.1.300's local agent-loader diagnostic lists all ten profiles; its skill loader
reports both project skills loaded (`settings-sync` and `scrum` are the two installed files).
Instruction walkthroughs cover WF-001-A–E, including dirty source, same-file work, a missing
subtitle decision, docs-only checks, unavailable review and later SDD. These are self-review,
not model behavior tests. All 33 tracked files outside workflow metadata match the dirty
baseline byte-for-byte. Evidence: Windows Temp `oyt-scrum-20261015-iv4_3px4/STRUCTURAL.txt`.

The ponytail and `/scrum` execution attempts were refused because the organization disabled
subscription access for Claude Code. Installed plugin instructions were read/applied manually;
account policies, credentials and models were not changed. No successful plugin execution,
live-team/model trial or independent review is claimed. `/skills` is unavailable in headless
mode; native interactive discovery/performance is not inferred from the loader diagnostics.
Application suites were not rerun for workflow setup. The later combined safety/workflow
delivery was rechecked on 15 Oct: Windows **159 passed, 3 symlink skips**, plain-script tests
passed and flake8/isort/mypy were clean. See the handoff's delivery checks and GitHub
PR/commit history for actual publication/CI state. These checks do not prove live teamwork.

## Previously recorded follow-ups

These are references to existing work, not a newly ordered Sprint or authorization to
implement everything. The owner selects the next bounded outcome.

| Existing work | Canonical record / constraint |
|---|---|
| Safety branch delivery | Punchlist 5.1–5.4 and 6.1 are WRITTEN; commit/PR/CI and owner observation are distinct from local implementation. |
| Session/input/duplicate-output fixes | Punchlist 5.5–5.8 remain OPEN; 5.9 records separate cleanup. |
| Subtitle prototype repairs | Punchlist 6.2–6.6 remain OPEN; validate them separately before porting helpers. |
| Subtitle integration | [Subtitle plan](docs/SUBTITLES_PLAN.md) owner decisions remain open; live AI refinement validation is required before its release phase. |

## Impediments and improvement

- First Sprint planning/Product Goal confirmation and stakeholder feedback have not occurred.
- Actual Claude model/plugin/team execution is unavailable under the current account policy;
  configuration checks cannot demonstrate team collaboration or performance.
- Proposed improvement experiment: use the next owner-selected bounded behavior story to
  trace an example through genuine Red/Green, actual permitted peer review and integrated
  acceptance. The facilitator records missing capabilities and avoidable handoff delays.
  Set its owner/measure/review date at planning and inspect it at the first actual retrospective.

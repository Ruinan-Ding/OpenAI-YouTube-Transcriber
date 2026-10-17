# Scrum backlog

Updated 17 Oct 2026. Human PO orders work. [Workflow](SCRUM_WORKFLOW.md) owns delivery;
[AGENTS.md](AGENTS.md) owns constraints/decisions, [PUNCHLIST.md](PUNCHLIST.md) implementation/
observation status, and [handoff](docs/CODEX_HANDOFF.md) source/environment evidence.
Load the active story rather than replaying history.

## Goals and scheduling

Proposed Product Goal, awaiting planning: reliable, understandable media downloading,
transcription/processing across interactive/profile sessions, preserving data and verifying
Windows behavior. No new app policy or subtitle integration implied.

No Sprint dates/duration/goal are agreed. Authorized work is unscheduled; no event is
invented. Agree goal/timebox, achievable selection and verification capacity at planning.

## Active spec: WF-002 — Token-efficient SDD intake

**r2 / Review.** Source: owner's 17 Oct request to save tokens, adopt SDD now and
translate informal “vibe coding” requirements automatically within the BDD/TDD Scrum team.
Revision 2 adds the owner's subsequent commit, push and merge instruction; intake examples
and app scope are unchanged.

**Outcome/scope:** one compact spec drives examples, tasks and evidence; retain ten senior
capabilities with selective context and focused delegation. Excludes app/prototype/settings
behavior, dependencies, model/permission changes and subtitle decisions. Publication is
authorized through a PR after its required CI passes.

**Accepted intent:** request above and existing [decisions](AGENTS.md#decisions); former
optional-later SDD is superseded this turn. No new product policy proposed. Actual Claude
execution depends on account access, which project instructions cannot supply.

| ID | Given / When / Then | Check |
|---|---|---|
| WF-002-A | Given informal intent, when intake runs, then one spec links scope/rules, stable BDD examples and writer-owned tasks without requiring a user-written spec. | Intake/routing walkthrough. |
| WF-002-B | Given ambiguity or open subtitle choices, when translated, then questions remain explicit and only dependent work stops; no behavior/approval is guessed. | Ambiguity/subtitle walkthroughs. |
| WF-002-C | Given behavior or docs work, when delivered, then shared example IDs link genuine TDD or appropriate structural checks to observed results. | Behavior/docs walkthroughs. |
| WF-002-D | Given small/delegated work, when loading context, then only relevant sections/roles load; no automatic translator/full roster or repeated history. | Context/packet review; byte-size comparison. |
| WF-002-E | Given the team configuration, when discovered, then ten profiles retain inherited models/tool boundaries, file ownership and permitted peer review. | YAML/JSON/links/native discovery. |
| WF-002-F | Given steering or resumed dirty source, when continuing, then reconcile spec revision/examples and source-bound evidence without losing work. | Steering/resume walkthrough; source hashes. |

**Plan/owner:** root is sole writer/integrator for workflow, skill/profiles and linked
guidance/status records. Update intake/roles, reconcile references/decisions, then validate
combined source. No app interfaces change. Start: clean `main` at `979e1c9`; branch
`chore/token-efficient-sdd-workflow`. App/prototype/tests/settings/profile/dependency/CI
files must match baseline hashes.
Delivery: commit/push this branch, open the PR, inspect its actual Linux/Windows CI results,
then merge and synchronize local `main`. GitHub records the publication outcome.

**Evidence (17 Oct):** Windows Python 3.12.4 YAML/JSON and all 65 local links/anchors pass;
34 tracked files outside workflow/docs match baseline hashes. Native Claude Code discovery
lists all ten agents and reports both project skills loaded. Self-review traces A–F through
clear/ambiguous intent, subtitle gating, behavior/docs checks, focused delegation and
steering/resume. These are instruction walkthroughs, not live-model behavior tests.

Entry skill: 3,042 -> 1,671 UTF-8 bytes (45% less); all profiles: 15,686 -> 8,298 (47% less).
The lead now reads selected sections and the active spec instead of the whole workflow/
backlog. These are text-size proxies; actual Claude tokens/costs remain unmeasured.
Detailed source hashes/results: Windows Temp `oyt-sdd-20261017-0ai1fqgn/STRUCTURAL.json`;
`INTAKE_REVIEW.md` records the self-review. `git diff --check` passes.

The Codex skill validator rejects Claude's existing `argument-hint` extension; its standard
fields pass in an isolated copy with that extension omitted, and native Claude discovery
passes with it retained. Ponytail and `/scrum` execution remain blocked by organization
policy. No independent review/live team trial ran; unchanged app suites were not rerun.
Configuration is WRITTEN; workflow behavior/usage trial and owner observation remain pending.

## Earlier delivery and follow-ups

WF-001 (15 Oct) introduced project Scrum profiles/settings and BDD/TDD; its later-SDD scope
is superseded. Configuration merged in PR #57; original evidence is in punchlist 7/handoff.
Live trial remains OPEN (7.2), distinct from configuration loading and owner-SEEN.

| Existing work | Canonical record; not a newly ordered Sprint |
|---|---|
| Safety/publication | Punchlist 5.1–5.4, 6.1, 8.1; PR #57. |
| Session/input/duplicate outputs | 5.5–5.8 OPEN; 5.9 separate cleanup. |
| Subtitle prototype repairs | 6.2–6.6 OPEN; validate before porting. |
| Main-script subtitles | [Plan](docs/SUBTITLES_PLAN.md): ten unanswered owner decisions; separate live-refinement gate. |
| Planning/live workflow trial | 7.2–7.3 OPEN; no agreed Sprint or stakeholder feedback. |

**Impediment:** Claude subscription execution refused again on 17 Oct by organization policy.
Ponytail instructions read/applied manually; no account/model changes or successful live run.

**Improvement experiment:** next owner-selected behavior story traces an example through
actual Red/Green, permitted peer review and integrated acceptance. Lead records actual usage,
repeated context and quality/flow; agree review date at planning, not an invented retrospective.

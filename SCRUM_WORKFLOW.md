# Claude Scrum workflow

One senior cross-functional team delivers this Python/media/AI CLI. The human is Product
Owner. Specification-driven development (SDD) defines intent, BDD makes it observable, and
TDD implements it. [AGENTS.md](AGENTS.md) owns repo constraints/product decisions; this guide
owns delivery. User instructions and existing authorization prevail.

Use `/scrum <task>` or describe development work normally. The
[skill](.claude/skills/scrum/SKILL.md) translates informal “vibe coding” requests automatically;
no spec vocabulary, separate translator command or SDD framework is needed.

## Context routing

Read AGENTS.md once per context and the active [backlog](SCRUM_BACKLOG.md) story, then:

| Assignment | Load these sections only |
|---|---|
| Lead starting/changing work | Delivery loop; SDD intake; Definition of Done |
| Delegated work/review | Team contract; assigned profile/spec/examples; affected source |
| Staffing/runtime choice | Capabilities and runtime |
| Scrum planning/events | Scrum accountabilities and events |
| Context growth/resume | Token discipline |

Read affected code/callers before edits. Targeted context does not excuse incomplete
understanding. Invoke Ponytail as AGENTS.md requires; reuse unchanged instructions.

## Delivery loop

1. Inspect branch/HEAD, dirty source, affected callers and prior evidence. Select the
   authorized outcome and create/update its compact spec through SDD intake.
2. Pair product/development/quality perspectives on BDD examples (Three Amigos). Recorded
   owner intent supplies product input; three perspectives need not mean three agents.
   Identify checks, design risks, dependencies and writer-owned tasks before editing.
3. Establish baseline; run a meaningful failing regression on unchanged production code
   (**Red**), implement minimally (**Green**), then **Refactor** while green. Record commands
   and results by example ID. Setup/import failures are not behavioral Red.
4. Review integrated source against spec/examples and current-source evidence; fix findings,
   check drift and run applicable acceptance checks. Reassess any later affected delta.
5. Apply Definition of Done and update canonical records with actual evidence/gaps.

Refactors use characterization checks; docs/config use structural/link/native-loader checks.
Don't invent test-first history for existing code. Preserve failed output and investigate
flakiness; a lucky green does not resolve an unexplained failure.

## SDD intake

The lead translates intent, using the product-analyst capability when useful. This is not
an extra agent/model call or approval stage. Apply it to new requests and user steering:

1. Extract outcome/observable behavior from the user's words; inspect affected source and
   link existing decisions/settings. Separate accepted intent, technical proposals and
   unanswered product choices. Explicit requests/recorded rules are accepted intent;
   agent-proposed product behavior is not. Ask small batches about missing choices, most
   expensive first; block dependent clauses only. Silence never supplies approval.
2. Write one small spec with stable Given/When/Then example IDs. Cover normal use plus
   relevant failure/boundary/profile/repeat/language/batch/Windows cases. Map each example
   to a named test or actual manual/live observation; unresolved behavior stays a question.
3. Add affected interfaces/callers, ordered tasks, file owners and checks. Include material
   design rationale/tradeoffs; avoid separate documents repeating requirements/design/tasks.

```text
Story ID / revision / status / source request:
Outcome; in / out of scope:
Accepted intent + rule links; proposals / open questions:
AC-ID: Given ... When ... Then ... -> test or observation -> result/pending
Plan: interfaces; tasks/dependencies; writer + owned paths:
Evidence: source identity; Red/Green/refactor or structural checks; review; gaps:
```

Omit empty optional detail; six lines can suffice. Keep small specs inside their backlog
story. Larger multi-session changes may use `docs/specs/<story-id>.md`, linked from the
backlog without copying it. Git supplies version history. Keep example IDs stable; increment
revision for intent changes and identify superseded clauses. Status is Ready, In progress,
Review, Done or Blocked with its dependency; distinguish accepted/implemented/verified via
clauses and evidence. Ready never manufactures product approval.

| Informal request | Translation |
|---|---|
| “One bad download shouldn't stop the batch.” | Link existing failure isolation; reproduce the failing path, then failed-source/next-source example and regression. No new retention policy implied. |
| “Make the output cleaner.” | Ask which observable output: transcript wording, console text or files; investigate while waiting. Don't invent defaults, names or deletion behavior. |
| “Fix subtitle grammar but keep the times.” | Link accepted polish rule; examples preserve every timestamp. Main-script integration still awaits the plan's unanswered owner decisions. |

Specs link authorities rather than copying SETTINGS, owner decisions or subtitle rules.
Use settings-sync when fields/semantics change. Steering updates affected clauses/examples,
plan and checks; record changed owner decisions in AGENTS.md that turn, replacing superseded
text. A different outcome becomes a linked story. Before closure compare spec -> examples ->
code -> evidence; investigate drift instead of weakening expectations. No duplicate `.feature`
suite or new Gherkin tooling is required.

## Team contract

Everyone traces callers, anticipates realistic failures, preserves compatibility/data,
explains material tradeoffs and owns meaningful evidence. Specialties share responsibility
for the Increment rather than forming departments. Pair early; swarm on unfinished work.
A senior role/model label is an expectation, not proof of performance.

The lead integrates. Workers stay within assignments, return findings and never start nested
teams or unrelated backlog work. Use a compact packet:

```text
Spec path#story / revision / AC IDs; objective + relevant rule links
Branch/HEAD + required dirty-file identity; affected paths/callers
Writer paths / read-only paths / integrator; dependencies + allowed side effects
Checks or review delta/new files + current-source results; runtime limits
Return: changed paths, AC results/commands, trigger/impact/location findings, gaps/next action
```

Link shared facts; supply readable excerpts if references are inaccessible. One writer per
file, especially script/tests/metadata; transfer ownership before another edits. Worktrees
must include intended dirty changes. Never reset/stash/commit others' work for delegation
convenience or split the app to manufacture parallel tasks.

A qualified peer who did not author the implementation/design reviews the integrated delta,
new files and acceptance evidence when available/permitted. Read-only reviewers request
missing artifacts and cannot claim execution. Fix material findings and recheck. Bind checks/
review to HEAD plus dirty-file hashes/diff identity, reassessing later edits; independently
green branches are insufficient. Disclose missing independent review; the integrator checks
combined source. Only the assigned writer updates shared records.

## Capabilities and runtime

| Profile | Contribution |
|---|---|
| [Scrum Master](.claude/agents/scrum-master.md) | Goals, flow, impediments, events, improvement |
| [Product analyst](.claude/agents/product-analyst.md) | Intent-to-spec, PO questions, journeys, BDD |
| [Architect](.claude/agents/architect.md) | One-script design, interfaces, compatibility, review |
| [Python developer](.claude/agents/python-developer.md) | CLI, sessions, profiles, configuration, batches |
| [Media engineer](.claude/agents/media-engineer.md) | yt-dlp, ffmpeg, streams, names, file lifecycle |
| [AI engineer](.claude/agents/ai-engineer.md) | Whisper, languages/caches, backends, refinement |
| [Quality engineer](.claude/agents/quality-engineer.md) | BDD/TDD pairing, regression, acceptance, exploration |
| [UX/accessibility](.claude/agents/ux-accessibility.md) | Console/keyboard flows, comprehension, recovery |
| [Security/reliability](.claude/agents/security-reliability.md) | Trust, secrets, subprocesses, data/resource safety |
| [Release engineer](.claude/agents/release-engineer.md) | Integration, Windows/Linux CI, packaging, evidence |

Profiles inherit the lead's model/runtime permissions. Advisory profiles have read/search/
Skill only; Skill grants no shell/edit tools. Start with the lead covering needed capabilities;
add focused workers/reviewers for distinct useful results, not a full roster, permanent
translator or testing department. Respect runtime delegation/capacity and file ownership.
Overlapping edits stay sequential. Quality remains shared.

[Settings](.claude/settings.json) enable experimental in-process native teams for interactive
Claude Code; use them when sustained collaboration helps. `claude -p` uses ordinary subagents.
Follow the current runtime's delegation policy; sequential coverage is valid when delegation
is unavailable, with missing independence stated. Restart Claude after first adding agents.
Configuration cannot enable account access: don't change credentials/providers/permissions/
inherited models to bypass failed checks.

## Scrum accountabilities and events

The human **Product Owner** owns priorities, product decisions and acceptance; analysts
support them. The **Scrum Master** facilitates effectiveness without approval queues; the
lead can cover this role. **Developers** self-manage planning, delivery and quality together.

The backlog owns Product/Sprint Goals, ordered stories and impediments/improvements;
PUNCHLIST owns OPEN/WRITTEN/SEEN; the handoff owns source/environment evidence. Link records;
native tasks coordinate workers but don't replace the persistent plan. One implementation
slice per writer. Expose displaced work, including urgent defects, while retaining checks.

Agree Sprint dates, duration (one month or less), goal and selection with the PO. Authorized
unscheduled work can proceed meanwhile; a session is not a Sprint. Developers adapt work
within its goal; only the PO cancels a Sprint whose goal is obsolete.

| Event | Concrete outcome |
|---|---|
| Refinement, ongoing | Product/development/quality clarify examples/dependencies and split stories; PO orders work. |
| Planning, Sprint start | Why/what/how, dates, goal, achievable selection, verification capacity. |
| Daily Scrum | Developers inspect goal/progress and adapt within 15 minutes; no invented meetings. |
| Review, Sprint end | Inspect running Increment with PO/stakeholders; record actual feedback/adapt backlog. |
| Retrospective, after review | One improvement with owner, measure, review date; inspect next Sprint. |

For one-month Sprints, Planning/Review/Retrospective maxima are eight/four/three hours;
shorter Sprints use shorter events. Record missing events honestly, without ceremony
transcripts. Inspect outcomes, defects, blocked/cycle time and acceptance gaps, not imaginary
velocity or agent rankings. Trial the process on the next owner-selected behavior story.

## Token discipline

- Delegate bounded distinct deliverables only; reuse worker context for related follow-ups
  and release finished workers. No automatic full-team fan-out or translator/model call.
- Start with narrow `rg`/source ranges; expand to the affected flow as correctness requires.
  Don't load every historical doc/profile/log. Batch independent reads; avoid truncated dumps.
- Share spec IDs/paths and source-bound findings, not repeated chat history. Return concise
  evidence; full logs stay in artifacts with durable outcomes in tracked records. Skip
  repeated “all clear” messages, role introductions and simulated debates.
- Reuse evidence only while relevant source/environment match. After edits rerun affected
  and required integration/CI checks; token savings never remove Windows/media/security/
  review obligations or missing owner decisions.
- Checkpoint spec/revision, branch/dirty identity, owners, questions, failures/evidence and
  exact next action. Resume by inspecting actual source/live workers, not replaying history.
- Compare actual usage on similar stories when available. Bytes/words are prompt-size proxies,
  not Claude tokens or billing savings. Optimize context/calls, not acceptance coverage.

## Definition of Done

Every applicable condition passes, or the dependency remains pending:

- Accepted spec clauses, stable BDD examples, implementation and observed results agree;
  unresolved product choices stay gated, including main-script subtitle integration.
- Real Red/Green/refactor or truthful characterization/structural evidence is recorded;
  focused/integrated checks pass on combined source. Apply AGENTS.md/DEV.md test/lint/types,
  plain-runner/app-journey, settings-sync, packaging and real-media rules where affected.
- Paths/quoting/names/subprocesses have actual Windows evidence. Stubs/unit tests don't prove
  live AI/player/owner observations. Report missing tools/skips and unresolved failures.
- Data safety, compatibility, recovery, language/models, security/accessibility and packaging
  are covered where affected. Qualified independent review is recorded when available,
  material findings resolved and drift checked; disclose missing review/runtime evidence.
- Relevant docs/changelog/backlog/punchlist/handoff are current, without secrets/generated
  media/unused scaffolding. Evidence identifies source, environment, commands/results/limits.
  Only the owner marks SEEN. Publication, if in scope, requires actual PR/CI evidence; main
  moves through a PR under existing authorization.

Workflow-only changes need structural checks, not unchanged app suites. Loader discovery
proves configuration, not live teamwork. [CI](.github/workflows/tests.yml) runs both suites
on Windows/Linux Python 3.11 and lint/types on Linux; it cannot prove SDD/BDD agreement,
TDD chronology, collaboration, live AI or owner acceptance. Scrum/SDD add no permission gates
or external-message authorization; prepare reviewable work before any missing approval.

References: [Scrum Guide](https://scrumguides.org/scrum-guide.html), Claude
[teams](https://code.claude.com/docs/en/agent-teams), [subagents](https://code.claude.com/docs/en/sub-agents),
[skills](https://code.claude.com/docs/en/skills), [context/costs](https://code.claude.com/docs/en/costs#reduce-token-usage).

# Claude Scrum workflow

One cross-functional Scrum team owns a working Increment: application, media and AI
processing, console experience, tests, documentation and delivery. We use BDD to agree
observable behavior and TDD to implement it. [AGENTS.md](AGENTS.md) remains the authority
for repository constraints and owner decisions; this guide describes the delivery process.
The user's instructions and existing authorization take precedence.

This adapts the owner's ChessPlusPlus workflow to this Python CLI. It configures roles and
working practices; a role label does not establish expertise or prove a high-performing team.
Judge the team through working outcomes, honest evidence, collaboration and improvement.

## Running the team

Start a fresh Claude Code session in this repository and run `/scrum <task>`, or describe a
development task normally. The [skill](.claude/skills/scrum/SKILL.md) applies this process;
the [profiles](.claude/agents/) supply reusable capabilities. Restart an existing session
after first installing the new agent directory. Invoke Ponytail as required by AGENTS.md;
the Scrum skill does not replace that plugin or install it automatically.

Project [settings](.claude/settings.json) enable experimental native agent teams in-process,
without changing model selection or permissions. Native teammates need an interactive Claude
session. `claude -p` uses ordinary subagents, not native teammates. Use direct teammate
discussion and shared tasks when collaboration benefits the story; focused subagents suit
independent investigation and review. Follow the current runtime's delegation policy.
If delegation is unavailable, cover the responsibilities sequentially and state that no
independent review occurred. Never fabricate teammate conversations, tests or approvals.

Staff for the work rather than launching every profile. A small documentation change can
have one writer and structural checks. Behavior changes need development/quality pairing
and a qualified independent reviewer when available. Media/AI/session changes bring in the
affected specialists. A participant can cover several capabilities; a profile can have
multiple instances for genuinely independent work within runtime capacity.

The application is one script. Parallelize exploration, acceptance design and review;
sequence edits to the script and shared test file under one writer per file. Do not split
the app into modules to create parallel work. Workers apply their assigned task packet and
report to the main conversation; they do not start another Scrum team. On resume, inspect
the actual branch, dirty files, evidence and live workers before renewing assignments.

## Accountabilities and senior engineering standard

The **human owner is Product Owner**: product priorities, meanings/defaults of settings,
filenames, retention/deletion policy and acceptance remain theirs. The product analyst
supports that accountability and cannot assume it. Resolve routine technical choices within
the accepted intent; ask only about genuinely missing product decisions, in small batches.

The **Scrum Master** facilitates effectiveness, flow and impediment removal. The lead may
perform that responsibility directly; it is not a separate management or approval layer.
**Developers** collectively own planning, implementation, verification and the Increment.
The specialisms below are capabilities within one self-managing team, not departments.
Pair early, challenge assumptions respectfully, help outside a specialty and swarm on
unfinished work before starting more.

Every participant works to a senior standard: trace affected callers, explain material
tradeoffs, anticipate realistic failure modes, preserve compatibility/data, produce meaningful
acceptance evidence and own follow-through. All profiles inherit the lead's model. Seniority
is an expectation assessed through results and review, not a model upgrade or credential.

| Profile | Contribution to the shared outcome |
|---|---|
| [Scrum Master](.claude/agents/scrum-master.md) | Goals, facilitation, impediments, coordination and improvement |
| [Product analyst](.claude/agents/product-analyst.md) | PO support, refinement, user journeys and BDD examples |
| [Architect](.claude/agents/architect.md) | One-script design, contracts, settings compatibility and peer review |
| [Python/CLI developer](.claude/agents/python-developer.md) | Sessions, profiles, prompts, batch orchestration and Python implementation |
| [Media engineer](.claude/agents/media-engineer.md) | yt-dlp, ffmpeg/ffprobe, streams, output naming and safe file lifecycle |
| [AI/Whisper engineer](.claude/agents/ai-engineer.md) | Language/task selection, model/cache behavior, AI backends and timed-text contracts |
| [Quality engineer](.claude/agents/quality-engineer.md) | BDD/TDD pairing, regression/acceptance checks and exploratory verification |
| [UX/accessibility](.claude/agents/ux-accessibility.md) | Console comprehension, keyboard flows, profile discoverability and recovery |
| [Security/reliability](.claude/agents/security-reliability.md) | Trust boundaries, secrets, subprocesses, file safety and resource/failure risks |
| [Release engineer](.claude/agents/release-engineer.md) | Integrated checks, Windows/Linux CI, packaging, documentation and delivery evidence |

Advisory profiles have read/search/Skill access and return findings or proposals. They cannot
claim shell execution or edit shared records. Implementation and verification profiles use
only the tools and permissions their parent session permits. Skill access lets each invoke
Ponytail; it does not grant otherwise unavailable tools. The integrator owns shared metadata
unless it explicitly transfers file ownership.

## Goals, backlog and Scrum events

[SCRUM_BACKLOG.md](SCRUM_BACKLOG.md) holds the Product Goal, ordered stories, current Sprint
Goal/plan, impediments and one improvement experiment. [PUNCHLIST.md](PUNCHLIST.md) owns
implementation/observation status; [docs/CODEX_HANDOFF.md](docs/CODEX_HANDOFF.md) owns current
source/environment evidence. Link their entries instead of copying the historical ledger.
Native task lists coordinate current workers; they do not replace the persistent backlog.

Agree the first Sprint's duration, dates and goal with the Product Owner during planning.
Sprints last one month or less; two weeks is an option, not a scheduled commitment. Work
already authorized may proceed as an unscheduled story. An agent session is not a Sprint.

| Event | Participants and concrete result |
|---|---|
| Refinement, throughout | PO/analyst, development and quality clarify outcomes/examples, split stories and expose dependencies. The PO orders the backlog. |
| Sprint Planning, at the start | Agree why the Sprint matters, an achievable selection and how to begin, including verification capacity. Record dates, goal and selected stories. |
| Daily Scrum, each working day | Developers inspect progress toward the goal and adapt the plan within 15 minutes. Actual session updates can provide inspection evidence; do not invent a meeting. |
| Sprint Review, at the end | Inspect a running Increment with the PO/available stakeholders, record actual observations and feedback, then adapt the backlog. |
| Retrospective, after review | Inspect quality, collaboration and flow; choose one improvement with an owner, measure and next-review date, and inspect its result next Sprint. |

For a one-month Sprint, Planning is at most eight hours, Review four and Retrospective
three; scale to shorter Sprints. Finish when the outcome is clear rather than generating
ceremonial conversation. Record events that have not occurred and observations still missing.
Only the Product Owner cancels a Sprint whose goal becomes obsolete.

Each small vertical story records its ID/request, user or maintainer outcome, in/out of
scope, relevant owner decisions, acceptance examples with IDs, dependencies/questions,
writer/owned paths, status and evidence/review links. Use Ready, In progress, Review, Done
or Blocked with the exact dependency. Ready is a refinement aid, not another permission
checkpoint. Keep one implementation slice active per writer and make displaced work visible.

Done describes the agreed technical delivery scope. It never sets the punchlist's SEEN
status: only the owner can do that. Where publication is part of the story, include actual
PR/CI results before calling that delivery Done; otherwise record publication as pending.

## BDD: discovery, formulation, automation

Before behavior changes, bring product, development and quality perspectives together
(Three Amigos). Recorded owner intent can supply the product perspective; this is not a
requirement for three agents to repeat each other.

1. **Discover** the user's purpose in existing code, decisions and examples. Separate an
   accepted behavior from an open product question. Unanswered questions block dependent
   changes, while independent work continues. Keep the subtitle integration gate intact.
2. **Formulate** Given/When/Then examples with a concrete starting state, action and
   observable result. Select meaningful failure, boundary, language, profile/repeat,
   local/remote, batch and Windows-path cases according to the affected behavior.
3. **Automate** with the existing plain-assert/pytest tools and real media pipeline. Map
   examples to test names or explicitly required manual observations before implementation;
   record results after execution. Follow AGENTS.md's test rules and DEV.md's commands.

For example, the accepted preservation policy gives this scenario:

```gherkin
Given a complete audio download and requested MP3 and FLAC outputs
When MP3 succeeds and FLAC fails
Then the original download and completed MP3 remain available
And the failure is reported without preventing the next batch source
```

Test actual files/codecs and batch behavior rather than only checking called functions.
No Cucumber/Behave dependency, duplicated `.feature` files or parallel setting specification
is needed. Owner decisions stay in AGENTS.md; each setting stays in SETTINGS, with the
existing [settings-sync skill](.claude/skills/settings-sync/SKILL.md) for multi-place changes.

## TDD: Red, Green, Refactor

Establish the relevant baseline before changing behavior. For each new behavior or defect:

1. **Red:** write the smallest meaningful behavior regression first and run it against
   unchanged production code. Record the test, command and intended failure. A missing
   dependency, import error, incompatible fixture or wrong interpreter is not behavioral Red.
2. **Green:** implement the smallest correct change, following Ponytail and repo patterns;
   run the focused checks. Never weaken expected behavior to match the implementation.
3. **Refactor:** improve duplication, names or boundaries while tests stay green; then run
   the relevant regression and acceptance checks on the integrated source.

Pure refactors need characterization protection, not a fictitious new behavior failure.
Docs/configuration work uses format/link/native-discovery checks as applicable; do not invent
failing application tests. If code already existed, say so: prove the regression against
the original source or an isolated fault when useful, without inventing test-first history.

Select the layer that can observe the problem. Real ffmpeg outputs, Windows locks/quoting,
profile and interactive/repeat journeys, installed-package data, and live AI quality are
different evidence. A mocked response or passing unit test cannot prove a live model or
owner observation. Follow AGENTS.md's network-faking boundary and skip/report missing tools.
Preserve the existing plain-script runner and restore every patch in a finally block.

Keep baseline/environment failures distinct from regressions. Preserve failed output and
source identity before investigating. Rerun to test a cause, not to seek a lucky green;
unresolved flakiness remains visible. Do not hide failures or unexplained skips to claim Done.

## Delegation, review and integration

Before assigning work, inspect the actual branch/diff, handoff and existing dirty source.
The lead integrates the story, preserving earlier authorized work. Every worker receives:

```text
Story/goal and acceptance example IDs:
Accepted owner decisions and unresolved questions:
Branch/HEAD and required dirty source; relevant callers/paths:
Owned write paths, shared/read-only paths and integrator:
Dependencies, interfaces and step ordering:
Expected Red/Green/acceptance checks and evidence:
For review: readable story diff/new files and current-source check results:
Permitted side effects and known runtime/environment limits:
Return: changed paths, actual results, findings and remaining work:
```

Assign one writer per file, including tests and docs. Peers can discuss directly and propose
changes; transfer ownership before another participant edits. Sequence overlapping changes
to the one script. Separate worktrees must include the intended dirty source, not merely
HEAD. Do not commit, reset or stash someone else's work for delegation convenience.

A qualified peer who did not author the implementation/design reviews the integrated diff
and acceptance evidence when delegation is available. Provide all new files, source identity
and a readable story delta distinct from earlier dirty work. Tool-limited reviewers request
missing artifacts and return source findings; they cannot claim commands they did not run.
Fix concrete findings and recheck affected behavior. The integrator verifies the final
combined source; independently green branches do not establish a green integration.

Bind review/check results to the tested commit plus uncommitted-file identity. Reassess any
later delta even when HEAD has not changed. Record a missing independent review honestly.
On interruption, preserve status, owners, decisions, failing checks and exact next action;
on resume inspect reality before trusting the handoff. Clean up only this task's workers and
private fixtures/services, preserving owner media, profiles, configuration and other work.

## Changes, defects and decisions

User steering updates the active story's examples/scope and records what it supersedes.
A distinct outcome becomes another item. Developers adapt the plan within the Sprint Goal;
product priorities and goal changes remain with the PO. Existing authorization persists;
routine clarification does not create a new approval gate.

For defects, record expected/actual behavior, user impact, reproduction, source/profile/
platform and evidence. Swarm on urgent authorized defects, keeping displaced work visible
and retaining regression/review checks. Separate broken accepted behavior from a proposed
new default or policy. For a significant design decision, keep context, rationale, material
alternatives and compatibility consequences in the relevant existing guide/story; record
owner decisions in AGENTS.md and update superseded entries rather than adding contradictions.

## Definition of Done and feedback

The Increment meets every applicable condition, or the remaining work is explicit:

- Accepted examples are implemented and mapped to observed results. Missing product decisions
  and material defects are resolved or explicitly outside the owner's agreed scope.
- Meaningful Red/Green/Refactor evidence exists, or the truthful characterization/structural
  verification reason is recorded. Tests and documentation are part of development.
- Relevant focused and integration checks pass on the combined source. Changed application
  code meets AGENTS.md/DEV.md's lint, type, full-suite, plain-runner and real-run requirements;
  setting changes use settings-sync. Paths, quoting, filenames and subprocesses are exercised
  on Windows. A Linux-only result does not satisfy that Windows check.
- File preservation, failure recovery, compatibility, language/model behavior, security,
  console accessibility, performance and packaging are checked where affected.
- Peer review is complete and material findings addressed when available; missing required
  review or runtime capability is stated. No self-review is labelled independent.
- Relevant guides, changelog, backlog, handoff and punchlist match the actual state. No secret,
  generated media, unused scaffolding or unapproved dependency is introduced.
- Delivery evidence identifies source, environment, commands, results, skips and limits.
  A required check not run remains pending. Published work links actual PR/CI results;
  private temporary logs supplement the tracked result rather than replace it.

[Current CI](.github/workflows/tests.yml) runs both test files on Windows/Linux with Python
3.11 and lint/type checks on Linux. It does not enforce BDD agreement, test-first chronology,
peer review, owner observation or live AI quality merely because these instructions exist.
Workflow-only edits need structural checks, not unchanged media/AI suites. Role discovery
proves the configuration loads; use an actual story to evaluate team performance.

Technical completion does not mean committed, merged, released or owner-SEEN. Work reaches
main through a PR. Follow existing authorization for commits/pushes/merges and other side
effects; Scrum events add no permission gates. Prepare a concrete reviewable result before
asking for any genuinely missing authorization. Internal coordination does not authorize
email, chat or other external messages.

Inspect escaped defects, blocked/cycle time, acceptance gaps and Sprint Goal outcomes.
Use estimates for planning, not ranking agents. Do not optimize for code/test/token counts
or invented velocity. At review, choose one measurable improvement and inspect it next time.
Use the next owner-selected bounded behavior story as a real trial: trace its examples
through genuine Red/Green, peer collaboration and integrated acceptance, then improve the
process from observed friction. Do not invent a feature or Sprint to test the organization.

## SDD later

SDD here means **specification-driven development**, as in ChessPlusPlus. It remains an
optional future adoption, not a framework installed now or a replacement for BDD/TDD.
If the owner adopts it, build on accepted examples and current decision/settings/docs:
keep a small versioned behavior contract, trace it to tests/code and review drift. Keep one
authoritative home per rule and distinguish proposed, accepted, implemented and verified
states. Clarify the acronym if a different meaning is intended; do not prebuild spec tooling.

## References

The [Scrum Guide](https://scrumguides.org/scrum-guide.html) defines the accountabilities,
events and commitments. Claude's [agent teams](https://code.claude.com/docs/en/agent-teams),
[subagents](https://code.claude.com/docs/en/sub-agents) and
[skills](https://code.claude.com/docs/en/skills) document the native runtime and file formats.
Organization authentication/managed policies remain outside these project instructions.

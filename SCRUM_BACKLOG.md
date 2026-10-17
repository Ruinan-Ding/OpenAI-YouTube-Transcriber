# Delivery backlog

Updated 17 Oct 2026. Human PO orders work. [Team workflow](SCRUM_WORKFLOW.md) owns delivery;
[SAFe coordination](docs/SAFE_WORKFLOW.md) owns feature/PI guidance; [AGENTS.md](AGENTS.md)
owns constraints/decisions, [PUNCHLIST.md](PUNCHLIST.md) implementation/observation status,
and [handoff](docs/CODEX_HANDOFF.md) source/environment evidence. Read only the active spec
and coordination deltas needed for the assignment.

## Goals and coordination

Proposed Product Goal, awaiting planning: reliable, understandable media downloading,
transcription/processing across interactive/profile sessions, preserving data and verifying
Windows behavior. This authorizes no new app policy or subtitle integration.

One delivery team; no actual ART, PI, Sprint dates/cadence, capacity or commitments agreed.
Authorized work is unscheduled. Feature/objective ordering, business values and priorities
await the owner's actual input; do not manufacture a train calendar or estimates.

When feature/PI coordination is needed, keep its one record here using the
[compact format](docs/SAFE_WORKFLOW.md#minimal-coordination-record). Link child specs and
reuse their evidence. No empty parallel feature/risk boards or ceremony transcripts now.

## Active spec: WF-004 — Focused Claude plugin toolchain

**r2 / Review.** Source: owner's request to add relevant Claude plugins, explicitly
including Ralph, to the SAFe/SDD/BDD/TDD workflow while preserving token efficiency.
Revision 2 adds the owner's commit, push and merge instruction for the combined SAFe/plugin
changes; implementation examples and application scope remain unchanged.

**Scope/intent:** retain Ponytail and add official Ralph Loop, PR Review Toolkit, Pyright
LSP and commit/PR commands at project scope. Install necessary tool dependencies separately
from application Python. Reuse the current dirty SAFe work; no app behavior, credential/model/
permission policy change, live AI task, loop, scan or full-team launch is implied. Publication
is authorized through a PR after Linux/Windows CI passes.

| ID | Given / When / Then | Check |
|---|---|---|
| WF-004-A | Given a fresh project runtime, when plugins load, then the five declared plugin IDs resolve at project scope on Windows and WSL with existing team/settings preserved. | Settings/manifest/native installation/discovery checks. |
| WF-004-B | Given an authorized bounded story, when Ralph is explicitly started, then its prompt names spec/checks and a positive iteration cap; limit/promise/cancel outcomes never manufacture technical completion or owner-SEEN. | Isolated real setup/Stop-hook checks; state ignore and usage review. |
| WF-004-C | Given targeted quality work, when review tools are used, then only relevant aspects run, upstream model costs remain explicit and external publication follows existing authority. | Routing/source/model inspection; no automatic broad review. |
| WF-004-D | Given Python code navigation, when the LSP starts, then its server initializes on Windows/WSL without altering app requirements or replacing mypy/real tests. | Dependency availability and JSON-RPC initialization. |
| WF-004-E | Given existing dirty SAFe work, when configuring plugins, then source is preserved, shared metadata is reconciled and app/settings/session/subtitle decisions remain intact. | Baseline hashes, diff and workflow-link checks. |

**Plan/writer:** root owns plugin settings, dependency setup and linked workflow/status docs;
preserve one writer per file. Inspect official sources, install locally at project scope,
exercise native dependencies/hooks in temporary fixtures, then record results/limits.
App source/tests/dependencies/config and existing SAFe reference stay unchanged.

**Evidence (17 Oct):** all five project installations/states verified on native Windows and
WSL: Ponytail 5.3.2; Ralph Loop/Pyright LSP 1.0.0; PR toolkit/commit helpers catalog revision
`ea10b213686c`. PR toolkit is installed with shared activation false. Claude's detail estimate
is about 1,600 tokens per enabled session for that toolkit; activation is phase-specific.
Optional Ponytail ledger/name sending are disabled locally; webhook URL/token remain unset.

Six real runtime checks pass on each OS: inactive Ralph hook, other-session isolation,
bounded continuation, iteration-cap stopping, matching-promise stopping, and Pyright JSON-RPC
initialization/navigation capability/shutdown. Fixtures use paths with spaces/Japanese text;
no actual checkout loop was started. Windows Git Bash/Perl, jq and the Node/Pyright development
tooling are available separately from application Python. Scoop's jq install refreshed its
manager/catalog and reported an unrelated Java-bucket ownership warning; no Git trust
exception or unrelated app update was applied.

Windows YAML/JSON/settings/link/source checks pass: 84 local links/anchors, ten unchanged
project profiles, and 45 pre-existing files byte-preserved, including prior SAFe profiles,
entry skill/reference and application/test/config/dependency files. Existing runtime/team
settings and source ownership are preserved; Ralph state is ignored. `git diff --check`
passes. Native Claude loaders recognize plugin commands and the Pyright LSP registration.

Detailed checks/source identity: Windows Temp `oyt-plugins-20261017-2b6zvusg/STRUCTURAL.json`,
`RUNTIME-Windows.json`, `RUNTIME-Linux.json` and installation/detail logs. These are config/
tool checks, not live model quality, independent review, measured billing savings or
owner-SEEN. Application suites were not rerun for this configuration-only change.

Live Ponytail/model invocation remains unavailable: WSL reports organization-disabled
subscription access; native Windows reports expired OAuth that could not be refreshed.
No credentials, account policy or permission/model defaults were changed to bypass those
limits. Configuration is WRITTEN; actual agent iteration/review and owner observation remain
pending. The owner subsequently requested publication; GitHub records the actual PR/CI/merge
outcome separately from local configuration checks.

## Prior spec: WF-003 — SAFe coordination without default context growth

**r1 / Review.** Source: owner's 17 Oct request: “make it a SAFe level workflow while
still keeping token efficiency.” Prior SDD/vibe-translation and BDD/TDD requirements remain.

**Outcome/scope:** add feature/enabler hierarchy, PI objectives/planning, dependency/risk
coordination, integrated demos and Inspect & Adapt. Existing profiles cover SAFe
accountabilities; one reference loads only when relevant. Ordinary story instructions must
not grow against the prior workflow. No app/subtitle/settings changes, new agents, models,
permissions, dependencies, real ART/PI commitments or publication are authorized by this item.

**Accepted intent:** the explicit process request; [owner decisions](AGENTS.md#decisions)
remain authoritative. Use SAFe as a project adaptation, accurately describing one current
team. No new product defaults, budget or staffing choices are proposed.

| ID | Given / When / Then | Check |
|---|---|---|
| WF-003-A | Given a bounded informal request, when routed, then it uses the compact SDD/BDD/TDD path without a PI packet or extra model/role call. | Routing walkthrough; default instruction-byte budget. |
| WF-003-B | Given multi-story feature/PI work, when planned, then goal/feature/story/AC links, real capacity, objectives, dependencies, ROAM risks and acceptance evidence share one linked record. | Feature/PI/change walkthroughs; local links. |
| WF-003-C | Given existing profiles, when SAFe roles are needed, then RTE/PM/System Architect/System Team responsibilities reuse them; human product authority and tool/model boundaries remain. | YAML/JSON/native discovery; role walkthrough. |
| WF-003-D | Given missing dates, business value, capacity, access or subtitle choices, when planning, then unknowns stay visible and no event, commitment, acceptance or product behavior is invented. | Unscheduled/ambiguity/subtitle/access walkthroughs. |
| WF-003-E | Given integrated work or a dependency change, when inspected, then source-bound checks, representative demo feedback and improvement actions update affected objectives/specs; real quality obligations remain. | Integration/steering/review walkthrough; source hashes. |

**Plan/ownership:** root is sole writer/integrator for the coordination reference, team
entry/routing, four affected role profiles, backlog and linked guidance/status docs. Read
public official SAFe guidance, map accountabilities without extra profiles, reconcile docs,
then validate on Windows and through native discovery. Start: clean `main` at `0dfebc7`;
branch `chore/token-efficient-safe-workflow`. App, prototype, tests, settings, CI, dependencies,
shipped data and the six other role profiles must match baseline hashes.

**Evidence (17 Oct):** Windows Python 3.12.4 YAML/JSON, 75 local links/anchors and source
checks pass. All 40 tracked files outside the change, including the six other profiles,
match baseline hashes. AGENTS content outside its delivery section/decision is unchanged.
Native discovery finds all ten profiles and both project skills. Self-review traces A–E
through small/feature work, roles, missing inputs, subtitle gates and integration/steering;
these are instruction walkthroughs, not model-behavior tests or independent review.

Entry skill: 1,671 -> 1,507 UTF-8 bytes (10% less). Common instructions, including AGENTS,
CLAUDE, the skill and required team sections: 23,259 -> 22,993 bytes, excluding variable
story/source content. The additional SAFe reference is 9,943 bytes and loads by relevant
section only for coordination work. These are text-size proxies, not measured Claude tokens,
billing savings or quality outcomes. Detailed results/source identities: Windows Temp
`oyt-safe-20261017-3w4jtbai/STRUCTURAL.json`; self-review: `ROUTING_REVIEW.md`.

`git diff --check` passes. Standard skill fields validate in an isolated copy omitting
Claude's existing `argument-hint` extension; native checks retain it. Live `/scrum` and
Ponytail execution remain blocked by organization policy. Unchanged app suites were not
rerun. Configuration is WRITTEN; real planning/team/usage trial and owner observation remain
pending. No live performance, independent review or app TDD chronology is claimed.

## Earlier delivery and follow-ups

WF-002 introduced compact SDD/vibe intake and token-efficient BDD/TDD Scrum delivery, merged
through [PR #58](https://github.com/Ruinan-Ding/OpenAI-YouTube-Transcriber/pull/58). Linux and
Windows PR CI passed. Entry skill/profile text fell 45%/47% against WF-001; these historical
byte reductions do not measure current Claude tokens/costs. Evidence is in punchlist 7.4
and the dated handoff; live workflow/owner observation remain pending. WF-003 extends this
process without duplicating the prior spec. WF-001 setup merged in PR #57.

| Existing work | Canonical record; not newly ordered implementation |
|---|---|
| Safety/publication | Punchlist 5.1–5.4, 6.1, 8.1; PR #57. |
| Session/input/duplicate outputs | 5.5–5.8 OPEN; 5.9 separate cleanup. |
| Subtitle prototype repairs | 6.2–6.6 OPEN; validate before porting. |
| Main-script subtitles | [Plan](docs/SUBTITLES_PLAN.md): ten unanswered owner decisions; separate live-refinement gate. |
| Actual planning/live workflow trial | 7.2–7.3 OPEN; no agreed Sprint/PI or stakeholder feedback. |

**Impediment:** Claude subscription execution refused again on 17 Oct by organization policy.
Ponytail instructions read/applied manually; no account/model changes or successful live run.

**Improvement experiment:** next owner-selected behavior story traces an example through
actual Red/Green, permitted peer review and integrated acceptance. Lead records actual usage,
repeated context and quality/flow; agree review date at actual planning.

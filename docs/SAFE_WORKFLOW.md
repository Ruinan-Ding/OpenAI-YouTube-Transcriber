# SAFe coordination

This is this project's SAFe adaptation. [SCRUM_WORKFLOW.md](../SCRUM_WORKFLOW.md) owns team
SDD/BDD/TDD, review and Done; [AGENTS.md](../AGENTS.md) owns constraints/decisions. SAFe adds
alignment across features, capacity, dependencies and integrated outcomes. The current repo
has one cross-functional team, not an operating Agile Release Train (ART). Ten profiles are
ten capabilities, not ten teams. Activate actual train coordination when multiple delivery
teams exist; no staffing, certification, meetings or performance is implied by configuration.

## Routing

- One bounded story: follow `/scrum` and its existing compact spec; no PI packet or extra
  agent call. Link its feature/objective if one exists rather than manufacture a parent.
- A multi-story feature/enabler, shared dependency/risk or explicit SAFe planning request:
  read the relevant sections here and update the coordination record in the backlog.
- Multiple real teams: use one shared feature/dependency plan plus each team's linked stories.
  Parallelize within runtime limits and file ownership; the single script stays one script.
- Multiple products/value streams or ARTs: propose the needed portfolio/solution coordination
  to the owner, adding only actual epic/funding/supplier decisions. Do not generate a pretend
  portfolio, budget, Solution Train or additional agent hierarchy in this single-product repo.

## Roles

| Accountability | Coverage in this project |
|---|---|
| Business Owner, Product Management authority, Product Owner | Human owner retains priorities, product policy, business value and acceptance. |
| Product Management support | Product analyst turns intent into benefit/acceptance, feature ordering proposals and child-story links; it cannot accept its own product proposals. |
| Release Train Engineer (RTE); team Scrum Master/Coach | Scrum-master capability/lead facilitates coordination, planning, dependencies, risks and improvement. No management or approval queue. |
| System Architect | Architect aligns interfaces, NFRs and necessary architectural runway with existing one-script/settings/file-lifecycle rules. |
| Agile Teams; System Team/DevOps support | Existing engineering capabilities deliver vertical slices; release/quality support integrated environments, pipeline evidence and demos. They remain shared contributors. |

Use these accountabilities through existing profiles, not new always-on agents. One person/
agent may cover several capabilities where appropriate; self-review remains distinct from
independent review. Shared outcome ownership and the existing senior standard still apply.

## Work hierarchy and economics

Trace `owner goal -> feature/enabler -> story/spec -> AC IDs -> TDD tasks -> evidence`.
A feature describes an outcome, benefit and observable acceptance, and is split to fit a PI
once PIs are activated; stories fit iterations. Enablers address demonstrated technical
constraints or runway, not speculative rewrites. Cross-cutting NFRs link existing invariants
and checks instead of copying another settings/security/compatibility specification.

The owner orders work. When competing features warrant economic comparison, support Weighted
Shortest Job First: `(user/business value + time criticality + risk reduction/opportunity)
/ job size`. Record input sources/uncertainty and a positive size; missing inputs stay unknown.
Do not invent owner values, estimates, budgets or velocity. Discuss dependencies/capacity
alongside the score; WSJF is a proposal for sequencing, not authority to start new scope.

## Minimal coordination record

Keep this in SCRUM_BACKLOG.md only when needed; link specs without repeating them:

```text
Goal/vision; feature/enabler ID -> benefit + acceptance + child spec links
PI/iteration dates and capacity basis, or explicitly unscheduled
Objective -> feature IDs -> measure -> proposed/committed/uncommitted -> actual evidence
Dependency: consumer <- producer -> deliverable/check -> owner -> needed by/status
Risk: impact -> ROAM state -> owner/action -> next review/evidence
Decisions/change impact; integrated demo/release evidence; improvement owner/measure/review
```

Only populate actual information. Dates, capacity and commitments are not inferred from a
chat, model context window or profile count. Unknown owner choices remain questions in the
linked spec. Unscheduled authorized work continues independently of setting a PI calendar.

## Planning and flow

When activating PIs, agree dates, iteration cadence and innovation/planning capacity with the
owner. Typical SAFe PIs span 8–12 weeks; this is reference context, not this repo's schedule.
Use PI Planning to align owner vision, prioritized features, architecture/NFR constraints,
real capacity and dependencies. Developers plan the work and verification together. Capture
objectives, dependency owners, risks, confidence and actual tradeoffs in the compact record;
if confidence is insufficient, adjust scope/capacity before describing the plan as committed.

Mark objectives proposed until planning participants have actually agreed them. Distinguish
committed from uncommitted outcomes; uncertainty remains visible and uncommitted work still
consumes capacity. Business value comes from the human owner. Do not invent a planning event,
confidence vote, objective acceptance or commitment when participants/access are absent.

Flow is `proposed -> analyzed -> ready -> implementing -> validating -> done`, with blockers
shown on the actual item rather than a duplicate queue. Reuse story status/Done evidence.
Limit active implementation to one slice per writer; reserve verification and improvement
capacity and finish work before expanding WIP. Material dependency changes update producer,
consumer, objective forecast and affected AC checks, then adapt the plan within owner intent.

Use ROAM for actual risks: **Resolved** has resolution evidence; **Owned** has an accountable
owner/next action; **Accepted** records who accepted the exposure and why; **Mitigated** links
the action/check reducing it. Classification alone never fixes a risk. No category overrides
repo invariants, product-decision gates, required checks or publication authorization.

## Cadence, demonstration and improvement

| Event | Record outcomes, not simulated conversations |
|---|---|
| PI Planning | Actual scope/capacity agreements, objectives, dependencies, risks and confidence; use the planning guidance above. |
| ART Sync / PO Sync / Coach Sync | At the agreed cadence inspect objective/dependency/impediment deltas. Combine coordination where the same people cover roles; no fabricated separate meetings. |
| Iteration System Demo | Demonstrate the integrated result against feature/objective acceptance in a representative environment, capture actual stakeholder feedback and update forecasts. Individual green branches/status slides are insufficient. |
| Inspect & Adapt, PI end | Inspect integrated outcomes and quality/flow measures, identify causes of the largest problem, and select one improvement with owner, measure and next review. |
| Innovation and Planning capacity | Protect exploration, improvement and next-PI preparation; do not defer ordinary testing/integration into this space. |

Team Scrum events remain in the base workflow. With one team, the same actual review may
cover team and integrated outcomes when both occurred; don't report two invented events.
A missing system demo/owner observation stays pending. Native-loader checks and instruction
walkthroughs are appropriate workflow-config evidence, not a live agent demonstration.

## Built-in quality and delivery

Continuous exploration uses the existing informal-intent -> spec -> BDD path. Continuous
integration uses genuine TDD, peer review when available and combined-source checks, including
actual Windows/media requirements. Release engineering prepares appropriate CLI/package
artifacts and installation checks when affected; don't introduce hosting/deployment tooling
for a desktop CLI merely to fill a diagram. Release on demand follows existing PR/CI and
owner authorization, independently of PI boundaries. Planning approval grants no new external
side effects, and integration cannot bypass the subtitle owner's unanswered decisions.

## Token discipline and feedback

Only the coordinator loads relevant SAFe sections; workers receive their spec/AC IDs,
owned paths and dependency deltas under the existing task packet. Keep one feature/objective/
risk record, link team evidence and avoid cloned ART/team/spec status reports. Use concise
actual decisions rather than ceremony transcripts; don't spin up RTE/PM/System Team workers
without a distinct deliverable. Reuse source-bound evidence only while it remains valid.

Inspect objective outcomes, blocked/dependency age, WIP, lead time, defects and actual usage
where measured. No invented business-value predictability, savings or agent rankings.
Prompt-size comparisons are proxies; quality checks and owner observations remain separate.

## Sources

This is a local adaptation; reference cadences are not automatic commitments. Official SAFe:
[ARTs](https://framework.scaledagile.com/agile-release-train/),
[features](https://framework.scaledagile.com/features-and-capabilities/),
[WSJF](https://framework.scaledagile.com/wsjf/?frame=0),
[PI Planning](https://framework.scaledagile.com/pi-planning/),
[PI objectives](https://framework.scaledagile.com/blog/glossary_term/pi-objectives),
[team/ART practices](https://framework.scaledagile.com/team-and-technical-agility-discipline),
[System Demo](https://framework.scaledagile.com/system-demo/),
[Inspect & Adapt](https://framework.scaledagile.com/inspect-and-adapt/),
[ROAM example](https://framework.scaledagile.com/wp-content/uploads/delightful-downloads/2017/09/LEGO_update.pdf),
[release on demand](https://framework.scaledagile.com/blog/glossary_term/release-on-demand).

---
name: scrum
description: Deliver OpenAI YouTube Transcriber features, fixes and reviews with the project's senior cross-functional Scrum team, BDD acceptance examples and TDD. Use for development work or explicit planning, refinement, review and retrospective requests in this repository; not for ordinary app usage or general Scrum questions.
argument-hint: "<task>"
---

# Scrum delivery

Read [AGENTS.md](../../../AGENTS.md), [SCRUM_WORKFLOW.md](../../../SCRUM_WORKFLOW.md)
and the current [backlog](../../../SCRUM_BACKLOG.md). They define the repo constraints,
delivery process and current goals. The request is `$ARGUMENTS`; if empty, use the active
request/handoff rather than inventing a story. Invoke Ponytail for code work as required.

The main conversation orchestrates. An assigned worker applies its role/task packet and
returns to the lead; it does not create another team or select unrelated backlog work.

1. Inspect the branch, dirty source, handoff and actual affected callers before selecting a
   bounded story. Preserve existing work, owner priorities and authorization. State scope,
   relevant owner decisions and open questions; incorporate steering into the active story.
2. Refine observable Given/When/Then examples from product, development and quality
   perspectives. Map acceptance examples to meaningful checks before implementation.
   Ask only about missing product decisions; continue independent work while waiting.
3. Use the relevant `.claude/agents/` profiles within runtime policy/capacity. Native
   interactive teammates suit direct collaboration, focused subagents suit investigation
   and review, and overlapping/dependent edits run sequentially. Assign one writer per file:
   especially the single app script, shared tests and metadata. Do not launch every role
   merely to fill the roster or claim independent review when working alone.
4. Follow evidenced Red → Green → Refactor for behavior changes. Pair on BDD/TDD early,
   use existing plain-assert tests and real media checks, preserve settings-sync and the
   subtitle decision gate, then integrate and obtain qualified independent review when
   available. Give reviewers the readable story delta/new files and current-source results.
   Docs/config changes use structural checks; an environment failure is not behavioral Red.
5. Complete the applicable Definition of Done checks, including actual Windows checks for
   paths/subprocesses, or state remaining work. Investigate failures/flakiness rather than
   retrying to a lucky green. Update backlog/handoff/punchlist with actual evidence and
   propose one measurable improvement; only the owner marks SEEN. Preserve existing
   authorization and the PR workflow without adding ceremonial approval gates.

All capabilities share responsibility for the Increment and work to the workflow's senior
engineering standard. SDD means specification-driven development and remains a future
option: do not install a framework or create a second source of product/setting rules now.

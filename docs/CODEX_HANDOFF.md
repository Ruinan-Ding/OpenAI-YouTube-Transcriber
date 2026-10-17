# Claude and Codex handoff

> **Status: workflow refreshed 17 Oct 2026; application review baseline remains `8d0b2d1`.** This
> extends the 3 Oct review/safety snapshot (which replaced 2 Oct's `c79e56a` snapshot).
> The combined safety/workflow delivery was rechecked on 15 Oct below. Git history and the
> GitHub pull request record publication/CI state; the punchlist records owner acceptance.

## Read first

1. [AGENTS.md](../AGENTS.md): the source of agent guidance, architecture invariants and
   owner decisions. Its Claude workflow uses the actual ponytail plugin; this handoff does
   not substitute a checklist for it.
2. [SCRUM_WORKFLOW.md](../SCRUM_WORKFLOW.md) and [backlog](../SCRUM_BACKLOG.md): Claude's
   SDD/BDD/TDD team and current story; start with `/scrum <task>` or an informal development
   request. Read the active spec and relevant workflow sections, not every historical entry.
3. [PUNCHLIST.md](../PUNCHLIST.md): current work and evidence, with OPEN, WRITTEN and SEEN
   defined there.
4. [Subtitle plan](SUBTITLES_PLAN.md): the proposed integration and its ten unanswered
   decisions. The eight proposed settings are not in the application yet.
5. [Development setup](../DEV.md), then [CHANGELOG.md](../CHANGELOG.md), `[Unreleased]`.

`CLAUDE.md` points to `AGENTS.md`. For any setting change, read
[settings-sync](../.claude/skills/settings-sync/SKILL.md). Use the required Claude plugin
workflow from `AGENTS.md`, plus correctness review of data preservation and failure handling:
ponytail's review and audit cover overengineering, not general correctness.

## Verified starting state

At the review baseline, the checkout was clean at `8d0b2d1`; local `main`,
`feature/subtitles` and cached origin references pointed there. Cached references are not a
fresh check of GitHub. Windows Python checks passed: **147 tests passed, 2 symlink tests
skipped**, with flake8, isort and mypy clean. These are automated baseline checks, not owner
acceptance or evidence that the newly found defects are fixed. Mypy checks both the app and
`subtitle_prototype.py`; CI details and commands are in `DEV.md`.

The owner works in `C:\Users\DRuin\OneDrive\Documents\OpenAI-YouTube-Transcriber`.
The existing application Python is
`C:\Users\DRuin\AppData\Local\Programs\Python\Python312\python.exe`, with the runtime
and checking tools installed. Ffmpeg and ffprobe are on PATH through Scoop. Follow `DEV.md`
for an isolated development environment; do not install pre-commit into that existing Python.

Earlier fixes and the prototype were merged directly; those are historical exceptions to the
owner's PR decision. If `gh` is unauthenticated, create the PR through GitHub in the browser.
Commit and push only when requested; fix forward without rewriting pushed history.
Leave the local `fix/yt-dlp-migration` stash and locally excluded `test.txt` alone.
Do not print configuration contents or API keys.

## Delivery checks (15 Oct 2026)

The owner requested commit, push and merge of the pending safety/workflow changes. The
delivery was prepared on `fix/pre-subtitle-media-safety` from `8d0b2d1`, with these fresh
Windows Python 3.12 results: **159 passed, 3 symlink skips**, clean flake8/isort/mypy and
the main tests passing as a plain script. Workflow YAML/JSON/link checks also pass. The
fresh real application/profile smoke produced ten valid outputs from two local sources,
preserving both originals and audio-free video-only files. The 3 Oct reproduction evidence
below retains its original date.

Publication follows the PR policy: check the GitHub PR/commit history for the actual CI and
merge result, rather than treating this preparation snapshot as proof of publication.
Owner-SEEN, live Claude team execution and live AI polish remain separate observations.

The [first PR CI run](https://github.com/Ruinan-Ding/OpenAI-YouTube-Transcriber/actions/runs/38832961848)
passed Linux but failed Windows while deleting the metadata test's file-URL input, after
its download assertions passed. Disabling cyclic collection reproduced WinError 32 locally;
collecting unreachable yt-dlp response cycles released the file. Download fixtures now
exercise delayed collection and collect those cycles before strict temporary cleanup,
restoring the caller's original collection mode. The cache-retry test points at an
unavailable URL instead of deleting an input that the response may still hold open.
This publication follow-up changes test lifetime management, not application behavior.

## Token-efficient SDD update (17 Oct 2026)

The owner adopted SDD now and requested automatic translation of informal requirements.
[The workflow](../SCRUM_WORKFLOW.md#sdd-intake) owns
the intake: one compact spec, stable BDD examples and writer-owned TDD tasks, with unanswered
product choices kept explicit. WF-002 in the backlog is this change's spec and evidence.
Ten senior capabilities remain available; relevant sections/roles load on demand, the lead
can cover several responsibilities, and no translator/full-team call is automatic.

Started from clean merged `main` at `979e1c9` on `chore/token-efficient-sdd-workflow`.
Application/prototype/test/settings/CI files match the starting source. Windows structural
checks and native agent/skill discovery pass; WF-002 records prompt-size reductions and
intake self-review. These do not prove live Claude execution, independent review or actual
billed token savings; unchanged app suites were not rerun.
The 17 Oct Ponytail invocation was refused by the same organization subscription policy;
installed instructions were read/applied manually without changing credentials or providers.
The subtitle owner-decision gate and pending prototype repairs still apply.
The owner subsequently requested commit, push and merge; publication follows the PR/CI
policy, with its actual outcome recorded in GitHub rather than inferred from local checks.

## Original Claude Scrum setup (15 Oct 2026)

Adapted the sibling ChessPlusPlus workflow to this CLI: ten reusable specialist profiles,
the `/scrum` skill, experimental native in-process teams and a persistent backlog. The
human remains Product Owner; BDD/TDD, senior engineering expectations and shared delivery
are defined in the workflow. Its original optional-later SDD scope was superseded on 17 Oct.
Preserve one writer per
file, especially the application script and shared tests; capabilities are not ten workers
that must all run on every task. No Sprint dates/goals or product priorities were invented.

Windows YAML/JSON/link/structural checks pass; Claude Code 2.1.300's local agent-loader
diagnostic lists all ten project profiles and its skill loader reports both project skills
loaded. `/skills` is unavailable in headless mode; no interactive discovery/trial is claimed.
Source hashes preserve the earlier dirty
application, prototype, tests, profiles, package/dependency and CI files. The current
workflow delta changes neither app behavior nor the subtitle integration gate. Detailed
evidence: Windows Temp `oyt-scrum-20261015-iv4_3px4/STRUCTURAL.txt`; punchlist 7 records
the durable outcome. Application suites were not rerun during workflow setup; the combined
delivery's fresh application checks are recorded above.

The actual `/ponytail full` invocation was refused: the organization currently disables
Claude subscription access for Claude Code. Installed plugin instructions were read and
applied manually, without changing account policies/credentials. No live model/team trial,
independent agent review or successful plugin execution is claimed. Use the next
owner-selected bounded behavior story for the real workflow trial when access permits.
Agent discovery and instruction walkthroughs do not demonstrate team performance.

## Work before subtitle integration

The owner approved the pre-subtitle safety work on 3 Oct 2026:

- Record the review and decisions, and correct this handoff and development instructions.
- Protect download destinations and conversion scratch paths: punchlist 5.1 and 6.1.
- Preserve sources until every requested replacement lands, guard in-place replacement
  failures, and finalize complete standalone files after a later download fails: 5.2–5.4.
- Keep unfinished retry audio and report the source as incomplete; continue the batch.

The configuration and absent `KEEP_TRANSCRIPT` questions (formerly 5.10 and 5.11) are
settled in `AGENTS.md`. Session consistency bugs 5.5–5.8 and tidy-ups 5.9 remain on the
punchlist for later work. Track progress there and record the actual Windows checks and real
runs; the baseline above must not be reused as validation of a new change.

The safety implementation was prepared on `fix/pre-subtitle-media-safety`; 5.1–5.4 and
6.1 are WRITTEN. See the punchlist's original safety validation for the 3 Oct checks: Windows
**159 passed, 3 symlink skips**, clean lint/type checks, plain-script tests and a real
application/profile smoke. A targeted Linux check exercised file-symlink reservations;
the full Linux suite is checked by PR CI. No item was promoted to SEEN.

The correctness review also reproduced yt-dlp consuming a queued `.part` source even
after its final name was claimed. All shared-folder downloads now stage privately, then
publish a claimed complete file; complete ID-named audio caches are reused before staging.

On 3 Oct, Claude's `/ponytail full` invocation was blocked by its weekly usage limit.
The installed plugin instructions were read and applied manually, with separate agent
reviews for overengineering and correctness. Run the actual plugin review when Claude is
available; do not describe that session as a completed Claude plugin run.

## Subtitle state and next gate

`subtitle_prototype.py` remains standalone. It times cues from Whisper or YouTube captions,
optionally polishes wording, writes SRT, and produces soft or hard copies. The earlier real
runs covered "Me at the zoo" and the 108-second Spanish fable "La liebre y la tortuga";
outputs are in the gitignored `OpenAIYouTubeTranscriber/Video/Subtitled/` folder.

Polish has **never run against a live model**. Its `_one_request` temporarily overrides the
app's private chunking function; integration needs the planned single-request backend mode.
Long-video quality and owner viewing remain unverified.

The additional review is now punchlist 6.2–6.6: same-input/output mux cleanup can delete the
input; linger exceeds the cue duration limit; equal-start cues overlap; mixed-width splitting
exceeds the line width; and the prototype reports process success despite mux or burn
failure. Their reproduction evidence is recorded in the punchlist. Repair and validate the
prototype before porting its helpers.

Resolve the ten subtitle decisions in `docs/SUBTITLES_PLAN.md` before integration. Also settle
H.264 download preference, translation model selection and fallback, and existing subtitle
track defaults. The plan proposes the first refined track as default, while the prototype
preserves an existing track's default. These need one owner-approved policy.

Punchlist 3.12 is a translation quality decision, not a capability restriction: multilingual
`tiny`, `base` and `small` translate; Whisper recommends `medium` or `large` for quality,
while turbo is not trained for translation. The app can fall back to `base` after a requested
model fails to load, so a model policy must account for the actual loaded model.

After the safety work and those decisions, follow the subtitle plan's staged integration:
port core and tests, add the six non-AI fields, then add the two refinement fields after
live-model validation. Do not treat the prototype's passing tests as permission to skip
these gates.

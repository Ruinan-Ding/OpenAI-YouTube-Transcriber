# Punchlist

What is in flight, written back in plain terms so the owner can correct it.

Status means one thing only:

| Status | Meaning |
|---|---|
| **SEEN** | The owner has watched it work in a real run. |
| **WRITTEN** | Code is in and its tests pass. **Nobody has seen it work in a real run.** |
| **OPEN** | Not built, not decided, or not understood. |

A passing test is not a working feature. Nothing moves to **SEEN** except by the owner saying
so. When an item lands on `main` and the owner has seen it, it leaves this list for
`CHANGELOG.md`.

Last updated 17 Oct 2026.

---

## 1. Windows paths (merged into `main` 2 Oct 2026)

Merged without a pull request. CI has passed on Linux and Windows since.

| # | Item | Status |
|---|---|---|
| 1.1 | A double-quoted Windows path in a profile or `config.txt` keeps its backslashes (`"C:\Users\me\new"`, `"\\server\share"`, `"D:\"`). | WRITTEN |
| 1.2 | `~/clip.mp3` expands in Windows' own separators. | WRITTEN |
| 1.3 | Captions read as prose keep a word said twice across two cues ("He had" / "had enough"). | WRITTEN |
| 1.4 | CI runs the tests on Windows as well as Linux. Green on every push since the merge. | WRITTEN |

## 2. Media fixes on `main` (`f3bc322`, `729070b`)

| # | Item | Status |
|---|---|---|
| 2.1 | A "Video Only" download whose audio cannot be removed is deleted and the failure reported, instead of kept with its audio. | WRITTEN |
| 2.2 | YouTube's rolling captions, read as prose, keep each cue's restated text once. | WRITTEN |

## 3. Subtitles (merged into `main` 2 Oct 2026, as a prototype)

A standalone prototype, `subtitle_prototype.py`. The owner specified the settings on 2 Oct
2026; the plan, `docs/SUBTITLES_PLAN.md`, ends with the decisions still open, and nothing goes
into the main script until they are answered. "Me at the zoo" with subtitles, three ways, and
"La liebre y la tortuga" with English and Spanish tracks are in
`OpenAIYouTubeTranscriber/Video/Subtitled/` for the owner to watch.

| # | Item | Status |
|---|---|---|
| 3.1 | Timed from a video's own written captions, cue timing kept as the uploader set it. Run on "Me at the zoo". | WRITTEN |
| 3.2 | Timed from Whisper's word timestamps, with the silences Whisper stretches words over taken back out. Run on "Me at the zoo". | WRITTEN |
| 3.3 | Timed from YouTube's own recognition (json3, a time per word). Checked on a real 3.5-minute track; not run through the whole prototype on such a video. | WRITTEN |
| 3.4 | Whisper's English translation, timed by segment. Run on a 108-second Spanish fable: `small` called the hare "the lion" throughout; `medium` translated it well, cues within about 0.3 s of the speech, 2 min 40 s on the CPU. | WRITTEN |
| 3.5 | **Polish**: each cue's wording corrected by the AI backend, its timing kept. **Never run against a real model** (no API key on the development machine); tested with a stand-in. | WRITTEN |
| 3.6 | Soft subtitles: a track the player can turn off (MP4, MKV, WebM). | WRITTEN |
| 3.7 | Hard subtitles: burned into the picture, a separate file. | WRITTEN |
| 3.8 | Prefer H.264 over AV1 when the video is downloaded to be subtitled, so Windows plays it without an extension. | OPEN |
| 3.9 | Into the main script, in three phases (plan). Waits on the decisions (3.10). | OPEN |
| 3.10 | Specified by the owner on 2 Oct 2026: `VIDEO_SUB`, `VIDEO_SUB_WHISPER`, `VIDEO_SUB_AI_REFINEMENT`, `VIDEO_SOFT_HARD_SUB` and the same for `VIDEO_ONLY_`. Its decisions are still open, at the end of the plan. | OPEN |
| 3.11 | A full cue ends at its last sentence end, or its last clause end a third in, not mid-phrase ("...la liebre y la" / "tortuga." is gone), and "Mr." no longer ends a cue. Rerun on the Spanish fable, both languages. | WRITTEN |
| 3.12 | Decide the translation model and fallback policy. Multilingual `tiny`, `base` and `small` support translation; `medium` or `large` are recommended for quality, and `large-v3-turbo` is not trained to translate. The Spanish trial favoured `medium`; it does not establish a required minimum. See [Whisper's model guidance](https://github.com/openai/whisper#command-line-usage). | OPEN |
| 3.13 | Review fixes in the prototype: refinement in one request per batch and failures counted, soft mux keeps the file's own tracks, cues within limits after a cut, no negative times, hard copy 8-bit with playable audio, overlapping YouTube events clamped, CJK width, every Whisper language tagged. Rerun on the Spanish video (soft and hard); refinement never run against a real model. | WRITTEN |

## 4. Agent workflow (merged into `main` 2 Oct 2026)

| # | Item | Status |
|---|---|---|
| 4.1 | `AGENTS.md` (single source of guidance), `CLAUDE.md` pointer, `ponytail` declared for the repo, the `settings-sync` skill, this punchlist. | WRITTEN |

## 5. Whole-codebase review (2 Oct 2026; safety fixes written 3 Oct)

Found by a review of the whole codebase; ✓ was reproduced by running the code, the rest
from reading it. Each fix needs a test that fails on the code as it is.

| # | Item | Status |
|---|---|---|
| 5.1 | Downloads stage privately, including yt-dlp's `.part` and fragment files, then claim the complete file before publishing it. A queued local source survives both final-name and sidecar collisions; file symlinks share their target's reservation. Merges use that allocator instead of a separate `samefile` check. Complete ID-named retry audio is still reused. | WRITTEN |
| 5.2 | `_convert_all` keeps the original until every requested format lands. A same-container result is published over the download only after the other formats succeed; partial successes keep their files and the untouched download for a retry. | WRITTEN |
| 5.3 | In-place replacement catches a Windows file lock, reports the failure and removes only its scratch file. The original survives and the next batch source runs. A locked deferred replacement keeps the completed conversions too. | WRITTEN |
| 5.4 | A later download failure finalizes complete standalone downloads once, reports the source as incomplete and keeps retry audio. The next source still runs; merge-only video scratch is cleaned up. | WRITTEN |
| 5.5 | Source, prompt and transcript pickers accept Explorer-quoted paths, preserving spaces, commas and Windows separators. Saved source/prompt lists retain filename commas on reload and transcript relocation. | WRITTEN |
| 5.6 | "Run again?" retains settings answered across a mixed round when its final pass is a transcript or local file. Questions a round never asked stay unset; per-video names are still cleared. | WRITTEN |
| 5.7 | Interactive repeats retain file/inline prompts and the selected local/cloud backend. File prompts reload; inline text and entered keys stay in session memory without leaking into the environment. | WRITTEN |
| 5.8 | Audio aliases selecting one stream merge once per video/container. Different stream IDs remain distinct even when their displayed bitrates round to the same number. | WRITTEN |
| 5.9 | Tidy-ups: dependency errors go to stdout, not `error()`; `load_opening` runs ffmpeg without `FFMPEG_RUN` and no comment says why; `_same_file` repeats `_path_identity`; `audio_stream_for` rebuilds its selector on every call. | OPEN |
| 5.12 | Failed local conversions report the source as incomplete instead of “Tasks complete.” Originals survive and later sources still produce their exports. | WRITTEN |

Decisions 5.10 and 5.11 were settled on 3 Oct 2026: configuration stays tracked and an absent
`KEEP_TRANSCRIPT` still asks. The record is in `AGENTS.md`, *Decisions*.

Safety validation on 3 Oct 2026: Windows Python 3.12, **159 passed, 3 symlink skips** across
both test files; the main test file also passed as a plain script. Flake8, isort and mypy
were clean. Seven defect regressions failed against the original `8d0b2d1` code; the
sidecar regression also reproduced deletion before private staging. A separate Linux check
ran the actual allocation functions with real file symlinks; the full Linux suite awaits CI.
A real Windows application/profile smoke produced ten valid media outputs from two local
sources, kept both originals and produced audio-free video-only copies. Network failure
checks use disk-served streams and real yt-dlp/ffmpeg. These are agent checks, not owner
acceptance; nothing is SEEN.

The combined safety/workflow delivery was rechecked on 15 Oct before publication: Windows
**159 passed, 3 symlink skips**, clean flake8/isort/mypy and the main tests passing as a
plain script. A fresh Windows application/profile smoke again produced ten valid outputs
and preserved its two local sources. GitHub's PR/commit history records the actual CI and
merge result. These checks do not change owner-SEEN or validate deferred subtitle work.

Application consistency repair on 17 Oct 2026: the owner authorized 5.5–5.8 and the newly
reproduced local completion defect, 5.12. Six new regressions failed on unchanged `8a3c263`;
two further failures exposed comma-carrying lists losing their meaning on save/repeat.
The repaired source passes Windows **166 tests, 3 symlink skips**, the main plain runner,
and flake8/isort/mypy. Real Windows CLI/profile/repeat checks preserve both original media
files, report the locked destination's source as incomplete and produce later outputs.
APP-001 in the backlog owns current checks and remaining review evidence.
Prepared on `fix/session-input-and-completion`; the owner subsequently requested commit/push.
Git records delivery; owner-SEEN remains pending. Subtitle repairs and decisions remain open.

## 6. Additional review (3 Oct 2026)

Evidence below was gathered before the safety changes. Reproduced means a targeted check,
not an owner viewing or an end-to-end application run. Subtitle findings stay open until the
prototype is repaired and checked separately from integration.

| # | Item | Evidence | Status |
|---|---|---|---|
| 6.1 | Stripping audio and converting in place use unique scratch files. Existing `.silent` and `.converting` filenames survive, and each operation cleans up only its own temporary file. | Before the fix, real ffmpeg on Windows removed an existing reserved file; regression tests now preserve it. | WRITTEN |
| 6.2 | **Can lose a file.** The prototype's soft-mux helper given the same input and output path removes the input during failure cleanup. Replacing a subtitled video needs a separate scratch output and a guarded swap. | Reproduced at helper level with real ffmpeg. | OPEN |
| 6.3 | `settle()` adds linger after enforcing the seven-second limit, so a seven-second generated cue lasts 7.5 seconds. | Reproduced with a generated cue. | OPEN |
| 6.4 | Cues with identical start times still overlap: `settle()`'s minimum positive duration overrides the next-cue limit. | Reproduced with two cues starting at 1.0 seconds. | OPEN |
| 6.5 | Mixed-width unspaced text accepted by `fits()` can exceed 42 columns after `split_lines()`. | Reproduced with 84 columns of ASCII and a Chinese character; the two lines were 43 and 41 columns. | OPEN |
| 6.6 | The prototype's `main()` returns 0 when requested soft muxing or burning fails, so callers see success for missing deliverables. | Inspection of the return handling; not exercised through the CLI. | OPEN |

## 7. Claude SAFe / Scrum workflow (15–17 Oct 2026)

The owner asked to adapt ChessPlusPlus's full cross-functional workflow, with every
capability held to a senior standard. On 17 Oct the owner added active SDD, automatic
informal-requirement translation and token efficiency alongside TDD/BDD, then SAFe
coordination using the same capabilities. Process and current goals live in
[SCRUM_WORKFLOW.md](SCRUM_WORKFLOW.md) and
[SCRUM_BACKLOG.md](SCRUM_BACKLOG.md); existing app/subtitle decisions remain in force.

| # | Item | Evidence | Status |
|---|---|---|---|
| 7.1 | Original ten-profile Scrum setup, `/scrum`, native in-process teams, backlog/events, BDD/TDD, ownership/review and Done criteria; 7.4 extends it with SDD. Model/permission policy and Ponytail configuration are preserved. | Windows YAML/JSON/local-link/structural checks pass. Claude Code 2.1.300's local agent-loader diagnostic lists all ten profiles, and its skill loader reports both project skills loaded. Existing application/prototype/tests/profiles/dependencies/CI match the dirty baseline byte-for-byte. | WRITTEN |
| 7.2 | Exercise an owner-selected bounded behavior story through actual BDD/TDD, peer collaboration/review and integrated acceptance. Evaluate the senior standard from results, not profile labels. | No live-team/model trial or independent review ran. Claude Code subscription access is disabled by the current organization policy; the ponytail invocation was refused. | OPEN |
| 7.3 | Agree actual Product/Sprint/PI goals, dates and capacity when planning is activated, then inspect stakeholder feedback and one measurable improvement. | No Sprint, PI or event is invented; workflow setup can proceed as an unscheduled story. | OPEN |
| 7.4 | Token-efficient SDD intake translates informal intent to one spec, BDD examples and TDD tasks; keeps ten capabilities, selective context, focused delegation and owner-decision gates. | Windows YAML/JSON/links and native discovery pass; WF-002 records unchanged source hashes, smaller instructions and intake self-review. Live Claude execution/usage trial remains blocked by organization policy; no owner-SEEN or independent review claimed. | WRITTEN |
| 7.5 | SAFe coordination adds feature/PI outcomes, dependencies, ROAM risks, integrated demos and improvement through existing profiles and an on-demand reference; preserves compact story delivery. | Windows structure/links/source checks and native discovery pass. WF-003 records smaller common guidance and scenario self-review. Live workflow remains blocked by organization policy; no actual ART, PI commitments, independent review or owner-SEEN claimed. | WRITTEN |
| 7.6 | Add focused Claude plugins, per-runtime dependencies and bounded/plugin-review routing while preserving the dirty SAFe work. | Five project installs verified on Windows/WSL; six real hook/LSP checks per OS and Windows link/settings/source checks pass. PR toolkit is on demand. WF-004 records actual limits; no live model review, independent review or owner-SEEN claimed. | WRITTEN |

Verification is scoped to workflow configuration, not the 3 Oct safety implementation.
Instruction walkthroughs are self-review, not model-behavior tests. Workflow setup did not
rerun application suites or make live AI calls; the later delivery checks are recorded
above. GitHub records publication; owner-SEEN acceptance is still absent. Detailed
structural evidence is in Windows Temp `oyt-scrum-20261015-iv4_3px4/STRUCTURAL.txt`;
the tracked backlog/handoff retain the outcomes without depending on private logs alone.

## 8. Publication check (15 Oct 2026)

| # | Item | Evidence | Status |
|---|---|---|---|
| 8.1 | Release yt-dlp file-URL response cycles before strict test-directory cleanup. Exercise delayed collection and restore its original mode; retain all download assertions. | PR #57's first CI run passed Linux but Windows could not delete the fixture's input. Reproduced locally with cyclic collection disabled; the fix passes that case, six focused real-download tests, the full Windows suite (159 passed, 3 symlink skips), the plain runner and lint/type checks. Later PR CI records the integrated result. | WRITTEN |

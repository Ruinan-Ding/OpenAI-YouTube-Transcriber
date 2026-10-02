> **Handoff prompt for Codex, written 2 Oct 2026 (at c79e56a).** Paste it into Codex as it is.
> It is a snapshot: `AGENTS.md` and `PUNCHLIST.md` are kept current, and win where they differ.

You're picking up work on OpenAI-YouTube-Transcriber (github.com/Ruinan-Ding/OpenAI-YouTube-Transcriber) from a Claude Code session. Everything below was committed and pushed as of c79e56a on `main`, with CI (Linux and Windows) green on it.

## Read first, in this order

1. `AGENTS.md`: the single source of guidance for agents here. It covers how to work, the commands, the nine architecture invariants, the owner's decisions and the known quirks. It is binding.
2. `PUNCHLIST.md`: what is in flight, each item OPEN, WRITTEN or SEEN.
3. `docs/SUBTITLES_PLAN.md`: the subtitle feature. It holds the owner's specification and the plan, and ends with 10 open decisions.
4. `CHANGELOG.md`, the [Unreleased] section.

`CLAUDE.md` only points to `AGENTS.md`. `.claude/` holds Claude Code settings. One file there matters to you: `.claude/skills/settings-sync/SKILL.md` is a plain checklist for adding, renaming or removing a profile field. Follow it whenever you touch a setting.

`AGENTS.md` says to run the `ponytail` plugin. That's a Claude Code plugin you don't have, so apply what it stands for instead:
- make the smallest change that works;
- reuse what the script already has;
- use the standard library before writing new code;
- add no dependencies or abstractions nobody asked for;
- fix a bug at its root, in the shared function every caller goes through;
- leave one test that fails if the logic breaks.

## Ground rules

These come from `AGENTS.md`; they are the ones most often broken.

- **The owner decides what the app does**: a file name, a default, what a blank field means, whether something is deleted. If the Decisions section of `AGENTS.md` doesn't settle it, ask. Don't pick a "reasonable default".
- **Record each decision** in the Decisions section of `AGENTS.md` the turn it's made.
- **Only the owner moves a punchlist item to SEEN.** Say what you ran and what you didn't.
- **The owner is on Windows.** CI runs on Linux and Windows. Test anything involving paths, quotes, file names or subprocesses on Windows.
- **Don't build subtitles into `OpenAIYouTubeTranscriber.py`** until the owner has answered the 10 decisions in `docs/SUBTITLES_PLAN.md`.
- **Never print API keys.** `OpenAIYouTubeTranscriber/Profile/config.txt` can hold them.
- **Don't rewrite pushed history** (no amend plus force-push). Fix forward with a new commit.
- **Commit or push only when the owner asks.**

## Commands

- **Lint, as CI does:** `flake8`, then `isort --check-only .`, then `mypy`. mypy checks only the main script; its configuration is in `pyproject.toml`.
- **Tests, as CI does:** `python -m pytest -ra test_transcriber.py test_subtitle_prototype.py`
- **Known drift:** `make test` still runs only `test_transcriber.py`, while CI runs both. It's a one-line fix in the `Makefile`.

On the owner's machine:
- **The repo** is `C:\Users\DRuin\OneDrive\Documents\OpenAI-YouTube-Transcriber`.
- **The Python** with every dependency is `C:\Users\DRuin\AppData\Local\Programs\Python\Python312\python.exe`. It has flake8, isort, pytest, mypy, whisper and yt_dlp; ffmpeg and ffprobe are on PATH via scoop.
- **Don't install pre-commit** into that Python: it upgrades filelock from 3 to 4, which torch and huggingface_hub rely on.
- **Expect 147 passed, 2 skipped** on Windows. The two skips are symlink tests.
- **`gh` isn't logged in** there, so branches have been merged into `main` directly, without pull requests.

## What happened this session

1. **Media fixes** and a tidy-up of their tests, on `main` (f3bc322, 729070b).
2. **Merged `fix/windows-paths-and-captions`:**
   - A double-quoted Windows path in a profile or `config.txt` keeps its backslashes. python-dotenv had been decoding `\t` and `\n` inside them; the fix is `_env_text`.
   - `~` expands in Windows separators (`_expand_home`).
   - Captions read as prose keep a word said twice across two cues.
   - CI gained a windows-latest job.
3. **Merged `chore/agent-workflow`:** `AGENTS.md`, the `CLAUDE.md` pointer, `PUNCHLIST.md` and the settings-sync skill, with ponytail declared in `.claude/settings.json`.
4. **Merged `feature/subtitles-prototype`:** `subtitle_prototype.py`, with `test_subtitle_prototype.py`. It is standalone: nothing in the main script calls it.
   - **Timing** comes from Whisper's word timestamps, or from YouTube's captions (json3 or VTT). For Whisper, `tighten` gives back the silences Whisper stretches words over.
   - **Cues** are cut to at most 2 lines of 42 columns and 7 seconds each.
   - **Polish** (optional) corrects each cue's wording with the AI backend and keeps its timing.
   - **Output:** an .srt, a soft track muxed in, or a burned-in hard copy.
   - **Fixed since:** cues now break at sentence ends, and not after "Mr.". A review then found ten bugs, fixed in fb09f5c:
     - polish sends each batch in one request, and a failed backend counts as failed;
     - soft muxing keeps the streams the file already has;
     - a cue is checked again after a cut;
     - no negative times;
     - the hard copy is 8-bit H.264 with audio Windows can play;
     - overlapping YouTube events are clamped;
     - Chinese, Japanese and Korean lines are measured in display width;
     - every language Whisper knows is tagged.
   - **Tried on real videos:**
     - "Me at the zoo".
     - A 108-second Spanish fable, "La liebre y la tortuga". Whisper `small` translated "liebre" (hare) as "the lion"; `medium` translated it well, with cues within about 0.3 s of the speech.
     - The outputs are in `OpenAIYouTubeTranscriber/Video/Subtitled/`, which is gitignored.
   - **Never run:** polish against a live model. There is no API key on the development machine.
   - **Temporary:** for each polish request, `_one_request` overrides the main script's private `_run_chunked_enhancement`. The plan says to give the backends a single-request mode when the prototype is ported.
5. **The owner specified the subtitle settings** (c79e56a):
   - `VIDEO_SUB` (from the YouTube transcript), `VIDEO_SUB_WHISPER`, `VIDEO_SUB_AI_REFINEMENT` and `VIDEO_SOFT_HARD_SUB` (soft, hard or both);
   - the same four for `VIDEO_ONLY_`;
   - placed after `TRANSCRIPT_PATH` in profiles, each asked only when what it needs is on.

   `docs/SUBTITLES_PLAN.md` lays out the tracks, the outputs, the code changes, the tests and three phases, and ends with the 10 decisions.

## Open, waiting on the owner

- **The 10 decisions** at the end of `docs/SUBTITLES_PLAN.md`:
  1. hard copies, one per track and video file;
  2. refined versus unrefined subtitles;
  3. where the .srt files go;
  4. YouTube's `all`;
  5. containers that can't hold subtitles;
  6. a local video without re-encoding;
  7. the `VIDEO_SUB` name;
  8. a sample profile;
  9. refined subtitles without a transcript PROMPT;
  10. file names and track titles.
- **Two punchlist items:** 3.8 (prefer H.264 over AV1 when downloading a video to subtitle) and 3.12 (translation needs Whisper `medium` or larger).
- **Old branches on GitHub** (`fix/windows-paths-and-captions`, `feature/subtitles-prototype`, `chore/agent-workflow`) are merged and redundant, but not deleted.
- **Leave alone** a local stash on `fix/yt-dlp-migration` (a change to `config.txt`) and the locally excluded `test.txt`.

## Your first reply

Don't change any code yet. Read the files above, then reply with:
1. a short summary of the state, in your own words;
2. anything in the docs that contradicts the code;
3. the open decisions, in the order you'd ask them.

Then wait for the owner's task.

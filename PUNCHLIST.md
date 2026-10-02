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

Last updated 2 Oct 2026.

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
| 3.12 | Translation needs `medium` or larger (not `large-v3-turbo`, never trained to translate); the setting should not default to `base` for it. | OPEN |
| 3.13 | Review fixes in the prototype: refinement in one request per batch and failures counted, soft mux keeps the file's own tracks, cues within limits after a cut, no negative times, hard copy 8-bit with playable audio, overlapping YouTube events clamped, CJK width, every Whisper language tagged. Rerun on the Spanish video (soft and hard); refinement never run against a real model. | WRITTEN |

## 4. Agent workflow (merged into `main` 2 Oct 2026)

| # | Item | Status |
|---|---|---|
| 4.1 | `AGENTS.md` (single source of guidance), `CLAUDE.md` pointer, `ponytail` declared for the repo, the `settings-sync` skill, this punchlist. | WRITTEN |

## 5. Whole-codebase review (2 Oct 2026, nothing fixed yet)

Found by a review of the whole codebase; ✓ was reproduced by running the code, the rest
from reading it. Each fix needs a test that fails on the code as it is.

| # | Item | Status |
|---|---|---|
| 5.1 | **Can lose a file.** Downloads are written straight into their folder without `_take_path`, so a local source queued later in the batch with the same name (video "Lecture", then `Audio/Lecture.m4a`) is overwritten, then deleted by `_convert_all`. Claiming download names also removes `merge()`'s `samefile` special case. | OPEN |
| 5.2 | **Can lose a file.** `_convert_all` deletes the download once any format is written, though another asked for (`mp3,flac`, flac failing) did not land (invariant 3). | OPEN |
| 5.3 | **Ends the batch.** `convert_media`'s in-place `os.replace` is unguarded: a OneDrive or Defender lock raises `PermissionError`, which `_run_pipeline` does not catch, and the sources after it are skipped (invariant 5). | OPEN |
| 5.4 | A `DownloadFailed` partway through a pass skips `convert()` and `clear_temp_audio()`: the video-only file stays in the downloaded codec, and Audio/Temp is left full, unreported. | OPEN |
| 5.5 | ✓ A double-quoted path is refused at the source prompt and the transcript and prompt pickers (Explorer's "Copy as path", drag and drop); the profile and folder prompts strip the quotes. | OPEN |
| 5.6 | ✓ "Run again?" after a batch that ends on a transcript or local file keeps only `TARGET_LANGUAGE` and `KEEP_TRANSCRIPT`: `_Remembered.carry` reads the last pass's `cfg.url`. | OPEN |
| 5.7 | "Run again?" never carries `PROMPT`, or a backend chosen at the console, so both are asked every round (`docs/USAGE.md` says a repeat asks only for the new source). | OPEN |
| 5.8 | ✓ Two audio wordings for one stream (`medium,highest`, where medium is the top) make two identical merged files. | OPEN |
| 5.9 | Tidy-ups: dependency errors go to stdout, not `error()`; `load_opening` runs ffmpeg without `FFMPEG_RUN` and no comment says why; `_same_file` repeats `_path_identity`; `audio_stream_for` rebuilds its selector on every call. | OPEN |
| 5.10 | **Owner's decision.** `config.txt` is tracked, so its `.gitignore` line does nothing and a key typed into it is staged by `git add -A` (the committed copy is an empty template). Stop tracking it and let the app create it, ship `config.example.txt` instead, or leave it? Recommended: stop tracking it. | OPEN |
| 5.11 | **Owner's decision.** `KEEP_TRANSCRIPT` left out of a profile means "ask", so a pre-1.2 profile that refines stops unattended (invariant 2). Should a missing value mean `y` (the old behaviour) or `n`? Recommended: `y`. | OPEN |

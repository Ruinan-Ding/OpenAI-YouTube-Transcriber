# AGENTS.md

Guidance for AI agents working in this repo, and readable by people too. `README.md` covers
using the app, `DEV.md` setting up and the day-to-day commands; this file covers what is easy
to get wrong, what the owner has decided, and how work here is done.

## How to work here

**Invoke the `ponytail` plugin for all code work in this repo**: `/ponytail` (default level
`full`). The repo declares it in `.claude/settings.json` (marketplace
`DietrichGebert/ponytail`), so Claude Code offers to install it once the folder is trusted; by
hand it is `/plugin marketplace add DietrichGebert/ponytail`, then
`/plugin install ponytail@ponytail`. The plugin is the source of truth for what "lazy" means
here; don't restate its rules in this file, run it. Siblings: `/ponytail-review` (a diff),
`/ponytail-audit` (the repo), `/ponytail-debt`, `/ponytail-help`.

Under it, these hold:

- **What the app does is the owner's call, never a reasonable default.** A file name, a
  default answer, what a setting means when left blank, whether something is deleted: if
  *Decisions* below does not settle it, stop and ask. Ask in small batches, the question that
  is most expensive to get wrong first.
- **Record a decision the turn it is made**, in *Decisions*. A decision that lives only in a
  chat is one the next session will contradict. When a later one replaces it, edit the entry
  and check what code relied on the old one; don't append a contradiction.
- **A passing test is not a working feature.** `PUNCHLIST.md` tracks what is in flight as
  OPEN, WRITTEN (code and tests) or SEEN (the owner watched it work), and only the owner
  moves anything to SEEN. Say what was run and what was not; never report a feature as done
  on the strength of its tests.
- **Read the code a change touches before changing it.** The script is one long file whose
  parts lean on each other (see the invariants); a small diff in the wrong place passes the
  tests and breaks a promise the app makes elsewhere.
- **The owner works on Windows.** CI runs on Linux. Anything that touches a path, a quote, a
  file name or a subprocess is tested on Windows before it is called done (see *Known quirks*).

## What this is

A command-line app that downloads YouTube videos, audio and captions with yt-dlp, transcribes
with OpenAI Whisper, refines, translates or summarises the transcript with an AI backend
(OpenAI-compatible, Anthropic or a local Hugging Face model), and converts and merges media
with ffmpeg. Sessions are answered at the console or replayed from saved profiles. One
Python script, `OpenAIYouTubeTranscriber.py`.

## Commands

```bash
make dev                          # the development tools (requirements-dev.txt)
make lint                         # flake8, isort and mypy, as CI runs them; must be clean
make test                         # pytest over test_transcriber.py and test_subtitle_prototype.py
python test_transcriber.py        # the app's tests without pytest
python OpenAIYouTubeTranscriber.py   # the app (or: python .)
```

CI (`.github/workflows/tests.yml`) runs flake8, isort, mypy and both test files on every push
to `main` and every pull request, with Python 3.11: the tests on Ubuntu and Windows, the
linters on Ubuntu. It installs ffmpeg, so the pipeline tests that merge and re-encode real
files run there; locally they are reported as
skipped (`-ra`) without it. `DEV.md` has the rest.

## Architecture invariants

Break these and the app stops keeping its promises.

**1. One script.** `OpenAIYouTubeTranscriber.py` is the whole app: it runs as it stands, it is
the module `pip install .` installs, and `openai-youtube-transcriber` runs its `main()`. It
was split into a package and folded back (`fded975`); don't split it again. New code goes in
the script, in the part of it `DEV.md`'s *Code Layout* names.

**2. Each setting is described once.** A profile and an interactive session settle every
setting through one function, `_configure`, reading one table, `SETTINGS`, which says what a
profile that leaves a field out (`absent`) or blank (`blank`) means. `_Profile` and
`_Remembered` only say where the answers are kept. Adding, renaming or removing a field
touches several places: **use the `settings-sync` skill.** A profile written before a field
existed must still load, so a field that turns something on is off when absent.

**3. Nothing the user has is lost to a failure.**
- A source is retired only after every output that replaces it has landed
  (`_settle_source`), and transcripts are written atomically (`write_text_atomically`).
- **ffmpeg can exit 0 having written nothing.** Every conversion checks its output exists
  and is not empty before anything relies on it (`convert_media`, `strip_audio`,
  `combine_audio_video`), and removes a half-written one (`_discard`).
- A conversion that could land on its own source writes beside it and swaps
  (`convert_media`). Paths are compared as files (`_same_file`), never as text: a symlink, or
  `C0001.MP4` beside `C0001.mp4` on Windows, is the same file.
- **Every output name is claimed in one place** (`_claim_name`, `_reserve_sources`), compared
  case-insensitively, so two sources of one title, or an output and a queued source, never
  share a file.

**4. ffmpeg and ffprobe run with `FFMPEG_RUN`**: no stdin (ffmpeg reads its keyboard commands
there, and ate the first character of the answer waiting after it), and output decoded as
UTF-8 with errors replaced (a Japanese file name in cp1252 ended the batch).

**5. Failures go to stderr through `error()`; progress goes to stdout.** `error()` flushes
stdout first so the reason lands next to the step that hit it. A function that fails returns
`None` (or its input unchanged, for enhancement) and says why; it doesn't raise into the
batch, so one bad source never ends the others.

**6. Profiles are read back exactly as written.** The app writes each value through
`env_value` (single-quoted wherever dotenv would change it) and reads profiles through
`_read_profile` (a single-quoted value literally, with no `${...}` expansion). `config.txt` holds
configuration, `AI_PROVIDER`, `API_KEY`, `MODEL` and `BASE_URL`, which goes to the
environment where the backends read it; a profile's fields go into the `Session`, never into
the environment (a shell's `VIDEO_ONLY=y` once answered for a profile that left it out).

**7. Whisper is told the language spoken, never the one to write.** `SOURCE_LANGUAGE` is the
spoken language (`auto`: Whisper detects it); `TARGET_LANGUAGE` is what to write: `auto` is
the spoken language, `en` is Whisper's own translation, and anything else comes back as the
spoken-language transcript with a note pointing at the translator prompt. Transcripts are
named for the language they are actually in. One model is held at a time, and a pass over an
audio file is cached for that file only (`transcribe_audio_file`).

**8. A video's metadata is fetched once** (`fetch_video_info`) and every download, caption
fetch and format choice works from it; extracting the video again per deliverable could pick
other formats than the names were made from. `requirements.txt` is deliberately unpinned:
yt-dlp goes stale whenever YouTube changes.

**9. What ships is named file by file.** The prompts and sample profiles an installed copy
carries are listed one by one in `pyproject.toml` (`[tool.setuptools.package-data]`), never
globbed: `Prompt/` and `Profile/` also hold the user's own files, and `config.txt` can hold an
API key. A new shipped prompt or profile goes in that list.

## Tests

- **Plain functions and plain `assert`**, so `test_transcriber.py` runs under pytest and as a
  script. Under pytest, `conftest.py` puts back everything a test patched; without it, a test
  that patches restores in a `finally`.
- **A test's name is the behaviour as a sentence, and its docstring the bug it guards**: what
  went wrong without it. Add a regression test with every fix.
- **Only the network is faked.** ffmpeg runs for real; a test that needs it calls
  `_skip('no ffmpeg')` when it is missing, so it reports a skip and not a pass. Console
  answers go through `builtins.input`; module functions are patched on the module.
- Don't pin a test to something the owner may change (a default model, a sample profile's
  contents); look it up from where it is defined.

## Style

- **flake8 (with bugbear), isort and mypy must be clean.** 100 columns, single quotes, no
  auto-formatter. mypy is strict on the script (`pyproject.toml`); the tests are not
  annotated.
- **A comment says why, and usually by naming what went wrong without the line under it**
  ("ffmpeg can exit 0 having written nothing usable…"). Match the density and voice of the
  code around it. Don't narrate what the code plainly does.
- **Every user-visible change gets a `CHANGELOG.md` entry** under `[Unreleased]`, in the same
  voice: what was wrong, what happens now. A field or behaviour the user sets is documented
  in `README.md` / `docs/USAGE.md` in the same change.
- **Commits**: the subject is what the change does, as a sentence ("Fix quoted Windows
  paths, ~ separators and single-word caption repeats"); the body says why and what was
  checked (tests, lint, a real run). Work lands on `main` through a pull request, so CI runs
  first; branches are `fix/…`, `feature/…` or `chore/…`.
- **One of everything.** Don't copy guidance between files; point to where it lives. A
  document that has gone out of date gets a dated status line at its top
  (`docs/CODE_REVIEW_REPORT.md`) rather than being left to mislead.

## Decisions

The owner's decisions, the running record. Not complete, and not meant to be. Dates are
when the owner decided.

- **Agent workflow** (1 Oct 2026): this file is the single source of agent guidance, with
  `CLAUDE.md` a pointer to it, `ponytail` for all code work, a `PUNCHLIST.md`, and skills for
  changes that touch many places, after the owner's ChessPlusPlus repo.
- **Changes land through pull requests** (1 Oct 2026), so CI runs before `main` moves.
- **Captions read as prose drop a cue's restatement of the cue before it** (1 Oct 2026):
  YouTube's rolling captions repeat the end of the previous cue, and that text is kept once. A
  single shared word counts as a repeat only when it was the whole previous cue, so "He had" /
  "had enough" keeps both words.
- **"Video Only" never names a file that still has its audio** (1 Oct 2026): when the audio of
  a muxed download cannot be removed, the download is deleted and the failure reported.
- **Subtitles are prototyped apart from the script first** (1 Oct 2026):
  `subtitle_prototype.py` and `docs/SUBTITLES_PLAN.md`, merged into `main` as a prototype
  (2 Oct 2026). Subtitles are timed from Whisper or YouTube's captions, never by a language
  model.
  **Polish mode** corrects each cue's wording and keeps its timestamps exactly: the owner's
  *"maybe the user decides to keep timestamp but fix grammar"*. Both soft subtitles (a track)
  and burned-in ones were asked about.
- **The owner specified the subtitle settings** (2 Oct 2026): `VIDEO_SUB`,
  `VIDEO_SUB_WHISPER`, `VIDEO_SUB_AI_REFINEMENT` and `VIDEO_SOFT_HARD_SUB`, and the same four
  for `VIDEO_ONLY_`, each asked only when what it needs is on. See `docs/SUBTITLES_PLAN.md`.

Open, waiting on the owner: the decisions at the end of `docs/SUBTITLES_PLAN.md`.
**Don't build subtitles into the main script until they are answered.**

## Known quirks

- **CI is Linux and the owner is on Windows.** A double-quoted Windows path in a profile lost
  its backslashes to dotenv's escapes (`\t`, `\n`), `~/clip.mp3` expanded to
  `C:\Users\me/clip.mp3`, and a test built `'file://' + path`, which is no URL with a drive
  letter. Every Linux run passed. Fixed, and CI has run the tests on Windows since
  2 Oct 2026.
- **yt-dlp's `bv*[ext=mp4]` can be AV1**, which Windows plays only with the AV1 Video
  Extension installed. A stream copy keeps it AV1.
- **Whisper's word timestamps stretch over silences**: after a pause the first word gets no
  length and the next one absorbs the silence. The subtitle prototype corrects it (`tighten`).
- **Agent editing tools can write `\uXXXX` as the character itself.** A regex range written
  as `[\u3040-\u30ff]` came back as the literal characters. It means the same, but check with
  `grep` after editing one, and rewrite it with a script if the escapes matter.

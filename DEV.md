# Development Setup

## Initial Setup

Create a virtual environment:

```bash
python -m venv .venv

# Windows:
.\.venv\Scripts\activate

# macOS/Linux:
source .venv/bin/activate
```

Install everything:

```bash
make deps      # Install runtime dependencies
make dev       # Install dev tools (linters, formatters, etc.)
make install   # Install the package in editable mode
```

Without `make`:

```bash
pip install -r OpenAIYouTubeTranscriber/requirements.txt
pip install -r requirements-dev.txt
pip install -e .
```

## Code Layout

The app is one script, `OpenAIYouTubeTranscriber.py`. It runs as it stands
(`python OpenAIYouTubeTranscriber.py`, or `python .`), and it is the module
`pip install .` installs, whose `main()` the `openai-youtube-transcriber`
command runs. From the top, it holds:

- the words everything is written in: yes/no, qualities, Whisper models, AI
  providers, `error()`;
- `YouTubeTranscriber`, the app's tools: what the user is asked, its folders
  and text files, yt-dlp, ffmpeg, Whisper, and refining with a model;
- `SessionConfig`, what a session is set to do, and `Session`, what a run
  carries between rounds;
- the `SETTINGS` table, where an answer comes from (`_Profile`, `_Remembered`),
  and `_configure`, which settles every setting for a profile and a person
  alike, with the menus and typed answers it asks;
- refining and saving transcripts, and what each file is called;
- one pass per source: `_run_pipeline`, `_Pass` and its steps, `_run_one`;
- the session's rounds, "Run again?", and `main()`.

`subtitle_prototype.py` is a standalone trial of subtitles, not part of the app or the
wheel; `docs/SUBTITLES_PLAN.md` says what it is for and when it goes.

## Workflow

**Run the app to test changes:**
```bash
make run
```

**Check code quality (flake8, isort and mypy, as CI runs them):**
```bash
make lint
```

**Run the test suite:**
```bash
make test                        # pytest over test_transcriber.py and test_subtitle_prototype.py
python test_transcriber.py       # the app's tests, no pytest needed
```

The tests are plain functions and plain `assert`, so they run either way.
Under pytest, `conftest.py` puts back everything a test patched - environment
variables, `input()`, the attributes of the script and of
`YouTubeTranscriber`, stand-in modules - after every test, so one that fails
halfway cannot break the ones after it; without pytest, every test still runs
and each failure is listed. A test patches a function on the module
(`module._run_one = ...`), and answers the console through `builtins.input`. The
pipeline cases merge and re-encode real files through the installed ffmpeg,
and are reported as skipped (`-ra` lists them) where it is missing. Only the
network calls are faked.

## Type Checking

Every function in the script says what it takes and returns, and `mypy`
(configured in `pyproject.toml`) holds it to that: strict, except that a value
handed on from yt-dlp or Whisper, which publish no types, is taken as the type
the function says. The tests are not annotated.

- The script starts with `from __future__ import annotations`, so annotations
  are never evaluated, and a function can name `YouTubeTranscriber` or
  `SessionConfig` wherever it is defined in the file.
- A value that is only missing where no code reads it (a pass's URL, a
  video's metadata) is checked once with `assert ... is not None` where it is
  read, rather than typed as always there.

## Style

There is no auto-formatter. This codebase is 100 columns and single-quoted;
black defaults to 88 and double quotes, so it is not enabled. `flake8` (with
`flake8-bugbear`) is the enforced standard and must report zero issues.

## Continuous Integration

`.github/workflows/tests.yml` runs flake8, isort, mypy and the suite (under pytest) on
every push to `main` and on every pull request, on Ubuntu with Python 3.11. It installs the
CPU build of torch before the requirements, so Whisper does not drag in CUDA.

## Git Hooks

Install the pre-commit hooks to lint automatically on each commit:

```bash
make precommit-install
```

If a hook fails, fix the reported issue and commit again. To run every hook over
the whole repository, as a check before a pull request:

```bash
pre-commit run --all-files
```

## Notes

- `OpenAIYouTubeTranscriber/requirements.txt` is deliberately unpinned. yt-dlp goes stale the moment YouTube changes something, which is what this project migrated to it for, so a pin there would be a scheduled breakage. Add a lower bound if a change needs one.
- Don't commit audio or video files; they're covered by `.gitignore`.
- If you add a dependency, update both `requirements.txt` and `pyproject.toml`,
  which holds the package's metadata; there is no `setup.py`. The optional AI
  backends are the `ai` extra there: `pip install -e ".[ai]"`.

## Makefile Targets

- `make install`: Install the package in editable mode
- `make deps`: Install runtime dependencies
- `make dev`: Install development tools
- `make lint`: Run flake8, isort and mypy as CI does
- `make test`: Run the test suite under pytest
- `make run`: Run the app
- `make clean`: Remove build artifacts
- `make precommit-install`: Set up git hooks

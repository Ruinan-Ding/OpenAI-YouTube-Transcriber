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

## Workflow

**Run the app to test changes:**
```bash
make run
```

**Check code quality (flake8 and isort, as CI runs them):**
```bash
make lint
```

**Run the test suite:**
```bash
make test                        # python -m pytest -ra test_transcriber.py
python test_transcriber.py       # the same tests, no pytest needed
```

The tests are plain functions and plain `assert`, so they run either way.
Under pytest, `conftest.py` puts back everything a test patched - environment
variables, module attributes, stand-in modules - after every test, so one that
fails halfway cannot break the ones after it; without pytest, every test still
runs and each failure is listed. The pipeline cases merge and re-encode real
files through the installed ffmpeg, and are reported as skipped (`-ra` lists
them) where it is missing. Only the network calls are faked.

There is no auto-formatter. This codebase is 100 columns and single-quoted;
black defaults to 88 and double quotes, so it is not enabled. `flake8` (with
`flake8-bugbear`) is the enforced standard and must report zero issues.

## Continuous Integration

`.github/workflows/tests.yml` runs flake8, isort and the suite (under pytest) on
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
- `make lint`: Run flake8 and isort as CI does
- `make test`: Run the test suite under pytest
- `make run`: Run the app
- `make clean`: Remove build artifacts
- `make precommit-install`: Set up git hooks

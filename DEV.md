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

**Check code quality (flake8):**
```bash
make lint
```

**Run the self-check suite:**
```bash
make test
```

No framework: plain `assert`, and `python test_transcriber.py` runs every
`test_*` in the file and prints `all passed`. The pipeline cases merge and re-encode real
files through the installed ffmpeg, and skip themselves if it is missing. Only
the two network calls are faked.

There is no auto-formatter. This codebase is 100 columns and single-quoted;
black defaults to 88 and double quotes, so it is not enabled. `flake8` (with
`flake8-bugbear`) is the enforced standard and must report zero issues.

## Continuous Integration

`.github/workflows/tests.yml` runs flake8, isort and the suite on every push to
`main` and on every pull request, on Ubuntu with Python 3.11. It installs the
CPU build of torch before the requirements, so Whisper does not drag in CUDA.

## Git Hooks

Install the pre-commit hooks to lint automatically on each commit:

```bash
make precommit-install
```

If a hook fails, fix the reported issue and commit again.

## Notes

- `OpenAIYouTubeTranscriber/requirements.txt` is deliberately unpinned. yt-dlp goes stale the moment YouTube changes something, which is what this project migrated to it for, so a pin there would be a scheduled breakage. Add a lower bound if a change needs one.
- Don't commit audio or video files; they're covered by `.gitignore`.
- If you add a dependency, update both `requirements.txt` and `setup.py`.

## Makefile Targets

- `make install`: Install the package in editable mode
- `make deps`: Install runtime dependencies
- `make dev`: Install development tools
- `make lint`: Check code quality
- `make test`: Run the self-check suite
- `make run`: Run the app
- `make clean`: Remove build artifacts
- `make precommit-install`: Set up git hooks

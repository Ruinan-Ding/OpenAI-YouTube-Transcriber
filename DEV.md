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

**Auto-format (black + isort):**
```bash
make format
```

## Git Hooks

Install the pre-commit hooks to lint and format automatically on each commit:

```bash
make precommit-install
```

If a hook fails, fix the reported issue and commit again.

## Notes

- Keep `OpenAIYouTubeTranscriber/requirements.txt` pinned to specific versions so installs are reproducible. The versions in `setup.py` can be looser.
- Don't commit audio or video files; they're covered by `.gitignore`.
- If you add a dependency, update both `requirements.txt` and `setup.py`.

## Makefile Targets

- `make install` — Install the package in editable mode
- `make deps` — Install runtime dependencies
- `make dev` — Install development tools
- `make lint` — Check code quality
- `make format` — Auto-format code
- `make run` — Run the app
- `make clean` — Remove build artifacts
- `make precommit-install` — Set up git hooks

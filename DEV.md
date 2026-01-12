# Setting Up for Development

Want to work on the code? Here's how to get your environment ready.

## Initial Setup

Create a virtual environment to keep things isolated:

```bash
python -m venv .venv

# On Windows:
.\.venv\Scripts\activate

# On macOS/Linux:
source .venv/bin/activate
```

Then install everything:

```bash
make deps      # Install runtime dependencies
make dev       # Install dev tools (linters, formatters, etc.)
make install   # Install the package in editable mode
```

If you don't have `make`, you can do it manually:

```bash
pip install -r OpenAIYouTubeTranscriber/requirements.txt
pip install -r requirements-dev.txt
pip install -e .
```

## Working on Code

**Run the app to test changes:**
```bash
make run
```

**Check code quality:**
```bash
make lint
```

This uses flake8 to catch potential issues and style problems.

**Format everything nicely:**
```bash
make format
```

This uses black and isort to auto-fix formatting issues.

## Git Hooks

We use pre-commit hooks to automatically check things before you commit:

```bash
make precommit-install
```

This sets up automatic linting and formatting on every commit. If something fails, fix it and try committing again. The hooks exist to keep the code clean.

## Important Notes

- Keep `OpenAIYouTubeTranscriber/requirements.txt` pinned to specific versions so installs are reproducible. The versions in `setup.py` can be looser though.
- Don't commit audio or video files—they're already in `.gitignore` for good reason.
- If you add new dependencies, update both `requirements.txt` and `setup.py`.

## Makefile Targets

- `make install` — Install the package in editable mode
- `make deps` — Install runtime dependencies
- `make dev` — Install development tools
- `make lint` — Check code quality
- `make format` — Auto-format code
- `make run` — Run the app
- `make clean` — Remove build artifacts
- `make precommit-install` — Set up git hooks

Pretty straightforward stuff.
# Developer Workflow

This file documents the recommended developer workflow for the project.

Setup

```bash
python -m venv .venv
# Windows
.\.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

# Install runtime deps
make deps

# Install development tools
make dev

# Install editable package
make install
```

Common tasks

- Run the CLI:

```bash
make run
```

- Lint the code with `flake8`:

```bash
make lint
```

- Format with `black`:

```bash
make format
```

- Run tests:

```bash
pytest
```

Pre-commit hooks

Install and enable pre-commit hooks:

```bash
pip install pre-commit
pre-commit install
pre-commit run --all-files
```

Make targets

- `make dev` — install development dependencies from `requirements-dev.txt`
- `make precommit-install` — install git hooks via `pre-commit install`

Notes

- Keep `requirements.txt` pinned for reproducible installs; keep `install_requires` in `setup.py` as the looser package dependency list.
- Avoid committing large media files (audio/video) — they are covered by `.gitignore`.

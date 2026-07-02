Build, test, and lint

- Primary developer workflow uses Makefile targets defined in README/DEV.md. Common commands:
  - make deps       # install runtime dependencies
  - make dev        # install dev tools (formatters, linters)
  - make install    # install package in editable mode (pip install -e .)
  - make run        # run the application (same as `python OpenAIYouTubeTranscriber.py`)
  - make lint       # run flake8 (checks code quality)
  - make format     # run black + isort
  - make precommit-install  # install git pre-commit hooks

- If you don't have make (or for single-command use):
  - python -m venv .venv && .\.venv\Scripts\activate  # Windows example
  - pip install -r OpenAIYouTubeTranscriber/requirements.txt
  - pip install -r requirements-dev.txt
  - pip install -e .
  - Run the app directly: python OpenAIYouTubeTranscriber.py

- Tests: This repository contains no automated test suite. To exercise behavior manually, run the application on small inputs (short YouTube IDs or local audio files). There is no documented single-test runner.

High-level architecture

- Top-level package: OpenAIYouTubeTranscriber
  - The project is a single-script / small package CLI tool that: downloads audio/video (pytubefix + ffmpeg), extracts audio, and transcribes with OpenAI Whisper.
  - Entry points:
    - Script: python OpenAIYouTubeTranscriber.py (documented quick-start)
    - Console script entry: openai-youtube-transcriber (setup.py)
      - Note: README also references `youtube-transcriber` as a convenience command if installed; actual setup.py entry point is `openai-youtube-transcriber`.
  - Profiles: user session settings are saved under OpenAIYouTubeTranscriber/Profile/ as simple text files (key=value) and are loaded by the CLI to pre-fill prompts.
  - Output directories (convention):
    - OpenAIYouTubeTranscriber/Transcript/  (transcripts)
    - OpenAIYouTubeTranscriber/Audio/       (downloaded audio)
    - OpenAIYouTubeTranscriber/Video/       (downloaded video)
    - OpenAIYouTubeTranscriber/VideoWithoutAudio/ (edge-case videos without audio)

- External runtime dependencies of note:
  - FFmpeg: required on PATH for audio/video processing
  - openai-whisper: installed from GitHub in setup.py
  - pytubefix: YouTube downloading; occasionally requires updates when YouTube changes

Key conventions and repository-specific patterns

- Profiles-as-plain-text: Profiles are simple INI-like key=value plain text files placed in OpenAIYouTubeTranscriber/Profile/. New profiles are created automatically by the CLI; treat them as editable but keep keys consistent (see README examples).

- CLI prompts + profile fallback: The CLI will list and let you choose a profile at start; it accepts full YouTube URLs, short URLs, or raw 11-character video IDs and normalizes them to the ID.

- Model choices (resource guidance): Whisper model selection is surfaced to users; be mindful of memory requirements (tiny/base/small/medium/large-v1/v2/v3) when recommending defaults in automation.

- Packaging vs README command mismatch: README examples sometimes mention `youtube-transcriber` while setup.py defines `openai-youtube-transcriber` as the console script. Use the setup.py entry or run the script directly if commands seem inconsistent.

- Pin runtime deps in OpenAIYouTubeTranscriber/requirements.txt: DEV.md and README ask maintainers to keep OpenAIYouTubeTranscriber/requirements.txt pinned for reproducible installs; setup.py may use looser version specifications.

Other AI assistant configs

- This repository does not contain CLAUDE.md, AGENTS.md, .cursorrules, .windsurfrules, CONVENTIONS.md, or other known assistant config files. No extra assistant-specific files were merged into this document.

MCP servers

- Would you like help configuring any MCP servers (for example Playwright or other CI/test runners) relevant to this repo? If so, specify which server(s) to configure.

Summary

- Added guidance for building, running, linting, and the main architectural overview plus repository conventions. Ask to adjust or add coverage for any specific areas (packaging, profiles, CLI automation, or adding tests).

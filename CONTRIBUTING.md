# Contributing

Bug fixes, features, and documentation improvements are all welcome.

## Getting Started

1. Fork the repo on GitHub
2. Clone your fork
3. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   ```
4. Install dependencies:
   ```bash
   pip install --upgrade -r OpenAIYouTubeTranscriber/requirements.txt
   pip install -r requirements-dev.txt
   ```

## Making Changes

**Code style** — Follow [PEP 8](https://www.python.org/dev/peps/pep-0008/) as a general guide. Use clear variable names, keep lines under 100 characters, and add a docstring to any new function.

**Test before submitting** — There is no automated test suite, so exercise your changes manually:
- Different YouTube URLs
- Local files
- Downloading as well as transcribe-only
- Different models
- Different languages, if you changed language handling

**Commit messages** should be short and descriptive:
```
Fix: Correct URL validation issue
Feature: Support for local subtitle files
Docs: Update installation guide
```

## Submitting a Pull Request

1. Push to your fork
2. Open a pull request with:
   - A title that explains what you changed
   - A description of why you changed it
   - A reference to any issue it fixes (e.g. "Fixes #42")
3. Expect review feedback; requested changes are normal
4. Once approved, it gets merged

## Reporting Bugs

Check whether the bug has already been reported first. If not, include:

- What happened
- Steps to reproduce
- OS and Python version
- The error message, if any

## Code of Conduct

Be respectful and keep disagreements constructive.

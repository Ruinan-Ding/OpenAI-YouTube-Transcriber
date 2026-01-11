# Contributing to OpenAI YouTube Transcriber

Thank you for your interest in contributing! We welcome contributions of all kinds.

## Getting Started

1. **Fork the repository** and clone your fork locally
2. **Create a virtual environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. **Install dependencies**:
   ```bash
   pip install --upgrade -r OpenAIYouTubeTranscriber/requirements.txt
   ```

## Making Changes

### Code Style
- Follow [PEP 8](https://www.python.org/dev/peps/pep-0008/) guidelines
- Use meaningful variable and function names
- Add docstrings to functions and classes
- Keep lines under 100 characters when reasonable

### Manual Testing
- Test your changes thoroughly before submitting
- Ensure the script runs without errors on your system
- Test with different YouTube URLs and local files
- Verify all download and transcription options work correctly

### Commit Messages
Use clear, descriptive commit messages:
```
Fix: Correct YouTube URL validation regex
Feature: Add support for playlist downloads
Docs: Update README installation steps
```

## Submitting Changes

1. **Push to your fork**: `git push origin your-feature-branch`
2. **Create a Pull Request** with:
   - Clear title describing the change
   - Description of what was changed and why
   - Reference any related issues (e.g., "Fixes #123")
3. **Respond to feedback** and make requested changes

## Reporting Issues

Before opening an issue, please:
- Check existing [issues](https://github.com/Ruinan-Ding/OpenAI-YouTube-Transcriber/issues)
- Provide clear reproduction steps
- Include Python version and OS information
- Share relevant error messages

### Issue Template
```
## Description
Brief description of the issue

## Steps to Reproduce
1. Step one
2. Step two

## Expected Behavior
What should happen

## Actual Behavior
What actually happens

## Environment
- OS: 
- Python Version:
- OpenAI Whisper Version:
```

## Code of Conduct

- Be respectful and inclusive
- Provide constructive feedback
- Help others learn and improve

Thank you for contributing!
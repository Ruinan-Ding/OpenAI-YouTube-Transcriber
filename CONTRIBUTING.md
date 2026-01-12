# Contributing

Thanks for wanting to help! Whether you're fixing bugs, adding features, or just improving docs, it's all appreciated.

## Want to Contribute?

### First Time?

1. Fork the repo on GitHub
2. Clone your fork to your machine
3. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   ```
4. Install what you need:
   ```bash
   pip install --upgrade -r OpenAIYouTubeTranscriber/requirements.txt
   pip install -r requirements-dev.txt  # For dev tools
   ```

### Making Your Changes

**Code style** — Keep it readable. Follow [PEP 8](https://www.python.org/dev/peps/pep-0008/) as a general guide. Use clear variable names. Don't make lines unnecessarily long (aim for under 100 characters). If you're adding a function, throw in a docstring explaining what it does.

**Test it before you submit** — Run the script with different scenarios:
- Try it with different YouTube URLs
- Test with local files
- Try both downloading and just transcribing
- Make sure different models work
- Check different languages if you changed language handling

**Commit messages** should be straightforward:
```
Fix: Correct URL validation issue
Feature: Support for local subtitle files
Docs: Update installation guide
```

## Submitting Your Work

1. Push to your fork
2. Open a pull request with:
   - A title that explains what you changed
   - A description of why you changed it
   - Reference any issue it fixes (like "Fixes #42")
3. We'll review and might ask for changes—that's normal
4. Once it looks good, it gets merged

## Found a Bug?

Check if someone already reported it first. If not:

- Explain what happened
- How to reproduce it
- What OS and Python version you're using
- The error message if there was one

## Be Cool

- Respect other people
- If someone disagrees with an idea, keep it constructive
- Help others out if you can

That's it. Appreciate you! 🙌
# OpenAI YouTube Transcriber

![Python](https://img.shields.io/badge/Python-3.6+-3776AB?logo=python&logoColor=white)
![OpenAI](https://img.shields.io/badge/OpenAI-Whisper-412991?logo=openai&logoColor=white)
![License](https://img.shields.io/badge/License-BSD%203--Clause-blue)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)

A command-line tool that downloads audio or video from YouTube (or takes a local media file) and transcribes it with [OpenAI Whisper](https://github.com/openai/whisper). Supports 99+ languages with automatic language detection, reusable settings profiles, and optional AI post-processing of the transcript.

## Quick Start

```bash
pip install --upgrade -r OpenAIYouTubeTranscriber/requirements.txt
python OpenAIYouTubeTranscriber.py
```

Then follow the prompts.

## Contents

- [Features](#features)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Usage](#usage)
- [Profiles](#profiles)
- [AI Transcript Enhancement](#ai-transcript-enhancement)
- [Output Files](#output-files)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [Tips](#tips)
- [Known Issues](#known-issues)
- [Supported Languages](#supported-languages)
- [License](#license)

## Features

- **Interactive CLI** — answer a few prompts; no configuration files required.
- **Flexible input** — accepts any of the following:
  - Full URL: `https://www.youtube.com/watch?v=jNQXAC9IVRw`
  - Short URL: `https://youtu.be/jNQXAC9IVRw`
  - Video ID: `jNQXAC9IVRw`
  - Local file: `/path/to/audio.mp3`

  The 11-character video ID is extracted from any URL format; query parameters such as timestamps (`&t=30s`) or playlist info (`&list=...`) are ignored.
- **99+ languages** with automatic language detection.
- **Selectable Whisper model** — tiny, base, small, medium, large-v1, large-v2, or large-v3, trading speed for accuracy.
- **Profiles** — save a session's settings to a file and reuse them.
- **Resolution control** for video downloads, or automatic selection.
- **Cross-platform** — Windows, macOS, and Linux.
- **Audio handling** — extracts audio from video, merges separate audio/video streams, and converts formats via FFmpeg.
- **AI transcript enhancement (optional)** — clean up the raw transcript with OpenAI, OpenRouter, or Anthropic (API key required), or a local Hugging Face model, guided by a prompt file or a custom prompt.

## Prerequisites

**Python 3.6+** — check with `python --version`. Installation guides:
- [Windows](https://phoenixnap.com/kb/how-to-install-python-3-windows)
- [macOS](https://docs.python-guide.org/starting/install3/osx/)
- [Linux (Ubuntu)](https://phoenixnap.com/kb/how-to-install-python-3-ubuntu)

**pip** — usually bundled with Python; verify with `python -m pip --version`.

**FFmpeg** — required for all audio/video processing and must be on your PATH.

Windows (PowerShell, using Scoop):
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
Invoke-RestMethod -Uri https://get.scoop.sh | Invoke-Expression
scoop install ffmpeg
```
Or download it manually from [ffmpeg.org](https://ffmpeg.org/download.html).

macOS (Homebrew):
```bash
brew install ffmpeg
```

Linux (Ubuntu/Debian):
```bash
sudo apt update && sudo apt install ffmpeg
```

## Installation

Clone the repository:
```bash
git clone https://github.com/Ruinan-Ding/OpenAI-YouTube-Transcriber.git
cd OpenAI-YouTube-Transcriber
```

Optionally create a virtual environment to keep dependencies isolated:
```bash
python -m venv venv

# Windows:
.\venv\Scripts\activate

# macOS/Linux:
source venv/bin/activate
```

Install the dependencies:
```bash
pip install --upgrade -r OpenAIYouTubeTranscriber/requirements.txt
```

To install the package in editable mode and get the `openai-youtube-transcriber` console command:
```bash
pip install -e .
```

## Usage

Run the script:
```bash
python OpenAIYouTubeTranscriber.py
```

You will be asked:

1. Where to get the audio (YouTube link or local file)
2. Whether to download the video
3. Whether to download just the audio
4. What video resolution to use (if downloading video)
5. Which Whisper model to use for transcription
6. What language to transcribe to
7. Whether to use the English-specific Whisper model
8. Whether to run again immediately

Example session:

```bash
$ python OpenAIYouTubeTranscriber.py

Enter the YouTube video URL or local file path: https://www.youtube.com/watch?v=jNQXAC9IVRw
Download video? (y/N): n
Download audio? (y/N): n
Transcribe the audio? (Y/n): y
Select Whisper model (1-7, default Base): 2
Enter target language (default English): en
Use English-specific model? (y/N): n

[Whisper transcribes the audio...]
Saved transcript to OpenAIYouTubeTranscriber/Transcript/video_title.txt

Run again? (y/N): n
```

## Profiles

Profiles save a full set of answers so recurring workflows don't require re-entering everything. On startup, the script lists any saved profiles:

```
Available profiles:
1. profile.txt
2. profile1.txt
3. profile2.txt

Select a profile (number or name, default 1. profile.txt, or 'no' to skip):
```

### Creating a Profile

After a successful run, the script offers to save the session as a profile. The resulting file contains the settings you just used.

### Profile Format

Profiles are plain text files in `OpenAIYouTubeTranscriber/Profile/` and can be edited directly:

```ini
URL=https://www.youtube.com/watch?v=example
DOWNLOAD_VIDEO=n
NO_AUDIO_IN_VIDEO=n
RESOLUTION=
DOWNLOAD_AUDIO=n
TRANSCRIBE_AUDIO=y
MODEL_CHOICE=base
TARGET_LANGUAGE=en
USE_EN_MODEL=n
AI_ENHANCEMENT=n
PROMPT=
REPEAT=n
```

The `URL` field accepts any of the supported input formats (full URL, short URL, bare video ID, or URL with extra query parameters — only the video ID is used).

### Included Profiles

- **profile-transcriber.txt** — transcribe only (no downloads)
- **profile1-video_downloader.txt** — download video with audio
- **profile2-audio_downloader.txt** — download audio only
- **profile0-translator.txt** — transcribe into other languages

## AI Transcript Enhancement

Whisper output can have inconsistent punctuation and grammar. After transcription, the script can optionally run the transcript through an AI model to clean it up.

When asked `Enhance transcript with AI?`, the options are:

- **`y`** — use the default cloud provider ([OpenRouter](https://openrouter.ai/), `openai/gpt-4o-mini` by default).
- **A provider name** — `openai`, `openrouter`, or `anthropic`.
- **`local`** — use a free local model (Qwen2.5-1.5B-Instruct by default). No API key; runs entirely on your machine. The first run downloads the model (~3GB).
- **A model name** — a specific local model (`qwen2.5-1.5b`, `qwen2.5-0.5b`, `distilgpt2`, `gpt2`, `gpt2-medium`, `phi-1_5`, `deepseek-1_5b`) or any Hugging Face model ID such as `microsoft/phi-2`.
- **`n`** — skip (the default).

### Cloud Providers

Cloud providers require an API key: set the matching environment variable, add it to `Profile/config.txt`, or enter it when prompted.

| Provider | Choice | API key env var | Model env var | Default model |
|---|---|---|---|---|
| OpenAI | `openai` | `OPENAI_API_KEY` | `OPENAI_MODEL` | `gpt-4o-mini` |
| OpenRouter | `openrouter` (default) | `OPENROUTER_API_KEY` | `OPENROUTER_MODEL` | `openai/gpt-4o-mini` |
| Anthropic | `anthropic` | `ANTHROPIC_API_KEY` | `ANTHROPIC_MODEL` | `claude-opus-4-8` |

OpenAI and OpenRouter both use the OpenAI-compatible chat completions API, so either can be pointed at another compatible endpoint (Groq, Together, Azure OpenAI, a local Ollama server, ...) via `OPENAI_BASE_URL` / `OPENROUTER_BASE_URL`. OpenRouter proxies many models, selectable via `OPENROUTER_MODEL` (e.g. `anthropic/claude-3.5-sonnet`, `deepseek/deepseek-chat`, or a free tier model like `meta-llama/llama-3.1-8b-instruct:free`). Anthropic uses its native Messages API; `ANTHROPIC_BASE_URL` works if you route through a compatible proxy.

Local models require the `transformers` and `torch` packages (included in requirements.txt). The default Qwen2.5-1.5B-Instruct is instruction-tuned and follows prompts reliably. Small base models such as `distilgpt2` and `gpt2` download faster but only complete text rather than follow instructions, so results are rough. Cloud providers give the best quality.

### Prompts

Enhancement is guided by a prompt that tells the model what to do with the transcript. Put `.txt` prompt files in `OpenAIYouTubeTranscriber/Prompt/` and the script will offer them for selection, or choose `E` to type a custom prompt in the console.

Example prompt file:
```
Correct the grammatical and punctuation errors in this transcript.
Keep all the original content—don't summarize or skip anything.
```

Long transcripts are split into chunks, enhanced separately, and merged back together.

### In Profiles

Set the `AI_ENHANCEMENT` and `PROMPT` fields:

```ini
AI_ENHANCEMENT=openrouter   # or: n, local, anthropic, openai, qwen2.5-1.5b, distilgpt2, ...
PROMPT=prompt-refinement.txt   # a file in OpenAIYouTubeTranscriber/Prompt/
```

## Output Files

- **Transcripts**: `OpenAIYouTubeTranscriber/Transcript/`
- **Downloaded audio**: `OpenAIYouTubeTranscriber/Audio/`
- **Downloaded video**: `OpenAIYouTubeTranscriber/Video/`
- **Video without audio**: `OpenAIYouTubeTranscriber/VideoWithoutAudio/`

Transcript filenames include the detected language in brackets for non-English content:

- `video_title.txt` (English)
- `video_title [es].txt` (Spanish)
- `video_title [fr].txt` (French)

## Troubleshooting

### FFmpeg not found

```
ERROR: ffmpeg is not found in the system PATH.
```

FFmpeg isn't installed or isn't on your PATH. See [Prerequisites](#prerequisites), then verify with `ffmpeg -version`.

### YouTube downloads failing

YouTube changes its internals regularly and the downloader occasionally needs an update:
```bash
pip install --upgrade pytubefix
```

If it still fails, check the [issue tracker](https://github.com/Ruinan-Ding/OpenAI-YouTube-Transcriber/issues) to see whether it's a known problem.

### Out of memory

Whisper models have different memory requirements:

- `tiny` — ~1GB RAM (fastest, least accurate)
- `base` — ~2GB RAM (good default)
- `small` — ~3GB RAM (noticeably better)

On machines with limited RAM, stick with `tiny` or `base`.

### Poor transcription quality

1. Try a larger model — accuracy improves at the cost of speed
2. Check the audio quality; heavy background noise degrades results
3. Make sure the language setting matches the content
4. For English content, try the English-specific model option

### Not enough disk space

- 1080p video: 500MB–2GB depending on length
- Audio: roughly 5–50MB per minute
- Whisper models: 140MB (tiny) to ~3GB (large), downloaded once

If space is tight, skip the video download — audio is all that's needed for transcription.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

Development setup:

```bash
make dev
```

Or without `make`:
```bash
pip install -r requirements-dev.txt
```

Common tasks:
```bash
make lint    # Check for code quality issues
make format  # Auto-fix formatting
make run     # Run the app
```

## Tips

### Video IDs

YouTube video IDs are exactly 11 characters (letters, numbers, dashes, underscores). The script extracts the ID from any URL format:

- `youtube.com/watch?v=jNQXAC9IVRw` → `jNQXAC9IVRw`
- `youtu.be/jNQXAC9IVRw` → `jNQXAC9IVRw`
- `youtube.com/watch?v=jNQXAC9IVRw&t=30s` → `jNQXAC9IVRw`

You can also paste just the ID.

### Cleaning up transcripts manually

The built-in [AI Transcript Enhancement](#ai-transcript-enhancement) automates this, but a transcript can also be pasted into any LLM with a prompt like:

```
Correct the grammatical and punctuation errors in this transcript.
Keep all the original content—don't summarize or skip anything.
[transcript]
```

```
Turn this transcript into a nicely formatted document with section headers.
Fix grammar but keep everything else the same.
[transcript]
```

```
What are the main takeaways from this transcript?
List the most important points.
[transcript]
```

### Profiles for recurring workflows

Create one profile per use case, for example:

- Meetings: base model, English
- Podcasts: medium model, auto-detect language
- Lectures: large model, specific language
- Short clips: tiny model, English

### Supported file formats

- **Audio**: MP3, WAV, FLAC, OGG, M4A
- **Video**: MP4, AVI, MOV, MKV, WebM

Anything FFmpeg can read should work.

### Console command

If installed with `pip install -e .`:
```bash
openai-youtube-transcriber
```

## Known Issues

- **Punctuation** — Whisper doesn't always place commas and periods correctly; AI enhancement usually fixes this.
- **Uncommon words** — domain-specific jargon and unusual names may be transcribed incorrectly and can need manual review.
- **Very long videos** — content over ~3 hours may produce fragmented transcriptions that need cleanup.

## Supported Languages

Whisper handles [99+ languages](https://github.com/openai/whisper#supported-languages). Common codes:

| Language | Code | Language | Code |
|----------|------|----------|------|
| English | `en` | Spanish | `es` |
| French | `fr` | German | `de` |
| Chinese | `zh` | Japanese | `ja` |
| Russian | `ru` | Arabic | `ar` |
| Portuguese | `pt` | Hindi | `hi` |

See [Whisper's documentation](https://github.com/openai/whisper#supported-languages) for the full list.

## License

BSD 3-Clause License. See [LICENSE](LICENSE).

## Acknowledgments

- [OpenAI Whisper](https://github.com/openai/whisper) for speech recognition
- [pytubefix](https://github.com/JuanBindez/pytubefix) for YouTube downloading
- [langdetect](https://github.com/Mimino666/langdetect) for language detection

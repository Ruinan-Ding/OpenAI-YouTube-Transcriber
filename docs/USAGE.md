# Usage

## Basic Usage

```bash
python OpenAIYouTubeTranscriber.py
```

The script walks through a series of prompts, then downloads and/or transcribes.

## The Prompts

**1. Source**

Three input options:
- **YouTube URL**: `https://www.youtube.com/watch?v=jNQXAC9IVRw`
- **Video ID only**: `jNQXAC9IVRw` (the 11-character code)
- **Local file**: `/path/to/audio.mp3` or `/path/to/video.mp4`

The video ID is extracted from any YouTube URL format — full URLs, short links (`youtu.be/...`), or the bare ID. Query parameters such as timestamps (`&t=30s`) or playlist info (`&list=...`) are stripped automatically.

**2. Download options**
- Download the video file? (yes/no)
- If yes, which resolution?
- Download the audio file separately? (yes/no)

**3. Transcription settings**
- Which Whisper model (tiny through large-v3)
- Which language (en, es, fr, ...)
- For English: whether to use the English-specific model (usually more accurate)

**4. Run again?**
- Start another transcription immediately or exit

## Profiles

For workflows you run repeatedly, save the answers as a profile.

### Saving a Profile

After a run, the script asks:
```
Do you want to save these settings as a profile? (y/N): y
```

Answering yes creates a reusable profile file.

### Loading a Profile

On the next run:
```
Available profiles:
1. profile.txt
2. profile1-video_downloader.txt

Pick one (1-2, or 'no' to skip): 1
```

### Editing a Profile

Profiles live in `OpenAIYouTubeTranscriber/Profile/` as plain text files:

```ini
URL=https://www.youtube.com/watch?v=example
DOWNLOAD_VIDEO=y
RESOLUTION=highest
DOWNLOAD_AUDIO=n
TRANSCRIBE_AUDIO=y
MODEL_CHOICE=base
TARGET_LANGUAGE=en
USE_EN_MODEL=n
REPEAT=n
```

The `URL` field accepts any supported format:
- Full URLs: `https://www.youtube.com/watch?v=jNQXAC9IVRw`
- Short URLs: `https://youtu.be/jNQXAC9IVRw`
- The bare video ID: `jNQXAC9IVRw`
- URLs with extra parameters: `https://www.youtube.com/watch?v=jNQXAC9IVRw&t=30s` (parameters are ignored)

## Output Locations

- **Transcripts** — `OpenAIYouTubeTranscriber/Transcript/`
- **Audio files** — `OpenAIYouTubeTranscriber/Audio/`
- **Video files** — `OpenAIYouTubeTranscriber/Video/`
- **Video without audio** — `OpenAIYouTubeTranscriber/VideoWithoutAudio/`

## Examples

**Transcribe using just the video ID:**
```bash
python OpenAIYouTubeTranscriber.py
# URL: jNQXAC9IVRw
# Detected video ID, using: https://www.youtube.com/watch?v=jNQXAC9IVRw
# Download video? n
# Download audio? n
# Transcribe? y
# Model? 2 (base)
# Language? en
```

**Transcribe a YouTube video without downloading anything:**
```bash
python OpenAIYouTubeTranscriber.py
# URL: https://www.youtube.com/watch?v=jNQXAC9IVRw
# Download video? n
# Download audio? n
# Transcribe? y
# Model? 2 (base)
# Language? en
```

**Download the video and transcribe it:**
```bash
python OpenAIYouTubeTranscriber.py
# Select a profile with DOWNLOAD_VIDEO=y
```

**Transcribe a local file:**
```bash
python OpenAIYouTubeTranscriber.py
# URL: /Users/you/Downloads/my_podcast.mp3
# Download? n (it's already local)
# Transcribe? y
```

Short URLs (`https://youtu.be/...`) work the same way as full URLs.

## Supported Languages

See [Whisper's supported languages](https://github.com/openai/whisper#supported-languages) for the full list.

Common codes:
- `en` - English
- `es` - Spanish
- `fr` - French
- `de` - German
- `zh` - Chinese
- `ja` - Japanese

## Troubleshooting

### ffmpeg not found
Install ffmpeg:
- **Windows**: `scoop install ffmpeg` or download from [ffmpeg.org](https://ffmpeg.org/download.html)
- **macOS**: `brew install ffmpeg`
- **Linux**: `sudo apt install ffmpeg`

### Out of memory
Use smaller models (tiny, base) on machines with limited RAM.

### Poor transcription quality
- Try larger models (medium, large)
- Ensure audio is clear and in the target language
- Use the English-specific model for English content

# How to Use the Transcriber

## Basic Usage

Just run it:

```bash
python OpenAIYouTubeTranscriber.py
```

The script will ask you some questions and then do its thing.

## What It Asks You

**1. Where's the audio?**
- YouTube link: `https://www.youtube.com/watch?v=...`
- Local file: `/path/to/audio.mp3` or `/path/to/video.mp4`

**2. Download options**
- Want the video file? (yes/no)
- If yes, what resolution?
- Want just the audio file separately? (yes/no)

**3. Transcription settings**
- Which Whisper model? (tiny through large-v3)
- What language? (en, es, fr, etc.)
- For English: want the English-specific model? Usually gives better results

**4. Run again?**
- Do another transcription right away or exit?

## Using Profiles (The Smart Way)

If you find yourself running the same workflow repeatedly, use profiles.

### Saving a Profile

After running it once, it'll ask:
```
Do you want to save these settings as a profile? (y/N): y
```

Say yes, and it creates a profile file you can reuse.

### Loading a Profile

Next time you run it, you'll see:
```
Available profiles:
1. profile.txt
2. profile1-video_downloader.txt

Pick one (1-2, or 'no' to skip): 1
```

Just pick one and you're done—no more answering the same questions.

### Editing a Profile

Profiles live in `OpenAIYouTubeTranscriber/Profile/` and are just plain text files. Open one in your editor:

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

Change whatever you want. Pretty self-explanatory.

## Where Stuff Gets Saved

Everything goes into organized folders:

- **Transcripts** — `OpenAIYouTubeTranscriber/Transcript/`
- **Audio files** — `OpenAIYouTubeTranscriber/Audio/`
- **Video files** — `OpenAIYouTubeTranscriber/Video/`
- **Video without audio** (rare) — `OpenAIYouTubeTranscriber/VideoWithoutAudio/`

## Real Examples

**Just transcribe a YouTube video, don't download anything:**
```bash
python OpenAIYouTubeTranscriber.py
# URL: https://www.youtube.com/watch?v=jNQXAC9IVRw
# Download video? n
# Download audio? n
# Transcribe? y
# Model? 2 (base is solid)
# Language? en
```

**Download the video and transcribe it:**
```bash
python OpenAIYouTubeTranscriber.py
# Select a profile that has DOWNLOAD_VIDEO=y
# Let it do its thing
```

**Transcribe a local file:**
```bash
python OpenAIYouTubeTranscriber.py
# URL: /Users/you/Downloads/my_podcast.mp3
# Download? n (it's already local)
# Transcribe? y
# Pick your settings
```

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
Use smaller models (tiny, base) for lower-end systems.

### Poor transcription quality
- Try larger models (medium, large)
- Ensure audio is clear and in the target language
- Use English-specific model for English content
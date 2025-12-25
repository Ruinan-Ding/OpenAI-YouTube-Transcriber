# Usage Guide

## Running the Script

```bash
python OpenAIYouTubeTranscriber.py
```

## Interactive Mode

When you run the script without a profile, you'll be prompted to:

1. **Enter YouTube URL or local file path**
   - YouTube: `https://www.youtube.com/watch?v=...`
   - Local file: `/path/to/audio.mp3` or `/path/to/video.mp4`

2. **Download options**
   - Download video? (y/N)
   - If yes, choose resolution (highest, lowest, or specific)
   - Download audio separately? (y/N)

3. **Transcription options**
   - Transcribe the audio? (Y/n)
   - Select Whisper model (tiny, base, small, medium, large-v1, large-v2, large-v3)
   - Target language (e.g., 'en', 'es', 'fr')
   - Use English-specific model? (y/N) - only for English content

4. **Repeat?** - Run another transcription immediately

## Profile-Based Usage

### Creating a Profile

After running a successful session, you can save it as a profile:

```
Do you want to create a profile from this session? (y/N): y
```

This creates a profile file in `OpenAIYouTubeTranscriber/Profile/` directory.

### Using a Profile

Profiles are automatically detected and offered on startup:

```
Available profiles:
1. profile.txt
2. profile1.txt
3. profile2.txt

Select a profile (number or name, default 1. profile.txt, or 'no' to skip): 1
```

### Profile Format

Each profile is a text file with configurable fields:

```ini
URL=<Insert_YouTube_link_or_local_path_to_audio_or_video>
DOWNLOAD_VIDEO=n
NO_AUDIO_IN_VIDEO=
RESOLUTION=
DOWNLOAD_AUDIO=n
TRANSCRIBE_AUDIO=y
MODEL_CHOICE=base
TARGET_LANGUAGE=en
USE_EN_MODEL=n
REPEAT=
```

Edit any field directly in the profile file to customize behavior.

## Output Files

- **Transcripts**: `OpenAIYouTubeTranscriber/Transcript/`
- **Audio**: `OpenAIYouTubeTranscriber/Audio/`
- **Video**: `OpenAIYouTubeTranscriber/Video/`
- **Video (no audio)**: `OpenAIYouTubeTranscriber/VideoWithoutAudio/`

## Examples

### Example 1: Simple Transcription
```bash
python OpenAIYouTubeTranscriber.py
# Enter: https://www.youtube.com/watch?v=jNQXAC9IVRw
# Download video? n
# Download audio? n
# Transcribe? y (default)
# Model? 2 (base)
# Language? en (default)
```

### Example 2: Download and Transcribe
```bash
# Using profile1.txt (video downloader)
python OpenAIYouTubeTranscriber.py
# Select profile: 1
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
# Changelog

## [1.0.0] - 2024

**Initial Release**

First stable version of the transcriber. Everything you need to grab transcripts from YouTube videos or local files.

### What's Included

- Download audio and video from YouTube
- Transcribe with OpenAI's Whisper (7 model options)
- Automatic language detection
- Save your settings as reusable profiles
- Local file transcription (MP3, MP4, WAV, etc.)
- Support for 99+ languages
- Works on Windows, macOS, and Linux

### The Nitty Gritty

- **pytubefix** for reliable YouTube downloads
- **OpenAI Whisper** for the actual transcription
- **langdetect** to figure out what language you're transcribing
- **moviepy** for handling video stuff
- **python-dotenv** for configuration
- **tenacity** for retrying when things go wrong

---

## What's Next

We're thinking about:
- Downloading whole playlists at once
- Processing multiple files in batch
- Translating transcripts to other languages
- Generating subtitle files (.srt, .vtt formats)
- Maybe a web interface down the road
- API access if enough people want it
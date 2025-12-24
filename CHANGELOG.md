# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2024-01-XX

### Added
- Initial release of OpenAI YouTube Transcriber
- YouTube video and audio download functionality
- OpenAI Whisper integration for transcription
- Language detection using langdetect
- Profile-based configuration system
- Interactive and profile-based modes
- Support for multiple Whisper models (tiny, base, small, medium, large-v1, v2, v3)
- Multi-language transcription support
- Video and audio stream quality selection
- Automatic video/audio combination with ffmpeg

### Features
- Download audio from YouTube videos
- Extract audio from local video files
- Transcribe audio to text using OpenAI's Whisper
- Auto-detect language of transcription
- Save transcriptions as .txt files
- Create reusable profiles for common workflows
- Support for 99+ languages
- Cross-platform compatibility (Windows, macOS, Linux)

### Dependencies
- pytubefix - YouTube downloading
- openai-whisper - Speech-to-text
- langdetect - Language detection
- moviepy - Video processing
- python-dotenv - Configuration management
- tenacity - Retry logic

## [Unreleased]

### Planned
- Playlist support
- Batch processing
- Translation to other languages
- Subtitle generation (.srt, .vtt)
- Web interface
- API support
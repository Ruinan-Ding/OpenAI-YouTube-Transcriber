# Changelog

## [Unreleased]

### Changed

- **Downloads now use `yt-dlp` instead of `pytubefix`.** YouTube serves SABR-only
  streams that require a fully attested PoToken, which pytubefix's botGuard
  cold-start token no longer satisfies; downloads failed with
  `SABRError: ... PoToken PENDING`, and every other pytubefix client was either
  bot-detected or cut off with HTTP 403 partway through the file. `yt-dlp`
  replaces both the metadata and download paths. `py_mini_racer` is dropped with
  it, having existed only for pytubefix's JS interpreter.

### Fixed

- AI enhancement no longer duplicates text at every chunk boundary. Chunks were
  overlapped by 400 characters and rejoined by exact string match, but both
  copies of the overlap had been rewritten by the model, so no match survived
  and the overlap was pasted in twice - 1,604 duplicated characters in a
  47,000-character transcript. On repetitive speech the same match ran past the
  overlap and silently deleted whole sentences. Chunks no longer overlap; they
  already split on sentence boundaries.
- Multi-language videos are transcribed in their original language. Dubbed tracks
  are published at the same bitrate as the original, so picking the
  highest-bitrate audio stream chose an arbitrary language - a video whose top
  stream was the German dub was transcribed from German.
- A refused download prints one actionable line instead of a traceback, and video
  downloads retry like audio downloads always have.
- Playlist and channel URLs are rejected instead of accepted as a single video.
  They would have downloaded every entry into one output path, each overwriting
  the last. `youtube-nocookie.com` embed URLs are now accepted.
- A YouTube address typed without `https://` is accepted instead of rejected
  as invalid input.
- An invalid URL entered before the "fetch available resolutions" step re-prompts
  instead of exiting and discarding every answer already given.
- A non-YouTube web address in a profile re-prompts. It printed
  "Only YouTube URLs supported" and then used the address anyway.
- Loading a profile no longer makes two extra network round trips to validate a
  URL that is validated again moments later, and choosing `fetch` for the
  resolution no longer fetches the same metadata twice.
- Cleanup failures after a successful run no longer abort it. Removing the temp
  audio could raise `PermissionError` on Windows after the transcript was
  already saved.

## [1.1.0] - 2026-07-31

### Fixed

- `MODEL_CHOICE` in a profile is no longer case-sensitive. `Large-v3` passed validation
  but silently transcribed with `base`.
- `TARGET_LANGUAGE` accepts full language names as the interactive prompt always has.
  A profile written with `spanish` failed to load back. Values are now normalised to
  Whisper's 2-letter code, so `english` correctly selects the `.en` models.
- Transcription failures are no longer saved as the transcript. An error string was
  written to a `.txt`, opened in an editor, and (when enabled) sent to a paid AI
  backend for "enhancement".
- Transcripts with no terminal punctuation are chunked correctly. Noisy audio produced
  a single oversized chunk that silently overflowed the model's context window.
  Splitting now falls on word boundaries.
- The detected language no longer leaks region tags or detection failures into the
  filename (`Title [zh-cn].txt`, `Title [unknown].txt`).
- Audio downloaded for a video merge is reused for transcription instead of being
  downloaded a second time.
- Downloaded audio is kept when transcription fails, so a retry does not re-download it.
- A failing file-opener no longer reports a successfully written transcript as an error.
- `RESOLUTION=f` in a profile is expanded to `fetch`, matching the interactive prompt.

### Changed

- **Requires Python 3.10+.** The code has used `match`/`case` since 1.0.0, but the
  package declared `>=3.6`; installing on 3.6-3.9 succeeded and then failed at import.
- ffmpeg is invoked without a shell.
- `tiktoken` dropped from requirements; it was never imported.
- black removed from the tooling. It targets 88 columns and double quotes against a
  100-column, single-quoted codebase. `flake8` + `flake8-bugbear` is the standard and
  is now clean.
- Added `test_transcriber.py` and a `make test` target.

## [1.0.0] - 2024

Initial release.

### Features

- Download audio and video from YouTube
- Transcription with OpenAI Whisper (7 model options)
- Automatic language detection
- Reusable settings profiles
- Local file transcription (MP3, MP4, WAV, etc.)
- Support for 99+ languages
- Windows, macOS, and Linux support

### Dependencies

- **pytubefix**: YouTube downloads
- **OpenAI Whisper**: transcription
- **langdetect**: language detection
- **moviepy**: video handling
- **python-dotenv**: configuration
- **tenacity**: retry logic

## Planned

- Playlist downloads
- Batch processing of multiple files
- Transcript translation
- Subtitle file generation (.srt, .vtt)
- Web interface

<div align="center">
  <img src="https://capsule-render.vercel.app/api?type=waving&color=0:FF6B6B,100:4ECDC4&height=120&section=header&text=YouTube%20Transcriber&fontSize=45&fontColor=fff&animation=fadeIn" width="100%"/>
</div>

<div align="center">
  
  ![Python](https://img.shields.io/badge/Python-3.6+-3776AB?style=for-the-badge&logo=python&logoColor=white)
  ![OpenAI](https://img.shields.io/badge/OpenAI-Whisper-412991?style=for-the-badge&logo=openai&logoColor=white)
  ![License](https://img.shields.io/badge/License-BSD%203--Clause-blue?style=for-the-badge)
  ![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey?style=for-the-badge)
  
</div>

<br>

Ever wanted to grab a transcript from a YouTube video without doing it manually? This tool makes it dead simple. It downloads videos or audio from YouTube (or works with local files), then uses OpenAI's Whisper to transcribe everything. Supports 99+ languages with automatic language detection, and you can save your favorite settings as profiles so you don't have to reconfigure it every time.

<div align="center">
  <img src="https://raw.githubusercontent.com/andreasbm/readme/master/assets/lines/colored.png" width="100%"/>
</div>

## 🚀 Quick Start

Get up and running in about 30 seconds:

```bash
pip install --upgrade -r OpenAIYouTubeTranscriber/requirements.txt
python OpenAIYouTubeTranscriber.py
```

Then just follow the prompts. That's it.

<div align="center">
  <img src="https://raw.githubusercontent.com/andreasbm/readme/master/assets/lines/colored.png" width="100%"/>
</div>

## What's in Here

- [Features](#-features)
- [Prerequisites](#-prerequisites)
- [Installation](#-installation)
- [How to Use It](#-usage)
- [Profiles (save your settings)](#-profiles)
- [Where Your Files Go](#-output-files)
- [Stuck? Check Here](#-troubleshooting)
- [Want to Help?](#-contributing)
- [Pro Tips](#-tips--tricks)
- [Known Quirks](#-known-issues)

<div align="center">
  <img src="https://raw.githubusercontent.com/andreasbm/readme/master/assets/lines/colored.png" width="100%"/>
</div>

## ✨ What You Can Do

**Simple Interface** — No complicated configuration. Just answer a few questions and it handles the rest.

**Flexible Input Options** — Give it a YouTube URL, just the 11-character video ID, or point it at a local media file. All of these work:
- Full URL: `https://www.youtube.com/watch?v=jNQXAC9IVRw`
- Short URL: `https://youtu.be/jNQXAC9IVRw`
- Just the video ID: `jNQXAC9IVRw`
- Local file: `/path/to/audio.mp3`

The script automatically extracts just the video ID from URLs and ignores things like timestamps or playlist parameters.

**Handles 99+ Languages** — Whisper's got you covered whether it's English, Mandarin, Arabic, or something more obscure. Language detection is automatic.

**Pick Your Model** — Want speed? Use `tiny`. Need accuracy? Go with `large-v3`. Options are tiny, base, small, medium, large-v1, large-v2, and large-v3.

**Save Profiles** — Running the same transcription task repeatedly? Save your settings as a profile and reuse them next time.

**Video Quality Control** — Want 1080p or prefer smaller file sizes? You can choose, or let it auto-select.

**Cross-Platform** — Works on Windows, macOS, and Linux without any special tweaks.

**Smart Audio Handling** — Automatically extracts audio from videos, combines them if needed, handles format conversions.

<div align="center">
  <img src="https://skillicons.dev/icons?i=python,github" alt="Tech Stack" />
  <br><br>
  <p><em>Powered by OpenAI Whisper, pytubefix, and FFmpeg</em></p>
</div>

<div align="center">
  <img src="https://raw.githubusercontent.com/andreasbm/readme/master/assets/lines/colored.png" width="100%"/>
</div>

## 📦 Before You Start

You'll need a few things installed on your machine. Don't worry—none of this is complicated.

**Python 3.6+** is required. Check if you have it by running `python --version`. If you need to install:
- **Windows**: [phoenixnap.com guide](https://phoenixnap.com/kb/how-to-install-python-3-windows)
- **macOS**: [docs.python-guide.org](https://docs.python-guide.org/starting/install3/osx/)
- **Linux**: [phoenixnap.com Ubuntu guide](https://phoenixnap.com/kb/how-to-install-python-3-ubuntu)

**pip** almost certainly came with Python, but verify it's there: `python -m pip --version`

**FFmpeg** is the big one—it handles all the audio/video processing. This is what often trips people up, so pay attention:

On **Windows**, open PowerShell as admin and run:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
Invoke-RestMethod -Uri https://get.scoop.sh | Invoke-Expression
scoop install ffmpeg
```
Or just grab it from [ffmpeg.org](https://ffmpeg.org/download.html) if you prefer the manual route.

On **macOS**, if you have Homebrew: `brew install ffmpeg`. Don't have Homebrew? You should. Google it real quick.

On **Linux** (Ubuntu/Debian): `sudo apt update && sudo apt install ffmpeg`

<div align="center">
  <img src="https://raw.githubusercontent.com/andreasbm/readme/master/assets/lines/colored.png" width="100%"/>
</div>

## 💾 Getting Set Up

First, clone the repo:
```bash
git clone https://github.com/Ruinan-Ding/OpenAI-YouTube-Transcriber.git
cd OpenAI-YouTube-Transcriber
```

**Virtual environment** (highly recommended): This keeps your dependencies isolated from other Python projects.
```bash
python -m venv venv

# On Windows:
.\venv\Scripts\activate

# On macOS/Linux:
source venv/bin/activate
```

Now install the dependencies:
```bash
pip install --upgrade -r OpenAIYouTubeTranscriber/requirements.txt
```

That's the basic setup. If you want to use `youtube-transcriber` as a command from anywhere on your system:
```bash
pip install -e .
```

This installs the package in "editable mode" so you can run `youtube-transcriber` from the terminal without having to be in the repo directory.

<div align="center">
  <img src="https://raw.githubusercontent.com/andreasbm/readme/master/assets/lines/colored.png" width="100%"/>
</div>

## 🎯 How to Use It

Just run it:
```bash
python OpenAIYouTubeTranscriber.py
```

The script will walk you through the process step-by-step. You'll be asked:

1. Where to get the audio (YouTube link or local file)
2. Whether you want to download the video
3. Whether you want to download just the audio
4. What video resolution (if downloading video)
5. Which Whisper model to use for transcription
6. What language to transcribe to
7. Whether to use the English-specific Whisper model
8. Whether you want to run again immediately

Here's what it looks like in action:

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

**Note:** You can enter the full YouTube URL, short URL (`youtu.be/...`), or just the 11-character video ID. The script extracts the ID automatically and ignores query parameters like timestamps (`&t=30s`) or playlist info (`&list=PLxyz`).

<div align="center">
  <img src="https://raw.githubusercontent.com/andreasbm/readme/master/assets/lines/colored.png" width="100%"/>
</div>

## 📁 Profiles: Save Your Setup

If you find yourself running the same transcription over and over, profiles are your friend. They let you save all your settings so you don't have to answer the same questions every time.

When you start the script, it automatically finds any saved profiles:

```
Available profiles:
1. profile.txt
2. profile1.txt
3. profile2.txt

Select a profile (number or name, default 1. profile.txt, or 'no' to skip):
```

Just pick one and it'll load all your saved settings. Way faster than answering prompts every time.

### Creating Your Own Profile

After running the script successfully, you'll get asked if you want to save that session as a profile. Say yes, and it'll create a new profile file with whatever settings you just used. Next time you run the same workflow, you can just pick that profile instead of reconfiguring everything.

### What's Inside a Profile

Profiles are just text files in `OpenAIYouTubeTranscriber/Profile/`. You can edit them directly if you want:

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
REPEAT=n
```

Pretty straightforward. Most of it is self-explanatory.

**For the URL field**, you can use any of these formats:
- Full URL: `https://www.youtube.com/watch?v=jNQXAC9IVRw`
- Short URL: `https://youtu.be/jNQXAC9IVRw`
- Just the video ID: `jNQXAC9IVRw`
- With timestamp/playlist params: `https://www.youtube.com/watch?v=jNQXAC9IVRw&t=30s` (params ignored)

The script only cares about the 11-character video ID—everything else gets stripped out.

### Built-In Profiles

We've included a few pre-configured profiles to get you started:

- **profile.txt** — Just transcribe (no downloads)
- **profile1-video_downloader.txt** — Download video with audio and transcribe it
- **profile2-audio_downloader.txt** — Download just the audio and transcribe
- **profile0-translator.txt** — Transcribe in different languages

<div align="center">
  <img src="https://raw.githubusercontent.com/andreasbm/readme/master/assets/lines/colored.png" width="100%"/>
</div>

## 📤 Where Your Files End Up

Everything gets organized into separate folders:

- **Transcripts** go here: `OpenAIYouTubeTranscriber/Transcript/`
- **Downloaded audio**: `OpenAIYouTubeTranscriber/Audio/`
- **Downloaded video**: `OpenAIYouTubeTranscriber/Video/`
- **Video without audio** (rare edge case): `OpenAIYouTubeTranscriber/VideoWithoutAudio/`

The transcript filenames include the detected language in brackets, so you can tell at a glance what language it is:

- `video_title.txt` (English)
- `video_title [es].txt` (Spanish)
- `video_title [fr].txt` (French)

<div align="center">
  <img src="https://raw.githubusercontent.com/andreasbm/readme/master/assets/lines/colored.png" width="100%"/>
</div>

## 🔧 Running Into Issues?

### FFmpeg Not Found

If you see this:
```
ERROR: ffmpeg is not found in the system PATH.
```

FFmpeg isn't installed or isn't accessible. Go back to the Prerequisites section and install it. Then verify it's working: `ffmpeg -version`

### YouTube Downloads Are Failing

YouTube changes how it works pretty often, and sometimes the downloader needs an update. Try this:
```bash
pip install --upgrade pytubefix
```

Then try again. If it still fails, YouTube may have changed something major. Check the [issue tracker](https://github.com/Ruinan-Ding/OpenAI-YouTube-Transcriber/issues) to see if others are having the same problem.

### Running Out of Memory

If the transcription crashes or your system gets sluggish, you're probably hitting memory limits. The different Whisper models have different resource needs:

- `tiny` — ~1GB RAM (fastest, but less accurate)
- `base` — ~2GB RAM (good middle ground)
- `small` — ~3GB RAM (noticeably better)

If you're on a older machine with limited RAM, stick with `tiny` or `base`. The quality difference usually isn't huge unless you're dealing with accents or low-quality audio.

### The Transcription Doesn't Sound Right

A few things to check:

1. Did you pick the right model? Larger models = better accuracy but slower
2. Is the audio clear? Lots of background noise = worse transcription
3. Make sure the language is set correctly
4. For English content, try the English-specific model option—it usually does better

### Not Enough Disk Space

Large videos take up a lot of disk space:

- 1080p video: 500MB to 2GB depending on length
- Audio file: about 5-50MB per minute
- Whisper models: 140MB (tiny) up to 3GB (large) — only downloaded once though

If you're tight on space, don't download the video, just the audio. That's usually what you need for transcription anyway.

<div align="center">
  <img src="https://raw.githubusercontent.com/andreasbm/readme/master/assets/lines/colored.png" width="100%"/>
</div>

## 🤝 Contributing

Found a bug? Have a cool feature idea? Want to improve the code? Awesome, check out [CONTRIBUTING.md](CONTRIBUTING.md) for how to get involved.

If you want to contribute code, you'll need to set up the dev environment:

```bash
make dev
```

Or if you don't have `make`:
```bash
pip install -r requirements-dev.txt
```

Then you can lint your code and make sure it's formatted properly:
```bash
make lint    # Check for code quality issues
make format  # Auto-fix formatting
make run     # Test the app
```

<div align="center">
  <img src="https://raw.githubusercontent.com/andreasbm/readme/master/assets/lines/colored.png" width="100%"/>
</div>

## 💡 Tips for Better Results

### Quick Video ID Tips

YouTube video IDs are always exactly 11 characters made up of letters, numbers, dashes, and underscores. When you give the script a URL, it automatically extracts just the ID:

- `youtube.com/watch?v=jNQXAC9IVRw` → uses `jNQXAC9IVRw`
- `youtu.be/jNQXAC9IVRw` → uses `jNQXAC9IVRw`
- `youtube.com/watch?v=jNQXAC9IVRw&t=30s` → still just uses `jNQXAC9IVRw`

You can save time by copying just the ID instead of the whole URL.

### Improving Bad Transcripts

If Whisper mangles something, you can feed the transcript to an LLM to fix it up:

**Fix grammar and punctuation:**
```
Correct the grammatical and punctuation errors in this transcript.
Keep all the original content—don't summarize or skip anything.
[paste your transcript here]
```

**Clean up structure:**
```
Turn this transcript into a nicely formatted document with section headers.
Fix grammar but keep everything else the same.
[paste your transcript here]
```

**Pull out key points:**
```
What are the main takeaways from this transcript? 
List the most important points.
[paste your transcript here]
```

This is super useful for lectures or meetings where you want a clean version later.

### Multiple Profiles for Different Situations

Think about the different things you transcribe regularly. Make a profile for each:

- **Meetings**: base model, English
- **Podcasts**: medium model, auto-detect language  
- **Classes/Lectures**: large model, specific language
- **Social Media**: tiny model (fast), English

Then you just pick the right one instead of reconfiguring every time.

### What File Formats Work

Local files you can transcribe:

- **Audio**: MP3, WAV, FLAC, OGG, M4A
- **Video**: MP4, AVI, MOV, MKV, WebM

Basically anything that has audio should work. If it doesn't, FFmpeg probably doesn't support it.

### Using from Command Line

If you installed with `pip install -e .`:
```bash
youtube-transcriber
```

Much cleaner than typing out the whole `python OpenAIYouTubeTranscriber.py` every time.

<div align="center">
  <img src="https://raw.githubusercontent.com/andreasbm/readme/master/assets/lines/colored.png" width="100%"/>
</div>

## ⚠️ Known Quirks

A few things to be aware of:

**Punctuation sometimes gets weird.** Whisper doesn't always nail comma placement or period locations. An LLM cleanup usually fixes this though.

**Uncommon words might be wrong.** Domain-specific jargon, unusual names, or industry terms sometimes get transcribed incorrectly. If you're transcribing something specialized, you might need to do a manual review.

**Really long videos can get choppy.** Anything over 3+ hours might have fragmented transcriptions. Usually still usable though, just needs some cleanup.

All of these are fixable by editing the transcript yourself or running it through an LLM for post-processing.

<div align="center">
  <img src="https://raw.githubusercontent.com/andreasbm/readme/master/assets/lines/colored.png" width="100%"/>
</div>

## 🌍 Languages Supported

Whisper handles [99+ languages](https://github.com/openai/whisper#supported-languages). Here are the common ones:

| Language | Code | Language | Code |
|----------|------|----------|------|
| English | `en` | Spanish | `es` |
| French | `fr` | German | `de` |
| Chinese | `zh` | Japanese | `ja` |
| Russian | `ru` | Arabic | `ar` |
| Portuguese | `pt` | Hindi | `hi` |

Check [Whisper's docs](https://github.com/openai/whisper#supported-languages) for the full list if you need something else.

<div align="center">
  <img src="https://raw.githubusercontent.com/andreasbm/readme/master/assets/lines/colored.png" width="100%"/>
</div>

## 📜 License

BSD 3-Clause License. See [LICENSE](LICENSE) for the full legal stuff.

<div align="center">
  <img src="https://raw.githubusercontent.com/andreasbm/readme/master/assets/lines/colored.png" width="100%"/>
</div>

## Thanks

Big thanks to:

- **OpenAI** for Whisper—seriously impressive speech recognition
- **pytubefix** for keeping YouTube downloading reliable
- **langdetect** for the language detection magic

## 📞 Something Broken or Have Ideas?

Found a bug? [Open an issue](https://github.com/Ruinan-Ding/OpenAI-YouTube-Transcriber/issues).

Got questions? [Start a discussion](https://github.com/Ruinan-Ding/OpenAI-YouTube-Transcriber/discussions).

Want to contribute? Check out [CONTRIBUTING.md](CONTRIBUTING.md).

<div align="center">
  <img src="https://raw.githubusercontent.com/andreasbm/readme/master/assets/lines/colored.png" width="100%"/>
  
  <br>
  
  **Made with ❤️ for easier transcriptions**
  
  <br>
  
  <sub>Happy transcribing! 🎉</sub>
</div>
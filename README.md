# OpenAI YouTube Transcriber

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
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
- [Acknowledgments](#acknowledgments)

## Features

- **Interactive CLI**: answer a few prompts; no configuration files required.
- **Flexible input**: accepts any of the following:
  - Full URL: `https://www.youtube.com/watch?v=jNQXAC9IVRw`
  - Short URL: `https://youtu.be/jNQXAC9IVRw`
  - Video ID: `jNQXAC9IVRw`
  - Local file: `/path/to/audio.mp3`
  - A transcript to refine, or `S` to pick one: `Transcript/Raw/Me at the zoo.txt`
  - Several of any of those, separated by commas or spaces, run in turn: `clip.mp4, youtu.be/vid3, s`

  The 11-character video ID is extracted from any URL format; query parameters such as timestamps (`&t=30s`) or playlist info (`&list=...`) are ignored.
- **99+ languages** with automatic language detection, and several at once: `en,fr,ja` is three transcripts from one download.
- **Selectable Whisper model**: tiny, base, small, medium, large-v1, large-v2, or large-v3, trading speed for accuracy.
- **Profiles**: save a session's settings to a file and reuse them.
- **Three deliverables, independently**: the merged video, a video-only file with no audio track, and the audio on its own. Each has its own resolution and format, so they never fight over one setting.
- **Lists everywhere**: `144p, 720p` with `mp4, mkv` is four videos, each stream fetched once. The prompts take the same lists the profile fields do.
- **YouTube's own transcripts** saved as files beside Whisper's - the spoken language, every published track, or named ones.
- **Local files as sources**: transcribed, refined, and re-encoded into the same video, video-only and audio files a download produces.
- **Cross-platform**: Windows, macOS, and Linux.
- **Audio handling**: extracts audio from video, merges separate audio/video streams, and converts formats via FFmpeg.
- **AI transcript enhancement (optional)**: clean up the raw transcript with OpenAI, OpenRouter, or Anthropic (API key required), or a local Hugging Face model, guided by a prompt file or a custom prompt.

## Prerequisites

**Python 3.10+**: check with `python --version`. Installation guides:
- [Windows](https://phoenixnap.com/kb/how-to-install-python-3-windows)
- [macOS](https://docs.python-guide.org/starting/install3/osx/)
- [Linux (Ubuntu)](https://phoenixnap.com/kb/how-to-install-python-3-ubuntu)

**pip**: usually bundled with Python; verify with `python -m pip --version`.

**FFmpeg**: required for all audio/video processing and must be on your PATH.

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

You are asked for the source, then for each deliverable in turn. Questions in
brackets are only asked when the answer before them makes them mean something,
so a transcribe-only run answers six questions and a run that produces all three
files answers fifteen.

1. **Source** - a URL, video ID, local file, `S` to refine a transcript already on
   disk, or several of those separated by commas or spaces
2. **Download video?** - the merged video-and-audio file
   - [resolution, the audio resolution to mux in, and the container]
3. **Download a video-only file, with no audio track?**
   - [resolution and codec]
4. **Download audio?**
   - [resolution and format]
5. **Download YouTube's own transcript?** - yes, `all`, `f` to list what the video
   publishes, or language codes (skipped for a local file)
6. **Transcribe the audio?**
   - [the quality to fetch for it - asked only when nothing else is already
     putting audio on disk, since that copy is reused]
   - Whisper model, the language spoken (Enter detects it), the language to
     write, and whether to use the English-specific model
7. **Refine the transcript with AI?**
   - [backend, prompt, and whether to keep the unrefined copy in `Transcript/Raw/`]
8. **Save these settings as a profile?**
9. **Run again?**

A local source asks the same questions worded as re-encodes ("Re-encode the
video?"), because the same three files come out of it.

Example session:

```text
$ python OpenAIYouTubeTranscriber.py

Enter the YouTube video URL, video ID, local file path, or S to refine a transcript (several separated by commas or spaces run in turn): https://www.youtube.com/watch?v=jNQXAC9IVRw
Download video? (y/N): n
Download a video-only file, with no audio track? (y/N): n
Download audio? (y/N): n
Download YouTube's own transcript? (y/N, 'all', 'f' to list, or languages like 'en,fr' or 'en fr'): n
Transcribe the audio? (Y/n): y
Enter the desired audio quality for transcription (e.g., low, medium, 64, highest, lowest, or several separated by commas or spaces), or press Enter or type fetch to choose from a list:
Select Whisper model:
1. Tiny
2. Base
3. Small
4. Medium
5. Large-v1
6. Large-v2
7. Large-v3
Enter your choice (1-7 or model name, default Base): 2
Enter the language spoken in the audio (e.g., 'ja' or 'japanese'), or press Enter to detect it:
Enter the language the transcript should be in: press Enter (or 'auto') for the language spoken, 'en' to translate it into English, or several separated by commas or spaces for one transcript each. Whisper translates into English only; see https://github.com/openai/whisper#supported-languages:
Use English-specific model? (Recommended only if the video is originally in English) (y/N): n
Refine the transcript with AI? (y/N): n

[Whisper transcribes the audio...]
Saved transcript to OpenAIYouTubeTranscriber/Transcript/Me at the zoo [Whisper en].txt

Do you want to create a profile from this session? (y/N): n
Run again? Hit Enter to repeat (y/N): n
```

Every prompt with a default takes Enter for it. Blank answers to the quality and
format questions are a question, not a default: the run shows what the video
actually offers and asks which.

### Exit codes and output streams

Progress, prompts and results go to stdout; failures go to stderr, so
`python OpenAIYouTubeTranscriber.py > run.log` keeps the log readable and still
shows you what went wrong.

| exit code | meaning |
|---|---|
| `0` | the session finished, however many rounds of "Run again?" it ran |
| `1` | ffmpeg or a required directory was missing, or the run's only source could not be fetched |

A source that cannot be fetched ends its own pass, not the batch: with
`URL=a, b, c`, a private video at `b` is reported and `c` still runs. When the
metadata for a source cannot be read, the run offers to take a replacement URL -
press Enter there to give up on that one and move on.

## Profiles

Profiles save a full set of answers so recurring workflows don't require re-entering everything. On startup, the script lists any saved profiles:

```
Available profiles:
1. profile.txt
2. profile1.txt
3. profile2.txt

Select a profile (number, name or full path, default 1. profile.txt, or 'no' / 'n' / 'false' / 'f' / '0' / 'skip' / 's' to skip):
```

A profile kept somewhere else is picked by typing its full path (`~` works,
and so do the quotes a copied Windows path comes in), or ahead of time with
`LOAD_PROFILE=` in `config.txt`, which takes a name or a path alike.

### Creating a Profile

After a successful run, the script offers to save the session as a profile. The resulting file contains the settings you just used.

### Profile Format

Profiles are plain text files in `OpenAIYouTubeTranscriber/Profile/` and can be edited directly:

```ini
URL=https://www.youtube.com/watch?v=example
DOWNLOAD_VIDEO=n
VIDEO_RESOLUTION=
VIDEO_AUDIO_RESOLUTION=
VIDEO_RENAME=n
VIDEO_PATH=n
VIDEO_FORMAT=
VIDEO_ONLY=n
VIDEO_ONLY_RESOLUTION=
VIDEO_ONLY_RENAME=n
VIDEO_ONLY_PATH=n
VIDEO_ONLY_FORMAT=
DOWNLOAD_AUDIO=n
AUDIO_RESOLUTION=
AUDIO_RENAME=n
AUDIO_PATH=n
AUDIO_FORMAT=
DOWNLOAD_YT_TRANSCRIPT=n
TRANSCRIBE_AUDIO=y
TRANSCRIBE_AUDIO_QUALITY=
MODEL_CHOICE=base
SOURCE_LANGUAGE=auto
TARGET_LANGUAGE=auto
USE_EN_MODEL=n
AI_REFINEMENT=n
PROMPT=
TRANSCRIPT_RENAME=n
TRANSCRIPT_PATH=n
KEEP_TRANSCRIPT=
REPEAT=n
```

These 30 fields are what a saved profile contains. Two more are understood but
not written unless the session settled them - `AI_PROVIDER` and `MODEL`, which
normally live in `config.txt`; a blank line for either would override it with
nothing. See [In Profiles](#in-profiles).

`DOWNLOAD_VIDEO` and `VIDEO_ONLY` are independent, so a run can produce either or both:

| `DOWNLOAD_VIDEO` | `VIDEO_ONLY` | files |
|---|---|---|
| `n` | `n` | no video |
| `y` | `n` | `Video/` - video and audio merged into an MP4 |
| `n` | `y` | `VideoWithoutAudio/` - the video stream on its own |
| `y` | `y` | both, from a single download of the stream |

What each file ends up as is set by the format fields below. With
`VIDEO_ONLY_FORMAT=original` the video-only file is the stream as YouTube served
it - no re-encode - keeping that stream's own container (`.webm` for VP9,
`.mp4` for AVC); the default `h264` re-encodes it instead. A height YouTube publishes
only as a progressive stream arrives with the audio still in it; that track is dropped
by copying the video across, so the file is video-only either way and `original` still
costs no second generation. The merged file is built by
ffmpeg into whatever `VIDEO_FORMAT` names, `mp4` by default.

Each download has its own quality field, so they never fight over one setting:

| field | governs |
|---|---|
| `VIDEO_RESOLUTION` | the merged file's video stream |
| `VIDEO_AUDIO_RESOLUTION` | the audio track muxed into the merged file |
| `VIDEO_ONLY_RESOLUTION` | the bare video stream |
| `AUDIO_RESOLUTION` | the standalone audio file |
| `TRANSCRIBE_AUDIO_QUALITY` | the audio fetched to transcribe, default `lowest` |

A format is named the way you would write the extension, with or without the
leading dot: `AUDIO_FORMAT=mp3` and `AUDIO_FORMAT=.mp3` are the same answer, and
so are `MP3` and `mp3`. The name ffmpeg knows the muxer by is accepted too -
`matroska` writes `.mkv` just as `mkv` does - but prefer the extension: `m4a`
writes `.m4a`, while `ipod`, the muxer behind it, writes that muxer's own first
choice, `.m4v`.

### Languages: what was said, and what to write

Two fields, because Whisper needs to know two different things:

| field | means | default |
|---|---|---|
| `SOURCE_LANGUAGE` | the language **spoken** in the audio, which Whisper listens for | `auto`: Whisper detects it |
| `TARGET_LANGUAGE` | the language the transcript is **written** in | `auto`: the language spoken |

Whisper can write two things: the language spoken, and English. So:

| `TARGET_LANGUAGE` | Whisper does |
|---|---|
| `auto`, or the language spoken | transcribes it |
| `en`, when the speech is not English | translates it into English |
| any other language | transcribes the speech as spoken, and says so - Whisper cannot write it. Refine the transcript with `prompt0-translator.txt` (naming the language on its first line) for that |

Set `SOURCE_LANGUAGE` when detection gets the language wrong - a long music
intro, or a speaker who opens in another language - since detection listens to
the first 30 seconds only. A profile with no `SOURCE_LANGUAGE` line at all -
one written before the field existed - detects, without stopping to ask.

`TARGET_LANGUAGE` takes more than one language, separated by commas or spaces -
`TARGET_LANGUAGE=auto,en` on a Japanese video writes the Japanese transcript and
its English translation from one download. `AI_REFINEMENT` runs over every one
of them with the same prompt. Spacing, case and repeats are noise:
`EN, English, fr` and `EN English fr` both ask for two. A language Whisper does
not support is named and skipped rather than failing the run.

The files are named for the language the text is actually in -
`clip [Whisper ja].txt` and `clip [Whisper en].txt` - so a transcript is never
labelled with a language it is not in. Two targets that come out the same (`ja`
and `auto` on Japanese speech, or `fr` which Whisper cannot write) are one file,
not two copies of it.

### Naming and placing the files

Every deliverable takes two more fields, `*_RENAME` above `*_PATH` above its
`*_FORMAT`, and the transcript's pair sits after `PROMPT` because it is applied
to the finished text:

| field | what it does |
|---|---|
| `VIDEO_RENAME` / `VIDEO_PATH` | the merged video |
| `VIDEO_ONLY_RENAME` / `VIDEO_ONLY_PATH` | the video-only file |
| `AUDIO_RENAME` / `AUDIO_PATH` | the standalone audio |
| `TRANSCRIPT_RENAME` / `TRANSCRIPT_PATH` | the transcript, after refinement |

Both read the same way:

| value | means |
|---|---|
| a name, or an absolute path | use it, with no question asked - so a profile runs unattended |
| `y` | ask for one |
| `n` | leave the default alone |
| blank | ask, where Enter also leaves the default |
| the field is absent | leave the default alone, so a profile written before 1.2 still runs |

`VIDEO_RENAME=lecture` writes `lecture.mp4` instead of the video's title. One
name cannot name several videos, so with a `URL` list the name leads and each
source's own title follows it - `lecture - Me at the zoo.mp4`. The
quality and format tags still follow the name, so a list is still several files:
`VIDEO_RESOLUTION=144p,720p` with that rename gives `lecture [144p].mp4` and
`lecture.mp4`. A name goes through the same cleaning a title does, so it cannot
contain a path separator. A download under a name that is already taken replaces
that file, so a profile with a fixed name, run again on another video, replaces
the last one's.

`VIDEO_PATH` must be absolute - `D:\Lectures` and `/srv/media` both count - and
is checked when the field is read, so an unwritable one is refused before the
download rather than after it. `TRANSCRIPT_PATH` takes the unrefined copy with
it, into a `Raw/` beside the refinement rather than back in the project folder.

Answered interactively, one question gates all eight: say no to
`Rename any of this run's files, or send them somewhere other than the project
folder?` and nothing else is asked.

### YouTube's own transcripts as files

`DOWNLOAD_YT_TRANSCRIPT` saves them to `Transcript/` beside Whisper's, the
way `DOWNLOAD_AUDIO` saves audio. It takes more than yes and no:

| value | saves |
|---|---|
| `y` | the transcript in the language the video was spoken in |
| `n` | nothing |
| `f` / `fetch` | lists what this video offers and lets you pick |
| `a` / `all` | every track on offer |
| `en` or `EN, FR` or `en,zh,ja` | those languages; spacing and case are ignored |

The transcript of what was said carries no tag - `Me at the zoo.txt` - and every
other track is named for its language, `Me at the zoo [de].txt`, because a
translation is not a transcript of anything anyone said. Which one is which is
not guesswork: YouTube marks the source track `en-orig` and names it "English
(Original)", and the extractor reports the video's own language besides.

A language the video does not have is reported rather than dropped, and a video
with no transcripts at all says so instead of opening an empty menu.

`AI_REFINEMENT` covers both kinds of transcript with one answer, so a
downloaded transcript and a Whisper one are enhanced by the same `PROMPT` and
kept by the same `KEEP_TRANSCRIPT`. **`all` enhances only the original track** -
most videos list around 157 languages and enhancement is charged per file - so
run again naming the languages you want if you need more.

`TRANSCRIBE_AUDIO_QUALITY` only applies when transcription is the sole reason to
download anything. Any audio already coming down - a standalone `DOWNLOAD_AUDIO`, or the
track fetched for a merged video - is transcribed as it is, at whatever quality you
asked for it, rather than fetching a second copy. The field is not asked for in that
case, and a value written into the profile by hand is reported as ignored rather than
dropped silently.

**A blank field asks.** It lists what that video actually offers and you pick, with Enter
taking the field's default - `highest` everywhere except transcription, which defaults to
the cheapest stream. Nothing is chosen silently on your behalf.

Transcription defaults to `lowest` because it costs nothing on speech: on a test clip the
transcript from the 60k stream was byte-identical to the one from 130k. It does cost
something on singing, where a 61k stream produced noticeably different lyrics from 129k -
raise it if you transcribe music.

Each download also has a format field:

| field | is a | `DEFAULT` / Enter | `original` |
|---|---|---|---|
| `VIDEO_FORMAT` | container | `mp4` | keep the served container, copy both streams |
| `VIDEO_ONLY_FORMAT` | video codec | `h264` | keep the served video, no re-encode |
| `AUDIO_FORMAT` | container | `mp3` | keep the served container |

A blank field lists every format this ffmpeg can write - 182 containers, 100 video
codecs - with `original` alongside, and Enter takes the default. Names ffmpeg spells
after the standard rather than the extension work as typed and write their own
extension, so `matroska` and `mkv` both produce `.mkv`; the handful of muxers that write
no media file, like `null`, are refused.

**The defaults usually re-encode.** YouTube mostly serves VP9 video and Opus audio, so
`h264` and `mp3` mean a full second-generation encode of every video-only and audio
download: slow on a long video, and lossy. `original` costs nothing and keeps the served
quality. Where a stream already is what was asked for - AVC video, or a container change
an audio stream can simply move into - it is copied instead. The merged file is cheaper
either way: nothing is re-encoded that the chosen container will accept as it is. The
exception is MP4, which may legally hold Opus but is asked for precisely because
everything plays it, so Opus audio going into an MP4 becomes AAC; MKV keeps it.

The same stream is only fetched once, however the requests for it were worded. Asking
for a merged file and a video-only file at the same resolution downloads one video
stream; asking for different resolutions necessarily downloads two. The same holds for
audio, on the stream each request resolves to rather than the word typed - on a video
whose best tier is `medium`, asking for `medium` and for `highest` is one download.
Audio already on disk is reused for transcription rather than fetching a second copy.

`VIDEO_RESOLUTION` takes `highest`, `lowest`, a height (`720p` or `720`), or `fetch`
(`f`) to list what the video offers and pick from it. `AUDIO_RESOLUTION` works the same
way with YouTube's own tier names:

```ini
AUDIO_RESOLUTION=          # blank or highest - best available, the default
AUDIO_RESOLUTION=lowest    # the lowest tier the video offers
AUDIO_RESOLUTION=low       # or medium - matched against the video's own tiers
AUDIO_RESOLUTION=64        # a ceiling in kbps: the best stream at or under it
AUDIO_RESOLUTION=fetch     # or f - list the tiers and pick
```

YouTube labels its audio `low` and `medium` (yt-dlp also knows `ultralow` and `high`;
neither appeared on any video tested). Each label covers several streams, so a bitrate
gets you finer control than a tier name. A typical video:

| stream | bitrate | tier |
|---|---|---|
| 249 Opus | ~47k | low |
| 139 AAC | ~49k | low |
| 250 Opus | ~60k | low |
| 251 Opus | ~106k | medium |
| 140 AAC | ~130k | medium |

`low` selects the best stream in the low tier (~60k) and `48` selects the best at or
under 48 kbps (~47k). A ceiling below every stream falls to the smallest rather than
silently to the best. At the `fetch` menu you can type a bitrate instead of a menu
number, as long as it is larger than the number of entries listed.

A tier the video does not offer is reported and you are asked to pick from the ones it
has, the same as for video. Only original-language streams are offered: a dubbed video
publishes a full set of tiers per language, and choosing one of those would transcribe
the wrong language. `RESOLUTION` is still read as a synonym for `VIDEO_RESOLUTION` so
profiles written before this change keep working.

Lower audio costs Whisper almost nothing in accuracy and downloads noticeably faster -
on a test clip, `lowest` was 60 kbps and 144 KB against `highest` at 106 kbps and 252 KB.

#### Several at once

The quality and format fields take lists, separated by commas or spaces, and
multiply out within their own deliverable:

```ini
DOWNLOAD_VIDEO=y
VIDEO_RESOLUTION=144p, 720p
VIDEO_AUDIO_RESOLUTION=low
VIDEO_FORMAT=mp4, mkv
```

That is four merged videos - every resolution in every container.
`VIDEO_ONLY_RESOLUTION` x `VIDEO_ONLY_FORMAT` and `AUDIO_RESOLUTION` x
`AUDIO_FORMAT` do the same for their own files. The groups do not multiply
across each other: asking for two audio bitrates does not double the videos.

The prompts take the same lists, so this needs no profile: type `144p, 720p`
where it asks for a resolution, or pick `2, 1` from the menu it offers, and
`mp4, mkv` where it asks for a container.

Each stream is fetched once however many files want it - two containers are two
conversions off one download, and the merge still borrows the video-only copy
when both asked for the same resolution. Transcription does not multiply
either: one copy of the audio is recognised however many deliverables there
are, so a list in `TRANSCRIBE_AUDIO_QUALITY` names that copy rather than
several of them.

The quality tag keeps the files apart, and the container extension does the
rest. Only where two formats would land on one name - `h264` and `mpeg4` both
live in `.mp4` - does the format join it too
(`clip [144p h264] - Video Only.mp4`); `mp3, flac` need no such help, and a
single format is named exactly as it always was.

The `URL` field accepts any of the supported input formats (full URL, short URL, bare video ID, or URL with extra query parameters - only the video ID is used), and accepts several of them separated by commas or spaces. `URL=clip.mp4, youtu.be/vid3, s` runs three passes in the order given, the last of them a refinement of transcripts already on disk. The rest of the profile is answered once and applies to every pass. Leave `URL` blank and the same question is asked at the start of the run, taking the same answers; a profile with `REPEAT=y` asks it again for each round, so a batch can be a different list every time.

Two sources of one list that would be written under one name - two videos with
the same title, or `a/clip.mp4` and `b/clip.mp4` - each keep their files: the
second takes its video ID (`Same title [dQw4w9WgXcQ].mp4`), or a number for a
local file (`clip (2).mp4`). The same source named twice keeps its one name.

A saved profile writes a value in single quotes wherever dotenv would otherwise
change it on the way back - a path containing ` #`, `$`, or quotes - and a
single-quoted value is read exactly as written. An unquoted `${HOME}` in a
profile you wrote yourself still expands.

### Included Profiles

- **profile-transcriber.txt**: transcribe only (no downloads), in the language spoken
- **profile1-video_downloader.txt**: download video with audio
- **profile2-audio_downloader.txt**: download audio only
- **profile0-translator.txt**: translate the speech into English with Whisper;
  its comments say how to get another language through `prompt0-translator.txt`

## AI Transcript Enhancement

Whisper output can have inconsistent punctuation and grammar. After transcription, the script can optionally run the transcript through an AI model to clean it up.

`AI_REFINEMENT=` is a plain yes or no: refine, or don't. *Which* model does
it is `AI_PROVIDER=` in `Profile/config.txt`, because that is a fact about your
machine and your accounts rather than about this job:

- **A provider name**: `openai`, `openrouter`, or `anthropic`. Needs `API_KEY=`.
- **`local`**: a free model on your machine (Qwen2.5-1.5B-Instruct by default).
  No API key; the first run downloads the model (~3GB).
- **Blank**: whoever `API_KEY=` belongs to, by its prefix. With no key either,
  the run asks once.

`MODEL=` names the model for whichever of those is chosen - a cloud model id
(`gpt-4o-mini`, `claude-opus-4-8`, `anthropic/claude-3.5-sonnet` through
OpenRouter) or, with `AI_PROVIDER=local`, a local one: `qwen2.5-1.5b`,
`qwen2.5-0.5b`, `distilgpt2`, `gpt2`, `gpt2-medium`, `phi-1_5`, `deepseek-1_5b`,
or any Hugging Face model ID such as `microsoft/phi-2`. Blank takes the
provider's default.

### Cloud Providers

Cloud providers require an API key: set the matching environment variable, add it to `Profile/config.txt`, or enter it when prompted.

| Provider | Choice | Key looks like | Default model |
|---|---|---|---|
| OpenAI | `openai` | `sk-...` | `gpt-4o-mini` |
| OpenRouter | `openrouter` | `sk-or-...` | `openai/gpt-4o-mini` |
| Anthropic | `anthropic` | `sk-ant-...` | `claude-opus-4-8` |

`Profile/config.txt` comes blank - `LOAD_PROFILE=`, `AI_PROVIDER=`, `API_KEY=`
and `MODEL=`, with a note on each. It is tracked, so `.gitignore` does not keep
a key you put in it out of a commit. Before you fill it in, run this once in
your clone and git will leave your copy alone:

```bash
git update-index --skip-worktree OpenAIYouTubeTranscriber/Profile/config.txt
```

Or keep the key out of the file altogether, in the vendor's environment
variable below. If the file is missing, the first profile you save writes it.

One provider runs per session, so config.txt carries one `API_KEY=` and one
`MODEL=` rather than a pair each. Leave `AI_PROVIDER=` blank and the key names
the provider itself - an `sk-ant-` key means Anthropic. Leave `API_KEY=` blank
and the vendor's own variable is read (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`,
`OPENROUTER_API_KEY`), so a key already exported in your shell needs no entry
here. That variable is read too when `API_KEY=` holds another provider's key -
an `sk-or-` key is never sent to Anthropic - unless `BASE_URL=` says where it
goes. `MODEL=` blank takes the provider's default above.

```ini
LOAD_PROFILE=
AI_PROVIDER=
API_KEY=
MODEL=
```

OpenAI and OpenRouter both use the OpenAI-compatible chat completions API, so either can be pointed at another compatible endpoint (Groq, Together, Azure OpenAI, a local Ollama server, ...) by setting `BASE_URL`. OpenRouter proxies many models, selectable via `MODEL` (e.g. `anthropic/claude-3.5-sonnet`, `deepseek/deepseek-chat`, or a free tier model like `meta-llama/llama-3.1-8b-instruct:free`). Anthropic uses its native Messages API; `BASE_URL` works there too if you route through a compatible proxy. A key for one of those endpoints will not match any prefix above, so name it in `AI_PROVIDER=` rather than leaving it to the key.

Local models require the `transformers` and `torch` packages (included in requirements.txt). The default Qwen2.5-1.5B-Instruct is instruction-tuned and follows prompts reliably. Small base models such as `distilgpt2` and `gpt2` download faster but only continue text rather than follow instructions: tried on a talk with the shipped prompts, `distilgpt2` wrote on to its output limit on every chunk, and each was kept as transcribed. They also read only 1024 tokens, most of which a prompt takes, so their chunks are small. Cloud providers give the best quality.

### Prompts

Enhancement is guided by a prompt that tells the model what to do with the transcript. Put `.txt` prompt files in `OpenAIYouTubeTranscriber/Prompt/` and the script will offer them for selection, or choose `E` to type a custom prompt in the console. A typed prompt is saved to `Prompt/prompt<N>.txt` when you save the session as a profile, so the profile can name it. An installed copy (`pip install .`) carries the four shipped prompts with it; a prompt of the same name in the working directory's `Prompt/` takes their place. It carries the four sample profiles too, and copies them into the working directory's `Profile/` the first time it runs there, if there is no `Profile/` yet.

Example prompt file:
```
Correct the grammatical and punctuation errors in this transcript.
Keep all the original content - don't summarize or skip anything.
```

Four ship with the project:

| file | writes |
|---|---|
| `prompt-refinement.txt` | the transcript as it was said: punctuated, in paragraphs, filler removed |
| `prompt0-translator.txt` | the transcript in another language - French, until you change its first line, `Target language: French` |
| `prompt1-summarizer.txt` | the main points, much shorter than the video |
| `prompt2-explainer.txt` | the content rewritten for a newcomer, with the terms it leaves unexplained explained |

Apart from the translator, they write in the transcript's own language. They lay
out with Markdown headers, and treat whatever the speaker says - "summarize
this", a question to the viewer - as speech rather than an instruction.

Long transcripts are split into chunks - about 12,000 characters of English for
a cloud provider, roughly 13 minutes of speech, and about 1,200 for a local model,
with a third as many in Chinese or Japanese, where a character takes three bytes -
each enhanced on its own and joined back together. No model sees the whole of a
long video at once, so its summary comes out in sections, one per chunk, and the
explainer can explain a term again in a later section. A prompt of your own
should expect to be handed part of a transcript.

A local model's reply is discarded if it is under 30% of the length of the text
it was given, because that is usually a model that stopped early. A summary is
shorter than that on purpose, so a prompt with `summar` in its filename is let
off the check - name a summary prompt of your own that way too, or its chunks
come back unsummarized. A refinement, a prompt with `refine` in its filename, is
held to more: its reply is discarded if it leaves out 15 or more of the chunk's
words in a row, which is a dropped sentence rather than filler taken out. A
refinement prompt named otherwise gets only the length check.

A small local model is not reliable on long text, even in chunks. Refining a
20-minute talk with the default Qwen2.5-1.5B, about one chunk in six came back
with most of it left out, and was kept as transcribed instead; the run names
every chunk that was (`Warning: 1 of 16 chunk(s) kept as transcribed`). What
the checks cannot see still gets through: a refinement missing a few words, or
a summary that leaves out a whole section. Short clips come out well. For a
long video, use a cloud provider or a larger local model (`MODEL=` takes any
Hugging Face id).

### In Profiles

Set the `AI_REFINEMENT` and `PROMPT` fields:

```ini
AI_REFINEMENT=y   # or n; the backend is AI_PROVIDER= in config.txt
PROMPT=prompt-refinement.txt   # a file in OpenAIYouTubeTranscriber/Prompt/
KEEP_TRANSCRIPT=y   # keep the unrefined transcript in Transcript/Raw/
```

`PROMPT` takes a list, and every prompt runs over every transcript - two
prompts across three transcripts is six files, each tagged with the prompt that
made it. Commas or spaces separate the entries, here and in every other list
field; an entry that contains a space, such as a path, is not split when it is
already a file, so only two space-carrying paths in one answer need the comma. An entry that is not a file in `Prompt/` is taken as a path to one
anywhere:

```ini
PROMPT=prompt-refinement.txt,prompt0-translator.txt,~/prompts/house-style.txt
```

A profile can carry its own `AI_PROVIDER=`, `API_KEY=` or `MODEL=` to override
config.txt for that profile: config.txt is read first and the profile second.
A profile created from a session writes the backend it used into `AI_PROVIDER=`
so that the replay uses the same one; delete the line to fall back to
config.txt. Leaving it blank is not the same thing - a blank line overrides
config.txt with nothing.

`KEEP_TRANSCRIPT` only applies when enhancement runs; it is ignored otherwise.
Leave it blank to be asked, where pressing Enter keeps the original.

### Re-encoding a file you already have

The three download deliverables are also three ways to cut up a file you
already have. Point `URL` at it and the same fields apply, ffmpeg doing the
work a download would otherwise have done:

```ini
URL=C:\Users\you\Videos\lecture.mkv
DOWNLOAD_VIDEO=y
VIDEO_RESOLUTION=720p
VIDEO_AUDIO_RESOLUTION=128
VIDEO_FORMAT=mp4
VIDEO_ONLY=y
VIDEO_ONLY_FORMAT=h264
DOWNLOAD_AUDIO=y
AUDIO_RESOLUTION=64
AUDIO_FORMAT=mp3
```

That is one run and three files: `Video/lecture [720p 128k].mp4`,
`VideoWithoutAudio/lecture - Video Only.mp4` and `Audio/lecture [64k].mp3`. The
fields take lists here as well, so `VIDEO_RESOLUTION=480p, 720p` with
`VIDEO_FORMAT=mp4, mkv` cuts four videos out of the one file -
and `TRANSCRIBE_AUDIO=y` still transcribes alongside them, `AI_REFINEMENT` and
`PROMPT` refining the result exactly as they would for a download. Whisper is
handed the original file, not whichever deliverable was just cut from it, so a
64k audio file for your phone does not cost you transcription accuracy.

A file has one stream, not a list of tiers, so it is its own highest and its
own lowest: only a number is a constraint. `VIDEO_RESOLUTION=1080p` against a
720p file says so, leaves it at 720p and drops the tag rather than upscaling it,
and `highest`, `lowest` and a blank all mean "as it already is". `original` keeps
the file's own container or codec. Changing only the format is a remux, which
costs no quality; a resolution or bitrate change is a real re-encode.

The source is only ever read. A file with no audio track says so and skips the
audio deliverable rather than failing the run, and a deliverable that would be
written over the source itself - pointing `URL` at a file already in `Video/`
and asking for the same resolution and container - is skipped with a note.

### Refining a transcript you already have

Refinement does not need a video. Answer the source question with a transcript
instead, and nothing is downloaded or transcribed - the run is the refinement:

```
Enter the YouTube video URL, video ID, local file path, or S to refine a transcript (several separated by commas or spaces run in turn): s
Available transcripts:
  1. Transcript/Raw/Me at the zoo.txt
  2. Transcript/Me at the zoo - translator.txt
Select transcripts to refine (numbers or paths, separated by commas or spaces, or Enter to go back): 1
```

`S` lists what is in `Transcript/Raw/` and `Transcript/`, originals first, since
`Raw/` is where earlier refinements put the untouched text. A path works just as
well, and several run as a batch - four transcripts by three prompts is twelve
files, so the run says how many passes it is about to make.

`S` is also an entry in a list, so a run can download and refine in one go:
`clip.mp4, youtu.be/vid3, s` transcribes a local file, then a video, then asks
which transcripts to refine. Each `S` asks separately, so two of them are two
refinements. Naming a transcript anywhere in the list is answer enough that the
run refines - `AI_REFINEMENT` is not asked again.

The same answers go in a profile's `URL=`, which is what makes a refinement
replay unattended:

```ini
URL=Transcript/Raw/Me at the zoo.txt
AI_REFINEMENT=y
PROMPT=prompt0-translator.txt
KEEP_TRANSCRIPT=y
```

A refined transcript leaves `Transcript/` as its refinement arrives there: the
untouched text is written to `Transcript/Raw/` and the original file removed, so
you are left with one original and one file per prompt rather than a duplicate.
`KEEP_TRANSCRIPT=n` skips the copy, and the unrefined text is gone - unless the
only prompts that changed it were a summary or a translation, which do not say
what it said, so the transcript stays where it is. Two things
are never removed: a transcript that already lives in `Transcript/Raw/`, and one
named from anywhere else on disk - those are read, not taken over. Neither is a
transcript no prompt actually changed.

## Output Files

- **Transcripts**: `OpenAIYouTubeTranscriber/Transcript/`
- **Pre-enhancement transcripts**: `OpenAIYouTubeTranscriber/Transcript/Raw/`, written
  only when AI enhancement changed the text and `KEEP_TRANSCRIPT` is not `n`
- **Downloaded audio**: `OpenAIYouTubeTranscriber/Audio/`
- **Downloaded video**: `OpenAIYouTubeTranscriber/Video/`
- **Video without audio**: `OpenAIYouTubeTranscriber/VideoWithoutAudio/`

A download is never given an extension it does not match. Left at `original`, audio is
usually `.webm` (Opus) and a video-only download `.webm` (VP9) or `.mp4` (AVC), exactly
as served. Converted files carry the format actually written, and the merged file is
built by ffmpeg into the container `VIDEO_FORMAT` names.

Anything below the best available is labelled, so downloads at different qualities sit
side by side instead of the second silently reusing the first:

| download | filename |
|---|---|
| audio, default | `video_title.webm` |
| audio at `low` | `video_title [60k].webm` |
| video, both default | `video_title.mp4` |
| video at `144p` | `video_title [144p].mp4` |
| video with audio at `low` | `video_title [60k].mp4` |
| video at `144p`, audio at `low` | `video_title [144p 60k].mp4` |
| video only, `144p` | `video_title [144p] - Video Only.webm` |
| video only, default | `video_title - Video Only.mp4` |

The label is the bitrate of the stream that was actually downloaded, not the word you
typed or the tier's headline figure: `lowest`, `low` and `64` all produce `[60k]` on a
video whose low tier is 60 kbps, so two runs that fetch the same stream get the same
filename. The `medium` tier is labelled `[106k]` rather than `[130k]` because yt-dlp
prefers the 106k Opus stream to the 130k AAC one sitting beside it. `NO_AUDIO_IN_VIDEO` is still read as a synonym for
`VIDEO_ONLY`.

Both kinds of transcript share `Transcript/`, so the name says where the words
came from. YouTube's own text keeps the plain title, and anything Whisper heard
says so:

- `video_title.txt` - YouTube's transcript, in the language spoken
- `video_title [de].txt` - YouTube's German track
- `video_title [Whisper fr].txt` - Whisper's reading of French audio
- `video_title [Whisper en].txt` - Whisper's English: English speech, or its
  translation into English

The tag is the language the text is in, whatever was asked for.

A standalone audio file that would share a folder, name and container with the
merged video - `AUDIO_PATH` and `VIDEO_PATH` one folder, both `mkv` - is written
as `video_title - Audio.mkv` rather than over the video.

An AI-enhanced transcript is also tagged with the prompt that produced it, taken from
the prompt filename's `prompt<number>-<description>.txt` shape:

- `video_title [fr] - refinement.txt` (from `prompt-refinement.txt`)
- `video_title [fr] - translator.txt` (from `prompt0-translator.txt`)

A prompt with no description (`prompt.txt`, `prompt0.txt`, `prompt-.txt`) and a custom
prompt typed at the menu have no description to take a tag from, so they are tagged
` - Refined`. No prompt tags with nothing: an untagged refinement would be named exactly
like the transcript it refined. The copy in `Transcript/Raw/` keeps the untagged name, so
refining the same video with several prompts leaves one original and one file per prompt.

## Troubleshooting

### FFmpeg not found

```
ERROR: ffmpeg is not found in the system PATH.
```

FFmpeg isn't installed or isn't on your PATH. See [Prerequisites](#prerequisites), then verify with `ffmpeg -version`.

### YouTube downloads failing

YouTube changes its internals regularly and the downloader occasionally needs an update:
```bash
pip install --upgrade yt-dlp
```

If it still fails, check the [issue tracker](https://github.com/Ruinan-Ding/OpenAI-YouTube-Transcriber/issues) to see whether it's a known problem.

### "No supported JavaScript runtime could be found"

yt-dlp prints this before it lists a video's formats. It is a deprecation
notice, not a failure - the run carries on, and on the videos this was measured
against the format list was identical with and without a runtime. Installing
[Deno](https://deno.com) silences it and is what yt-dlp will eventually require;
yt-dlp enables only Deno by default, so another runtime needs naming
explicitly (`--js-runtimes node`). Worth doing if a video offers fewer
resolutions than the site does.

### One video in a list fails

Private, deleted and region-blocked videos fail the metadata fetch. The run says
which one and offers a replacement URL; press Enter to give up on it, and the
sources after it still run. The failure is printed to stderr, so it is still
visible when stdout is redirected to a file.

### Out of memory

Whisper models have different memory requirements:

- `tiny`: ~1GB RAM (fastest, least accurate)
- `base`: ~2GB RAM (good default)
- `small`: ~3GB RAM (noticeably better)

On machines with limited RAM, stick with `tiny` or `base`.

### Poor transcription quality

1. Try a larger model - accuracy improves at the cost of speed
2. Check the audio quality; heavy background noise degrades results
3. Make sure the language setting matches the content
4. For English content, try the English-specific model option

### Not enough disk space

- 1080p video: 500MB–2GB depending on length
- Audio: roughly 5–50MB per minute
- Whisper models: 140MB (tiny) to ~3GB (large), downloaded once

If space is tight, skip the video download - audio is all that's needed for transcription.

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
make test    # Run the self-check suite
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
Keep all the original content - don't summarize or skip anything.
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

- **Punctuation**: Whisper doesn't always place commas and periods correctly; AI enhancement usually fixes this.
- **Uncommon words**: domain-specific jargon and unusual names may be transcribed incorrectly and can need manual review.
- **Very long videos**: content over ~3 hours may produce fragmented transcriptions that need cleanup.
- **A dead first source in a list**: if the first entry's metadata cannot be read
  and you decline a replacement, the run ends rather than moving to the second
  entry. The quality menus are built from that video's own stream list, so there
  is nothing to ask about until one of them answers.

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
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) for YouTube downloading
- [langdetect](https://github.com/Mimino666/langdetect) for language detection

# Usage

## Basic Usage

```bash
python OpenAIYouTubeTranscriber.py
```

The script walks through a series of prompts, then downloads and/or transcribes.

## The Prompts

A question is only asked when the answers before it make it mean something: a
transcribe-only run answers six, and a run producing all three files answers
fifteen. Every prompt with a default takes Enter for it.

**1. Source**

- **YouTube URL**: `https://www.youtube.com/watch?v=jNQXAC9IVRw`
- **Short URL**: `https://youtu.be/jNQXAC9IVRw`
- **Video ID only**: `jNQXAC9IVRw` (the 11-character code)
- **Local file**: `/path/to/audio.mp3` or `/path/to/video.mp4`
- **A transcript to refine**: a `.txt` path, or `S` to pick from what is on disk
- **Several of any of those**, separated by commas or spaces, run in turn

The video ID is extracted from any YouTube URL format - full URLs, short links
(`youtu.be/...`), or the bare ID. Query parameters such as timestamps (`&t=30s`)
or playlist info (`&list=...`) are stripped automatically. Playlist and channel
URLs are refused rather than downloaded entry by entry.

**2. The three deliverables**

Each is asked for on its own and carries its own quality and format questions.
They are independent: a run can produce all three, or none.

- **Download video?** - the merged video-and-audio file, into `Video/`
  - resolution, the audio resolution to mux into it, and the container
- **Download a video-only file, with no audio track?** - into `VideoWithoutAudio/`
  - resolution and codec
- **Download audio?** - into `Audio/`
  - resolution and format

A blank answer to any quality or format question lists what the video actually
offers and asks which; `fetch` (or `f`) asks for that list outright. Each takes a
comma- or space-separated list, and lists multiply out within their own
deliverable.

A local source is asked the same three questions worded as re-encodes
("Re-encode the video?"), because the same three files come out of it.

**3. YouTube's own transcript**

`y` for the language the video was spoken in, `all` for every published track,
`f` to list what this video has, or language codes (`en,fr`). Skipped for a local
file, which publishes nothing.

**4. Transcription settings**

- Whether to transcribe at all
- The audio quality to fetch for it - asked only when nothing else is already
  putting audio on disk, since that copy is reused rather than fetched twice
- Which Whisper model (tiny through large-v3)
- Which language (`en`, `es`, `fr`, ...), or several for one transcript each
- For English: whether to use the English-specific model (usually more accurate)

**5. AI refinement**

Whether to run a prompt over the transcript, which backend and prompt to use, and
whether to keep the unrefined copy in `Transcript/Raw/`.

**6. Save these settings as a profile?**

Offered after a run that produced something, and only when the run was not itself
started from a profile.

**7. Run again?**

Start another round immediately or exit. A repeat reuses the answers this
session gave and asks only for the new source - and for anything this session
had no reason to ask, such as the download questions after a round that only
refined a transcript. A new name for a file is asked again rather than reused:
it was that video's name, and the next video's file would replace it.

## Exit Codes

| code | meaning |
|---|---|
| `0` | the session finished, however many rounds it ran |
| `1` | ffmpeg or a required directory was missing, or the run's only source could not be fetched |

Failures are written to stderr, so redirecting stdout to a file still shows them.
One source of a list failing is reported and the rest still run.

## Profiles

For workflows you run repeatedly, save the answers as a profile.

### Saving a Profile

After a run that produced something, and only when the run was not itself
started from a profile, the script asks:
```text
Do you want to create a profile from this session? (y/N): y
```

Answering yes writes the answers you just gave to a new profile file.

### Loading a Profile

On the next run:
```text
Available profiles:
1. profile.txt
2. profile1-video_downloader.txt
Select a profile (number, name or full path, default 1. profile.txt, or 'no' / 'n' / 'false' / 'f' / '0' / 'skip' / 's' to skip): 1
```

Enter takes the first one. To skip the question entirely and always load the
same profile, set `LOAD_PROFILE` in `OpenAIYouTubeTranscriber/Profile/config.txt`
to its filename; `LOAD_PROFILE=no` always goes interactive, and blank asks.

A profile does not have to live in `Profile/`. Both `LOAD_PROFILE` and the prompt
take a full path to one anywhere - `~` expands, the `.txt` can be left off, and a
path pasted with quotes around it is fine - and "Run again?" reloads it from there.

`config.txt` comes blank. It is tracked, so before putting an API key in it run
`git update-index --skip-worktree OpenAIYouTubeTranscriber/Profile/config.txt`
once, or a commit can carry the key with it. If the file is missing, saving your
first profile writes it.

### Editing a Profile

Profiles live in `OpenAIYouTubeTranscriber/Profile/` as plain text files:

```ini
URL=https://www.youtube.com/watch?v=example
DOWNLOAD_VIDEO=y
VIDEO_RESOLUTION=highest
VIDEO_AUDIO_RESOLUTION=highest
VIDEO_RENAME=n
VIDEO_PATH=n
VIDEO_FORMAT=DEFAULT
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
TRANSCRIBE_AUDIO_QUALITY=lowest
MODEL_CHOICE=base
TARGET_LANGUAGE=en
USE_EN_MODEL=n
AI_REFINEMENT=n
PROMPT=
TRANSCRIPT_RENAME=n
TRANSCRIPT_PATH=n
KEEP_TRANSCRIPT=
REPEAT=n
```

These 29 fields are what a saved profile contains. `AI_PROVIDER` and `MODEL` are
understood too, but are written only when the session settled them: they
normally live in `config.txt`, and a blank line for either would override it
with nothing.

Every deliverable also takes `*_RENAME` and `*_PATH` (the transcript's pair sits
after `PROMPT`, being applied to the finished text). A name or an absolute path
is used as it stands, `y` asks for one, `n` and an absent field leave the default
alone, and a blank one asks. The quality and format tags still follow a rename,
so a list is still several files.

A format is named the way you would write the extension, with or without the
leading dot: `mp3`, `.mp3` and `MP3` are one answer.

A blank quality or format field is a question, not a default: the run stops and asks
what that video should be fetched or written as. Fill in the ones you want answered in
advance - `highest`, `lowest`, a resolution, a bitrate, `DEFAULT` or `original` - and a
profile runs unattended. Fields belonging to a download you have turned off are never
read, so they can stay blank.

The `URL` field accepts any supported format, and several of them separated by
commas or spaces - `URL=clip.mp4, youtu.be/vid3, s` runs three passes in the
order given, with the rest of the profile answered once for all of them. Left
blank, the same question is asked at the start of the run, and on every round
of a `REPEAT=y` batch:
- A transcript to refine: `Transcript/Raw/Me at the zoo.txt`, or several separated by commas or spaces
  (that pass downloads and transcribes nothing; `S` lists what is on disk and asks which)
- Full URLs: `https://www.youtube.com/watch?v=jNQXAC9IVRw`
- Short URLs: `https://youtu.be/jNQXAC9IVRw`
- The bare video ID: `jNQXAC9IVRw`
- URLs with extra parameters: `https://www.youtube.com/watch?v=jNQXAC9IVRw&t=30s` (parameters are ignored)

The resolution and format fields take lists too, separated by commas or spaces,
and multiply out within their own deliverable: `VIDEO_RESOLUTION=144p, 720p`
with `VIDEO_FORMAT=mp4, mkv` is four merged videos, each stream fetched once.
The prompts take those same lists, typed or picked from the menu, so a profile
is not needed to ask for them.

## Output Locations

- **Transcripts**: `OpenAIYouTubeTranscriber/Transcript/` - both Whisper's, tagged
  `[Whisper en]`, and YouTube's own, which keep the plain title
- **Pre-enhancement transcripts**: `OpenAIYouTubeTranscriber/Transcript/Raw/`, written
  only when AI enhancement changed the text and `KEEP_TRANSCRIPT` is not `n`
- **Audio files**: `OpenAIYouTubeTranscriber/Audio/`
- **Video files**: `OpenAIYouTubeTranscriber/Video/`
- **Video without audio**: `OpenAIYouTubeTranscriber/VideoWithoutAudio/`

Anything fetched below the best available quality is labelled with what it actually is,
so downloads of the same video at different settings sit side by side:
`Title [144p 60k].mp4`, `Title [60k].mp3`, `Title [144p] - Video Only.webm`.

## Examples

**Transcribe a YouTube video, downloading nothing:**
```bash
python OpenAIYouTubeTranscriber.py
# URL: jNQXAC9IVRw          (a full or short URL works the same)
# Detected video ID, using: https://www.youtube.com/watch?v=jNQXAC9IVRw
# Download video? n
# Download a video-only file? n
# Download audio? n
# Download YouTube's own transcript? n
# Transcribe? y
# Model? 2 (base)
# Language? en
```

**Several sources in one run:**
```bash
python OpenAIYouTubeTranscriber.py
# URL: jNQXAC9IVRw, youtu.be/vid2, /Users/you/talk.mp4
# ...the rest of the answers are given once and apply to all three
```

**Every resolution, in every format:**
```bash
python OpenAIYouTubeTranscriber.py
# Download video? y
# Resolution? 144p, 720p
# Format? mp4, mkv        -> four files, each stream fetched once
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
# Re-encode the video? n
# Transcribe? y
```

**Re-encode a local file:**
```bash
python OpenAIYouTubeTranscriber.py
# URL: /Users/you/Videos/lecture.mkv
# Re-encode the video? y  -> 720p, mp4
# Save the audio as its own file? y  -> 64, mp3
```
The resolution and format fields work as they do for a download, except that a
file has one stream rather than a list of tiers: only a number constrains it,
and one at or above what the file already is leaves it alone. The source is
never written over.

**Refine a transcript already on disk:**
```bash
python OpenAIYouTubeTranscriber.py
# URL: s                   (or name the .txt path directly)
# ...lists what is in Transcript/ and Transcript/Raw/ and asks which
# Refine the transcript with AI? y
```
That pass downloads and transcribes nothing. The refined text lands in
`Transcript/`, and the transcript it came from moves to `Transcript/Raw/` unless
`KEEP_TRANSCRIPT=n`.

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

# Subtitles: plan and prototype findings

> **Status, 2 Oct 2026: merged into `main` as a prototype; the design is not decided.**
> How subtitles fit the app will be specified later by the owner, including:
> - whether and when a video is subtitled at all;
> - a video-only download, which has no audio to time subtitles from;
> - subtitles muxed into a merged (video and audio) download;
> - soft subtitles (a track), hard ones (burned in), or both.
>
> The integration below is a proposal to be revised against that specification. Nothing
> goes into `OpenAIYouTubeTranscriber.py` until then.

Timed subtitles for any video the app handles: written as an `.srt` beside the
transcript, muxed into the video as a track the viewer can switch off, or
burned into the picture. **Polish** mode corrects each subtitle's wording with
the AI backend while keeping its timing exactly.

The prototype is `subtitle_prototype.py` (tests: `test_subtitle_prototype.py`).
It is standalone and borrows the main script's AI backends and ffmpeg settings;
nothing in `OpenAIYouTubeTranscriber.py` calls it yet.

```
python subtitle_prototype.py "lecture.mp4" --polish api --mux soft
python subtitle_prototype.py https://youtu.be/jNQXAC9IVRw --timing youtube --mux both
python subtitle_prototype.py "talk.mp4" --translate          # Whisper's English, by segment
```

## How it works

| Step | Source of truth | Notes |
|---|---|---|
| Timing | Whisper word timestamps, or YouTube's captions | No language model is involved in timing |
| Cues | `build_cues` | ≤2 lines of ≤42 characters, ≤7 s, cut at pauses (0.6 s) and sentence ends |
| Polish | `polish_cues` | Numbered batches of 40 cues; text fixed in place, times untouched |
| Output | `.srt`, soft track, burn-in | Soft: stream copy. Hard: full re-encode (x264, CRF 18) |

Timing sources, best first:

1. **A subtitle track the uploader wrote**: each cue's timing is kept as set.
2. **Whisper**: per-word times (`word_timestamps=True`). For a translation into
   English, per segment only (Whisper warns that word times on translations
   may not be reliable), with words spread across the segment by length.
   Tried on a Spanish fable: `small` mistranslates (the hare became "the lion");
   `medium` reads well, its cues within about 0.3 s of the speech.
3. **YouTube's speech recognition** (json3): per-word start times.

Polish checks every reply line before using it. A cue keeps its original text
when the reply:
- leaves its number out, or gives the number twice;
- moves words into or out of it (the whole batch is matched word by word, so a
  word that crosses a cue boundary is caught);
- loses more than a third of its words, or adds more than half again;
- no longer fits two lines.

## What the prototype found

Each of these was checked on real videos ("Me at the zoo", and a 3.5-minute
auto-captioned music video) or in the tests.

- **Whisper stretches words over silences.** After a pause it puts the first
  word at the segment's start with no length, and the next word absorbs the
  silence ("The" at 3.88 s, "cool" from 3.88 to 5.38 s). `tighten` trims any
  word longer than its letters plausibly take. On "Me at the zoo" this moved a
  cue from 1.44 s early to 0.66 s early, compared with the uploader's track.
- **Whisper mishears words that polish should fix**, for example "one of the
  elephants" (in front of) and "hunts" (trunks).
- **YouTube's recognised captions** give each word a start time but no end, and
  each event's duration overlaps the next. A word therefore ends where the next
  one starts, capped at 1.5 s. An event's first word arrives without a leading
  space ("to" + "love." came out as "tolove.").
- **Fitting two lines is not "84 characters".** A line can only break at a
  space, so an 84-character cue produced a 44-character line. `fits` tries the
  actual break.
- **Burning in on Windows**: ffmpeg's `subtitles` filter reads the file name
  inside its own filter syntax, where `C:`, backslashes and quotes all need
  escaping. Running ffmpeg next to a copy named `subs.srt` avoids it; this is
  tested with a folder named `it's a [test], folder`.
- **Containers**: MP4/M4V/MOV take only `mov_text`, MKV takes SRT, WebM takes
  WebVTT; anything else becomes MKV. Matroska leaves out the `und` language tag.
- **Not yet tested**: polish against a live model (no API key on the
  development machine), and timing quality and speed on long videos.

## Integration plan

### Settings (profile fields)

| Field | Values | Default |
|---|---|---|
| `SUBTITLES` | `y` / `n` | `n` |
| `SUBTITLE_TIMING` | `auto` (written track, else Whisper), `whisper`, `youtube` | `auto` |
| `SUBTITLE_TEXT` | `raw`, `polish` | `raw` |
| `SUBTITLE_EMBED` | `soft`, `hard`, `both`, `none` (`.srt` only) | `soft` |

### Code changes in `OpenAIYouTubeTranscriber.py`

1. **Keep Whisper's timing.** `transcribe_audio_file` caches only text and
   language (around "The text and its language, not the segments"). Cache the
   segments as well, and pass `word_timestamps=True` when subtitles are wanted.
   That flag becomes part of the cache key, so a text-only pass is never
   reused for subtitles.
2. **Keep YouTube's timing.** Next to `fetch_caption_text` (prose), add a
   `fetch_caption_cues` that returns cues from the same json3 or VTT download.
3. **Port the prototype's functions** as module-level helpers: `json3_cues`,
   `vtt_cues`, `tighten`, `build_cues`, `fits`, `split_lines`, `settle`,
   `to_srt`, `polish_cues`, `moved_cues`, `acceptable`.
4. **Ship the polish prompt** as `Prompt/prompt-subtitle-polish.txt`, so users
   can adjust it like the other prompts.
5. **Mux.**
   - A merged download: `combine_audio_video` takes an optional subtitle input
     (`-i subs.srt -map 2:s -c:s <codec>`), so it is still one ffmpeg pass.
   - A video-only, local or converted file: copy every stream plus the track
     into a file beside it, then swap it in (the pattern `strip_audio` uses).
   - Hard subs: a separate `<name> - Subtitled.mp4`. When `convert_media` is
     already re-encoding, draw the subtitles in that same pass instead.
6. **Naming.** `<name> [Whisper en].srt` beside the transcript, following the
   transcript naming, plus `.polished` when polished.

### Tests

Port `test_subtitle_prototype.py` into `test_transcriber.py`, and add a
pipeline test: a local clip through `_run_pipeline` with `SUBTITLES=y`,
asserting the `.srt` and the muxed track.

### Phases

1. Prototype: **done**, merged 2 Oct 2026.
2. Raw subtitles: Whisper and YouTube timing, `.srt`, soft mux.
3. Polish mode, once tried against a live model on a few long videos.
4. Hard subs, and translated subtitles into languages other than English (cue
   by cue through the translator prompt).

## Decisions needed

- The whole shape, to be specified by the owner (see the status note at the top).
- When a video has both an uploader's track and Whisper output, which wins
  under `auto`? (The plan above prefers the uploader's track.)
- Where the `.srt` goes: beside the transcript, or beside the video.
- Whether hard subs belong in the first release or wait for phase 4.

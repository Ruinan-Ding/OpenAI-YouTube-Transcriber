# Subtitles: plan and prototype findings

> **Status, 2 Oct 2026: specified by the owner (the fields below); not built.** The only code
> is the prototype, `subtitle_prototype.py`. The open decisions at the end are the owner's.

Subtitles for the merged video and the video-only file, timed from YouTube's transcript or
Whisper's, optionally with their wording refined by AI with the timing kept, muxed in soft (a
track the viewer can turn off), burned in hard, or both.

## The settings

Eight profile fields: four for the merged video, the same four for the video-only file. Each
is asked only when what it needs is on, so a session can be asked several of them, and each
yes adds subtitles of its own.

| Field | Asked when | Values | Absent / blank |
|---|---|---|---|
| `VIDEO_SUB` | `DOWNLOAD_VIDEO=y` and a YouTube transcript is downloaded | `y` / `n` | `n` / asks |
| `VIDEO_SUB_WHISPER` | `DOWNLOAD_VIDEO=y` and `TRANSCRIBE_AUDIO=y` | `y` / `n` | `n` / asks |
| `VIDEO_SUB_AI_REFINEMENT` | `DOWNLOAD_VIDEO=y`, `AI_REFINEMENT=y`, and `VIDEO_SUB` or `VIDEO_SUB_WHISPER` is `y` | `y` / `n` | `n` / asks |
| `VIDEO_SOFT_HARD_SUB` | `VIDEO_SUB` or `VIDEO_SUB_WHISPER` is `y` | `soft` / `hard` / `both` | `soft` / asks (Enter is `soft`) |
| `VIDEO_ONLY_SUB` | `VIDEO_ONLY=y` and a YouTube transcript is downloaded | `y` / `n` | `n` / asks |
| `VIDEO_ONLY_SUB_WHISPER` | `VIDEO_ONLY=y` and `TRANSCRIBE_AUDIO=y` | `y` / `n` | `n` / asks |
| `VIDEO_ONLY_SUB_AI_REFINEMENT` | `VIDEO_ONLY=y`, `AI_REFINEMENT=y`, and `VIDEO_ONLY_SUB` or `VIDEO_ONLY_SUB_WHISPER` is `y` | `y` / `n` | `n` / asks |
| `VIDEO_ONLY_SOFT_HARD_SUB` | `VIDEO_ONLY_SUB` or `VIDEO_ONLY_SUB_WHISPER` is `y` | `soft` / `hard` / `both` | `soft` / asks (Enter is `soft`) |

- **In a profile** they follow `TRANSCRIPT_PATH`, in the order above, and come before
  `KEEP_TRANSCRIPT`.
- **At the console** they are asked once the transcript's name and folder are settled, which is
  when everything they depend on is known:

```
Subtitle the video with YouTube's transcript? (y/N): y
Subtitle the video with the Whisper transcript? (y/N): y
Also add AI-refined subtitles (wording corrected, timing kept)? (y/N): y
Video subtitles: soft (a track you can turn off), hard (burned in) or both? [soft]: both
Subtitle the video-only file with YouTube's transcript? (y/N):
Subtitle the video-only file with the Whisper transcript? (y/N): y
Also add AI-refined subtitles to the video-only file? (y/N):
Video-only subtitles: soft, hard or both? [soft]:
```

  This session downloads the video, the video-only file and a YouTube transcript, transcribes
  with Whisper and refines with AI, so every question comes up. Turn one of those off and the
  questions that need it are not asked.

- **Old profiles** do not carry these fields, so they make no subtitles and ask nothing, as
  before.
- **A field set where it means nothing** (`VIDEO_SUB_WHISPER=y` with `TRANSCRIBE_AUDIO=n`) is
  reported as ignored with the reason, as `USE_EN_MODEL` is today.

## What a session makes

**Tracks.** Each yes adds subtitles from that source:

- **`VIDEO_SUB`**: a track for each YouTube transcript the session downloads: each language
  `DOWNLOAD_YT_TRANSCRIPT` names, or the original for `y`. For `all`, see decision 4.
- **`VIDEO_SUB_WHISPER`**: a track for each Whisper transcript written, one per language in
  `TARGET_LANGUAGE`.
  - A transcription is timed word by word.
  - Whisper's English translation is timed by segment, and needs the `medium` model or larger
    (punchlist 3.12).
- **`VIDEO_SUB_AI_REFINEMENT`**: a refined copy of each of those tracks. Each subtitle's
  wording is corrected and its timing is kept. It runs on the `AI_REFINEMENT` backend with a
  prompt of its own, not `PROMPT`: a summary or an explanation has no timing to keep. It refines
  the same transcripts `AI_REFINEMENT` does. Whether it can run without a transcript `PROMPT`
  is decision 9.

**Soft** adds every track to the video file by stream copy: it takes seconds and nothing is
re-encoded.
- Each track is titled ("Whisper en", "Whisper en, AI refined") and tagged with its language
  (proposed titles: decision 10).
- The first refined track is the default, or else the first track (decision 10).
- Tracks and streams the file already has (subtitles, fonts, chapters) are kept.
- The tracks go into a copy beside the video, which replaces it once complete (the
  `strip_audio` pattern), so a failure leaves the video as it was.

**Hard** burns the subtitles into a separate copy, `<video name> - Hard Subs [Whisper en].mp4`,
in the video's folder (proposed name: decision 10). It is 8-bit H.264, with audio in a codec
every MP4 player takes, so Windows' own player opens it. This is a full H.264 re-encode, which is slow. A picture holds one set
of subtitles, so several tracks or several video files mean several copies (decision 1). The
count is printed before the first one starts, as the "N passes" count is for prompts and
transcripts today.

**Both** does both.

**Every video file** the session writes gets them: each resolution and format of the merged
video, and each codec of the video-only file.

**`.srt` files** go beside the transcript (decision 3), named after it (decision 10):

| Transcript | Subtitles |
|---|---|
| `Title.txt` (YouTube, original language) | `Title.srt`, `Title - AI Refined.srt` |
| `Title [es].txt` (YouTube, Spanish track) | `Title [es].srt` |
| `Title [Whisper en].txt` | `Title [Whisper en].srt`, `Title [Whisper en] - AI Refined.srt` |

### Edge cases

- **A local file** has no YouTube transcript, so `VIDEO_SUB` is never asked. Whisper subtitles
  work. A local video is only subtitled when "Re-encode the video?" is answered yes
  (decision 6).
- **A batch** settles the answers once, on the first source. A local file in a URL list gets no
  YouTube track, as it gets no YouTube transcript today.
- **No YouTube transcript in a language, or no speech for Whisper**: no track. The transcript
  step already says why.
- **A target language Whisper cannot write** comes back in the language spoken. Its track is
  tagged with the language the text is actually in.
- **A container that holds no text subtitles**: soft subtitles are skipped and reported, and
  the `.srt` is there (decision 5). MP4, MOV and M4V take `mov_text`, MKV takes SRT and WebM
  takes WebVTT.
- **Refinement rejects a subtitle's new wording** (words moved between subtitles, too much lost
  or added, too long for two lines): that subtitle keeps its unrefined text. These are the
  prototype's checks.
- **`KEEP_TRANSCRIPT`** is about transcript files only; it does not drop unrefined subtitles.

## Code changes

1. **One script** (AGENTS.md invariant 1). Move the prototype's core into
   `OpenAIYouTubeTranscriber.py`:
   - `Word`, `Cue` and the reading-limit constants;
   - the timing functions: `tighten`, `segment_words`, `json3_cues`, `json3_words`,
     `vtt_cues`;
   - the cue builders: `build_cues`, `_clause_cut`, `_ends`, `fits`, `split_lines`, `settle`,
     `to_srt`;
   - refinement: `polish_cues`, `moved_cues`, `parse_numbered`, `acceptable`;
   - muxing: `mux_soft`, which needs to take several tracks, and `burn_in`.

   Reuse what the script already has rather than moving the prototype's copies:
   `vtt_cue_lines` for WebVTT, `convert_media`'s retry loop and `_discard` for ffmpeg runs, and
   `longest_missing_run`'s word splitter. Then delete `subtitle_prototype.py`, with its tests
   moved into `test_transcriber.py`.

   **Fixed in the prototype** (2 Oct), after a review reproduced each one. The port carries the
   fixes and their tests:
   - **Refinement could drop spoken words.** `enhance_text` cut a 40-cue batch at a sentence end
     inside a line, on the local backend's small chunk budget; a cue lost "So we" and passed
     every check. Each batch now goes in one request, and a batch the backend would cut goes
     again in smaller ones.
   - **A failed backend read as "nothing to fix"**: the backends hand back their input when a
     chunk fails. A failure now raises, and is counted as `failed`. The prototype does this by
     standing in for the backends' `_run_chunked_enhancement` for the call; **at the port, give
     the backends a single-request mode instead.**
   - **Soft muxing dropped what the file had.** Every stream is copied now (`-map 0`). The new
     track is numbered after the file's own and is the default only when the file had none.
   - **A cue could break the reading limits** after a cut (a 43-character line). The rest is
     checked again.
   - **Times could go negative** (`-0.28 s`, written as `-1:59:59,720`). `tighten` stops at the
     words before.
   - **The hard copy might not play on Windows** (High 10 from a 10-bit source, Opus in MP4). It
     is 8-bit 4:2:0 now, with the audio copied only where MP4 plays it.
   - **Overlapping YouTube events** now end where the next begins; their timing is otherwise
     kept.
   - **Chinese, Japanese and Korean lines** are measured in display width.
   - **Languages**: every language Whisper knows, and YouTube's common extra codes, are tagged;
     any other three-letter code passes through, and only an unknown one is `und`.
   - **A container with no text subtitles** is reported and left alone, no longer made an MKV
     (decision 5 can still choose the MKV).

   CI now runs `test_subtitle_prototype.py` and type-checks the prototype.
2. **Keep Whisper's timing.** `transcribe_audio_file` keeps only the text and language (the
   cache near "The text and its language, not the segments"). Have it return the segments too,
   with `word_timestamps=True` when any `*_SUB_WHISPER` is `y`, on transcription passes only.
   Whisper's English translation keeps it off, as the prototype does: word times are unreliable
   there, and with them on Whisper also moves its segment bounds by them. Make the flag part of
   the cache key, and of the alias the cache stores, so a text-only pass is never reused for
   subtitles.
3. **Keep YouTube's timing.** `fetch_caption_text` downloads a track and returns prose. Have it
   return the downloaded payload as well, so the text and the cues come from one download.
4. **Settle the fields.** Call a new `_settle_subtitles(transcriber, cfg, answers)` from
   `_settle_refinement`, straight after the transcript's placement.
   - It walks `("video", "VIDEO", cfg.download_video)` and
     `("video_only", "VIDEO_ONLY", cfg.video_only)`, as `_PLACEMENTS` does, so both prefixes
     share one code path.
   - It stores one small `Subtitling(youtube, whisper, refined, mode)` per prefix on
     `SessionConfig`.
5. **Make them.**
   - `_save_yt_transcripts` and `_Pass.transcribe` keep each track's cues on the pass, with
     its label and language, instead of throwing the timing away.
   - **The pass records every video file it writes.** Today none of them are kept: `merge()`
     drops `combine_audio_video`'s path, `_local_deliverables` returns nothing, and
     `_convert_all` keeps its paths in a local list. Each adds its finished files to the pass.
   - A new `_Pass.subtitle()` runs after `convert()` in `_run_one`, once every video file is in
     its final format. It writes the `.srt` files, refines, muxes soft and burns hard.
   - **Every new name is claimed** through `_take_path`: the `.srt` files, the hard copies and
     the soft mux's temporary copy (invariant 3). Two sources with one title must not write
     over each other's subtitles.
6. **The refinement prompt stays in the script**, as `POLISH_PROMPT` is in the prototype. In
   `Prompt/` it would be offered as a transcript `PROMPT`, and its numbered lines saved as a
   refined transcript. A file users can edit can come when someone asks for one.
7. **Everything else a field needs**, per `.claude/skills/settings-sync/SKILL.md`:
   - `DEFAULT_FIELDS`, `SETTINGS`, `SessionConfig`, `_Remembered.carry`;
   - all four sample profiles, with `n` and a blank soft/hard field;
   - `README.md`, `docs/USAGE.md` and `CHANGELOG.md`.

### Tests

- **The prototype's tests**, moved across.
- **Settings:**
  - `test_the_settings_table_covers_every_field` (automatic);
  - the eight fields added to `test_a_profile_and_a_repeat_settle_alike`;
  - an old profile without the fields asks nothing and makes no subtitles;
  - a blank field asks;
  - each field is asked only on its condition, and reported as ignored otherwise.
- **Pipeline:** a local clip through `_run_pipeline`, with Whisper stubbed to return segments
  and the AI backend stubbed for refinement. Assert:
  - the soft tracks are in the merged and the video-only files, with their titles, languages
    and default;
  - the hard copies exist;
  - the `.srt` files are beside the transcript;
  - a failed mux leaves the video untouched;
  - a file's own subtitle track survives a soft mux.
- **The review's findings** have a test each in `test_subtitle_prototype.py`, which move
  across with the rest.

### Phases

1. **Port** the prototype's core and tests into the script, with a single-request mode for the
   backends, and delete the prototype. Nothing changes for the user.
2. **The six fields without AI**: YouTube and Whisper tracks, soft, hard or both, for the video
   and the video-only file, and the `.srt` files. A release.
3. **The two AI fields**, after refinement has been tried against a live model on a few long
   videos (punchlist 3.5).

Not specified yet, so not planned:
- subtitles translated into other languages through the translator prompt;
- preferring H.264 over AV1 when downloading a video to subtitle (punchlist 3.8);
- warning when Whisper is asked to translate with a model too small for it (3.12).

## Decisions for the owner

Each has a recommendation; nothing is built until they are answered.

1. **Hard subtitles with several tracks or video files.** Make one burned copy per video file
   per track, the way two prompts on three transcripts make six files? Or burn only one?
   *Recommended: one per file per track, with the count printed first.*
2. **Refined and unrefined together.** Soft carries both, with the refined track as default.
   Should hard burn only the refined text when there is one, rather than doubling the slow
   re-encodes? *Recommended: yes.*
3. **Where the `.srt` files go**: beside the transcript, beside the video, or nowhere (made
   only to mux, then deleted)? *Recommended: beside the transcript. The subtitle questions
   follow `TRANSCRIPT_PATH`, and a player or editor can use them.*
4. **`DOWNLOAD_YT_TRANSCRIPT=all`**: a track for the original language only, as refinement
   does today, or one for every language? A video can have over 150 of them.
   *Recommended: the original only.*
5. **A container with no text-subtitle support**: keep the file as chosen and report it, or
   also write an MKV with the tracks? *Recommended: keep it and report it.*
6. **A local video** is only subtitled when re-encoded (`DOWNLOAD_VIDEO` means "Re-encode the
   video?" for a local file). Is that acceptable, or should a local video be subtitled without
   re-encoding?
7. **The name `VIDEO_SUB`** is the YouTube one, but reads as "any subtitles". `VIDEO_SUB_YT`
   would sit beside `VIDEO_SUB_WHISPER`. A rename after release means reading the old name
   forever (`legacy=`), so now is the cheap time. *As specified unless you say otherwise.*
8. **A sample profile for subtitles** (`profile3-video_subtitler.txt`)? *Optional.*
9. **Refined subtitles without a refined transcript.** Today `AI_REFINEMENT=y` turns AI back off
   when no transcript `PROMPT` is chosen or no API key is found, and every chosen prompt runs.
   So refined subtitles would also cost a refined transcript. Should `*_SUB_AI_REFINEMENT` be
   able to run without a transcript `PROMPT`? *Recommended: yes. Your call: it changes what
   `AI_REFINEMENT=y` with no prompt does.*
10. **Names and titles** proposed above:
    - hard copies: `<video name> - Hard Subs [Whisper en].mp4`;
    - refined `.srt` files: `<transcript name> - AI Refined.srt`;
    - track titles: "YouTube en", "Whisper en", "Whisper en, AI refined";
    - the default track: the first refined one, or else the first.

    Keep them, or name them differently?

Settled by the specification, from the earlier list:
- Which timing source wins: none does, because each source is its own yes.
- Whether hard subtitles ship: yes, in phase 2.

## Background: the prototype

`subtitle_prototype.py` (tests: `test_subtitle_prototype.py`) is standalone. It borrows the
main script's AI backends and ffmpeg settings, and nothing in `OpenAIYouTubeTranscriber.py`
calls it.

```
python subtitle_prototype.py "lecture.mp4" --polish api --mux soft
python subtitle_prototype.py https://youtu.be/jNQXAC9IVRw --timing youtube --mux both
python subtitle_prototype.py "talk.mp4" --translate          # Whisper's English, by segment
```

| Step | Source of truth | Notes |
|---|---|---|
| Timing | Whisper word timestamps, or YouTube's captions | No language model is involved in timing |
| Cues | `build_cues` | ≤2 lines of ≤42 characters, ≤7 s, cut at pauses (0.6 s) and sentence ends |
| Polish | `polish_cues` | Numbered batches of 40 cues; text fixed in place, times untouched |
| Output | `.srt`, soft track, burn-in | Soft: stream copy. Hard: full re-encode (x264, CRF 18) |

Timing sources:

1. **A subtitle track the uploader wrote**: each cue's timing is kept as set.
2. **Whisper**: per-word times (`word_timestamps=True`). For a translation into English, per
   segment only, with words spread across the segment by length. Whisper warns that word times
   on translations may not be reliable.
   - Tried on a Spanish fable: `small` mistranslates (the hare became "the lion").
   - `medium` reads well, its cues within about 0.3 s of the speech.
3. **YouTube's speech recognition** (json3): per-word start times.

Polish checks every reply line before using it. A cue keeps its original text when the reply:
- leaves its number out, or gives the number twice;
- moves words into or out of it (the whole batch is matched word by word, so a word that
  crosses a cue boundary is caught);
- loses more than a third of its words, or adds more than half again;
- no longer fits two lines.

### What the prototype found

Each of these was checked on real videos or in the tests. The videos were "Me at the zoo", a
3.5-minute auto-captioned music video and a Spanish fable.

- **Whisper stretches words over silences.** After a pause, it puts the first word at the
  segment's start with no length, and the next word absorbs the silence ("The" at 3.88 s,
  "cool" from 3.88 to 5.38 s). `tighten` trims any word longer than its letters plausibly take.
  On "Me at the zoo", this moved a cue from 1.44 s early to 0.66 s early, compared with the
  uploader's track.
- **Whisper mishears words that polish should fix**: for example, "one of the elephants" for
  "in front of", and "hunts" for "trunks".
- **YouTube's recognised captions** give each word a start time but no end, and each event's
  duration overlaps the next. A word therefore ends where the next one starts, capped at 1.5 s.
  An event's first word arrives without a leading space ("to" + "love." came out as "tolove.").
- **Fitting two lines is not "84 characters".** A line can only break at a space, so an
  84-character cue produced a 44-character line. `fits` tries the actual break.
- **Where a full cue is cut.** A sentence or clause end had to fall in the cue's second half to
  count. That cut "...bajo la sombra de un" / "árbol a descansar." and left "tortuga." alone in
  a cue. A full cue now ends at its last sentence end, or its last clause end a third in, and
  "Mr." does not end a sentence.
- **Burning in on Windows**: ffmpeg's `subtitles` filter reads the file name inside its own
  filter syntax, where `C:`, backslashes and quotes all need escaping. Running ffmpeg next to a
  copy named `subs.srt` avoids it. This is tested with a folder named `it's a [test], folder`.
- **Containers**: MP4/M4V/MOV take only `mov_text`, MKV takes SRT, WebM takes WebVTT.
  Matroska leaves out the `und` language tag.
- **Not yet tested**: polish against a live model (there is no API key on the development
  machine), and timing quality and speed on long videos.

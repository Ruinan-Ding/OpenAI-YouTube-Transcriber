# Changelog

## [Unreleased]

Fixes for the sixteen findings in `docs/CODE_REVIEW_REPORT.md`, each with a
regression test.

### Changed

- **Whisper is told the language spoken, not the one to write** (F06). A new
  `SOURCE_LANGUAGE` field names the spoken language, and by default (`auto`)
  Whisper detects it. `TARGET_LANGUAGE` is the language to write: `auto` (now
  what Enter takes) is the language spoken, `en` is Whisper's own translation
  into English, and any other language, which Whisper cannot write, comes back
  as the spoken-language transcript with a note pointing at
  `prompt0-translator.txt`. Transcripts are named for the language they are
  in, and two targets that come out the same are saved once. Before, the
  target was passed as Whisper's spoken-language hint, so French asked of
  English speech was decoded as if it were French, and files were labelled by
  what was asked for. `profile0-translator.txt` now translates into English.

### Fixed

- **A refinement renamed onto its own source is no longer deleted** (F01). The
  source is never retired when an output landed on its path, the Raw/ copy is
  written before the refinement, and transcripts are written atomically.
- **A refinement that failed to save no longer retires its source** (F02):
  only a whole refinement that actually landed replaces it.
- **Audio no longer overwrites the merged video** in a shared folder and
  container (F03); it becomes `<name> - Audio.<ext>`, remote and local alike.
- **Sources of one list with one name keep their own files** (F04): the second
  takes its video ID, or a number, and the same source twice keeps its name.
- **Scratch cleanup deletes only what the pass fetched** (F05), in a folder of
  its own under `Video/Temp`, even when the pass fails part way.
- **A caption request stands for every video of a list** (F07), rather than
  being narrowed to the tracks the first video had.
- **Saved profiles read back exactly** (F08): values dotenv would change are
  single-quoted, and single-quoted values are read literally. This needs
  `python-dotenv>=1.2.3`, the first release to read a quoted value that ends
  in a backslash; earlier ones lost that value and the line after it.
- **A typed prompt is saved with the profile** (F09) as `Prompt/prompt<N>.txt`,
  instead of `PROMPT=(inline)`.
- **A new `config.txt` names the profile actually written** (F10).
- **A transcript or prompt in another encoding no longer ends the run** (F11):
  UTF-16 and BOM-marked files are read, and anything else that is not UTF-8
  is reported and skipped.
- **A failed enhancement hands back the text unchanged** (F12), and **every
  chunk respects its size budget** (F13), mixed scripts included: chunks are
  exact spans of the text rather than `textwrap` output. The local backend
  measures its chunks with the model's own tokenizer, as it already measured
  the room they have.
- **Installed copies carry the shipped prompts and sample profiles** (F14).
  The samples are copied into the working directory's `Profile/` on first
  run. Each file is named in `setup.py` rather than globbed, so a wheel built
  from a checkout never carries the user's own prompts or profiles, and never
  `config.txt`.
- **WebVTT captions are read by cue block** (F15): cue numbers, `NOTE`, `STYLE`
  and `REGION` blocks are not speech, and `&amp;` is decoded.
- **`~/clip.mp3` is accepted as a source** (F16).

### Fixed after a second review

- **One place settles every output's name.** A batch reserves every file it
  writes, and every source it has yet to read, comparing folders through
  symlinks and names without regard to case. A refinement no longer lands on
  the transcript queued after it, a Whisper transcript on a queued transcript
  of its name, two audio streams that round to one bitrate on one file, or the
  audio on the merged video through a symlinked folder.
- **A local source reached another way is never written over.** `convert_media`
  compared paths as text, so a symlinked `VIDEO_PATH` - or `C0001.MP4` beside
  `C0001.mp4` on Windows or macOS - let ffmpeg overwrite the file it read.
- **A summary never replaces a source whose `Raw/` copy failed to save**, with
  `KEEP_TRANSCRIPT=y` as with `n`.
- **A prompt that fails no longer saves the unrefined text** beside another
  prompt's output; when every prompt fails, the transcript is saved once.
- **The log names the `Raw/` folder the copy really went to** under
  `TRANSCRIPT_PATH`.
- **ffmpeg's output is read as UTF-8.** Read in the locale's encoding (cp1252
  on Windows), a Japanese filename in it raised and ended the batch.
- **A superscript digit at a menu asks again** instead of raising.
- **A video with nothing to pick gives way to the next** while the settings
  are asked, instead of ending the batch.
- **Input running out ends the run without a traceback**: exit code 0 once the
  work asked for is done (a `REPEAT=y` round asking for more), 1 otherwise.
  A single-source yt-dlp error exits 1 as `DownloadFailed` does.
- **Profile fields read as their questions do**: `s`/`skip` declines a
  `*_RENAME` or `*_PATH`, `~` works in a `*_PATH`, `LOAD_PROFILE` is read as
  dotenv reads it (quotes and a trailing `# comment`), and `USE_EN_MODEL=y`
  is ignored when `SOURCE_LANGUAGE` or `TARGET_LANGUAGE` rule English out.
- **A caption pick from the listing stands for each video of a list.** The
  original is recorded as `original` (also accepted in
  `DOWNLOAD_YT_TRANSCRIPT`), so the next video's original is taken, not its
  translation into the first one's language; picking every track is `all`.
- **Audio is copied only into a container that plays it**: Opus asked for as
  `mp4` becomes AAC, AAC as `wav` becomes PCM.
- **Whisper work is not repeated**: `auto,en` on English speech is one pass,
  a model that failed to load is not tried again for each target and source,
  and detection decodes the first 30 seconds rather than the whole file.
- **The local model is given `torch_dtype` or `dtype`**, whichever the
  installed transformers takes (renamed in 4.56).
- **Downloads reuse the metadata already fetched** instead of extracting each
  video again per deliverable.

### Also fixed

- **ffmpeg no longer reads the keyboard.** It takes its commands from stdin
  while it works: `q` stopped a re-encode part way, and the first character
  of an answer waiting after it was eaten, so a path piped to a profile's
  next round arrived without its leading `/`. ffmpeg and ffprobe now get no
  stdin, as the ffmpeg runs of yt-dlp and Whisper already did.

### Development

- **`pyproject.toml` replaces `setup.py`.** Same package, module, data files
  and console command; the optional AI backends are now the `ai` extra
  (`pip install ".[ai]"`).
- **The tests run under pytest** (`make test`, and in CI with `-ra`), and
  still without it (`python test_transcriber.py`). `conftest.py` restores
  whatever a test patched after every test, so a failure cannot leak into the
  next; the plain runner now runs every test and lists each failure instead of
  stopping at the first; a test that cannot run here (no ffmpeg, no symlinks)
  is reported as skipped instead of passing silently.
- **CI and hooks are current**: `actions/checkout@v7` and
  `actions/setup-python@v7` (Node 24; the v4/v5 majors ran on the deprecated
  Node 20), isort 9.0.2, flake8 7.4.1 from its own repository (the mirror
  was archived) and pre-commit-hooks v6.0.0. `make lint` runs isort as well
  as flake8, as CI does. Ten files gained the final newline the repository's
  own end-of-file hook asks for.
- **Each setting is described once.** A profile and an interactive session
  (with the answers a "Run again?" round remembers) used to be settled by two
  functions of about 150 lines each, which had drifted apart: a field could
  mean one thing typed and another in a profile. `_configure` now settles
  every setting for both. A `SETTINGS` table says what a profile that leaves a
  field out, or blank, means, and two small sources (`_Profile`, `_Remembered`)
  say where the answers are kept. A test holds the two to the same result for
  the same answers. What a user sees changes only at the edges:
  - `s` and `skip` decline a stored yes/no, as they already did for
    `AI_REFINEMENT` and the placement fields. `DOWNLOAD_VIDEO=skip` was called
    invalid and asked.
  - A pre-1.2 `NO_AUDIO_IN_VIDEO` that is neither yes nor no is asked about,
    as any yes/no field is, instead of being taken as no.
  - A profile's format fields are reported when loaded, like its other fields.
  - "Invalid value" names the profile it came from, not ".env".
  - "Loaded URL: … transcript(s) to refine" appears only when the profile's
    own URL names them, not for transcripts typed at the prompt.

## [1.2.0] - 2026-09-12

### Added

- **A profile can live anywhere.** `LOAD_PROFILE=` and the profile prompt both
  take a full path, with `~`, without the `.txt`, or in the quotes a copied
  Windows path arrives in. An absolute `LOAD_PROFILE` did load before, by way
  of `os.path.join` dropping `Profile/` in front of it, but the run kept only
  the filename, so "Run again?" looked for it in `Profile/` and missed.
- **Refinement without a video.** `AI_REFINEMENT` can now run on a transcript
  already on disk: answer the source prompt with `S` to pick from
  `Transcript/Raw/` and `Transcript/`, or name a `.txt` path - several
  run as a batch, every prompt over every transcript. A
  profile takes the same answers in `URL=`, so a refinement replays
  unattended. The refined source leaves `Transcript/` as its refinement
  arrives there, its untouched text written to `Transcript/Raw/` unless
  `KEEP_TRANSCRIPT=n`. A transcript already in `Raw/`, one named from outside
  the project, one no prompt changed, and - with `KEEP_TRANSCRIPT=n` - one only
  summarized or translated are never removed.
- **Every resolution, in every format.** The quality and format fields take
  lists too, and multiply out within their own deliverable:
  `VIDEO_RESOLUTION=144p,720p` with `VIDEO_FORMAT=mp4,mkv` is four merged
  videos, and `VIDEO_ONLY_*` and `AUDIO_*` do the same for their own files.
  The prompts take those same lists, typed or picked from the menu by number,
  so this needs no profile.
  Each stream is fetched once however many files want it - two containers are
  two conversions off one download, and a merge still borrows the video-only
  copy when both asked for the same resolution. Transcription does not
  multiply: one copy of the audio is recognised however many deliverables were
  asked for, so a list in `TRANSCRIBE_AUDIO_QUALITY` names that copy rather
  than several of them. Only where two formats would land on one name - `h264`
  and `mpeg4` both live in `.mp4` - does the format join the filename; a single
  format is named exactly as it always was.
- **A local file gets the same three deliverables, by re-encoding.**
  `DOWNLOAD_VIDEO`, `VIDEO_ONLY` and `DOWNLOAD_AUDIO` used to be ignored for a
  local source; they now cut the merged video, a copy with the audio stripped,
  and the audio on its own out of the file with ffmpeg, in one run. The
  resolution and format fields mean the same things: a height scales, a number
  sets the audio bitrate, and the format picks the container or codec. A file
  has one stream rather than a list of tiers, so it is its own highest and its
  own lowest - only a number is a constraint, and one at or above what the file
  already is leaves it alone rather than re-encoding it bigger. The source is
  only ever read: a file with no audio says so instead of failing, and a
  deliverable that would land on the source itself is skipped rather than
  written over.
- **`URL` is a list of jobs.** `URL=clip.mp4, youtu.be/vid3, s, youtu.be/vid2, s`
  runs five passes in the order given: two videos, a local file, and two
  refinements that each pick their own transcripts. `s` is an entry like any
  other, so one run can download, transcribe and refine what is already on
  disk. Every other field is answered once and applies to all of them, and the
  menus that list what a video offers - resolutions, audio tiers, caption
  tracks - are shown for the first video in the list. A profile records the
  whole list rather than the placeholder, so it replays as a batch.
- **`TARGET_LANGUAGE` accepts several languages**, comma or space separated:
  `TARGET_LANGUAGE=en,fr,ja` transcribes one download three times and saves a
  file per language, with `AI_REFINEMENT` applied to each. Spacing, case and
  repeats collapse; an unsupported language is named and skipped. With more
  than one language the transcripts are named for the language requested
  rather than the one detected, so two passes cannot resolve to one filename.

- **`DOWNLOAD_YT_TRANSCRIPT` - YouTube's own transcripts as files.** Saved to
  `Transcript/` beside Whisper's. `y` takes the language the
  video was spoken in, `all` takes every track, `f` lists them, and a list
  like `en, fr` takes those. The spoken-language transcript is untagged
  (`Me at the zoo.txt`); everything else is named for its language
  (`Me at the zoo [de].txt`), since a translation transcribes nothing anyone
  said. The source track is identified by YouTube's `-orig` marker and the
  extractor's reported language, not guessed.
  Downloaded transcripts are enhanced by the same `AI_REFINEMENT`, `PROMPT`
  and `KEEP_TRANSCRIPT` as Whisper's, rather than a second set of fields.
  `all` enhances only the original track, since enhancement is charged per
  file and most videos list around 157 languages.


- **Name the files, and say where they go.** Every deliverable takes a
  `*_RENAME` and a `*_PATH` beside its `*_FORMAT` - `VIDEO_*`, `VIDEO_ONLY_*`,
  `AUDIO_*`, and `TRANSCRIPT_*` after `PROMPT`, that one being applied to the
  finished text. A name or an absolute path in the field is used as it stands,
  so a profile carrying one still runs unattended; `y` asks for one, `n` and a
  field that is not there leave the default alone, and a blank one asks. The
  quality and format tags still follow a rename, so `VIDEO_RESOLUTION=144p,720p`
  with `VIDEO_RENAME=lecture` is still two files. A path is checked when it is
  read rather than after the download it would have held, and `TRANSCRIPT_PATH`
  takes the unrefined copy with it. Answered interactively, one question gates
  all eight.

### Changed

- **Every list field takes commas, spaces, or both.** `PROMPT`, `TARGET_LANGUAGE`,
  `DOWNLOAD_YT_TRANSCRIPT`, `URL` and the menus behind them read `en,fr`, `en, fr`
  and `en fr` alike. An entry that already contains a space - a path, a two-word
  language name - is not split further, so only two space-carrying paths in one
  answer still need the comma to separate them.
- **`AI_ENHANCEMENT` is now `AI_REFINEMENT`.** One word for the feature,
  matching the `Transcript/Raw/` copy it is described by and the prompt it
  asks. A profile still saying `AI_ENHANCEMENT=` is honoured under the old
  name, so existing profiles keep running unattended; profiles this script
  writes use the new one.
- **One `AI_REFINEMENT`, `PROMPT` and `KEEP_TRANSCRIPT` for both kinds of
  transcript.** `AI_ENHANCE_YT_TRANSCRIPT` and `KEEP_YT_TRANSCRIPT` existed
  because YouTube's transcripts and Whisper's went to two folders; they share
  one now, under names that cannot collide, so they take one answer each. A
  run that only downloads transcripts reaches `PROMPT` and `KEEP_TRANSCRIPT`
  too, which previously hung off `TRANSCRIBE_AUDIO` and were skipped.

- **`PROMPT=` takes a list, and every prompt runs over every transcript.**
  `PROMPT=prompt-refinement.txt,prompt0-translator.txt` across three
  transcripts is six files, each tagged with the prompt that made it; two
  prompts that read as the same word are still given a file each. An entry
  that is not a file in `Prompt/` is taken as a path to one anywhere, so a
  prompt need not be copied into the project to be used.

- **`AI_PROVIDER=` names the backend; `AI_REFINEMENT=` is back to yes or no.**
  Which model enhances a transcript is a fact about your machine and accounts,
  so it lives in config.txt beside the key it selects, while the profile only
  says whether to enhance. `AI_PROVIDER=local` runs a local model and `MODEL=`
  carries its HuggingFace id, the same field the cloud models use. Profiles
  that said `AI_REFINEMENT=openrouter` or `AI_REFINEMENT=qwen2.5-1.5b` now
  say `AI_REFINEMENT=y` with the rest in config.txt.

- **config.txt carries one `API_KEY=` and one `MODEL=`** in place of a pair per
  provider. One provider runs per session, and which one is read off the key:
  `sk-ant-` is Anthropic, `sk-or-` OpenRouter, `sk-` OpenAI, so a blank
  `AI_PROVIDER=` uses whoever the key belongs to instead of always defaulting
  to OpenRouter. A blank `API_KEY=` falls back to the vendor's own
  variable (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY`), so a
  key already exported in the shell still works. `BASE_URL=` likewise replaces
  the three `*_BASE_URL` overrides.

- **Whisper transcripts are named `Title [Whisper en].txt`.** YouTube's own
  transcripts share the folder now, and the plain title belongs to the text the
  video was published with, so Whisper's reading says whose it is - in every
  language, English included. Previously an English transcript was `Title.txt`.

- **Downloads now use `yt-dlp` instead of `pytubefix`.** YouTube serves SABR-only
  streams that require a fully attested PoToken, which pytubefix's botGuard
  cold-start token no longer satisfies; downloads failed with
  `SABRError: ... PoToken PENDING`, and every other pytubefix client was either
  bot-detected or cut off with HTTP 403 partway through the file. `yt-dlp`
  replaces both the metadata and download paths. `py_mini_racer` is dropped with
  it, having existed only for pytubefix's JS interpreter.
- An AI enhancement pass no longer overwrites the original transcript. The text
  as Whisper produced it is now kept in `Transcript/Raw/`, while the finished
  transcript stays in `Transcript/` as before. The new `KEEP_TRANSCRIPT` profile
  field turns that copy off; it is ignored when enhancement is not running, and a
  blank value asks, defaulting to keeping it.
- An enhanced transcript is named after the prompt that produced it, so refining
  one video with several prompts no longer has each result overwrite the last:
  `prompt0-translator.txt` saves `Title [fr] - translator.txt`. A prompt with no
  description in its filename, and a custom prompt typed at the menu, are tagged
  ` - Refined` rather than left untagged, which would name the refinement exactly
  like the transcript it refined.
- `AUDIO_RESOLUTION` selects the audio quality tier, the way the video resolution
  field selects a height: `highest`, `lowest`, a tier name (`low`, `medium`,
  `high`), a kbps ceiling, or `fetch` to list what the video offers. A tier the
  video does not have is reported and re-prompted rather than silently
  downgraded. Only original-language streams are offered, so a dubbed video
  cannot be transcribed in the wrong language by picking a "quality".
- `RESOLUTION` is renamed `VIDEO_RESOLUTION`, next to the new `AUDIO_RESOLUTION`.
  The old name is still read, so profiles written before this keep working.
- Downloaded files are named for what they actually contain. The extension was
  hardcoded, so `Title.mp3` held Opus in a WebM container and a 144p `Title.mp4`
  held VP9 in WebM - readable by ffmpeg and Whisper, rejected by media players.
  The merged video, which ffmpeg writes, is still `.mp4`.
- Downloads below the best available quality are labelled with it, so fetching
  the same video at two resolutions no longer has the second silently reuse the
  first: `Title [144p low].mp4`, `Title [low].webm`,
  `Title [144p] - Video Only.webm`.
  A download at the default quality is unlabelled, as before. The label is the
  bitrate of the stream yt-dlp actually selects rather than the word typed or
  the tier's headline figure, so `lowest`, `low` and `64` all name the file
  `[60k]` when they land on the same 60 kbps stream, and video `lowest` reads
  `[144p]`. Verified against the downloaded files on three videos.
- The `fetch` menu shows each tier's real bitrate (`medium (106k)`) rather than
  the tier's headline figure, and accepts a bitrate typed in place of a menu
  number. A bitrate is matched against individual streams rather than tier
  ceilings, so it can select within a tier: a tier spans roughly 47k to 60k.
- An `AUDIO_RESOLUTION` bitrate below every tier a video offers now selects the
  cheapest tier. It filtered to nothing and fell back to `bestaudio`, so asking
  for the smallest possible download returned the largest.
- `NO_AUDIO_IN_VIDEO` is renamed `VIDEO_ONLY`, and its download is suffixed
  `- Video Only` rather than `- No Audio`. The old field name is still read.
- Each download has its own quality field: `VIDEO_RESOLUTION` and
  `VIDEO_AUDIO_RESOLUTION` for the merged file, `VIDEO_ONLY_RESOLUTION` for the
  bare stream, `AUDIO_RESOLUTION` for the standalone audio, and the new
  `TRANSCRIBE_AUDIO_QUALITY` for the audio fetched to transcribe, which
  defaults to the cheapest stream. One resolution field previously governed both
  video downloads and one audio field governed every audio fetch.
- A blank quality field asks, listing what that video offers, instead of
  silently taking the best available. Enter takes the field's default.
- Output formats are selectable: `VIDEO_FORMAT` (container, default `mp4`),
  `VIDEO_ONLY_FORMAT` (video codec, default `h264`) and `AUDIO_FORMAT`
  (container, default `mp3`). `original` keeps what YouTube served with no
  re-encode, `DEFAULT` takes the default, and a blank field lists every format
  the installed ffmpeg can write. The merged file copies its video stream
  wherever the container allows, so only its audio is re-encoded.
- `VIDEO_ONLY` is independent of `DOWNLOAD_VIDEO` instead of modifying it. It was
  a switch between two mutually exclusive outputs; it is now its own download, so
  a run can save the merged video, the bare video stream, or both. When both are
  asked for the stream is fetched once and the merged file is built from the copy
  that was kept. The video-only file stays in the stream's own container, neither
  remuxed nor re-encoded.

### Removed

- **moviepy and requests are no longer dependencies.** `requests` was never
  imported. moviepy served one branch that extracted a local video's audio
  before transcribing it, which could not be reached - a local source is only
  accepted after the same media check that branch tested for - and was not
  needed either, since Whisper reads a video container as readily as an audio
  one.

### Fixed

- A deliverable asked for in several formats no longer costs the download when
  every one of those conversions fails. The file as downloaded was deleted once
  the last format had been tried, on the assumption that at least one had
  replaced it, so a run could end with neither; a single format has always kept
  it. The one-format and several-format paths are now the same code.

- A profile that does not name a `URL` - a template with the field blank, and
  every round of a `REPEAT=y` batch - now asks for the source up front, with
  the prompt that takes a list or `S`. The question was deferred into the run
  and asked by a single-source prompt instead: it advertised `S to refine a
  transcript` and a comma-separated list, refused both, and asked again, so a
  repeated refinement could never get past it.

- A video later in a `URL` list is named after itself again. Its title is
  fetched once, to build the menus, and a local file ahead of it in the list
  renamed the run after itself; the video's own pass then saved its transcript
  under the local file's name and overwrote whatever was already there. The
  title is now carried and restored with the metadata it came from.

- Mistyping a file path no longer prints ffprobe's exit status at you. The
  media check runs ffprobe to ask a question, and "not a media file" is the
  answer to it, so a traceback-shaped line was appearing ahead of the message
  that actually helps.

- `f` at the transcript prompt lists the tracks it offers to. `f` is also how
  yes/no fields spell "false", and the refusals were read first, so the answer
  the prompt advertised did nothing at all. A bare `no` still means no;
  Norwegian is reachable as `nb`, `nn`, or through the listing.
- A profile made from a session records which AI backend it used. Only
  `AI_REFINEMENT=y` was written, so replaying a local-model session sent the
  transcript to whichever cloud provider the key on file belonged to, and
  billed for it. `AI_PROVIDER=` and, for a local model, `MODEL=` are written
  alongside it, and left out entirely when no backend was settled - a blank
  line would override config.txt with nothing.
- A video that publishes only muxed streams downloads instead of exiting. The
  resolution menu counts those streams, but the selector asked for
  `bestvideo`, which no muxed stream matches, so a resolution the menu had
  just offered ended the run. Every branch now falls back the way the audio
  selector always has.
- A conversion that ffmpeg reported as successful while writing an empty file
  no longer costs the source. The pre-conversion download is deleted on the
  converter's word, so the run's only deliverable could be destroyed and
  replaced with an unusable file.
- A run whose only output is YouTube's own transcript is offered profile
  creation, like every other run that produced something.
- `all` no longer announces enhancing the original transcript when there is no
  way to tell which one that is. It enhanced nothing and said otherwise; it
  now says so and suggests naming a language.
- Transcripts are fetched only in formats the parser reads. A track served as
  srv3 or ttml was parsed as if it were VTT, putting XML fragments in the
  transcript and billing the enhancement API for them.
- A script variant is no longer answered with its translation. A video spoken
  in `zh-Hans` could have `zh-Hant` filed as the original, and under `all` it
  was the one enhanced.
- `DOWNLOAD_YT_TRANSCRIPT` is forgotten when the session ends, like every other
  remembered answer, instead of being silently reused by the next one.
- `embed/videoseries?list=` URLs are rejected as the playlists they are.
- The Whisper model is released when a session ends. "Run again?" re-enters the
  program from inside the finished session, so each repeat added another model
  to memory rather than replacing it - four repeats at `medium` held four.

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
- A source that cannot be fetched no longer ends the whole `URL` list. The
  failure exited the process from inside the download itself, so a private or
  region-blocked video at position two meant positions three and four were
  never attempted; that pass is now reported and the batch carries on. A run
  whose only source fails still exits non-zero. The prompt offering a
  replacement for an unavailable video takes Enter for "give up on this one",
  which it had no way of saying before - and an unattended run, whose input has
  run out, says it that way too rather than waiting on a prompt.
- Errors go to stderr rather than stdout, so redirecting a run to a file no
  longer swallows the reason it stopped.
- Opening the finished transcript no longer crashes a headless machine, which
  has no `xdg-open`. The file was already saved by then.
- A `*_RENAME` given to a run with several sources no longer writes them all to
  one filename. One name cannot name several videos, so the name now leads and
  each source's own title still tells them apart; a single source is named
  exactly what was asked for. A transcript was the quiet case - the second
  simply overwrote the first.
- A replacement URL accepted while the questions are still being answered is no
  longer thrown away when the run starts. The list of sources is what each pass
  is handed, and the dead URL was coming back from it.
- A profile whose `AI_ENHANCEMENT` names the backend rather than saying `y` -
  `openrouter`, `anthropic`, `local`, or a model name, all of which that field
  accepted before 1.2 - replays unattended again instead of reporting an
  invalid value and stopping to ask.
- Prompts are found whether they sit beside the module or under the working
  directory, so an installed `openai-youtube-transcriber` can see its own
  `Prompt/` folder.
- A profile written before `DOWNLOAD_YT_TRANSCRIPT` existed replays unattended
  again. A field a profile does not carry means no, the way `DOWNLOAD_AUDIO`
  and `VIDEO_ONLY` already read one; this one stopped to ask instead.
- An audio quality copied back from the menu as `106k` is taken as the bitrate
  it is. The menu prints its tiers that way, then refused the answer it had
  just offered and asked again.
- `original` asked for beside another format no longer loses to it. The
  re-encode could land on the very file `original` asked to keep, overwriting
  it; both now carry the format in their name, as two formats sharing one
  extension already did. The merged video had no such guard at all, so
  `VIDEO_FORMAT=mp4,original` wrote one file over the other.
- `ffprobe` is checked at startup alongside `ffmpeg`. Some builds ship without
  it, and every question about a local file goes through it - a missing one
  read as "this file has no video stream" and produced nothing.
- `pip install .` installs the application again. The package listed no modules
  to install, so the `openai-youtube-transcriber` command it created had
  nothing to import.
- An API key typed at the prompt is no longer echoed to the terminal, where it
  stayed in the scrollback and in any log of the session.
- "Run again?" is a loop rather than a call back into `main()`, so a long
  session of repeats keeps one stack frame instead of one per round.
- The typed resolution and audio-quality prompts no longer open mid-sentence
  with an ellipsis ("... enter desired video resolution").
- `VIDEO_FORMAT`, `VIDEO_ONLY_FORMAT` and `AUDIO_FORMAT` take the format written
  with the dot people write extensions with: `.mp3` means what `mp3` means, at
  the prompt and in a profile. It used to report "ffmpeg cannot write '.mp3'",
  which stopped an unattended run on a field that was right, and quietly cost a
  file when one entry of a list carried the dot.
- `Profile/config.txt` ships blank in the one-key layout - `LOAD_PROFILE`,
  `AI_PROVIDER`, `API_KEY` and `MODEL`, with a note on what `AI_PROVIDER`
  accepts. It stays tracked, and `.gitignore` does not apply to a tracked file,
  so a key filled into it is one `git commit -a` from being published; README
  gives the one-time `git update-index --skip-worktree` that keeps it out, and a
  test fails if the copy git holds has any field filled in. With no config.txt,
  the first saved profile writes the same fields, where it used to write
  `LOAD_PROFILE` alone.
- The shipped prompts are rewritten for the text they are actually given: one
  unbroken run of speech recognition, perhaps one chunk of a longer video. The
  refinement prompt carried a 10KB example of YouTube's timestamped copy-paste
  format, which no transcript here is in, at the cost of some 2,200 tokens a
  chunk. It corrected misheard words "based on the context of software
  engineering" whatever the video was about, and asked for key sentences in
  capitals. None of the prompts said which language to write in, so an English
  prompt could turn a Spanish transcript into English, and none said that a
  speaker saying "summarize this" is speech to work on, not an instruction to
  follow. The translator's note to the reader about changing its language was
  sent to the model; the target language is now the file's first line.
- Chunking works for Chinese and Japanese. It split only at `.`, `!` or `?`
  followed by a space, so it cut their sentences anywhere, and rejoined chunks
  with a space, putting spaces into the text. It sized chunks at four characters
  a token, where Chinese runs about 1.7, so a local chunk held 2.4 times its
  budget. And both output caps fell short: the local one counted words by
  spaces, so a Chinese chunk was one word and its reply stopped at 256 tokens,
  about a third of the chunk - enough to pass the length check and be saved -
  while Anthropic's was characters over three, which cut a full chunk's reply
  off and kept the chunk unrefined. Chunks now also split at `。！？` - and at
  Hindi's `।` and Arabic's `؟`, which were cut through the same way - are sized
  by UTF-8 bytes, and have their output budgeted from that size.
- An OpenAI-compatible reply cut off at the output limit is no longer saved as
  the chunk's refinement. The Anthropic path kept the original chunk when its
  reply ran out of room; this one never checked, so half a reply stood in for
  the whole chunk. A reply with no content keeps its chunk too, instead of
  raising.
- A local model's translation into Chinese is no longer thrown away. The check
  that refuses a reply too short to be a whole chunk counted characters, and a
  faithful Chinese translation of English has about a quarter of them; it counts
  bytes now.
- The summarizer works on a local model. That check threw away any reply under
  30% of its chunk, which a summary is on purpose, so the transcript came back
  unsummarized. A prompt whose filename says summarizer is let off it, and a
  local reply that used its whole output budget is kept out as cut off, whatever
  the prompt, as the cloud providers' already were.
- A local refinement that dropped a sentence is no longer saved. The length
  check passed any reply over 30% of its chunk, and one reply left out a whole
  paragraph that way. A refinement - a prompt whose filename says refinement -
  that leaves out 15 or more of the chunk's words in a row now keeps the chunk;
  replies that were whole left out at most 7, to filler and misheard words.
- A chunk kept unrefined keeps its line breaks. The chunker joined sentences back
  on spaces, so a transcript with paragraphs or headers, such as one already
  refined, came out of any refused chunk as one line with its headers run into
  the text. A number opening a line no longer ends a sentence either: a numbered
  list could end one chunk on "1." and open the next with the item.
- The GPT-2 local models no longer fail on every chunk. A local chunk was sized
  from the model's context without counting the prompt that goes with it, and
  a shipped prompt is 621 to 804 of GPT-2's 1024 tokens, so each full-size
  chunk ended in "index out of range in self". Chunks and the reply budget now
  fit in what the prompt leaves, and a prompt that leaves no room skips local
  enhancement with a message saying so.
- A download is fetched rather than taken from a file already there under its
  name. The name is the video's title or a `*_RENAME`, which another video can
  share, and yt-dlp handed back that video's file as this one's. Audio kept for
  a transcription retry is still reused, named by the video's id.
- A Whisper model that fails to load falls back to `base`. A corrupt download,
  a checksum mismatch and an unknown name raise `RuntimeError`, which the
  fallback did not catch, so the batch ended in a traceback.
- Each video of a `URL` list gets its own YouTube transcript tracks. The answer
  was matched against the first video's tracks for all of them, so a Japanese
  video after an English one saved the English translation and never its
  original; and a list led by a video with no captions saved none for any video.
- Output a console cannot encode no longer ends the run. Redirected to a file on
  Windows, stdout is cp1252, and a Japanese, Russian or Hindi transcript raised
  as it was printed, before it was saved; a title or path did the same.
- Enter at a resolution or audio menu records `highest` (or `lowest`), not the
  height it landed on. A profile made from the session said `240p`, fetched
  240p of the next video, and asked again - crashing unattended - on one
  without it.
- A profile made from a refine-only session names the transcript where the
  session left it, in `Transcript/Raw/`. It named the `Transcript/` file the
  same session moved, and replayed as "Invalid input" and a crash.
- The merged video no longer takes the name of the audio it is made from. With
  `VIDEO_PATH` and `AUDIO_PATH` one folder and both in WebM at the top tier,
  ffmpeg refused to write over its input and the failed merge's cleanup deleted
  the downloaded audio; the merge is now tagged with its format.
- An audio file given as a local source is not re-encoded into `Video/` as an
  `.mp4` with no picture; `DOWNLOAD_VIDEO` says it has no video stream.
- One source re-asked a question an unattended run cannot answer - a resolution
  that video lacks - and the rest of the list was abandoned. That source fails
  and the list carries on.
- "Run again?" remembers the Whisper model when Enter picked it, rather than
  asking again every round.
- `API_KEY` is not sent to a provider its prefix says it does not belong to. An
  OpenRouter key with `AI_PROVIDER=anthropic` went to Anthropic, failed every
  chunk, and passed over the `ANTHROPIC_API_KEY` exported for it. A `BASE_URL`
  still takes `API_KEY` as it stands.
- `local` at the backend prompt runs the default local model it names, not
  `MODEL`, which there is a cloud model's name that HuggingFace cannot load.
- A profile with `REPEAT=y` no longer gives the next video the last one's
  `*_RENAME`, overwriting its file; an interactive repeat already dropped it.
- `KEEP_TRANSCRIPT=n` no longer deletes a refine-only source after a summary or
  a translation, which do not say what it said; only a refinement replaces it.
  The question now says that `n` keeps only the refined text.
- `DOWNLOAD_YT_TRANSCRIPT=all` fetches each track from the metadata already in
  hand, rather than extracting the whole video again per track - some 150
  extractions per video.
- A batch no longer opens a window for every transcript it saves.
- The language a transcript is named for is the same on every run; langdetect
  samples at random, so a short or mixed transcript could be `sk` once and `hr`
  the next time.
- A reply wrapped in a code block is unwrapped. The local model fenced its
  summary in ```` ```markdown ```` though the prompts say not to, and the fences
  were saved into the file.
- A chunk that enhancement could not use is reported. A local model's reply
  too short to be the whole chunk, or a backend error, kept that chunk as
  transcribed while the run said "enhancement complete", so a partly refined
  transcript read as a refined one. The run now names the chunks it kept.
- A local model is given about 1,200 characters at a time rather than 3,200.
  Refining a 20-minute talk with Qwen2.5-1.5B, a 550-word chunk came back cut
  down, commented on or replaced by the prompt's example in 5 of 12 runs, and
  a 200-word one in 1 of 6; one of the runs saved the model's notes on its own
  edits into the transcript.
- The refinement, summarizer and explainer prompts carry a second, Spanish
  example. With only an English one, the local model answered a Spanish
  transcript in English every time, whatever the prompt said about language.
- Enhancement no longer ends every prompt with "no preamble, headers, or
  commentary" right after prompts that ask for headers. Chunk replies were joined
  with a space, which put each chunk's opening header on the end of the previous
  chunk's last line; a chunk that ended a sentence is now followed by a blank
  line. A transcript with no punctuation is cut mid-sentence, and that seam still
  closes on a space, so the sentence is not split across two paragraphs.
- The video-only file has no audio track, whatever stream YouTube served. A
  height published only as a progressive stream matches no video-only selector,
  so the download fell back to a muxed one; with `VIDEO_ONLY_FORMAT=original`
  nothing then re-encoded it, and a file named "- Video Only" kept its audio.
  The track is now dropped by copying the video rather than re-encoding it, so
  `original` still costs no second generation.
- The merged video carries the audio tier it was asked for. Both streams were
  handed to ffmpeg without naming which to use, so a video that arrived muxed
  gave ffmpeg two audio tracks to choose between and it took the one with more
  channels - which could be the video's own rather than the tier downloaded
  beside it.

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

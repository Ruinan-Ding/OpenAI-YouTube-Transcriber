# Code correctness review

Reviewed September 26–27, 2026, against commit `99271f5c60acaafa6af02bae8d9a439e63e1b74d`.

This review found **16 correctness issues: 4 high, 11 medium, and 1 low priority**. The highest priorities involve deleting transcripts or overwriting requested outputs. Application code was not changed.

The review covered the application module, entry points, packaging, dependency declarations, CI, existing tests, profiles, prompts, and relevant documentation. Findings below include their trigger, observed behavior, source locations, and a suggested correction. Line numbers refer to the reviewed commit.

**Priority definitions:** P1/high means data loss in an ordinary supported workflow requiring prompt attention; P2/medium means an incorrect result, broken workflow, or loss requiring a narrower configuration; P3/low means a limited input-handling inconsistency.

| ID | Priority | Finding |
| --- | --- | --- |
| F01 | P1 | Refinement cleanup can delete the newly saved transcript |
| F02 | P1 | A failed refinement save can still authorize deletion of the original |
| F03 | P1 | Audio conversion can overwrite the merged video |
| F04 | P1 | Batch sources with matching names overwrite one another |
| F05 | P2 | Temporary video cleanup deletes files it does not own |
| F06 | P2 | Whisper's input language is treated as a translation target |
| F07 | P2 | Batch caption requests are narrowed to the first video's tracks |
| F08 | P2 | Saved profiles do not preserve literal field values |
| F09 | P2 | Saved profiles lose custom inline prompts |
| F10 | P2 | Newly created config can select the wrong profile |
| F11 | P2 | Non-UTF-8 text files abort processing with an uncaught exception |
| F12 | P2 | Failed enhancement can still change the transcript's words |
| F13 | P2 | Mixed-script chunks exceed their configured size budget |
| F14 | P2 | Built wheels omit the bundled prompts and profiles |
| F15 | P2 | VTT parsing includes metadata and encoded entities as speech |
| F16 | P3 | Home-relative media paths are rejected |

## Findings

### F01 — Refinement cleanup can delete the newly saved transcript

**P1 · Reproduced using actual file writes and cleanup.**

**Locations:** `OpenAIYouTubeTranscriber.py:3836–3846`, `3859–3877`, and `3906–3907`.

Refine `Transcript/talk - refinement.txt` with `prompt-refinement.txt`, set `TRANSCRIPT_RENAME=talk`, and select `KEEP_TRANSCRIPT=n`. The output filename is again `talk - refinement.txt`. Saving overwrites the source successfully; `_retire_source()` then deletes that same path, treating it as the superseded original.

**Observed:** the source disappeared and the transcript directory was empty after the operation. The save had reported success.

**Correction:** resolve source and final output identities before writing. Never retire a path that is also a retained output. Use a temporary file and atomic replacement for intentional in-place refinement.

**Regression check:** refine an already tagged transcript while renaming it to the stem that reproduces its existing filename, with original retention both enabled and disabled.

### F02 — A failed refinement save can still authorize deletion of the original

**P1 · Reproduced with an injected save failure and real source deletion.**

**Locations:** `OpenAIYouTubeTranscriber.py:3828–3829`, `3837–3846`.

Run a summary prompt and a refinement prompt over an existing transcript with `KEEP_TRANSCRIPT=n`. Let the summary save succeed and the refinement save fail. `rewritten` is set as soon as the refinement changes the text, before its save succeeds. The successful summary sets `kept`, so the final condition calls `_retire_source()` even though no full refinement was saved.

**Observed:** only `talk - summary.txt` remained; the original full transcript was deleted. The probe simulated the documented `False` return from a failed save, as can occur with a read-only destination or insufficient space.

**Correction:** record a successful full refinement only after its output has been saved. Base source retirement on the particular successfully persisted replacement, not on independent flags accumulated from different prompts.

**Regression check:** a successful summary plus a failed refinement must retain the full source, in either prompt order.

### F03 — Audio conversion can overwrite the merged video

**P1 · Reproduced through remote and local pipeline functions with simulated media operations.**

**Locations:** `OpenAIYouTubeTranscriber.py:4348–4358`, `4458–4463`, `4481–4484`; local equivalents at `4097–4100` and `4115–4118`.

Request merged video and standalone audio, give both the same output directory and stem, and select `VIDEO_FORMAT=mkv` and `AUDIO_FORMAT=mkv` at highest quality. These are accepted settings. The merged output is `clip.mkv`. The later audio conversion writes to the same path, replacing the video with an audio-only file. Local exports have the same collision.

The existing guard compares a merge destination with its raw audio input. It does not reserve the filenames that later conversions will use, or compare all deliverables with each other.

**Observed:** both operations targeted `outputs/clip.mkv`; the final simulated file contained only the audio deliverable.

**Correction:** allocate distinct destinations for every deliverable before processing, including final conversions and all input paths. Add a deliverable-type suffix or another stable discriminator when paths collide.

**Regression check:** request video and audio in a shared directory and container, for both remote and local sources, and verify that both outputs survive with their intended streams.

### F04 — Batch sources with matching names overwrite one another

**P1 · Reproduced through the actual batch pipeline with simulated downloads.**

**Locations:** `OpenAIYouTubeTranscriber.py:3122–3125`, `1837–1839`, `4166–4171`, and `1403–1405`.

Process two different YouTube IDs whose titles are both `Same title`, with audio download enabled and `AUDIO_FORMAT=original`. Both receive the destination `Same title.webm`. Downloads explicitly allow overwriting, so the second replaces the first. Batch renaming still appends only the title and does not solve the collision. Local files from different directories with the same basename, and titles that become equal after sanitization, have the same naming problem.

**Observed:** a two-source run produced only one audio file. Videos and transcripts share the same title-based stem generation and overwrite behavior.

**Correction:** track source identity separately from display titles. Include video IDs or allocate unique names for distinct sources across the entire batch, while preserving deliberate reuse for the same source.

**Regression check:** two distinct sources with identical titles, and two titles that sanitize to the same value, must each retain their outputs.

### F05 — Temporary video cleanup deletes files it does not own

**P2 · Reproduced through pipeline execution and real filesystem cleanup.**

**Locations:** `OpenAIYouTubeTranscriber.py:4298–4299`, `4365–4368`.

Scratch video downloads use the shared `Video/Temp` directory. Cleanup removes every file in that directory, without checking whether this run created it. Setting `VIDEO_PATH` to that directory is accepted. For a WebM download merged into MKV, the completed MKV is consequently removed immediately after creation. Pre-existing files or another concurrent run's scratch files are also subject to deletion.

**Observed:** the merge created `Video/Temp/clip.mkv`, but it no longer existed after `_run_one()` completed.

**Correction:** use a unique temporary directory per run or source and delete only explicitly owned scratch files. Keep output paths outside the cleanup set.

**Regression check:** a completed output and an unrelated sentinel file must survive scratch cleanup.

### F06 — Whisper's input language is treated as a translation target

**P2 · Verified against application code and the installed Whisper implementation.**

**Locations:** `OpenAIYouTubeTranscriber.py:661–679`, `2232–2234`, `4408–4425`; `README.md:8`, `48`, and `507`; `OpenAIYouTubeTranscriber/Profile/profile0-translator.txt`.

The CLI advertises a target language and supports several targets, but calls `model.transcribe(file_path, language=target_language)` without a translation task. In Whisper, `language` specifies the language spoken in the recording. Its default task is transcription in that language, not arbitrary target-language translation. The installed dependency documents this in `whisper/decoding.py:82–86` and `whisper/transcribe.py:537–538`.

Consequently, selecting French for English audio does not implement the advertised translation workflow. Several targets repeat recognition with different source-language assumptions; the batch then labels results using the requested targets regardless of detected language. Automatic audio-language detection is also unavailable through normal configuration: a nonempty language, defaulting to `en`, is always supplied. Running `langdetect` on the resulting text afterwards cannot correct the input-language assumption.

**Correction:** separate source language from requested output language. Allow automatic source detection by omitting the Whisper language hint. Use Whisper's translation task for supported translation into English, and a separate text-translation stage for other target languages. Update the translator profile and documentation accordingly. [Official OpenAI speech-to-text documentation](https://developers.openai.com/api/docs/guides/speech-to-text) likewise distinguishes original-language transcription from translation into English.

**Regression check:** inspect Whisper invocation options for automatic detection, explicit source-language transcription, English translation, and translation into other languages; validate the resulting language labels.

### F07 — Batch caption requests are narrowed to the first video's tracks

**P2 · Reproduced with per-video metadata fixtures.**

**Locations:** `OpenAIYouTubeTranscriber.py:3256–3264`, `3932–3935`.

Request `DOWNLOAD_YT_TRANSCRIPT=en,fr` for a batch whose first video offers only English and whose second offers both languages. Configuration stores only the first video's matched keys, `['en']`. The later video is therefore never asked for French, even though the original request included it.

There is a related regional failure: requesting `en` against an initial `en-US` track stores `en-US`. A later video's `en-GB` track no longer matches that narrowed request.

**Observed:** the second video fetched only `en` in the first scenario and nothing in the regional scenario.

**Correction:** retain the requested language codes independently of the first video's resolved track keys, and resolve them afresh for each source. Report missing tracks per source without removing them from the batch request.

### F08 — Saved profiles do not preserve literal field values

**P2 · Reproduced with the real `python-dotenv` parser.**

**Locations:** `OpenAIYouTubeTranscriber.py:2337`; profile loading at `2861`, `2888`, `2917`, and `2937`.

Profile serialization writes raw `FIELD=value` lines. Spaces followed by `#` become dotenv comments, while `${...}` is interpreted as variable interpolation when loading. Valid source or prompt paths can therefore change during a save/reload cycle.

| Saved value | Reloaded value in the probe |
| --- | --- |
| `URL=/tmp/Part #2.mp3,/tmp/other.mp3` | `/tmp/Part` |
| `TRANSCRIPT_PATH=/tmp/Course #2` | `/tmp/Course` |
| `PROMPT=/tmp/prompt-${COURSE}.txt` with `COURSE=unrelated` | `/tmp/prompt-unrelated.txt` |

This can drop source entries, select a different prompt, or redirect output to the wrong directory. The writer also does not escape other dotenv-sensitive characters.

**Correction:** serialize literal values with an appropriate quoting/escaping scheme and explicitly control interpolation. Single quoting alone does not disable `python-dotenv` variable interpolation. Preserve any intentional interpolation support separately from literal values written by the app.

**Regression check:** round-trip actual filenames containing ` #`, quotes, backslashes, and `${...}`, using the same parser settings as profile loading.

### F09 — Saved profiles lose custom inline prompts

**P2 · Reproduced through prompt selection, profile saving, and prompt reloading.**

**Locations:** `OpenAIYouTubeTranscriber.py:2535–2536`, `2575–2580`, `3725–3730`.

A custom prompt is represented as `(text, '(inline)')`, but the saved `PROMPT` field contains only labels. The resulting profile says `PROMPT=(inline)` and contains none of the custom instructions. Reloading treats that label as a filename, fails to find it, and asks the user to select another prompt.

**Observed:** the custom text was absent from the saved profile, and `_load_prompts()` returned an empty list.

**Correction:** save inline instructions to a prompt file and record its path, or add an explicitly supported inline-text field with lossless serialization.

### F10 — Newly created config can select the wrong profile

**P2 · Reproduced with actual profile/config files.**

**Locations:** `OpenAIYouTubeTranscriber.py:2296–2300`, `2318–2324`.

When `config.txt` is absent, `create_profile()` writes `LOAD_PROFILE=profile.txt` before deciding the new profile's actual filename. If profiles already exist, the new file is numbered instead. With just `profile-transcriber.txt` present, saving creates `profile0.txt`, but config points to nonexistent `profile.txt`. If an old `profile.txt` exists, the next launch loads its settings instead of the new ones.

**Observed:** `config.txt` selected a nonexistent file while `profile0.txt` contained the saved session.

**Correction:** choose and successfully write the actual profile first, then use that exact name when creating config.

### F11 — Non-UTF-8 text files abort processing with an uncaught exception

**P2 · Reproduced with UTF-16 and Windows-1252 text files.**

**Locations:** `OpenAIYouTubeTranscriber.py:836–845`, `929–938`; batch exception handling at `4145–4154`.

Transcript selection accepts existing `.txt` files, including files created by external editors. Both text readers decode strictly as UTF-8 but catch only `OSError`. `UnicodeDecodeError` is not covered, so a UTF-16 transcript or Windows-1252 prompt raises out of the reader and can terminate the entire session. The batch exception handler does not catch it either.

**Observed:** both `read_transcript()` and `load_prompt_file()` raised `UnicodeDecodeError` for the fixtures rather than returning an unreadable-file result.

**Correction:** support explicitly recognized encodings/BOMs where intended, or catch decoding failures and report the encoding requirement while skipping or re-prompting for that file. Avoid silently replacing undecodable content.

**Regression check:** an unreadable first transcript must not prevent a valid later transcript from being processed.

### F12 — Failed enhancement can still change the transcript's words

**P2 · Reproduced without any model calls.**

**Locations:** `OpenAIYouTubeTranscriber.py:953–965`, `1011–1013`, `1074–1078`.

Oversized sentences are split with `textwrap.wrap()`, which can split long words. The reassembly code reconstructs separators from character width, usually inserting a space. It has lost the information that a cut occurred inside a word. This also affects scripts such as Thai, whose characters do not trigger the Chinese/Japanese no-space heuristic.

**Observed:** chunking `'x' * 10000` with budget 300 and having every backend call return an empty result inserted eight spaces into the fallback text. Repeating `ภาษาไทย` 1,000 times inserted 17 spaces. Although no chunk was enhanced, the reconstructed text differed on `split()` and could therefore be treated as a successful refinement by `is_refinement()`.

**Correction:** preserve exact source spans and the separator at every cut. For unchanged or failed chunks, reassemble the original text exactly. Do not infer missing separators from the final character alone.

**Regression check:** complete backend failure must round-trip long tokens and languages without inter-word spaces without changing the text.

### F13 — Mixed-script chunks exceed their configured size budget

**P2 · Reproduced using the application's own size estimator.**

**Locations:** `OpenAIYouTubeTranscriber.py:1011–1013`, `1020–1025`; local context calculation at `1257–1261`.

The fallback wrapping width is calculated from the average bytes per character of an entire sentence. A mixed sentence can contain an ASCII-heavy section and a much denser CJK section. Equal character widths therefore have unequal byte budgets. The later loop accepts an oversized piece without splitting it again.

**Observed:** `chunk_text('a ' * 1800 + '中' * 1500, max_tokens=300)` produced a chunk estimated at **566 tokens**, using `estimate_tokens()` itself. This is separate from the unavoidable uncertainty of approximating real tokenizer counts.

The local backend sizes chunks to fit the model's remaining context. Violating that budget can leave too little room for a complete answer or cause a generation failure, falling back to unenhanced text.

**Correction:** enforce the budget on every emitted piece, using actual tokenizer counts where available or incremental UTF-8 byte counts for the generic splitter. Re-split any piece that exceeds its limit.

### F14 — Built wheels omit the bundled prompts and profiles

**P2 · Reproduced by building and inspecting a wheel, then loading it outside the checkout.**

**Locations:** `setup.py:21–23`; `OpenAIYouTubeTranscriber.py:802–811`, `813–845`.

Packaging includes only the top-level Python module through `py_modules`; no data files are declared. The built wheel contains the application module and distribution metadata, but none of the four bundled prompts or sample profiles.

**Observed:** an extracted wheel used from a separate working directory returned `[]` from `list_available_prompts()`. Loading `prompt-refinement.txt` failed, and Enter at the prompt menu selected nothing. The checkout version lists four bundled prompts. Editable installation masks this issue because the source tree is still available.

**Correction:** package the resources and resolve them through an installed-resource API, while keeping mutable user files in their working directory. Do not bundle a user's credential-bearing config file.

**Regression check:** build a wheel, install it into an isolated environment, change outside the checkout, and verify that default prompts load and the console entry point works.

### F15 — VTT parsing includes metadata and encoded entities as speech

**P2 · Reproduced with a WebVTT fixture.**

**Locations:** `OpenAIYouTubeTranscriber.py:1623–1631`.

The fallback parser filters individual lines rather than reading cue blocks. It retains cue identifiers, drops only the first line of a multiline `NOTE`, and leaves character references such as `&amp;` encoded. These are defined parts of the [WebVTT format](https://www.w3.org/TR/webvtt1/).

A fixture with two numbered cues containing `Tom &amp; Jerry` and `Hello`, separated by a multiline note, produced:

```text
1 Tom &amp; Jerry private annotation 2 Hello
```

The intended transcript was `Tom & Jerry Hello`. The extra text is saved as speech and may also be submitted to enhancement. This finding affects the VTT fallback; it does not establish the same failure in JSON3 parsing.

**Correction:** parse cue payloads, skip whole comment/style/region blocks and cue identifiers, and decode permitted character references after handling markup.

### F16 — Home-relative media paths are rejected

**P3 · Reproduced through source resolution.**

**Locations:** `OpenAIYouTubeTranscriber.py:533–541`, `503–517`, `448`.

The source splitter expands `~` to decide whether an answer is an existing path, but the media resolver then validates the original unexpanded string. An existing `~/clip.mp3` is rejected. Transcript and profile paths already expand `~`, making input behavior inconsistent.

**Observed:** `source_entries('~/clip.mp3')` returned an empty list despite the expanded path existing.

**Correction:** normalize home-relative local paths once before validation and carry the expanded path through the pipeline.

## Verification and limits

- Parsed all four Python source/test/entry-point files successfully.
- Exercised the findings with isolated application-function probes, temporary files, metadata fixtures, and controlled failure injection. Media path probes simulated download and FFmpeg boundaries; they establish overwrite/cleanup decisions, not codec compatibility or real network behavior.
- Used the installed real `python-dotenv` parser for serialization checks and read the installed Whisper source for language/task semantics.
- Built and inspected a wheel offline, then checked prompt discovery outside the checkout.
- Of 76 existing test functions, **61 passed in the isolated harness**, 1 was partially exercised, 4 skipped their FFmpeg checks, and 10 were excluded because they require real yt-dlp operations or dependency imports in a child process. No application failures were observed in the exercised subset. The config-index test was separately verified to execute its assertions successfully, rather than taking its early-return path.
- The harness used real `dotenv` and `langdetect`, Whisper language tables extracted from the installed dependency, and explicit stubs that block unavailable Whisper/yt-dlp execution. Tests were isolated in separate processes. Two local-enhancement tests also needed a Torch version stub because the available Windows binaries cannot load under Linux; their tokenizers and model generation were already mocked by the tests. These results are **not a full integration-suite pass**.
- The unmodified full suite could not start under Linux Python 3.14.4 because `dotenv` was missing; that environment also lacks native `yt_dlp`, `whisper`, `langdetect`, `ffmpeg`, and `ffprobe`. A separate installed Windows environment supplied readable dependency sources and pure-Python packages. Windows FFmpeg's version was verified, but it was not used for full media integration testing.
- No live YouTube downloads, model-weight downloads, paid API calls, or actual speech-recognition/model-generation runs were performed. This report therefore does not certify external-service behavior or completeness beyond the reviewed and reproduced cases.

The existing tests cover many nearby scenarios, including ordinary raw-copy failure, duplicate prompt tags, source-name reuse, and uniform-language chunk sizes. The missing cases are primarily combinations of those features: failed full refinement after successful summary, source/output aliasing, collisions across deliverable types or source identities, and mixed-script boundaries. The regression checks above target those gaps.

"""Refining and saving transcripts, and replacing a refined source."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from .common import YesNo, _same_file
from .config import SessionConfig
from .naming import _claim_name, _path_identity, _take_path
from .settings import _resolve_track, _several, _stem_for

if TYPE_CHECKING:
    from .transcriber import YouTubeTranscriber


def _enhance_and_save(transcriber: YouTubeTranscriber, cfg: SessionConfig, text: str, stem: str,
                      enhance: bool = True, open_after: bool = True,
                      source: str | None = None) -> bool:
    """Save one transcript to Transcript/, once per prompt. True if anything saved.

    Every prompt runs over every transcript, so two prompts on three
    transcripts is six files. The untouched text is kept once, on the first
    prompt that actually changed something, rather than rewritten per prompt.

    `source` is the file this text was read from, in a refine-only run. It is
    retired once a refinement has actually landed - never before, and never
    when every prompt left the text alone, which would delete the only copy.
    """
    final_dir = cfg.transcript_path or transcriber.TRANSCRIPT_DIR
    raw_dir = (os.path.join(cfg.transcript_path, "Raw") if cfg.transcript_path
               else transcriber.RAW_TRANSCRIPT_DIR)
    # Both names are taken before anything is written, so neither lands on a
    # transcript this batch has still to read, or on another deliverable
    plain = os.path.basename(_take_path(
        cfg, os.path.join(final_dir, f"{stem}{transcriber.TXT_EXT}"), ("plain", stem)))
    raw_path = _take_path(cfg, os.path.join(raw_dir, f"{stem}{transcriber.TXT_EXT}"),
                          ("raw", stem))
    raw_name = os.path.basename(raw_path)
    # One transcript is worth putting in front of the user; a batch opened a
    # window for every one of them
    open_after = open_after and not _several(cfg)
    if cfg.ai_mode is None or not enhance or not cfg.prompts:
        # An unenhanced transcript is its own original, which save_final_transcript
        # sees is no refinement and so does not keep a second copy of
        return transcriber.save_final_transcript(
            text, plain, original_text=text, original_filename=raw_name,
            keep_original=cfg.keep_transcript, open_after=open_after,
            output_dir=cfg.transcript_path or None)

    saved = kept = False
    # What this text was saved as, and which of those is a whole refinement -
    # the one output that says everything the source said
    outputs: list[str] = []
    replaced_by: str | None = None
    for prompt_text, label, tag in transcriber.tagged_prompts(cfg.prompts):
        print(f"\nEnhancing {stem} with {label} ({cfg.ai_mode.name.lower()})...")
        # ponytail: known by its filename, so a summary prompt named otherwise is
        # held to the whole-chunk check and kept unsummarized, reported per chunk,
        # and a refinement named otherwise is not checked for dropped sentences.
        # The filename alone: a prompt kept outside Prompt/ is labelled by its path
        name = os.path.basename(label or "").lower()
        keeps = "some" if "summar" in name else "words" if "refine" in name else "all"
        final = transcriber.enhance_text(
            text, cfg.ai_mode, prompt_text, api_key=cfg.api_key,
            provider=cfg.provider, local_model=cfg.local_model, keeps=keeps)
        # An enhancement that returned the text unchanged refined nothing, so
        # it does not earn the prompt's tag
        if not transcriber.is_refinement(text, final):
            # Saved under the plain name per prompt, a prompt that failed put the
            # unrefined text in Transcript/ beside the refinement another made,
            # KEEP_TRANSCRIPT=n or not. Whether it is needed is settled below,
            # once. A transcript read from disk is already saved where it is.
            print(f"{label} changed nothing"
                  + (f", so {os.path.basename(source)} is left as it was." if source
                     else "."))
            continue
        path = _take_path(cfg, os.path.join(final_dir, f"{stem}{tag}{transcriber.TXT_EXT}"),
                          ("transcript", stem, tag))
        name = os.path.basename(path)
        in_place = bool(source and _same_file(path, source))
        if in_place and keeps != "words" and not cfg.keep_transcript:
            # A rename can bring an output back to the source's own name. A
            # refinement may take its place; a summary or translation written
            # there, with no copy kept, would be the end of the words themselves
            print(f"Not saving {label}'s result as {name}: that is the transcript "
                  f"it was made from, and it keeps no copy. Rename it, or keep "
                  f"the unrefined transcript.")
            continue
        if in_place and cfg.keep_transcript and not _holds_words(transcriber, raw_path, text):
            # Written over, the source keeps its words only in Raw/, so they go
            # there first and have to be seen there: a Raw/ save that failed
            # let a summary replace the only copy of the transcript
            transcriber.save_transcript(text, raw_name, raw_dir, open_after=False)
            if not _holds_words(transcriber, raw_path, text):
                print(f"Not saving {label}'s result as {name}: that is the transcript "
                      f"it was made from, and its copy in Raw/ could not be saved.")
                continue
            kept = True
        if transcriber.save_final_transcript(
                final, name, original_text=text, original_filename=raw_name,
                keep_original=cfg.keep_transcript and not kept,
                open_after=open_after, output_dir=cfg.transcript_path or None):
            saved = kept = True
            outputs.append(path)
            # Counted once it has landed, never on the strength of the reply:
            # a refinement that failed to save replaces nothing
            if keeps == "words":
                replaced_by = path
    if source:
        if outputs:
            _settle_source(transcriber, cfg, source, raw_path, outputs, replaced_by)
        return saved
    # The text itself, under its plain name, once and only if no prompt made
    # anything of it: the transcript is not lost to an enhancement that failed,
    # and is not saved beside the outputs of one that worked, where
    # KEEP_TRANSCRIPT already says whether a copy goes to Raw/
    if not outputs:
        saved = transcriber.save_final_transcript(
            text, plain, original_text=text, original_filename=raw_name,
            keep_original=False, open_after=open_after,
            output_dir=cfg.transcript_path or None)
    return saved


def _holds_words(transcriber: YouTubeTranscriber, path: str, text: str) -> bool:
    """Whether the file at `path` says what `text` says, word for word."""
    try:
        with open(path, 'rb') as handle:
            return transcriber.decode_text(handle.read()).split() == text.split()
    except (OSError, UnicodeDecodeError):
        return False


def _settle_source(transcriber: YouTubeTranscriber, cfg: SessionConfig, source: str, raw_path: str,
                   outputs: list[str], replaced_by: str | None) -> None:
    """Decide what becomes of a refined transcript's source, once its outputs landed.

    Kept nowhere else, the source goes only for a refinement, which says what
    it said: after a summary or a translation it was the only copy of the words.
    And never when an output was written to the source's own path - a rename
    back onto its own name - where retiring it deleted what was just saved.
    """
    if any(_same_file(source, path) for path in outputs):
        print(f"{os.path.basename(source)} now holds its own refinement, so it stays.")
    elif cfg.keep_transcript or replaced_by:
        _retire_source(transcriber, cfg, source, raw_path)
    else:
        print(f"Kept {os.path.basename(source)}: a summary or translation does not replace it.")


def _retire_source(transcriber: YouTubeTranscriber, cfg: SessionConfig, source: str,
                   raw: str) -> None:
    """Drop a refined transcript from Transcript/, its text now in `raw`.

    Only files sitting directly in Transcript/, which is where the refinement
    that replaces them was just written. A transcript named from anywhere else
    - Raw/ included - was read, not taken over, and is left where it is.
    """
    given, source = source, os.path.abspath(os.path.expanduser(source))
    if os.path.dirname(source) != os.path.abspath(transcriber.TRANSCRIPT_DIR):
        return
    # Kept means a copy in Raw/ that says what the source says. A Raw/ save that
    # failed - no room, no permission - still let the refinement report success,
    # and the source was deleted with no copy anywhere. Decoded as the source
    # was read, BOM or UTF-16 and all.
    mine = transcriber.read_text_file(source, "transcript")
    copied = mine is not None and _holds_words(transcriber, raw, mine)
    if cfg.keep_transcript and not copied:
        print(f"Kept {source}: its copy in Raw/ was not saved.")
        return
    try:
        os.remove(source)
    except OSError as e:
        print(f"Warning: could not remove {source}: {e}")
        return
    if cfg.keep_transcript and cfg.used_fields.get("URL"):
        # A profile made from this session replays the same transcripts, and
        # named this one where it no longer is
        cfg.used_fields["URL"] = ",".join(
            raw if part == given else part for part in cfg.used_fields["URL"].split(","))
    # Where the copy really is: TRANSCRIPT_PATH sends it to a Raw/ of its own
    print(f"Moved {os.path.basename(source)} to {os.path.dirname(os.path.abspath(raw))}"
          if cfg.keep_transcript else f"Removed the unrefined {os.path.basename(source)}")


def _refine_transcripts(transcriber: YouTubeTranscriber, cfg: SessionConfig) -> None:
    """Refine transcripts already on disk. Nothing is downloaded or transcribed.

    _enhance_and_save already writes the untouched text to Transcript/Raw/ when
    KEEP_TRANSCRIPT says so, so a source in Transcript/ is a duplicate of it by
    the time the refinement lands, and is retired there rather than here.
    """
    if cfg.ai_mode is None or not cfg.prompts:
        print("No refinement backend or prompt, so there is nothing to refine.")
        return
    for source in cfg.refine_sources or []:
        text = transcriber.read_transcript(source)
        if not text:
            continue
        print(f"\nProcessing: {os.path.abspath(source)}...")
        # Two transcripts of one name from two folders would refine to one file
        cfg.identity = _path_identity(source)
        base = _claim_name(cfg, os.path.splitext(os.path.basename(source))[0], cfg.identity)
        # TRANSCRIPT_RENAME is asked in a refine-only run too, and was ignored
        stem = _stem_for(cfg, base, "transcript")
        _enhance_and_save(transcriber, cfg, text, stem, source=source)


def _save_yt_transcripts(transcriber: YouTubeTranscriber, cfg: SessionConfig,
                         filename_base: str) -> None:
    """Save YouTube's own transcripts to Transcript/.

    Enhancement is charged per transcript, so asking for every language YouTube
    knows enhances only the one the video was spoken in; a list the user wrote
    out is enhanced in full, because they named each one.
    """
    info = cfg.info
    # A video's pass, which has its metadata from the start
    assert info is not None
    original = transcriber.original_caption(info)
    # The answer was settled on the first video of a list, and each video after
    # it has tracks of its own: 'all' is this one's, 'y' this one's original,
    # and a named track the same name here. Settled once, a Japanese video
    # after an English one got the English translation and never its original.
    tracks = transcriber.caption_tracks(info)
    if cfg.yt_transcript_all:
        keys = list(tracks)
    elif cfg.yt_transcript_raw.strip().lower() in YesNo.YES.value:
        keys = [original] if original else []
        if not original:
            print("Cannot tell which language this video was spoken in, so its "
                  "transcript is skipped.")
    else:
        keys = []
        for want in cfg.yt_transcript_languages or []:
            key = _resolve_track(transcriber, info, tracks, want)
            if not key:
                print(f"This video has no transcript in: {want}")
            elif key not in keys:
                # 'en' and 'en-US' can name one track, fetched and billed once
                keys.append(key)
    enhancing: list[str] = []
    if cfg.ai_mode is not None and keys:
        if not cfg.yt_transcript_all:
            enhancing = keys
        elif original:
            enhancing = [original]
            print(f"Enhancing only the original transcript ({original}); rerun "
                  f"for the rest.")
        else:
            # Without an original there is no one transcript standing for the
            # rest, and enhancing all 157 of them is not what `all` asked for
            print("Cannot tell which language this video was spoken in, so no "
                  "transcript is enhanced. Name a language to enhance one.")
    for key in keys:
        text = transcriber.fetch_caption_text(info, key)
        if not text:
            print(f"Nothing came back for the {key} transcript.")
            continue
        # The language the video was spoken in is the transcript; the rest say
        # in their name that they are something else
        stem = filename_base if key == original else f"{filename_base} [{key}]"
        _enhance_and_save(transcriber, cfg, text, stem, enhance=key in enhancing,
                          open_after=False)

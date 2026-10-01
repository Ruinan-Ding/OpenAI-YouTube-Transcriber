"""One pass per source: the downloads, the merge, the conversions, the rest."""

from __future__ import annotations

import functools
import os
import shutil
import tempfile
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, TypeVar

import yt_dlp

from .common import (DownloadFailed, Info, ModelSize, Resolution, _is_number,
                     error)
from .config import SessionConfig
from .naming import _claim_name, _reserve_sources, _source_identity, _take_path
from .questions import _prompt_audio_selection, _prompt_resolution_selection
from .settings import _create_youtube_with_recovery, _dir_for, _stem_for
from .transcripts import (_enhance_and_save, _refine_transcripts,
                          _save_yt_transcripts)

if TYPE_CHECKING:
    from .transcriber import YouTubeTranscriber

# A field's value as a pass reads it: text, or None for a field left unset.
# A video resolution is always settled on one; an audio quality left unset
# stays None, which is the best there is.
_Value = TypeVar('_Value', bound='str | None')


def _local_quality(source: str, quality: str | None, reader: Callable[[str], int | None],
                   unit: str) -> int | None:
    """What to hold a local file's stream to, or None to leave it as it is.

    A file has one stream, not a list of tiers, so it is its own highest and its
    own lowest: only a number is a constraint. One at or above what the file
    already is would re-encode it bigger for nothing, so it is dropped - and
    said out loud, the remote path having a menu to offer where this has
    nothing. A stream whose size the container does not record rules nothing
    out, so there the ask stands.
    """
    wanted = str(quality or "").rstrip(unit)
    if not _is_number(wanted):
        return None
    have = reader(source)
    if have and int(wanted) >= have:
        print(f"{os.path.basename(source)} is already {have}{unit}, "
              f"so {wanted}{unit} leaves it as it is.")
        return None
    return int(wanted)


def _container_of(transcriber: YouTubeTranscriber, target_format: str, kind: str) -> str:
    """The extension convert_media writes a format into.

    Which is what says whether two formats need telling apart in the filename:
    h264 and mpeg4 both land in .mp4, mp3 and flac do not.
    """
    if kind == 'video':
        return transcriber.CODEC_CONTAINERS.get(target_format,
                                                transcriber.FALLBACK_CONTAINER)
    return transcriber.format_extension(target_format) or target_format


def _shared_container(transcriber: YouTubeTranscriber, chosen: Sequence[str],
                      kind: str) -> bool:
    """Would two of these formats be written to one filename?

    `original` is whichever container the download already has, which is not
    known here - and a re-encode landing on it would overwrite the very file
    `original` asked to keep untouched. Asked for beside anything else, it
    counts as a collision rather than risking that.
    """
    if transcriber.FORMAT_ORIGINAL in chosen and len(chosen) > 1:
        return True
    boxes = [_container_of(transcriber, fmt, kind) for fmt in chosen]
    return len(set(boxes)) != len(boxes)


def _local_deliverables(transcriber: YouTubeTranscriber, cfg: SessionConfig,
                        filename_base: str) -> None:
    """Make the download deliverables from a local file, by re-encoding it.

    The same three files a video download produces - the merged video, a copy
    with the audio stripped, and the audio on its own - cut from what is already
    on disk, and one of each per combination the list fields ask for. The source
    is only ever read: a deliverable that would land on it is skipped rather
    than written over.
    """
    stem_for = functools.partial(_stem_for, cfg, filename_base)
    dir_for = functools.partial(_dir_for, cfg)
    source = cfg.url
    # A local file is its own path
    assert source is not None

    def each(raw: str | None, fallback: _Value) -> Sequence[str | _Value]:
        """The values a field asks for, or the fallback for none. One
        deliverable per combination."""
        return transcriber.split_entries(raw or "") or [fallback]

    def container_for(chosen: str | None, default: str) -> str:
        """FORMAT_ORIGINAL keeps the source's own container: there is no
        YouTube stream to keep instead."""
        if chosen == transcriber.FORMAT_ORIGINAL:
            return os.path.splitext(source)[1].lstrip('.') or default
        return chosen or default

    def make(output_dir: str, stem: str, target_format: str, kind: str,
             height: int | None = None, bitrate: int | None = None) -> str | None:
        extension = _container_of(transcriber, target_format, kind)
        # AUDIO_PATH and VIDEO_PATH one folder and one container for both: the
        # audio, made after the video, takes the suffix
        target = _take_path(cfg, os.path.join(output_dir, f"{stem}.{extension}"),
                            ("local", kind, stem, target_format),
                            " - Audio" if kind == 'audio' else None)
        stem = os.path.basename(target)[:-len(extension) - 1]
        made = transcriber.convert_media(source, target_format, kind, output_dir, stem,
                                         height=height, bitrate=bitrate,
                                         replace_source=False)
        if made:
            print(f"Saved {os.path.abspath(made)}")
        return made

    def height_for(quality: str | None) -> int | None:
        return _local_quality(source, quality, transcriber.source_height, 'p')

    def bitrate_for(quality: str | None) -> int | None:
        return _local_quality(source, quality, transcriber.source_bitrate, 'k')

    def tag(height: int | None = None, bitrate: int | None = None,
            codec: str | None = None) -> str:
        return transcriber.quality_tag(f"{height}p" if height else None,
                                       f"{bitrate}k" if bitrate else None, codec)

    if cfg.video_only and transcriber.stream_codec(source, 'video') is None:
        print("Skipping the video-only file: this one has no video stream.")
    elif cfg.video_only:
        codecs = each(cfg.video_only_format, transcriber.DEFAULT_VIDEO_ONLY_CODEC)
        share = _shared_container(transcriber, codecs, 'video')
        done: set[object] = set()
        for res in each(cfg.video_only_resolution, None):
            height = height_for(res)
            if height in done:
                continue
            done.add(height)
            for chosen in codecs:
                codec = chosen
                if not codec or codec == transcriber.FORMAT_ORIGINAL:
                    # Keeping the source's codec only works where this ffmpeg
                    # can write it back; a decode-only codec falls to the default
                    have = transcriber.stream_codec(source, 'video')
                    codec = (have if have in transcriber.ffmpeg_formats('video')
                             else transcriber.DEFAULT_VIDEO_ONLY_CODEC)
                print(f"Re-encoding {os.path.basename(source)} without its audio...")
                make(dir_for("video_only", transcriber.VIDEO_WITHOUT_AUDIO_DIR),
                     stem_for("video_only")
                     + tag(height, codec=codec if share else None)
                     + " - Video Only", codec, 'video', height=height)

    # Two formats writing one extension (mkv and matroska, or original beside
    # the container the file is already in) wrote one file twice, the second
    # over the first: the format joins the name, as it does for a download and
    # the video-only file. And two qualities that come to the same file - highest
    # and lowest are both the file as it is - are one encode, not two
    if cfg.download_video and transcriber.stream_codec(source, 'video') is None:
        print("Skipping the video: this one has no video stream.")
    elif cfg.download_video:
        containers = each(cfg.video_format, transcriber.DEFAULT_VIDEO_FORMAT)
        share = _shared_container(transcriber, containers, 'container')
        done = set()
        for res in each(cfg.video_resolution, None):
            height = height_for(res)
            for rate in each(cfg.video_audio_resolution, None):
                bitrate = bitrate_for(rate)
                if (height, bitrate) in done:
                    continue
                done.add((height, bitrate))
                for chosen in containers:
                    print(f"Re-encoding {os.path.basename(source)}...")
                    make(dir_for("video", transcriber.VIDEO_DIR),
                         stem_for("video") + tag(height, bitrate, chosen if share else None),
                         container_for(chosen, transcriber.DEFAULT_VIDEO_FORMAT),
                         'both', height=height, bitrate=bitrate)

    if cfg.download_audio and transcriber.stream_codec(source, 'audio') is None:
        print("Skipping the audio file: this one has no audio stream.")
    elif cfg.download_audio:
        containers = each(cfg.audio_format, transcriber.DEFAULT_AUDIO_FORMAT)
        share = _shared_container(transcriber, containers, 'container')
        done = set()
        for rate in each(cfg.audio_resolution, None):
            bitrate = bitrate_for(rate)
            if bitrate in done:
                continue
            done.add(bitrate)
            for chosen in containers:
                print(f"Extracting the audio from {os.path.basename(source)}...")
                make(dir_for("audio", transcriber.AUDIO_DIR),
                     stem_for("audio") + tag(bitrate=bitrate, codec=chosen if share else None),
                     container_for(chosen, transcriber.DEFAULT_AUDIO_FORMAT),
                     'audio', bitrate=bitrate)


def _run_pipeline(transcriber: YouTubeTranscriber, cfg: SessionConfig) -> None:
    """Run one pass per source entry, in the order they were given."""
    cfg.sources = cfg.sources or [(cfg.url, cfg.is_local_file, cfg.refine_sources)]
    # Metadata already fetched to build the menus, and worth not fetching
    # twice. The title came with it, so it is carried and restored with it: an
    # entry reusing the metadata must not inherit the name of the pass before
    prefetched = ((cfg.url, cfg.info, cfg.video_title) if cfg.info is not None
                  else (None, None, ""))

    refining = sum(len(entry[2]) for entry in cfg.sources if entry[2])
    passes = refining * len(cfg.prompts or [])
    if passes > 1:
        print(f"\n{passes} passes ({refining} transcript(s) x "
              f"{len(cfg.prompts or [])} prompt(s)).")

    cfg.claimed_names = {}
    _reserve_sources(cfg)
    for index, entry in enumerate(cfg.sources):
        if len(cfg.sources) > 1:
            print(f"\n--- Source {index + 1} of {len(cfg.sources)} ---")
        cfg.url, cfg.is_local_file, cfg.refine_sources = entry
        reuse = bool(cfg.url) and cfg.url == prefetched[0]
        cfg.info = prefetched[1] if reuse else None
        cfg.video_title = prefetched[2] if reuse else ""
        try:
            _run_one(transcriber, cfg)
        except (DownloadFailed, yt_dlp.utils.DownloadError, EOFError) as e:
            # One source failing is not the batch failing: the reason has been
            # reported already, and the sources after this one are still owed.
            # Alone, it is the whole run, and main() gives it the exit code.
            # EOFError is an unattended run re-asked about this one video - a
            # resolution it does not have - which the ones after need not be.
            if len(cfg.sources) == 1:
                raise
            error(f"Source {index + 1} of {len(cfg.sources)} failed ({e}); "
                  f"carrying on with the rest.")
        finally:
            # A pass that failed part way still owns what it had fetched
            _clear_video_scratch(transcriber, cfg)


def _clear_video_scratch(transcriber: YouTubeTranscriber, cfg: SessionConfig) -> None:
    """Remove the folder this pass fetched merge-only video streams into.

    It is the pass's own, made fresh for it, so everything in it is this pass's
    to delete. Emptying the shared Video/Temp instead deleted whatever else was
    there: another run's streams, a file left in it, and a finished merge when
    VIDEO_PATH pointed at it.
    """
    scratch, cfg.video_scratch = cfg.video_scratch, None
    if not scratch:
        return
    try:
        shutil.rmtree(scratch)
    except OSError as e:
        # Windows can still hold a stream open just after the merge
        print(f"Warning: Could not clean up temporary files: {str(e)}")
    try:
        # The shared parent only once nothing else is in it
        os.rmdir(os.path.dirname(scratch))
    except OSError:
        pass


class _Pass:
    """One source's pass: the deliverables it asks for, what it has fetched
    towards them, and the steps that turn the one into the other.

    Every stream is fetched once however many deliverables want it, and kept
    as downloaded until the last of them has been written, so the steps share
    what they fetch: that is what this holds between them.
    """

    def __init__(self, transcriber: YouTubeTranscriber, cfg: SessionConfig) -> None:
        """Identify the source, claim its name, and settle its qualities."""
        self.transcriber, self.cfg = transcriber, cfg
        if not cfg.is_local_file and cfg.info is None:
            _create_youtube_with_recovery(transcriber, cfg)

        if cfg.is_local_file:
            cfg.video_title = os.path.splitext(os.path.basename(self.url))[0]

        cfg.identity = _source_identity(cfg)
        self.filename_base = _claim_name(
            cfg, transcriber.sanitize_filename(cfg.video_title), cfg.identity,
            None if cfg.is_local_file else (cfg.info or {}).get('id'))
        display_source = os.path.abspath(self.url) if cfg.is_local_file else self.url
        print(f"\nProcessing: {display_source}...")
        self.stem_for = functools.partial(_stem_for, cfg, self.filename_base)
        self.dir_for = functools.partial(_dir_for, cfg)

        # Audio fetched only to merge or to transcribe, rather than to keep
        self.temp_audio_paths: list[str] = []
        self.transcription_failed = False
        # One download per distinct stream, shared by every deliverable that
        # wants it, and kept as downloaded until the last of them has been written
        self.video_only_files: dict[str, str] = {}
        self.video_files: dict[str, str] = {}
        self.audio_files: dict[str, str] = {}
        self.merge_files: dict[str | None, str] = {}
        self.saved_audio_files: list[tuple[str | None, str]] = []
        self.audio_path: str | None = None
        self.speech_file: str | None = None

        # Three independent downloads, each with its own quality: the merged file,
        # a muxer-free copy of the raw video stream, and a standalone audio file
        remote = not cfg.is_local_file
        self.video_res = (self.qualities(cfg.video_resolution, self.settle_video)
                          if cfg.download_video and remote else [])
        self.only_res = (self.qualities(cfg.video_only_resolution, self.settle_video)
                         if cfg.video_only and remote else [])
        self.merge_audio = (self.qualities(cfg.video_audio_resolution, self.settle_audio)
                            if cfg.download_video and remote else [])
        self.saved_audio = (self.qualities(cfg.audio_resolution, self.settle_audio)
                            if cfg.download_audio and remote else [])
        # One copy of the audio is transcribed however many deliverables there are,
        # so a list in this field names that copy rather than several of them
        speech_raw = next(iter(transcriber.split_entries(cfg.transcribe_audio_quality or "")),
                          cfg.transcribe_audio_quality)
        self.speech_audio = (self.qualities(
            speech_raw, lambda q: self.settle_audio(q, Resolution.LOWEST.value))[0]
            if cfg.transcribe_audio and remote else None)

    @property
    def url(self) -> str:
        """The URL or path this pass is about: every pass over media has one."""
        assert self.cfg.url is not None
        return self.cfg.url

    @property
    def info(self) -> Info:
        """The video's metadata, fetched before the steps that read it: only a
        video's pass calls on it, and a local file has none."""
        assert self.cfg.info is not None
        return self.cfg.info

    def settle_video(self, quality: str | None) -> str:
        """Check a resolution against this video, and resolve "lowest"."""
        transcriber, info = self.transcriber, self.info
        available = transcriber.available_resolutions(info)
        if not available:
            # Nothing to pick from, and the keywords would sail past the check
            # below into a selector that cannot match. The picker says so.
            return _prompt_resolution_selection(transcriber, info)
        if quality not in (Resolution.HIGHEST.value, Resolution.LOWEST.value) \
                and quality not in available:
            print("Requested resolution not found, left null, or invalid.")
            quality = _prompt_resolution_selection(transcriber, info)
        # Name the file after what is downloaded, not the word asked for, which
        # also puts "lowest" on the same footing as the bottom of the menu
        if quality == Resolution.LOWEST.value and available:
            quality = available[-1]
        # ...and the top of the menu on the same footing as "highest", which
        # carries no tag because it is the default
        if available and quality == available[0]:
            quality = Resolution.HIGHEST.value
        return quality

    def settle_audio(self, quality: str | None,
                     default: str = Resolution.HIGHEST.value) -> str | None:
        """Check an audio quality against this video.

        bestaudio[abr<=N] degrades silently rather than failing, so this is the
        only thing that reports a request the video cannot satisfy. `default`
        is the field's own, so a re-prompt for transcription still offers the
        cheapest stream rather than the largest.
        """
        transcriber, info = self.transcriber, self.info
        if (quality and quality not in (Resolution.HIGHEST.value, Resolution.LOWEST.value)
                and not _is_number(str(quality))
                and quality not in transcriber.available_audio_qualities(info)):
            print("Requested audio resolution not found, left null, or invalid.")
            quality = _prompt_audio_selection(transcriber, info, default)
        return quality

    def qualities(self, raw: str | None,
                  settle: Callable[[str | None], _Value]) -> list[_Value]:
        """The resolved, deduplicated qualities a field asks for.

        Several, separated by commas or spaces, are several deliverables. Two
        wordings can still land on one quality - "medium" and "highest" on a
        video whose best tier is medium - and that is one of them, not two.
        """
        split = self.transcriber.split_entries
        seen: list[_Value] = []
        pieces: Sequence[str | None] = split(raw or "") or [raw]
        for piece in pieces:
            value = settle(piece)
            # A re-prompt can be answered with a list of its own, which is as
            # many deliverables as if the field had named them. Each is settled
            # in its own right, so the top tier still goes untagged either way.
            parts = split(value or "")
            for one in (map(settle, parts) if len(parts) > 1 else [value]):
                if one not in seen:
                    seen.append(one)
        return seen

    def formats(self, raw: str | None, default: str) -> list[str]:
        """The formats a field asks for; the deliverable is written in each."""
        return list(dict.fromkeys(self.transcriber.split_entries(raw or "")
                                  or [raw or default]))

    def audio_label_for(self, quality: str | None) -> str:
        # selected_bitrate caches per video, so the repeated lookups behind a
        # label cost a dict read
        return self.transcriber.audio_bitrate_label(quality, self.info)

    def audio_stream_for(self, quality: str | None) -> str:
        """Which stream a request lands on, so that two wordings for one stream
        are fetched once. "medium" and "highest" name the same audio on a video
        whose best tier is medium, and their selectors do not look alike.
        Falls back to the selector if yt-dlp's resolver cannot be run.
        """
        selector = self.transcriber.audio_format(quality, self.info)
        chosen = self.transcriber.selected_format(selector, self.info) or {}
        return chosen.get('format_id') or selector

    def audio_marks(self, quality: str | None) -> tuple[str, ...]:
        """What an audio stream's name says of it: its bitrate, and its format
        id too where another stream this pass fetches rounds to that bitrate.
        Named by the bitrate alone, the second download landed on the first
        and both deliverables were then made from one of them.
        """
        label, stream = self.audio_label_for(quality), self.audio_stream_for(quality)
        others = self.saved_audio + self.merge_audio + [self.speech_audio]
        shared = any(self.audio_label_for(other) == label
                     and self.audio_stream_for(other) != stream
                     for other in others if other)
        return (label, stream) if shared else (label,)

    def audio_stem_for(self, quality: str | None) -> str:
        return self.stem_for("audio") + self.transcriber.quality_tag(*self.audio_marks(quality))

    def fetch_video(self) -> None:
        """Download the video-only streams, then those the merge needs."""
        transcriber, cfg = self.transcriber, self.cfg
        for res in self.only_res:
            print(f"Downloading video stream ({res} without audio)...")
            downloaded = transcriber.download_format(
                self.url, transcriber.video_format(res),
                self.dir_for("video_only", transcriber.VIDEO_WITHOUT_AUDIO_DIR),
                self.stem_for("video_only") + transcriber.quality_tag(res) + " - Video Only")
            self.video_only_files[res] = transcriber.strip_audio(downloaded)
            print(f"Video downloaded to {os.path.abspath(self.video_only_files[res])}")

        for res in self.video_res:
            if res in self.video_only_files:
                # The merge wants the very stream just saved, so use that copy
                # rather than fetching it a second time
                self.video_files[res] = self.video_only_files[res]
                continue
            if cfg.video_scratch is None:
                # A folder of this pass's own inside Video/Temp, so that clearing
                # it afterwards touches nothing this pass did not put there
                scratch_root = os.path.join(transcriber.VIDEO_DIR, transcriber.TEMP_DIR)
                os.makedirs(scratch_root, exist_ok=True)
                cfg.video_scratch = tempfile.mkdtemp(prefix="merge-", dir=scratch_root)
            self.video_files[res] = transcriber.download_format(
                self.url, transcriber.video_format(res), cfg.video_scratch,
                self.stem_for("video") + transcriber.quality_tag(res))
            print(f"Video downloaded to {self.video_files[res]}")
        if not cfg.download_video and not cfg.video_only:
            print("Skipping video download...")

    def fetch_audio(self) -> None:
        """Download the audio to keep, then the audio the merge needs."""
        transcriber = self.transcriber
        # Compare the streams, not the words: "low", "lowest" and "60" are one
        # request when they land on one stream, and so are "medium" and "highest"
        # on a video whose best tier is medium
        for tier in self.saved_audio:
            stream = self.audio_stream_for(tier)
            if stream in self.audio_files:
                continue
            self.audio_files[stream], _ = transcriber.download_audio_stream(
                self.info, self.audio_stem_for(tier), is_temp=False,
                format_selector=transcriber.audio_format(tier, self.info),
                keep_in=self.dir_for("audio", transcriber.AUDIO_DIR))
            self.saved_audio_files.append((tier, self.audio_files[stream]))

        for tier in self.merge_audio:
            stream = self.audio_stream_for(tier)
            if stream not in self.audio_files:
                self.audio_files[stream], _ = transcriber.download_audio_stream(
                    self.info, self.audio_stem_for(tier), is_temp=True,
                    format_selector=transcriber.audio_format(tier, self.info))
                self.temp_audio_paths.append(self.audio_files[stream])
            self.merge_files[tier] = self.audio_files[stream]

        self.audio_path = next(iter(self.audio_files.values()), None)

    def merge(self) -> None:
        """Mux every video stream with every audio tier, in every container."""
        transcriber, cfg = self.transcriber, self.cfg
        # Two containers that write one extension would write one filename, so the
        # format joins the name - the same rule _convert_all applies to the others
        merge_formats = self.formats(cfg.video_format, transcriber.DEFAULT_VIDEO_FORMAT)
        merge_shares = _shared_container(transcriber, merge_formats, "container")
        for res in self.video_res:
            for tier in self.merge_audio:
                for chosen in merge_formats:
                    container = (os.path.splitext(self.video_files[res])[1].lstrip('.')
                                 if chosen == transcriber.FORMAT_ORIGINAL
                                 else transcriber.format_extension(chosen) or chosen)
                    for fmt in (chosen if merge_shares else None, chosen):
                        output = os.path.join(
                            self.dir_for("video", transcriber.VIDEO_DIR),
                            self.stem_for("video") + transcriber.quality_tag(
                                res, *self.audio_marks(tier), fmt) + f".{container}")
                        # The audio saved to the same folder in the same container
                        # can have this very name: ffmpeg refused to write over its
                        # own input, and the failed merge's cleanup deleted that
                        # input. The format tag tells the merge apart.
                        if not (os.path.exists(output) and any(
                                os.path.samefile(output, audio)
                                for audio in self.audio_files.values()
                                if os.path.exists(audio))):
                            break
                    # Taken before the audio converted after it can take it
                    output = _take_path(cfg, output, ("merge", res, tier, chosen))
                    # Every merge reads the streams as downloaded, so the scratch
                    # copies are cleared once afterwards rather than by the first
                    if transcriber.combine_audio_video(self.video_files[res],
                                                       self.merge_files[tier],
                                                       output) is None:
                        error(f"Error: the merged video was not created at {output}")

    def speech_audio_file(self) -> str:
        """The audio to recognise, fetched once however many languages want it."""
        transcriber, cfg = self.transcriber, self.cfg
        if self.speech_file is not None:
            return self.speech_file
        if not cfg.is_local_file:
            if self.audio_path is None:
                # Any audio already on disk is reused: fetching a second copy
                # to save bandwidth would defeat the point
                self.audio_path, _ = transcriber.download_audio_stream(
                    self.info, self.audio_stem_for(self.speech_audio), is_temp=True,
                    format_selector=transcriber.audio_format(self.speech_audio, self.info))
                self.temp_audio_paths.append(self.audio_path)
            self.speech_file = self.audio_path
        elif transcriber.is_valid_media_file(self.url):
            # Whisper reads a video container as readily as an audio one,
            # both being an ffmpeg call to it
            self.speech_file = self.url
        else:
            # is_local_file is only ever set after this same check passed,
            # so getting here means the file went away mid-run
            error(f"Error: {self.url} is no longer a readable media file.")
            raise DownloadFailed(f"{self.url} is no longer readable")
        return self.speech_file

    def transcribe(self) -> None:
        """Transcribe into each language asked for, and refine and save each."""
        transcriber, cfg = self.transcriber, self.cfg
        if not cfg.transcribe_audio:
            print("Skipping transcription.")
            return
        wanted = cfg.target_languages or [cfg.target_language]
        written: set[str | None] = set()
        for target in wanted:
            # English-specific variants (e.g. base.en) exist for the standard
            # sizes only, and only earn their keep on an English pass
            model_name = cfg.model_name
            if (cfg.use_en_model
                    and target in (transcriber.DEFAULT_LANGUAGE, transcriber.AUTO_LANGUAGE)
                    and cfg.source_language in (None, transcriber.DEFAULT_LANGUAGE)
                    and model_name in tuple(size.value for size
                                            in ModelSize.standard_models())):
                model_name += ".en"

            transcribed_text, language = transcriber.transcribe_audio_file(
                self.speech_audio_file(), model_name, target, cfg.source_language
            )

            if not transcribed_text:
                # Don't pay to "enhance" a failure, and don't save one as a transcript
                self.transcription_failed = True
                print(f"No {target} transcript produced; nothing saved.")
                continue
            # Named for the language the text is in, not the one asked for: a
            # target Whisper cannot write comes back in the language spoken,
            # which another target may already have saved
            if language in written:
                print(f"The {target} transcript is the {language} one already saved.")
                continue
            written.add(language)

            # Both kinds of transcript share the folder now, so Whisper's
            # reading is named for what it is even in the default language
            if not _enhance_and_save(transcriber, cfg, transcribed_text,
                                     f"{self.stem_for('transcript')} [Whisper {language}]"):
                # Nothing was saved, so the audio is still needed for a retry
                self.transcription_failed = True

    def convert(self) -> None:
        """Write the video-only and audio files in every format asked for."""
        transcriber, cfg = self.transcriber, self.cfg
        self._convert_all(
            list(self.video_only_files.items()), cfg.video_only_format,
            transcriber.DEFAULT_VIDEO_ONLY_CODEC, "video",
            self.dir_for("video_only", transcriber.VIDEO_WITHOUT_AUDIO_DIR),
            lambda res, fmt: (self.stem_for("video_only")
                              + transcriber.quality_tag(res, fmt) + " - Video Only"))
        self._convert_all(
            self.saved_audio_files, cfg.audio_format, transcriber.DEFAULT_AUDIO_FORMAT,
            "audio", self.dir_for("audio", transcriber.AUDIO_DIR),
            lambda tier, fmt: self.stem_for("audio") + transcriber.quality_tag(
                *self.audio_marks(tier), fmt))

    def _convert_all(self, made: Sequence[tuple[str | None, str]], raw: str | None,
                     default: str, kind: str, folder: str,
                     name_for: Callable[[str | None, str | None], str]) -> None:
        """Write every deliverable in every format asked for.

        The download is kept until the last format has been written, and the
        format joins the filename only where it must - two codecs can share one
        container, and would otherwise share one name.
        """
        transcriber, cfg = self.transcriber, self.cfg
        chosen = self.formats(raw, default) if made else []
        share = _shared_container(transcriber, chosen, kind)
        for quality, source in made:
            written: list[str] = []
            for fmt in chosen:
                if fmt == transcriber.FORMAT_ORIGINAL:
                    written.append(source)
                    continue
                stem = name_for(quality, fmt if share else None)
                extension = _container_of(transcriber, fmt, kind)
                # AUDIO_PATH and VIDEO_PATH one folder, one container for both:
                # the audio was written over the merged video
                target = _take_path(cfg, os.path.join(folder, f"{stem}.{extension}"),
                                    ("convert", kind, quality, fmt),
                                    " - Audio" if kind == "audio" else None)
                stem = os.path.basename(target)[:-len(extension) - 1]
                print(f"Re-encoding {os.path.basename(source)} to {fmt}...")
                converted = transcriber.convert_media(source, fmt, kind, folder, stem)
                if converted:
                    print(f"Saved {os.path.abspath(converted)}")
                    written.append(converted)
            # Nothing converted, so the file as downloaded is all there is:
            # keeping it beats ending the run with neither
            if written and source not in written and os.path.exists(source):
                try:
                    os.remove(source)
                except OSError as e:
                    print(f"Note: could not remove the pre-conversion file: {str(e)}")

    def clear_temp_audio(self) -> None:
        """Delete the audio fetched only to merge or to transcribe.

        Kept when transcription failed, so that the retryable step does not
        cost a second download.
        """
        for path in dict.fromkeys(self.temp_audio_paths):
            if not os.path.exists(path):
                continue
            if self.transcription_failed:
                print(f"Keeping downloaded audio for retry: {os.path.abspath(path)}")
                continue
            try:
                os.remove(path)
            except OSError as e:
                # Windows can still hold the file open just after transcription
                print(f"Note: could not delete the temp audio: {str(e)}")
            else:
                print(f"Deleted audio residual in {path}")

        temp_audio_path = os.path.join(self.transcriber.AUDIO_DIR, self.transcriber.TEMP_DIR)
        try:
            if os.path.exists(temp_audio_path) and not os.listdir(temp_audio_path):
                os.rmdir(temp_audio_path)
        except OSError:
            # The directory is recreated on demand, so leaving the empty one behind
            # is not worth reporting
            pass


def _run_one(transcriber: YouTubeTranscriber, cfg: SessionConfig) -> None:
    """Execute one pass: download streams, transcribe, enhance, and save."""
    if cfg.refine_sources:
        _refine_transcripts(transcriber, cfg)
        return

    run = _Pass(transcriber, cfg)
    if cfg.is_local_file:
        _local_deliverables(transcriber, cfg, run.filename_base)
    run.fetch_video()
    run.fetch_audio()
    run.merge()
    _clear_video_scratch(transcriber, cfg)

    # A list can mix a video with a local file, and DOWNLOAD_YT_TRANSCRIPT was
    # answered for the video: this pass has no metadata to read captions out of
    if cfg.yt_transcript_languages and not cfg.is_local_file:
        _save_yt_transcripts(transcriber, cfg, run.stem_for("transcript"))

    run.transcribe()
    # Re-encode the standalone files last, so the merge and the transcription
    # both worked from the stream as downloaded rather than a second-generation
    # copy of it
    run.convert()
    run.clear_temp_audio()
    print("Tasks complete.")

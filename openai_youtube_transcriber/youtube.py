"""What a YouTube video offers, and fetching it: streams and captions."""

from __future__ import annotations

import html
import json
import os
import re
import tempfile
from typing import Any

import yt_dlp

from .base import TranscriberBase
from .common import DownloadFailed, Info, Resolution, _is_number, error


class YouTubeMixin(TranscriberBase):
    """What a YouTube video offers, and fetching it."""

    # quiet only silences progress, not errors; warnings are kept because a
    # broken extractor announces itself there and nowhere else
    YDL_OPTS: dict[str, Any] = {'quiet': True, 'noplaylist': True}

    # yt-dlp's format selector, which does not change while the process runs.
    # Shared by every session: it holds sockets, and release_caches closes it.
    _selector_engine: Any = None

    def fetch_video_info(self, url: str) -> Info:
        """Fetch video metadata with yt-dlp.

        yt-dlp does its own extractor and network retries, so a failure that
        reaches the caller is settled: report it and re-prompt.
        """
        # YoutubeDL mutates the params dict it is given, so hand it a copy
        with yt_dlp.YoutubeDL(dict(self.YDL_OPTS)) as ydl:
            info = ydl.extract_info(url, download=False)
        # Kept for the downloads, under both names they are asked for by
        known = self.__dict__.setdefault('_video_info', {})
        for name in (url, (info or {}).get('webpage_url')):
            if name:
                known[name] = info
        return info

    @staticmethod
    def caption_language(info: Info, language: str | None) -> str | None:
        """The caption track that really is `language`, or None.

        The author's own captions come first. YouTube also machine-translates
        its transcript into every language it knows; those carry a `tlang` and
        say nothing Whisper would not say better, so they are passed over.

        The whole tag wins over its first subtag, so asking for zh-Hans is not
        answered with the zh-Hant transcript that happens to be listed first.
        """
        wanted = (language or '').lower()
        loose = None
        for source in ('subtitles', 'automatic_captions'):
            for key, tracks in (info.get(source) or {}).items():
                if key.split('-')[0].lower() == wanted.split('-')[0] and any(
                        'tlang=' not in (track.get('url') or '') for track in tracks):
                    if key.lower() == wanted:
                        return key
                    loose = loose or key
        return loose

    @staticmethod
    def caption_tracks(info: Info) -> dict[str, str]:
        """Every caption track on offer, key -> the name YouTube gives it.

        The uploader's own tracks win a key from the machine ones, being the
        better text where both exist.
        """
        tracks: dict[str, str] = {}
        for source in ('subtitles', 'automatic_captions'):
            for key, entries in (info.get(source) or {}).items():
                if key not in tracks and entries:
                    tracks[key] = entries[0].get('name') or key
        return tracks

    @classmethod
    def original_caption(cls, info: Info) -> str | None:
        """The track in the language the video was actually spoken in, or None.

        YouTube marks that one `<lang>-orig` and names it "(Original)"; the
        extractor also reports the video's own language. Everything else on
        offer may be a translation of it, machine-made or human.
        """
        keys = list(info.get('subtitles') or {}) + list(info.get('automatic_captions') or {})
        marked = next((key for key in keys if key.endswith('-orig')), None)
        # The whole tag, not just its first subtag: zh-Hans and zh-Hant are
        # different transcripts, and only one of them is the original
        spoken = marked[:-len('-orig')] if marked else (info.get('language') or '')
        if spoken:
            return cls.caption_language(info, spoken) or marked
        # Nothing declares the language: the uploader's own track is the
        # closest thing to a source of truth left
        return next(iter(info.get('subtitles') or {}), None) or next(
            (key for key, tracks in (info.get('automatic_captions') or {}).items()
             if tracks and 'tlang=' not in (tracks[0].get('url') or '')), None)

    def fetch_caption_text(self, info: Info, key: str) -> str | None:
        """One named caption track as plain text, or None if it cannot be had.

        yt-dlp does the fetching: a track arrives as a plain file or as an HLS
        playlist, and it knows the difference. It works from the metadata
        already fetched, as --load-info-json does; given the URL, it extracted
        the whole video again per track, some 150 times over for 'all'.
        """
        print(f"Fetching YouTube's own transcript ({key})...")
        with tempfile.TemporaryDirectory() as folder:
            # A caption fetch is one small HTTP read; a blip on it should not
            # cost the transcript, so yt-dlp is told to try again
            # No 'best' fallback: captions_to_text reads json3 and VTT, and
            # YouTube offers both for every track. srv3 and ttml would arrive
            # as XML and be parsed as cue text, putting tag soup in the
            # transcript and billing the enhancement API for it.
            options = dict(self.YDL_OPTS, skip_download=True, noprogress=True,
                           retries=3, writesubtitles=True, writeautomaticsub=True,
                           subtitleslangs=[key], subtitlesformat='json3/vtt',
                           outtmpl={'default': os.path.join(folder, 'captions.%(ext)s')})
            try:
                with yt_dlp.YoutubeDL(options) as ydl:
                    ydl.process_ie_result(ydl.sanitize_info(info), download=True)
                written = sorted(name for name in os.listdir(folder)
                                 if os.path.splitext(name)[1] in ('.json3', '.vtt'))
                if not written:
                    return None
                path = os.path.join(folder, written[0])
                with open(path, encoding='utf-8', errors='replace') as handle:
                    text = self.captions_to_text(handle.read(), os.path.splitext(path)[1])
            except (yt_dlp.utils.YoutubeDLError, OSError, ValueError) as e:
                print(f"Could not fetch YouTube's transcript: {str(e)}")
                return None
        return text or None

    @classmethod
    def captions_to_text(cls, payload: str, ext: str) -> str:
        """A caption file's text, as prose.

        YouTube's rolling captions restate the line before them so a viewer can
        finish reading it, so a line that arrives twice running is one line.
        """
        if ext == '.json3':
            cues = [''.join(seg.get('utf8', '') for seg in (event.get('segs') or []))
                    for event in json.loads(payload).get('events') or []]
        else:
            cues = cls.vtt_cue_lines(payload)
        lines: list[str] = []
        for cue in cues:
            cue = ' '.join(cue.split())
            if cue and (not lines or cue != lines[-1]):
                lines.append(cue)
        return ' '.join(lines)

    @staticmethod
    def vtt_cue_lines(payload: str) -> list[str]:
        """The spoken lines of a WebVTT file, block by block.

        A WebVTT file is blocks between blank lines, and only a cue's payload -
        the lines after its timing line - is speech. Read line by line, a cue's
        numeric identifier and all but the first line of a NOTE were kept as
        speech, and '&amp;' stayed encoded. A header, NOTE, STYLE or REGION
        block has no timing line and so contributes nothing.
        """
        lines: list[str] = []
        for block in re.split(r'\n[ \t]*\n', payload.replace('\r\n', '\n').replace('\r', '\n')):
            rows = block.strip('\n').split('\n')
            timing = next((i for i, row in enumerate(rows) if '-->' in row), None)
            # Everything before the timing line - a header run into the first
            # cue, a cue identifier - is not speech either
            if timing is None or re.match(r'(NOTE|STYLE|REGION)(\s|$)', rows[0]):
                continue
            # Tags first, then the character references: an encoded '&lt;'
            # is text, and must not be taken for the start of a tag
            lines += [html.unescape(re.sub(r'<[^>]*>', '', row)) for row in rows[timing + 1:]]
        return lines

    @staticmethod
    def available_resolutions(info: Info) -> list[str]:
        """Unique '1080p'-style resolutions offered for a video, highest first."""
        heights = {stream.get('height') for stream in info.get('formats', [])
                   if stream.get('vcodec') not in (None, 'none') and stream.get('height')}
        return [f"{height}p" for height in sorted(heights, reverse=True)]

    @staticmethod
    def video_format(resolution: str) -> str:
        """Build the yt-dlp format selector for a resolution keyword or '720p'.

        Every branch keeps a muxed fallback, as audio_format does: a video that
        publishes only progressive streams matches no "bestvideo" filter at
        all, and available_resolutions counts those streams, so the menu can
        offer a height that a video-only selector cannot download.
        """
        match resolution:
            case Resolution.HIGHEST.value:
                return 'bestvideo/best'
            case Resolution.LOWEST.value:
                return 'worstvideo/worst'
            case _:
                height = str(resolution).rstrip('p')
                return f"bestvideo[height={height}]/best[height={height}]/best"

    # yt-dlp's own quality words, as they appear in format_note
    AUDIO_TIERS = ('ultralow', 'low', 'medium', 'high')

    @staticmethod
    def _audio_streams(info: Info) -> list[dict[str, Any]]:
        """A video's usable audio streams: original language, no DRC.

        A dubbed video publishes a full set per language, so without the
        language filter a "quality" choice could hand back the wrong language.
        yt-dlp marks the original with the highest language_preference. DRC
        streams are dynamic-range compressed, not a quality step.
        """
        streams = [f for f in info.get('formats', [])
                   if f.get('vcodec') in (None, 'none')
                   and f.get('acodec') not in (None, 'none')
                   and f.get('abr')]
        preferences = [f['language_preference'] for f in streams
                       if f.get('language_preference') is not None]
        if preferences:
            best = max(preferences)
            streams = [f for f in streams if f.get('language_preference') == best]
        return [f for f in streams
                if 'drc' not in [part.strip().lower()
                                 for part in (f.get('format_note') or '').split(',')]]

    @classmethod
    def _audio_tiers(cls, info: Info) -> dict[str, float]:
        """Map each audio quality tier a video offers to its best bitrate.

        The tier word is matched by name, not position: format_note reads
        "medium, DRC" on a plain video but "English (US) original (default),
        medium" on a dubbed one, where a dub's note is its language.
        """
        tiers: dict[str, float] = {}
        for stream in cls._audio_streams(info):
            parts = [p.strip().lower()
                     for p in (stream.get('format_note') or '').split(',')]
            label = next((p for p in parts if p in cls.AUDIO_TIERS),
                         f"{round(stream['abr'])}k")
            tiers[label] = max(tiers.get(label, 0), stream['abr'])
        return tiers

    @classmethod
    def available_audio_qualities(cls, info: Info) -> list[str]:
        """Distinct audio tiers offered for a video, best first."""
        tiers = cls._audio_tiers(info)
        return sorted(tiers, key=lambda tier: tiers[tier], reverse=True)

    @classmethod
    def resolved_bitrate(cls, quality: str | None, info: Info) -> float | None:
        """The bitrate of the stream a quality request actually selects.

        None means "no constraint" - the request was for the best available,
        or names a tier this video does not have.
        """
        if not quality or quality == Resolution.HIGHEST.value:
            return None

        tiers = cls._audio_tiers(info)
        if not tiers:
            return None
        if quality == Resolution.LOWEST.value:
            # Not 'worstaudio': that sorts YouTube's bitrate-less HLS manifest
            # below every real stream, and picks it from whichever language it
            # happens to sit in. The lowest real tier is what "lowest" means.
            return min(tiers.values())
        if _is_number(str(quality)):
            # Measured against individual streams, not tier ceilings: a tier
            # spans ~47k to ~60k, so a budget has to be able to land inside one
            rates = [stream['abr'] for stream in cls._audio_streams(info)]
            if not rates:
                return None
            # A budget under every stream must not silently mean "best available"
            return int(quality) if any(r <= int(quality) for r in rates) else min(rates)
        return tiers.get(quality)

    @classmethod
    def selected_format(cls, selector: str, info: Info) -> dict[str, Any] | None:
        """The format yt-dlp's own selector picks, without downloading it.

        A tier's headline bitrate is not what arrives: YouTube's medium tier
        holds a 130k AAC beside a 106k Opus, and yt-dlp prefers the Opus.
        Asking the selector is the only way to name a file after the stream it
        will actually contain.
        """
        try:
            # One engine for every lookup: a menu asks this once per row, and
            # constructing a YoutubeDL is the expensive half
            engine = cls._selector_engine
            if engine is None:
                engine = cls._selector_engine = yt_dlp.YoutubeDL({'quiet': True})
            chosen = engine.build_format_selector(selector)({
                'formats': info.get('formats', []),
                'incomplete_formats': True})
            return next(iter(chosen), None)
        except Exception:
            # build_format_selector is a yt-dlp internal; a filename label is
            # not worth failing a download over if it ever changes shape
            return None

    @classmethod
    def selected_bitrate(cls, quality: str | None, info: Info) -> int | None:
        """The rounded bitrate a quality request actually downloads, or None.

        Cached on the info dict, which is one video's metadata and lives no
        longer: a menu asks this once per row and again per label, and every
        miss compiles a format selector and rewalks every format.
        """
        cache = info.setdefault('_bitrate_cache', {})
        if quality not in cache:
            chosen = cls.selected_format(cls.audio_format(quality, info), info) or {}
            # Fall back to the tier ceiling if the selector could not be run
            bitrate = chosen.get('abr') or cls.resolved_bitrate(quality, info)
            cache[quality] = round(bitrate) if bitrate else None
        return cache[quality]

    @classmethod
    def audio_bitrate_label(cls, quality: str | None, info: Info) -> str:
        """Filename label for the audio a request selects, e.g. "60k".

        Names the file after what is downloaded rather than what was typed, so
        "low", "lowest" and "64" all read alike when they land on one stream.
        Blank for the best available, which is the default however it was
        asked for: "highest" and the top of the menu name one file.
        """
        bitrate = cls.selected_bitrate(quality, info)
        if bitrate is None or bitrate == cls.selected_bitrate(Resolution.HIGHEST.value, info):
            return ""
        return f"{bitrate}k"

    @classmethod
    def audio_format(cls, quality: str | None, info: Info) -> str:
        """Build the yt-dlp audio selector for a tier name, bitrate, or keyword.

        Every branch keeps a bare "bestaudio" fallback: a filter that matches
        nothing must degrade rather than fail the download, and yt-dlp's own
        ordering is what keeps the original-language track ahead of any dub.
        """
        ceiling = cls.resolved_bitrate(quality, info)
        if not ceiling:
            return 'bestaudio/best'
        return f'bestaudio[abr<={ceiling}]/bestaudio'

    def download_format(self, url: str, format_selector: str, output_dir: str,
                        filename_stem: str, reuse: bool = False) -> str:
        """Download one yt-dlp format into output_dir, named after filename_stem.

        The extension is whatever the chosen stream actually is, not one we
        pick: forcing it wrote Opus-in-WebM into files named .mp3, which
        ffmpeg reads happily and media players refuse. Returns the real path.

        Exits with a message rather than a traceback: by the time a download
        fails there is nothing left for the caller to fall back to.

        reuse takes a file already there under the name instead of fetching
        it. Only for a name that says which video it is: yt-dlp hands back
        whatever file has the name, and a title or a RENAME can be another
        video's, whose file was then passed off as this one's.
        """
        os.makedirs(output_dir, exist_ok=True)
        options = dict(self.YDL_OPTS, format=format_selector, overwrites=not reuse,
                       outtmpl={'default': os.path.join(output_dir,
                                                        filename_stem + ".%(ext)s")})

        # The metadata this run already fetched, handed back as --load-info-json
        # does: extracted again for every download, one video with four
        # deliverables fetched its page and player four more times, and the
        # formats chosen could differ from the ones the names were made from
        info = getattr(self, '_video_info', {}).get(url)
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                # download() returns a status code; the resolved filename is
                # only on the info dict the extraction hands back
                downloaded = (ydl.process_ie_result(ydl.sanitize_info(info), download=True)
                              if info else ydl.extract_info(url, download=True))
        except yt_dlp.utils.DownloadError as e:
            error(f"Error: YouTube refused the download: {str(e)}")
            print("If this persists, YouTube may have changed something. "
                  "Try: pip install --upgrade yt-dlp")
            raise DownloadFailed("YouTube refused the download") from e

        requested = (downloaded or {}).get('requested_downloads') or [{}]
        path = requested[0].get('filepath')
        if not path or not os.path.exists(path):
            error(f"Error: the download did not produce a file in {output_dir}")
            raise DownloadFailed(f"no file produced in {output_dir}")
        return path

    def download_audio_stream(self, info: Info, filename_stem: str, is_temp: bool = False,
                              format_selector: str = 'bestaudio/best',
                              keep_in: str | None = None) -> tuple[str, str]:
        """Download an audio stream (optionally to the temp directory).

        The default 'bestaudio' keeps yt-dlp's preference for the
        original-language track: dubs are published at the same bitrate, so
        picking on bitrate alone would transcribe an arbitrary language. Every
        selector audio_format builds preserves that ordering.
        """
        print("Downloading the audio stream...")

        output_dir = (os.path.join(self.AUDIO_DIR, self.TEMP_DIR) if is_temp
                      else (keep_in or self.AUDIO_DIR))
        # Scratch audio outlives a transcription that failed, for the retry to
        # reuse rather than fetch again - named by the video's id, so what it
        # reuses is this video's and not another's with the same title
        reuse = is_temp and bool(info.get('id'))
        if reuse:
            filename_stem = f"{filename_stem} [{info['id']}]"

        relative_path = self.download_format(
            info['webpage_url'], format_selector, output_dir, filename_stem, reuse=reuse)

        absolute_path = os.path.abspath(relative_path)
        print(f"Audio downloaded to {absolute_path}")

        return relative_path, absolute_path

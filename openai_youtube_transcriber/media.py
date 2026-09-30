"""What ffmpeg and ffprobe say of a file, and what they make of it."""

import os
import re
import subprocess

from .common import FFMPEG_RUN, _is_number, _same_file, error


class MediaMixin:
    """What ffmpeg and ffprobe say of a file, and what they make of it."""

    # ffmpeg's lists of what it can write, which do not change while the process
    # runs. Shared by every session.
    _format_cache = {}
    _extension_cache = {}

    def is_valid_media_file(self, path):
        """Check if path is a supported audio/video file."""
        if not os.path.exists(path):
            return False

        format_name = self.get_file_format(path)
        if format_name is not None:
            return True

        valid_extensions = ['.mp3', '.mp4', '.wav', '.avi', '.mov',
                            '.mkv', '.flac', '.ogg', '.m4a', '.webm']
        file_ext = os.path.splitext(path)[1].lower()
        return file_ext in valid_extensions

    def get_file_format(self, file_path):
        """Get media format using ffprobe, or None if this is not media.

        Quiet about failing: is_valid_media_file uses this to ask a question,
        and "not a media file" is the answer to it, not an error. Printing
        ffprobe's exit status put a traceback-shaped line in front of anyone
        who mistyped a path, ahead of the message that actually helps.
        """
        try:
            cmd = [
                'ffprobe', '-v', 'error',
                '-show_entries', 'format=format_name',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                file_path
            ]
            result = subprocess.run(
                cmd, capture_output=True, check=True, **FFMPEG_RUN
            )
            return result.stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            return None

    # Keep what YouTube served, with no second-generation encode
    FORMAT_ORIGINAL = 'original'
    FORMAT_DEFAULT = 'default'
    DEFAULT_VIDEO_FORMAT = 'mp4'
    DEFAULT_VIDEO_ONLY_CODEC = 'h264'
    DEFAULT_AUDIO_FORMAT = 'mp3'
    # A container that will hold whatever codec was asked for, when the codec's
    # usual one will not
    FALLBACK_CONTAINER = 'mkv'
    # ffmpeg names some muxers after the standard rather than the extension
    # people type, and picks the muxer from the extension anyway
    FORMAT_ALIASES = {'mkv': 'matroska', 'mka': 'matroska', 'm4a': 'ipod',
                      'aac': 'adts'}
    # Containers asked for because everything plays them. MP4 may legally hold
    # Opus, but players that matter refuse it, so its audio is brought into line
    PORTABLE_CONTAINERS = ('mp4', 'm4v', 'mov')
    PORTABLE_AUDIO = ('aac', 'mp3', 'alac')
    CODEC_CONTAINERS = {'h264': 'mp4', 'hevc': 'mp4', 'av1': 'mp4', 'mpeg4': 'mp4',
                        'vp8': 'webm', 'vp9': 'webm'}
    # The audio codecs players expect of a container, where ffmpeg will copy
    # more into it than they play: Opus into .mp4, AAC into .wav. Audio in
    # any other codec is re-encoded to the container's own; Matroska, and a
    # container not named here, take what they are given.
    AUDIO_CODECS = {
        'mp4': PORTABLE_AUDIO, 'm4v': PORTABLE_AUDIO, 'mov': PORTABLE_AUDIO,
        'm4a': ('aac', 'alac'), 'm4b': ('aac', 'alac'), 'aac': ('aac',),
        'mp3': ('mp3',), 'flac': ('flac',), 'opus': ('opus',),
        'ogg': ('vorbis', 'opus', 'flac'), 'oga': ('vorbis', 'opus', 'flac'),
        'webm': ('vorbis', 'opus'),
        'wav': ('pcm_s16le', 'pcm_s24le', 'pcm_s32le', 'pcm_f32le', 'pcm_u8'),
    }

    @classmethod
    def audio_plays_in(cls, codec, container):
        """Whether audio in `codec` may be copied into `container` as it is."""
        return container not in cls.AUDIO_CODECS or codec in cls.AUDIO_CODECS[container]

    @classmethod
    def ffmpeg_formats(cls, kind):
        """Names ffmpeg accepts for `kind`: 'container' or 'video'.

        Read from the installed ffmpeg rather than hardcoded, so the menu can
        never offer something this build cannot write. Empty if ffmpeg is
        missing, which leaves only the defaults and 'original' on offer.
        """
        cached = cls._format_cache
        if kind in cached:
            return cached[kind]

        flag = '-muxers' if kind == 'container' else '-encoders'
        try:
            listing = subprocess.run(['ffmpeg', '-hide_banner', flag],
                                     capture_output=True, check=True, **FFMPEG_RUN).stdout
        except (subprocess.CalledProcessError, FileNotFoundError):
            cached[kind] = []
            return cached[kind]

        names = set()
        for line in listing.splitlines():
            parts = line.split()
            if len(parts) < 2 or not parts[0].startswith(('E', 'V', 'A', 'D', 'S', '.')):
                continue
            if kind == 'container':
                if parts[0] == 'E':
                    names.add(parts[1])
            elif parts[0][0] == 'V':
                # Prefer the codec name over the encoder name: "libx264" is one
                # way to write h264, and the codec is what a user will type
                match = re.search(r'\(codec (\w+)\)', line)
                names.add(match.group(1) if match else parts[1])
        names.update(alias for alias, muxer in cls.FORMAT_ALIASES.items()
                     if kind == 'container' and muxer in names)
        # The listing header slips a '=' through the column parse
        cached[kind] = sorted(n for n in names if re.match(r'^[a-z0-9][a-z0-9_]*$', n))
        return cached[kind]

    @classmethod
    def format_extension(cls, name):
        """The extension ffmpeg writes for a format, or None if it writes no file.

        A muxer is not always named after the extension people type - MKV is
        "matroska", M4A is "ipod" - and a few, like "null", write nothing at
        all. ffmpeg is the only authority on which is which, and this is one
        call for the one format that was actually chosen.
        """
        cached = cls._extension_cache
        if name not in cached:
            muxer = cls.FORMAT_ALIASES.get(name, name)
            try:
                listing = subprocess.run(['ffmpeg', '-hide_banner', '-h', f'muxer={muxer}'],
                                         capture_output=True, check=True, **FFMPEG_RUN).stdout
            except (subprocess.CalledProcessError, OSError):
                listing = ""
            match = re.search(r'Common extensions:\s*([^.\n]+)', listing)
            extensions = [e.strip() for e in match.group(1).split(',')] if match else []
            # Keep the name when it is itself one of them, so m4a stays .m4a
            # rather than becoming the ipod muxer's first choice, .m4v
            cached[name] = (name if name in extensions
                            else extensions[0] if extensions else None)
        return cached[name]

    @staticmethod
    def stream_property(path, kind, entry):
        """One ffprobe field of a file's first video or audio stream, or None.

        None covers every way of not knowing: no such stream, no ffprobe, and a
        container that does not record the field - matroska rarely stores an
        audio bitrate.
        """
        try:
            probe = subprocess.run(
                ['ffprobe', '-v', 'error',
                 '-select_streams', 'v:0' if kind == 'video' else 'a:0',
                 '-show_entries', f'stream={entry}', '-of', 'csv=p=0', path],
                capture_output=True, check=True, **FFMPEG_RUN).stdout.strip()
        except (subprocess.CalledProcessError, OSError):
            return None
        value = probe.splitlines()[0].strip() if probe else ""
        return None if value in ("", "N/A") else value

    @classmethod
    def stream_codec(cls, path, kind):
        """The codec of a file's first video or audio stream, or None."""
        return cls.stream_property(path, kind, 'codec_name')

    @classmethod
    def source_height(cls, path):
        """The height of a file's video, or None if it has none to read."""
        value = cls.stream_property(path, 'video', 'height')
        return int(value) if value and _is_number(value) else None

    @classmethod
    def source_bitrate(cls, path):
        """A file's audio bitrate in kbps, or None if it is not recorded."""
        value = cls.stream_property(path, 'audio', 'bit_rate')
        return round(int(value) / 1000) if value and _is_number(value) else None

    def strip_audio(self, path):
        """Drop a file's audio track, copying the video rather than re-encoding.

        A height YouTube publishes only as a progressive stream matches no
        video-only selector, so video_format falls back to a muxed one and the
        audio arrives with it. "Video Only" has to mean that however the stream
        was served, and a copy keeps FORMAT_ORIGINAL's promise of no second
        generation.
        """
        if self.stream_codec(path, 'audio') is None:
            return path
        stem, extension = os.path.splitext(path)
        silent = f"{stem}.silent{extension}"
        print(f"Removing the audio {os.path.basename(path)} arrived with...")
        try:
            subprocess.run(['ffmpeg', '-y', '-i', path, '-c', 'copy', '-an', silent],
                           capture_output=True, check=True, **FFMPEG_RUN)
        except (subprocess.CalledProcessError, OSError) as e:
            error(f"Error: could not remove the audio from "
                  f"{os.path.basename(path)}: {str(e)}")
            return path
        # ffmpeg can exit 0 having written nothing usable, and this replaces the
        # download: an unusable result has to leave the served file alone
        if not os.path.exists(silent) or os.path.getsize(silent) == 0:
            error(f"Error: stripping the audio from {os.path.basename(path)} "
                  f"produced nothing; keeping the file as served.")
            return path
        os.replace(silent, path)
        return path

    def convert_media(self, source, target_format, kind, output_dir, filename_stem,
                      height=None, bitrate=None, replace_source=True):
        """Re-encode `source` into target_format. Returns the new path, or None.

        Streams are copied where the container allows it, so asking for the
        format something already is costs a remux rather than a re-encode.
        `height` scales the video, `bitrate` re-encodes the audio at that many
        kbps, and neither can be had by copying - each rules out the cheap path
        for its own stream. `kind` is "video" for a file with the audio
        stripped, "audio" for the audio alone, and anything else to keep both.

        `replace_source=False` refuses to write over the source, which is what
        a file the user pointed us at needs and one we downloaded does not.
        """
        scale = ['-vf', f'scale=-2:{height}'] if height else []
        rate = ['-b:a', f'{bitrate}k'] if bitrate else []
        if kind == 'video':
            container = self.CODEC_CONTAINERS.get(target_format, self.FALLBACK_CONTAINER)
            attempts = [['-c:v', target_format, '-an'] + scale]
            # A stream that is already the codec asked for needs a remux, not a
            # generation of quality loss and minutes of CPU - but a scale is a
            # re-encode however well the codec already matches
            if not scale and self.stream_codec(source, 'video') == target_format:
                attempts.insert(0, ['-c:v', 'copy', '-an'])
        elif kind == 'audio':
            container = self.format_extension(target_format) or target_format
            # Remux first: changing the container need not re-encode the audio -
            # unless it lands in one that players refuse it in
            copy = not rate and self.audio_plays_in(self.stream_codec(source, 'audio'),
                                                    container)
            attempts = ([['-vn', '-c:a', 'copy']] if copy else []) + [['-vn'] + rate]
        else:
            container = self.format_extension(target_format) or target_format
            audio_copies = not rate and self.audio_plays_in(
                self.stream_codec(source, 'audio'), container)
            copyable = (([] if scale else ['-c:v', 'copy'])
                        + (['-c:a', 'copy'] if audio_copies else []))
            attempts = [copyable + scale + rate]
            if copyable:
                # A container that will not hold the streams as they are costs
                # a re-encode rather than a failure
                attempts.append(scale + rate)

        os.makedirs(output_dir, exist_ok=True)
        target = os.path.join(output_dir, f"{filename_stem}.{container}")
        # A codec change can land on the source's own container (AV1 and H.264
        # both live in .mp4), so equality of paths does not mean equality of
        # content: write beside it and swap. Compared as files, not as text: a
        # folder reached through a symlink, or C0001.mp4 beside C0001.MP4 on a
        # file system that does not tell case apart, is the source all the
        # same, and ffmpeg -y wrote over the file it was reading.
        in_place = _same_file(target, source)
        if in_place and not replace_source:
            print(f"Skipping {os.path.basename(target)}: it is the source file itself.")
            return None
        if in_place:
            target = os.path.join(output_dir, f"{filename_stem}.converting.{container}")

        last_error = ""
        for extra in attempts:
            command = ['ffmpeg', '-y', '-i', source] + extra + [target]
            try:
                subprocess.run(command, capture_output=True, check=True, **FFMPEG_RUN)
            except subprocess.CalledProcessError as e:
                last_error = e.stderr
                continue
            except OSError:
                error("Error running ffmpeg")
                return None
            # ffmpeg can exit 0 having written nothing usable - an encoder that
            # only warns on a codec its container will not hold, a truncated
            # write. The caller deletes the source on our word, so an empty
            # file has to read as a failure and not as a conversion.
            if not (os.path.exists(target) and os.path.getsize(target)):
                last_error = "ffmpeg reported success but wrote an empty file"
                self._discard(target)
                continue
            if in_place:
                os.replace(target, source)
                return source
            return target

        error(f"Error converting to {target_format}: {str(last_error)[-300:]}")
        return self._discard(target)

    @staticmethod
    def _discard(path):
        """Remove a half-written output and return None, for a failed ffmpeg run."""
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            pass
        return None

    def combine_audio_video(self, video_path, audio_path, output_path):
        """Merge separate video and audio files using ffmpeg.

        Nothing is re-encoded that the container will accept as it is: both
        streams are copied where possible, then the video alone, and only a
        container that will take neither costs a full re-encode.
        """
        output_dir = os.path.dirname(output_path)
        if not self.ensure_directory_exists(output_dir):
            error(f"Error: Cannot create video output directory {output_dir}")
            return None

        if not self.verify_file_writable(output_path):
            error(f"Error: Cannot write to output video file {output_path}")
            return None

        try:
            video_size = os.path.getsize(video_path)
            audio_size = os.path.getsize(audio_path)
            required_space = (video_size + audio_size) * 1.5

            free_space = self.get_free_disk_space(output_dir)
            if free_space is not None and free_space < required_space:
                error(f"Error: Not enough disk space to combine video. "
                      f"Need {required_space/1024/1024:.1f}MB, "
                      f"have {free_space/1024/1024:.1f}MB free.")
                return None
        except OSError as e:
            print(f"Warning: Could not verify file sizes: {str(e)}")

        if not os.path.exists(video_path):
            error(f"Error: Video file not found: {video_path}")
            return None

        if not os.path.exists(audio_path):
            error(f"Error: Audio file not found: {audio_path}")
            return None

        # Named streams, not ffmpeg's pick of them: a progressive fallback
        # arrives with audio already in it, and the default choice across
        # both inputs could take that over the tier this merge asked for
        base = ['ffmpeg', '-y', '-i', video_path, '-i', audio_path,
                '-map', '0:v:0', '-map', '1:a:0']
        # Copy what the container will take, and only fall back as far as needed
        attempts = [base + ['-c:v', 'copy', output_path], base + [output_path]]
        container = os.path.splitext(output_path)[1].lstrip('.').lower()
        if (container not in self.PORTABLE_CONTAINERS
                or self.stream_codec(audio_path, 'audio') in self.PORTABLE_AUDIO):
            # MKV takes Opus as served; MP4 gets it re-encoded to AAC
            attempts.insert(0, base + ['-c', 'copy', output_path])

        for index, command in enumerate(attempts):
            try:
                subprocess.run(command, capture_output=True, check=True, **FFMPEG_RUN)
                break
            except subprocess.CalledProcessError as e:
                if index == len(attempts) - 1:
                    error(f"Error combining audio and video: {e.stderr}")
                    return self._discard(output_path)
            except OSError:
                error("Error running ffmpeg")
                return self._discard(output_path)

        if not os.path.exists(output_path):
            error("Error: Failed to create combined video file")
            return None
        if not os.path.getsize(output_path):
            error("Error: the combined video file is empty")
            return self._discard(output_path)

        print(f"Combined video saved to {output_path}")
        return output_path

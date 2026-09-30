"""YouTubeTranscriber: the app's tools, composed of its mixins."""

from __future__ import annotations

import shutil

from .enhancement import EnhancementMixin
from .files import FilesMixin
from .inputs import InputsMixin
from .media import MediaMixin
from .transcription import TranscriptionMixin
from .youtube import YouTubeMixin


class YouTubeTranscriber(InputsMixin, FilesMixin, YouTubeMixin, MediaMixin,
                         TranscriptionMixin, EnhancementMixin):
    """Handles YouTube downloads, Whisper transcription, and AI enhancement.

    Each mixin is one concern, in a module of its own, and TranscriberBase
    holds what they share: where the app keeps its files and what a profile
    holds. This class is where they meet, and lets go of what a session held.
    """

    def release_caches(self) -> None:
        """Let go of what a finished session was holding.

        A Whisper model is gigabytes, and the round after this one may not
        transcribe at all; the format-selector engine holds yt-dlp's sockets.
        Neither should sit through a "Run again?" waiting to be asked for.
        """
        self._loaded_model_name = self._loaded_model = None
        self._whisper_results = {}
        # Format URLs expire, and the next round may be hours away
        self._video_info = {}
        engine = type(self)._selector_engine
        if engine is not None:
            type(self)._selector_engine = None
            try:
                engine.close()
            except Exception:
                pass

    def check_dependencies(self) -> bool:
        """Verify required system dependencies (ffmpeg, ffprobe) are installed."""
        # ffprobe is its own binary and some builds ship without it; every
        # question about a local file goes through it, and a missing one would
        # otherwise read as "this file has no video stream"
        missing = [n for n in ("ffmpeg", "ffprobe") if shutil.which(n) is None]
        if missing:
            print(f"ERROR: {' and '.join(missing)} is not found in the system PATH.")
            print("Please install ffmpeg and make sure it's in your PATH:")
            print("- Windows: https://ffmpeg.org/download.html")
            print("- macOS: brew install ffmpeg")
            print("- Linux: apt-get install ffmpeg")
            return False

        return True

"""YouTubeTranscriber: the app's tools, and where it keeps its files."""

import os
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

    Each mixin is one concern, in a module of its own; this class is where they
    meet, and holds what they share: where the app keeps its files, what a
    profile holds, and the caches a session lets go of when it ends.
    """

    DATA_DIR = "OpenAIYouTubeTranscriber"
    AUDIO_DIR = os.path.join(DATA_DIR, "Audio")
    TEMP_DIR = "Temp"
    VIDEO_DIR = os.path.join(DATA_DIR, "Video")
    TRANSCRIPT_DIR = os.path.join(DATA_DIR, "Transcript")
    # The transcript as it arrived, kept only when AI enhancement changed it.
    # Created on demand, so runs without enhancement leave no empty directory
    # behind.
    RAW_TRANSCRIPT_DIR = os.path.join(TRANSCRIPT_DIR, "Raw")
    VIDEO_WITHOUT_AUDIO_DIR = os.path.join(DATA_DIR, "VideoWithoutAudio")
    PROFILE_DIR = os.path.join(DATA_DIR, "Profile")
    PROMPT_DIR = os.path.join(DATA_DIR, "Prompt")
    # The names pyproject.toml installs Prompt/ and the sample profiles under, as data
    PROMPT_PACKAGE = "openai_youtube_transcriber_prompts"
    PROFILE_PACKAGE = "openai_youtube_transcriber_profiles"
    TXT_EXT = ".txt"
    PROFILE_PREFIX = "profile"
    ENV_EXT = ".txt"
    CONFIG_ENV = f"config{ENV_EXT}"
    PROFILE_NAME_TEMPLATE = f"{PROFILE_PREFIX}{{}}{ENV_EXT}"
    DEFAULT_PROFILE = f"{PROFILE_PREFIX}{ENV_EXT}"
    # The repo's Profile/config.txt is LOAD_PROFILE= and this, every field blank;
    # the first saved profile writes it with LOAD_PROFILE filled where there is none
    CONFIG_TEMPLATE = """\
# AI_PROVIDER - who refines the transcript when refinement is on:
#   openai, openrouter, anthropic  cloud; needs API_KEY, or the vendor's own
#                                  OPENAI_API_KEY / OPENROUTER_API_KEY / ANTHROPIC_API_KEY
#   local                          runs on this machine, no key; the first run downloads ~3GB
#   blank                          taken from API_KEY's prefix (sk-, sk-or-, sk-ant-),
#                                  and asked for if there is no key
# MODEL picks the model for whichever it is. Any other OpenAI-compatible endpoint
# (Groq, Together, Ollama, ...) is openai or openrouter plus BASE_URL=; its key
# matches no prefix, so name the provider.
AI_PROVIDER=
API_KEY=
MODEL=
"""
    URL_PLACEHOLDER = "<Insert_YouTube_link_or_local_path_to_audio_or_video>"
    DEFAULT_LANGUAGE = 'en'
    # The language spoken, whichever it is: detected as a SOURCE_LANGUAGE, and
    # as a TARGET_LANGUAGE the transcript in the language the audio is in
    AUTO_LANGUAGE = 'auto'

    # Default field values for profile creation (declaration order == profile file order)
    DEFAULT_FIELDS = {
        "URL": URL_PLACEHOLDER,
        "DOWNLOAD_VIDEO": "",
        "VIDEO_RESOLUTION": "",
        "VIDEO_AUDIO_RESOLUTION": "",
        "VIDEO_RENAME": "",
        "VIDEO_PATH": "",
        "VIDEO_FORMAT": "",
        "VIDEO_ONLY": "",
        "VIDEO_ONLY_RESOLUTION": "",
        "VIDEO_ONLY_RENAME": "",
        "VIDEO_ONLY_PATH": "",
        "VIDEO_ONLY_FORMAT": "",
        "DOWNLOAD_AUDIO": "",
        "AUDIO_RESOLUTION": "",
        "AUDIO_RENAME": "",
        "AUDIO_PATH": "",
        "AUDIO_FORMAT": "",
        "DOWNLOAD_YT_TRANSCRIPT": "",
        "TRANSCRIBE_AUDIO": "",
        "TRANSCRIBE_AUDIO_QUALITY": "",
        "MODEL_CHOICE": "",
        "SOURCE_LANGUAGE": "",
        "TARGET_LANGUAGE": "",
        "USE_EN_MODEL": "",
        "AI_REFINEMENT": "",
        "AI_PROVIDER": "",
        "MODEL": "",
        "PROMPT": "",
        "TRANSCRIPT_RENAME": "",
        "TRANSCRIPT_PATH": "",
        "KEEP_TRANSCRIPT": "",
        "REPEAT": ""
    }

    # Fields config.txt also carries. A profile line overrides config.txt, so a
    # blank one would wipe it: these are written only when the session settled
    # a value, which is what lets a local-model run be replayed as a local one.
    CONFIG_OVERRIDE_FIELDS = ("AI_PROVIDER", "MODEL")

    def release_caches(self):
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

    def check_dependencies(self):
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

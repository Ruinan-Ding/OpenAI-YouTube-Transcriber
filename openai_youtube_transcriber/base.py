"""What every part of YouTubeTranscriber may use of the others."""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from .common import Info


class TranscriberBase:
    """Where the app keeps its files, what a profile holds, and what one mixin
    calls on another.

    Every mixin derives from this and YouTubeTranscriber from every mixin, so
    what they share is written once, and what each one takes from another is
    declared where a type checker can hold it to that.
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

    # Source answers meaning "no media; refine what is already on disk". Safe
    # to reserve: a video ID is 11 characters, and an existing file of the
    # same name still wins, as one does over an ID-lookalike below.
    SKIP_SOURCE = ("s", "skip")

    # What a session holds, set as it goes and let go of by release_caches
    _video_info: dict[str, Info]
    _loaded_model_name: str | None
    _loaded_model: Any
    _whisper_results: dict[Any, Any]

    if TYPE_CHECKING:
        # Defined by one mixin and called by another; the definitions are
        # the mixins' own, and these only say what they take and give
        def is_valid_media_file(self, path: str) -> bool: ...

        def list_available_prompts(self) -> list[str]: ...

        def named_transcripts(self, text: str | None) -> list[str] | None: ...

        def ensure_directory_exists(self, directory_path: str) -> bool: ...

        def verify_file_writable(self, file_path: str) -> bool: ...

        def get_free_disk_space(self, directory: str) -> int | None: ...

        @staticmethod
        def split_entries(text: str | None,
                          is_whole: Callable[[str], object] | None = None) -> list[str]: ...

        @staticmethod
        def resolve_transcript_language(detected: str | None,
                                        fallback: str | None) -> str | None: ...

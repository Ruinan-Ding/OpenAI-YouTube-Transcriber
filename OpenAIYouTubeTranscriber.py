# Downloads audio/video from YouTube and transcribes it using OpenAI's Whisper
# Author: Ruinan Ding

# Run with: python OpenAIYouTubeTranscriber.py


import codecs
import difflib
import functools
import getpass
import html
import importlib.util
import inspect
import itertools
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from dataclasses import dataclass, field
from enum import Enum
from urllib.parse import parse_qs, urlparse

import whisper
import yt_dlp
from dotenv import dotenv_values, load_dotenv
from dotenv.parser import parse_stream
from langdetect import DetectorFactory, LangDetectException, detect

# langdetect samples at random, so a short or mixed transcript was tagged fr on
# one run and en the next, and named differently each time
DetectorFactory.seed = 0


# How ffmpeg's and ffprobe's output is read. text=True decoded it in the
# locale's encoding - cp1252 on Windows - and ffmpeg writes UTF-8, so a
# Japanese filename in its log raised UnicodeDecodeError and ended the batch.
# Only ever printed or parsed for ASCII, so a byte that does not decode is
# replaced rather than fatal.
FFMPEG_TEXT = {'encoding': 'utf-8', 'errors': 'replace'}


def _is_number(text):
    """Whether an answer is a whole number in ASCII digits.

    str.isdigit() is also true of '²' and other digits int() refuses, and a
    superscript typed at a menu ended the session with a traceback. ASCII only:
    the number goes into yt-dlp selectors and filenames as it was typed.
    """
    return text.isascii() and text.isdigit()


class DownloadFailed(Exception):
    """One source could not be fetched. The pass ends; the batch carries on."""


def error(message):
    """Report a failure on stderr, so redirecting stdout does not swallow it.

    stdout is flushed first: piped, it is block-buffered while stderr is not,
    and the reason for a failure belongs next to the step that hit it.
    """
    sys.stdout.flush()
    print(message, file=sys.stderr)


class YesNo(Enum):
    """Accepted spellings for yes/no/skip answers."""
    YES = ('y', 'yes', 'true', 't', '1')
    NO = ('n', 'no', 'false', 'f', '0')
    SKIP = ('skip', 's')

    @classmethod
    def all_no_and_skip(cls):
        return cls.NO.value + cls.SKIP.value


class Resolution(Enum):
    """Special (non-numeric) resolution keywords."""
    HIGHEST = 'highest'
    LOWEST = 'lowest'
    FETCH = 'fetch'
    F = 'f'

    @classmethod
    def values(cls):
        return [item.value for item in cls]

    @classmethod
    def normalize(cls, value):
        """Lowercase a resolution answer, expand 'f', and drop a bitrate's unit.

        The audio menu prints its tiers as "106k", so that is what a person
        copies back into the field; without this it reached the check as a
        tier name, matched none, and re-asked for what it had just offered.
        """
        value = value.strip().lower()
        if value == cls.F.value:
            return cls.FETCH.value
        if len(value) > 1 and value.endswith('k') and _is_number(value[:-1]):
            return value[:-1]
        return value


class ModelSize(Enum):
    """Whisper model sizes."""
    TINY = 'tiny'
    BASE = 'base'
    SMALL = 'small'
    MEDIUM = 'medium'
    LARGE_V1 = 'large-v1'
    LARGE_V2 = 'large-v2'
    LARGE_V3 = 'large-v3'

    @classmethod
    def standard_models(cls):
        return [cls.TINY, cls.BASE, cls.SMALL, cls.MEDIUM]

    @classmethod
    def all_model_values(cls):
        return [model.value for model in cls]

    @classmethod
    def choice_numbers(cls):
        """1-based menu numbers ('1'..'7') matching declaration order."""
        return tuple(str(i) for i in range(1, len(cls) + 1))

    @classmethod
    def valid_choices(cls):
        """Every accepted non-empty model choice: menu numbers and model names."""
        return cls.choice_numbers() + tuple(cls.all_model_values())

    @classmethod
    def get_model_by_number(cls, number):
        models = list(cls)
        try:
            index = int(number) - 1
        except (TypeError, ValueError):
            return cls.BASE
        return models[index] if 0 <= index < len(models) else cls.BASE

    @classmethod
    def get_model_by_name(cls, name):
        for model in cls:
            if model.value == name:
                return model
        return cls.BASE

    @classmethod
    def from_choice(cls, choice):
        """Resolve a menu number, model name, or blank string to a ModelSize."""
        choice = choice.strip().lower() if choice else choice
        if not choice:
            return cls.BASE
        if choice in cls.choice_numbers():
            return cls.get_model_by_number(choice)
        return cls.get_model_by_name(choice)


class Provider(Enum):
    """Cloud providers for AI transcript enhancement.

    OPENAI and OPENROUTER speak the OpenAI-compatible chat completions API
    (as does any OpenAI-compatible endpoint reached by pointing BASE_URL at it,
    e.g. Groq, Together, DeepSeek, Azure). ANTHROPIC uses Anthropic's native
    Messages API.

    One provider runs per session, so API_KEY, MODEL and BASE_URL are single
    settings rather than one set each. key_prefix says which provider a key
    belongs to, and vendor_key_env is the name that vendor's own tools read,
    so a key already exported in the shell needs no config.txt entry.
    """
    OPENAI = ('openai', 'sk-', None, 'gpt-4o-mini', 'OPENAI_API_KEY')
    OPENROUTER = ('openrouter', 'sk-or-', 'https://openrouter.ai/api/v1',
                  'openai/gpt-4o-mini', 'OPENROUTER_API_KEY')
    ANTHROPIC = ('anthropic', 'sk-ant-', None, 'claude-opus-4-8', 'ANTHROPIC_API_KEY')

    def __init__(self, key, key_prefix, default_base_url, default_model, vendor_key_env):
        self.key = key
        self.key_prefix = key_prefix
        self.default_base_url = default_base_url
        self.default_model = default_model
        self.vendor_key_env = vendor_key_env

    @classmethod
    def from_api_key(cls, api_key):
        """The provider a key belongs to, by its prefix, or None.

        Longest prefix first: OpenRouter's sk-or- and Anthropic's sk-ant- both
        start with OpenAI's sk-, so the general case has to be tried last.
        """
        key = (api_key or '').strip()
        for provider in sorted(cls, key=lambda p: -len(p.key_prefix)):
            if key.startswith(provider.key_prefix):
                return provider
        return None

    @classmethod
    def default(cls):
        """The provider a bare 'y' means: whoever the key on file belongs to.

        A key nobody recognises is an OpenAI-compatible endpoint more often
        than not, but OpenRouter reaches the most models for one key, so it
        stays the answer when there is nothing to go by.
        """
        return cls.from_api_key(os.getenv('API_KEY')) or cls.OPENROUTER

    @classmethod
    def from_string(cls, value):
        """Look up a Provider by its key (e.g. 'openai'). Returns None if no match."""
        if not value:
            return None
        lower = value.lower().strip()
        for provider in cls:
            if lower == provider.key:
                return provider
        return None

    def resolve_base_url(self):
        """Base URL: env override, else the built-in default (None = SDK default)."""
        return os.getenv('BASE_URL') or self.default_base_url

    def resolve_model(self):
        """Model ID for this provider: env override, else the built-in default."""
        return os.getenv('MODEL') or self.default_model

    def resolve_api_key(self):
        """The key: API_KEY, else whatever this vendor's own tools already read.

        Not an API_KEY that says it is another vendor's: an OpenRouter key sent
        to Anthropic failed every chunk and handed that key to the wrong company.
        A BASE_URL is somewhere the user pointed the provider themselves.
        """
        key = os.getenv('API_KEY')
        if key and Provider.from_api_key(key) not in (None, self) and not os.getenv('BASE_URL'):
            key = None
        return key or os.getenv(self.vendor_key_env)


class AIEnhancementMode(Enum):
    """Where enhancement runs. None, rather than a member, means it does not."""
    API = 'api'
    LOCAL = 'local'


class LocalModel(Enum):
    """Available local models for transcript enhancement."""
    QWEN_1_5B = ('qwen2.5-1.5b', 'Qwen/Qwen2.5-1.5B-Instruct')
    QWEN_0_5B = ('qwen2.5-0.5b', 'Qwen/Qwen2.5-0.5B-Instruct')
    DISTILGPT2 = ('distilgpt2', 'distilgpt2')
    GPT2 = ('gpt2', 'gpt2')
    GPT2_MEDIUM = ('gpt2-medium', 'gpt2-medium')
    PHI_1_5 = ('phi-1_5', 'microsoft/phi-1_5')
    DEEPSEEK_1_5B = ('deepseek-1_5b', 'deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B')

    def __init__(self, display_name, hf_model_id):
        self.display_name = display_name
        self.hf_model_id = hf_model_id

    @classmethod
    def default(cls):
        """The default local model: small, instruction-tuned, CPU-friendly."""
        return cls.QWEN_1_5B

    @classmethod
    def all_model_values(cls):
        return [model.display_name for model in cls]

    @classmethod
    def get_by_name(cls, name):
        """Look up a LocalModel by display name. Returns the default if not found."""
        for model in cls:
            if model.display_name == name.lower().strip():
                return model
        return cls.default()

    @classmethod
    def resolve_id(cls):
        """The local model to run: MODEL, else the default.

        A display name is shorthand for its HuggingFace id; anything else is
        taken as an id in its own right, so any model on the Hub can be named.
        """
        named = (os.getenv('MODEL') or '').strip()
        if not named:
            return cls.default().hf_model_id
        if named.lower() in cls.all_model_values():
            return cls.get_by_name(named).hf_model_id
        return named


class YouTubeTranscriber:
    """Handles YouTube downloads, Whisper transcription, and AI enhancement."""

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
    # Filename tag for a prompt that names no description of its own
    REFINED_TAG = " - Refined"
    # Source answers meaning "no media; refine what is already on disk". Safe
    # to reserve: a video ID is 11 characters, and an existing file of the
    # same name still wins, as one does over an ID-lookalike below.
    SKIP_SOURCE = ("s", "skip")
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
    YOUTUBE_HOSTS = ('youtube.com', 'www.youtube.com', 'm.youtube.com',
                     'music.youtube.com', 'youtube-nocookie.com',
                     'www.youtube-nocookie.com', 'youtu.be', 'www.youtu.be')
    # Paths naming one video. Playlist and channel URLs must not match: yt-dlp
    # would download every entry into the single output path we hand it.
    # /embed/videoseries is a playlist wearing an embed path, so it is excluded
    # here rather than left to YDL_OPTS' noplaylist to catch.
    YOUTUBE_VIDEO_PATH = re.compile(r'^/(shorts|embed|live|v)/(?!videoseries)[^/]')
    # quiet only silences progress, not errors; warnings are kept because a
    # broken extractor announces itself there and nowhere else
    YDL_OPTS = {'quiet': True, 'noplaylist': True}
    DEFAULT_SOURCE_PROMPT = ("Enter the YouTube video URL, video ID, local file path, "
                             "or S to refine a transcript (several separated by "
                             "commas or spaces run in turn): ")
    # Appended to the enhancement prompt so chat models don't add "Sure! Here's..." preambles.
    # It says nothing about layout: that is the prompt's to decide, and the
    # shipped ones ask for headers.
    ENHANCEMENT_OUTPUT_DIRECTIVE = (
        'Reply with the result alone: no opening line such as "Here is the edited '
        'transcript", and nothing after it.')
    # max_tokens is required by the Anthropic API (no SDK default); per-chunk value
    # is sized off the chunk itself (see enhance_with_anthropic), capped here
    ANTHROPIC_MAX_OUTPUT_TOKENS = 8192

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

    # Answers from the installed ffmpeg and from yt-dlp's format selector, which
    # do not change while the process runs. Shared by every session: the engine
    # holds sockets and is closed in release_caches, the two listings are text.
    _selector_engine = None
    _format_cache = {}
    _extension_cache = {}

    def ensure_directory_exists(self, directory_path):
        """Create directory if it doesn't exist. Returns True on success."""
        try:
            os.makedirs(directory_path, exist_ok=True)
            return True
        except OSError as e:
            error(f"Error creating directory {directory_path}: {str(e)}")
            return False

    def is_web_url(self, input_str):
        """Check if string is a valid http/https URL (no network calls)."""
        try:
            result = urlparse(input_str)
            return all([result.scheme in ['http', 'https'], result.netloc])
        except ValueError:
            return False

    def add_scheme_if_missing(self, text):
        """Accept a YouTube address typed without 'https://'.

        Matching the whole host keeps local file paths out of it.
        """
        if text.split('/', 1)[0].lower() in self.YOUTUBE_HOSTS:
            return 'https://' + text
        return text

    def is_youtube_video_id(self, text):
        """Check for a valid 11-character video ID (alphanumerics, dash, underscore)."""
        if len(text) != 11:
            return False
        return bool(re.match(r'^[a-zA-Z0-9_-]{11}$', text))

    def construct_youtube_url(self, video_id):
        """Build a full YouTube URL from a video ID."""
        return f"https://www.youtube.com/watch?v={video_id}"

    def is_youtube_url(self, url):
        """Check a URL names a single YouTube video (watch, short, embed forms).

        Shape only: whether the video actually exists is settled by the single
        metadata fetch in _create_youtube_with_recovery, which can re-prompt.
        """
        try:
            parsed = urlparse(url)
        except ValueError as e:
            print(f"Warning: Error checking YouTube URL: {str(e)}")
            return False

        host = parsed.netloc.lower()
        if host not in self.YOUTUBE_HOSTS:
            return False
        if host.endswith('youtu.be'):
            return len(parsed.path) > 1
        if parsed.path == '/watch':
            return 'v' in parse_qs(parsed.query)
        return bool(self.YOUTUBE_VIDEO_PATH.match(parsed.path))

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
                cmd, capture_output=True, check=True, **FFMPEG_TEXT
            )
            return result.stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            return None

    def get_yes_no_input(self, prompt_text, default="y"):
        """Prompt user for yes/no input with validation."""
        while True:
            user_input = input(prompt_text).strip().lower()
            if user_input in YesNo.YES.value:
                return True
            elif user_input in YesNo.NO.value:
                return False
            elif user_input == "":
                return default == 'y'
            else:
                print(f"Invalid input. Please enter one of {YesNo.YES.value + YesNo.NO.value}.")

    def resolve_source(self, text, origin=None):
        """One media entry as (url, is_local_file), or None if it names nothing.

        `origin` is the profile the entry came from, and only changes the
        wording: a profile reports what it loaded, a typed answer does not
        need reading back.
        """
        loaded = f" (from {origin})" if origin else ""
        # ~/clip.mp3 is a file like any other: expanded once, here, and carried
        # expanded, where it was expanded to be recognised as a path and then
        # checked unexpanded. No URL or video ID begins with a tilde.
        if text.startswith('~'):
            text = os.path.expanduser(text)
        url = self.add_scheme_if_missing(text)
        # An existing local file wins over an ID-lookalike filename
        if self.is_youtube_video_id(url) and not os.path.exists(url):
            url = self.construct_youtube_url(url)
            print(f"Detected video ID{' from profile' if origin else ''}, using: {url}")
        if self.is_web_url(url):
            if self.is_youtube_url(url):
                if origin:
                    print(f"Loaded YOUTUBE_URL: {url}{loaded}")
                return url, False
            error("Error: Only YouTube URLs supported for web inputs")
        elif self.is_valid_media_file(url):
            if origin:
                print(f"Loaded local file: {url}{loaded}")
            return url, True
        else:
            print("Invalid input. Please enter valid YouTube URL, video ID, or local file path")
        return None

    def source_entries(self, text, origin=None):
        """Resolve a source answer into the passes it asks for. [] if one fails.

        An answer is a list: videos, media files and transcripts in any order,
        each done in turn. An entry is (url, is_local_file, refine_sources),
        and a set refine_sources is a pass with no media at all - 's', which
        asks which transcripts, or a .txt path naming them outright.
        """
        entries = []
        # An existing path is one entry however many spaces are in it; a URL
        # never has one, so only the separators are left to split on
        for piece in self.split_entries(
                text, lambda part: os.path.exists(os.path.expanduser(part))):
            refine = self.named_transcripts(piece)
            if refine:
                entries.append((None, False, refine))
                continue
            if piece.lower() in self.SKIP_SOURCE and not os.path.exists(piece):
                return []
            resolved = self.resolve_source(piece, origin)
            if not resolved:
                return []
            entries.append(resolved + (None,))
        return entries

    def prompt_for_sources(self, prompt_text=None):
        """Prompt until every entry of the answer is usable. Returns the entries."""
        while True:
            entries = self.source_entries(
                input(prompt_text or self.DEFAULT_SOURCE_PROMPT).strip())
            if entries:
                return entries

    def prompt_for_source(self, prompt_text, allow_skip=False):
        """Prompt for one media source. Returns (url, is_local_file).

        The list belongs at the top of a session; a source asked for halfway
        through a download is being asked for this one video's replacement, so
        the wording is the caller's - the default prompt offers a list and 's',
        and this takes neither.

        `allow_skip` returns None for a blank answer, and for the end of input
        that an unattended run answers with, rather than asking again. Only a
        replacement is optional: the source a session opens with is not.
        """
        while True:
            try:
                answer = input(prompt_text).strip()
            except EOFError:
                if not allow_skip:
                    raise
                answer = ""
            if allow_skip and not answer:
                return None
            resolved = self.resolve_source(answer)
            if resolved:
                return resolved

    def get_model_choice_input(self):
        """Prompt for Whisper model selection (1-7 or name)."""
        while True:
            prompt = (
                "Select Whisper model:\n"
                "1. Tiny\n"
                "2. Base\n"
                "3. Small\n"
                "4. Medium\n"
                "5. Large-v1\n"
                "6. Large-v2\n"
                "7. Large-v3\n"
                "Enter your choice (1-7 or model name, default Base): "
            )
            model_choice = input(prompt).strip().lower()
            if model_choice in ModelSize.valid_choices() + ('',):
                return model_choice
            else:
                print("Invalid input. Please enter a valid model choice or number (1-7).")

    @staticmethod
    def resolve_transcript_language(detected, fallback):
        """Reduce a langdetect code to one Whisper knows, else `fallback`.

        Keeps region tags ('zh-cn') and detection failures out of the filename.
        """
        base = (detected or "").split('-')[0]
        return base if base in whisper.tokenizer.LANGUAGES else fallback

    @staticmethod
    def normalize_language(text):
        """Resolve a language code or name to Whisper's 2-letter code, or None.

        Must return a code: callers compare against DEFAULT_LANGUAGE to pick .en models.
        """
        lower = text.strip().lower()
        code = whisper.tokenizer.TO_LANGUAGE_CODE.get(lower, lower)
        return code if code in whisper.tokenizer.LANGUAGES else None

    @staticmethod
    def split_entries(text, is_whole=None):
        """Split a list answer on commas, spaces, or both.

        "a,b", "a, b" and "a b" are the same two entries. Entries can contain
        spaces themselves - a path, a language name - so `is_whole` says
        whether a piece is already one entry and must not be split further.
        The whole answer is tried first, which is how a file really called
        "Meeting, Q3.txt" survives the comma in its name.
        """
        text = (text or "").strip()
        if not text:
            return []
        if is_whole and is_whole(text):
            return [text]
        entries = []
        for part in text.split(','):
            part = part.strip()
            if not part:
                continue
            if is_whole and is_whole(part):
                entries.append(part)
            else:
                entries.extend(part.split())
        return entries

    def normalize_languages(self, text):
        """Split a comma- or space-separated answer into Whisper codes.

        Returns (codes, unknown). Order is kept and repeats collapse, so
        "en, English, fr" asks for two transcripts rather than three. 'auto',
        the language spoken, is kept as it is.
        """
        def code_of(piece):
            if piece.strip().lower() == self.AUTO_LANGUAGE:
                return self.AUTO_LANGUAGE
            return self.normalize_language(piece)

        codes, unknown = [], []
        for part in self.split_entries(text, lambda piece: code_of(piece) is not None):
            code = code_of(part)
            if code is None:
                unknown.append(part)
            elif code not in codes:
                codes.append(code)
        return codes, unknown

    def get_target_language_input(self):
        """Prompt for the language to write, or several separated by commas or spaces."""
        while True:
            prompt = (
                "Enter the language the transcript should be in: press Enter (or "
                f"'{self.AUTO_LANGUAGE}') for the language spoken, 'en' to translate it "
                "into English, or several separated by commas or spaces for one "
                "transcript each. Whisper translates into English only; see "
                "https://github.com/openai/whisper#supported-languages: "
            )
            answer = input(prompt).strip().lower()

            if not answer:
                return self.AUTO_LANGUAGE

            codes, unknown = self.normalize_languages(answer)
            if codes and not unknown:
                return ",".join(codes)
            print(f"Not a supported language: {', '.join(unknown) or answer}. Please "
                  "refer to the supported languages list and try again.")

    def get_source_language_input(self):
        """Prompt for the language spoken in the audio; Enter has Whisper detect it."""
        while True:
            answer = input("Enter the language spoken in the audio (e.g., 'ja' or "
                           "'japanese'), or press Enter to detect it: ").strip().lower()
            if not answer or answer == self.AUTO_LANGUAGE:
                return self.AUTO_LANGUAGE
            code = self.normalize_language(answer)
            if code:
                return code
            print(f"Not a supported language: {answer}. Please refer to "
                  "https://github.com/openai/whisper#supported-languages and try again.")

    def _validate_hf_model(self, model_name):
        """Check whether a HuggingFace model ID (e.g. 'microsoft/phi-2') exists."""
        try:
            from huggingface_hub import model_info
            model_info(model_name)
            return True
        except ImportError:
            # Can't validate without huggingface_hub; allow it through
            print("Note: Cannot validate model name (huggingface_hub not available). "
                  "Proceeding anyway.")
            return True
        except Exception:
            return False

    def get_ai_provider_input(self):
        """Prompt for the enhancement backend.

        Returns (API, provider, None) or (LOCAL, None, model_id). Only reached
        when AI_PROVIDER names nobody and no key on file says who it belongs to.
        """
        while True:
            suggestions = ", ".join(m.display_name for m in LocalModel)
            provider_names = "/".join(p.key for p in Provider)
            prompt = (
                "Which AI backend?\n"
                f" - Enter a cloud provider: {provider_names}\n"
                f" - Enter 'local' for the default local model "
                f"({LocalModel.default().display_name})\n"
                f" - Enter a model name (e.g., {suggestions})\n"
                "   or any HuggingFace model ID (e.g., microsoft/phi-2)\n"
                f"Choice (default {Provider.default().key}): "
            )
            user_input = input(prompt).strip()
            user_lower = user_input.lower()

            if not user_input:
                return AIEnhancementMode.API, Provider.default(), None

            provider = Provider.from_string(user_lower)
            if provider is not None:
                return AIEnhancementMode.API, provider, None

            if user_lower == 'local':
                # The default the prompt names, not MODEL: this is only asked
                # when AI_PROVIDER is not local, so a MODEL on file is a cloud
                # one, and gpt-4o-mini failed to load from HuggingFace
                return AIEnhancementMode.LOCAL, None, LocalModel.default().hf_model_id

            if user_lower in LocalModel.all_model_values():
                model = LocalModel.get_by_name(user_lower)
                return AIEnhancementMode.LOCAL, None, model.hf_model_id

            model_id = user_input  # preserve original case for HF model IDs
            print(f"Checking if model '{model_id}' exists on HuggingFace...")
            if self._validate_hf_model(model_id):
                print(f"Model '{model_id}' found.")
                return AIEnhancementMode.LOCAL, None, model_id
            else:
                print(f"Model '{model_id}' not found on HuggingFace. Please try again.")

    def _resolve_prompt_choice(self, token, prompts):
        """One entry of a selection: a number, a name in Prompt/, or a path."""
        token = token.strip()
        if _is_number(token) and 1 <= int(token) <= len(prompts):
            return prompts[int(token) - 1]
        for candidate in (token, token + self.TXT_EXT):
            if candidate in prompts:
                return candidate
        return token if os.path.exists(os.path.expanduser(token)) else None

    def get_prompt_input(self):
        """Prompt for prompt files or a custom prompt.

        Returns (filenames, None) for files, (None, text) for an inline prompt,
        or (None, None) if cancelled. Several entries, separated by commas or
        spaces, are several prompts, each running over every transcript.
        """
        prompts = self.list_available_prompts()
        if prompts:
            print("Available prompt files:")
            for i, p in enumerate(prompts):
                print(f"  {i+1}. {p}")
            ask = (f"Select prompt files (numbers, names or paths, separated by "
                   f"commas or spaces, "
                   f"or E for custom; default 1. {prompts[0]}): ")
        else:
            print("No prompt files found in Prompt/ directory.")
            ask = ("Enter a path to a prompt file, E for a custom prompt, "
                   "or press Enter to skip: ")
        print("  E. Enter custom prompt")

        while True:
            user_input = input(ask).strip()
            if not user_input:
                return ([prompts[0]], None) if prompts else (None, None)
            if user_input.lower() == 'e':
                return self._get_inline_prompt()
            chosen = [self._resolve_prompt_choice(token, prompts)
                      for token in self.split_entries(
                          user_input,
                          lambda piece: self._resolve_prompt_choice(piece, prompts))]
            if chosen and None not in chosen:
                return (chosen, None)
            print("Invalid selection. Please try again.")

    def _get_inline_prompt(self):
        """Read a multi-line prompt from the console; (None, text) or (None, None)."""
        print("Enter your custom prompt (press Enter twice to finish):")
        lines = []
        while True:
            line = input()
            if line == '':
                break
            lines.append(line)
        prompt_text = '\n'.join(lines).strip()
        if not prompt_text:
            print("Empty prompt. Skipping AI enhancement.")
            return (None, None)
        print(f"Custom prompt set ({len(prompt_text)} chars).")
        return (None, prompt_text)

    def prompt_dirs(self):
        """Where Prompt/ may be: beside this file, under the working directory,
        and where an installed copy keeps the prompts it shipped with.

        Every other folder is made relative to the working directory, and that
        is where an installed `openai-youtube-transcriber` keeps the user's own
        prompts; the copy beside the module is the repo's own, and still comes
        first. The shipped ones come last, so a prompt edited in the working
        directory is not shadowed by the original it was copied from.
        """
        beside = os.path.join(os.path.dirname(__file__), self.PROMPT_DIR)
        return [d for d in dict.fromkeys((beside, os.path.abspath(self.PROMPT_DIR),
                                          self.installed_prompt_dir()))
                if d and os.path.isdir(d)]

    @classmethod
    def installed_prompt_dir(cls):
        """The folder an installed copy's shipped prompts are in, or None."""
        return cls.installed_data_dir(cls.PROMPT_PACKAGE)

    @staticmethod
    def installed_data_dir(package):
        """The folder the build installed one package of data into, or None.

        pyproject.toml installs the shipped prompts and sample profiles as packages of
        data, and the import system is what knows where site-packages put them.
        A checkout has no such package, and has the files beside the module.
        """
        try:
            spec = importlib.util.find_spec(package)
        except (ImportError, ValueError):
            return None
        locations = list(spec.submodule_search_locations or []) if spec else []
        return locations[0] if locations else None

    def seed_sample_profiles(self):
        """Copy the shipped sample profiles into a Profile/ that does not exist yet.

        An installed copy has them in site-packages, and a profile is loaded,
        listed and saved in the working directory's Profile/. Copied there on
        first run, they are the user's to edit as a checkout's are. A Profile/
        that exists is never touched, so one the user emptied stays empty.
        """
        if os.path.exists(self.PROFILE_DIR):
            return
        source = self.installed_data_dir(self.PROFILE_PACKAGE)
        samples = sorted(name for name in os.listdir(source)
                         if name.startswith(self.PROFILE_PREFIX)
                         and name.endswith(self.ENV_EXT)) if source else []
        if not samples:
            return
        try:
            os.makedirs(self.PROFILE_DIR)
            for name in samples:
                shutil.copyfile(os.path.join(source, name), os.path.join(self.PROFILE_DIR, name))
        except OSError as e:
            error(f"Warning: could not copy the sample profiles: {str(e)}")
            return
        print(f"Copied {len(samples)} sample profiles to {os.path.abspath(self.PROFILE_DIR)}")

    def list_available_prompts(self):
        """List non-empty .txt files in the Prompt/ directory."""
        found = {}
        for prompt_dir in self.prompt_dirs():
            for f in os.listdir(prompt_dir):
                if (f.endswith(self.TXT_EXT) and f not in found
                        and os.path.getsize(os.path.join(prompt_dir, f)) > 0):
                    found[f] = True
        return sorted(found)

    def load_prompt_file(self, filename):
        """Load prompt text from Prompt/<filename>, or from a path to one anywhere.

        Prompt/ is looked in first, so the short names in a profile go on
        meaning what they always did. Empty string if missing or unreadable.
        """
        prompt_path = next(
            (os.path.join(d, filename) for d in self.prompt_dirs()
             if os.path.exists(os.path.join(d, filename))),
            os.path.expanduser(filename))
        if not os.path.exists(prompt_path):
            print(f"Warning: Prompt file not found: {filename}")
            return ""
        content = (self.read_text_file(prompt_path, "prompt file") or "").strip()
        if not content:
            print(f"Warning: Prompt file is empty or unreadable: {prompt_path}")
        return content

    @staticmethod
    def decode_text(data):
        """A text file's bytes as text: UTF-8, with or without a BOM, or UTF-16/32
        with one.

        Notepad's "Unicode" is UTF-16, and its BOM says so outright. Anything
        else has to be UTF-8: guessing among the legacy code pages reads the
        wrong one as readily as the right one, and saves the misreading as
        words. Raises UnicodeDecodeError for bytes that are neither.
        """
        for bom, encoding in ((codecs.BOM_UTF32_LE, 'utf-32'), (codecs.BOM_UTF32_BE, 'utf-32'),
                              (codecs.BOM_UTF16_LE, 'utf-16'), (codecs.BOM_UTF16_BE, 'utf-16')):
            if data.startswith(bom):
                text = data.decode(encoding)
                break
        else:
            text = data.decode('utf-8-sig')
        # As text mode reads it: a file saved on Windows is the same words
        return text.replace('\r\n', '\n').replace('\r', '\n')

    def read_text_file(self, path, what):
        """The text of a transcript or prompt, or None, having said why not.

        A file some other editor saved in another encoding raised out of the
        reader and ended the whole session, the transcripts after it included.
        """
        try:
            with open(os.path.expanduser(path), 'rb') as f:
                return self.decode_text(f.read())
        except OSError as e:
            error(f"Error reading {what} {path}: {e}")
        except UnicodeDecodeError:
            error(f"Error: {what} {path} is not UTF-8 text. Save it as UTF-8 "
                  f"(or UTF-16 with a BOM) and try again.")
        return None

    def is_transcript_file(self, path):
        """Is this an existing .txt file, i.e. a transcript rather than media?"""
        return bool(path) and path.lower().endswith(self.TXT_EXT) and \
            os.path.isfile(os.path.expanduser(path))

    def transcript_sources(self, text):
        """The transcripts `text` names, or None if it names something else.

        Commas or spaces separate several. A path that is itself a file wins
        over splitting it, so both "Me at the zoo.txt" and a hand-named
        "Meeting, Q3.txt" survive - but two space-carrying paths need the comma
        to tell them apart.
        """
        parts = self.split_entries(text, self.is_transcript_file)
        if parts and all(self.is_transcript_file(part) for part in parts):
            return [os.path.expanduser(part) for part in parts]
        return None

    def named_transcripts(self, text):
        """The transcripts a source answer names, or None if it names media.

        's' asks which; a path to a .txt, or several of them, names them
        outright. Both are refine-only runs: nothing is downloaded and
        nothing is transcribed.
        """
        text = (text or "").strip()
        if text.lower() in self.SKIP_SOURCE and not os.path.exists(text):
            return self.select_transcripts() or None
        return self.transcript_sources(text)

    def list_available_transcripts(self):
        """Transcripts to refine, Transcript/Raw/ first.

        Raw/ holds the originals earlier refinements moved out of the way, so
        it is the first place to look for something to try another prompt on.
        """
        found = []
        for folder in (self.RAW_TRANSCRIPT_DIR, self.TRANSCRIPT_DIR):
            if not os.path.isdir(folder):
                continue
            found.extend(os.path.join(folder, name) for name in sorted(os.listdir(folder))
                         if name.endswith(self.TXT_EXT)
                         and os.path.isfile(os.path.join(folder, name)))
        return found

    def _resolve_transcript_choice(self, token, found):
        """One entry of a selection: a number in the list, or a path."""
        token = token.strip()
        if _is_number(token) and 1 <= int(token) <= len(found):
            return found[int(token) - 1]
        return token if self.is_transcript_file(token) else None

    def select_transcripts(self):
        """Pick transcripts to refine. [] if the user backs out.

        Enter cancels rather than taking the first file: this list is a whole
        folder, not the handful of prompts, and refining is not what you want
        done to an arbitrary one of them.
        """
        found = self.list_available_transcripts()
        if found:
            print("Available transcripts:")
            for i, path in enumerate(found):
                print(f"  {i+1}. {os.path.relpath(path)}")
            ask = ("Select transcripts to refine (numbers or paths, separated by "
                   "commas or spaces, or Enter to go back): ")
        else:
            print(f"No transcripts found in {self.TRANSCRIPT_DIR}.")
            ask = "Enter a path to a transcript, or press Enter to go back: "

        while True:
            user_input = input(ask).strip()
            if not user_input:
                return []
            chosen = [self._resolve_transcript_choice(token, found)
                      for token in self.split_entries(
                          user_input,
                          lambda piece: self._resolve_transcript_choice(piece, found))]
            if chosen and None not in chosen:
                return [os.path.expanduser(path) for path in chosen]
            print("Invalid selection. Please try again.")

    def read_transcript(self, path):
        """Read a transcript to refine. Empty string if unreadable or empty."""
        content = self.read_text_file(path, "transcript")
        if content is None:
            return ""
        content = content.strip()
        if not content:
            print(f"Warning: Transcript is empty: {path}")
        return content

    @staticmethod
    def estimate_tokens(text):
        """A token count without a tokenizer: the text's UTF-8 bytes over four.

        Characters over four held for English, at 4.4 a token with Qwen's
        tokenizer, but not for Chinese at 1.7, where a chunk took 2.4 times the
        text it was meant to. A CJK character is three bytes, so this errs a
        little high for both.
        """
        return len(text.encode('utf-8')) // 4

    @staticmethod
    def rejoin(left):
        """What goes back where text was cut after `left`: a space, or nothing
        after Chinese or Japanese, which are written without spaces between words.

        Width finds those - their characters, kana and full-width stops and
        brackets are all wide - except Hangul, which is as wide but spaces its
        words, and lost a space at every seam of a Korean transcript.
        """
        if not left:
            return " "
        last = left[-1]
        wide = unicodedata.east_asian_width(last) in ("W", "F")
        return "" if wide and not unicodedata.name(last, "").startswith("HANGUL") else " "

    @staticmethod
    def longest_missing_run(source, reply):
        """The most words of source in a row that reply leaves out.

        Compared without case, accents or apostrophes, which a refinement fixes;
        a Chinese or Japanese character counts as a word.
        """
        def words(text):
            text = unicodedata.normalize("NFKD", text.lower().replace("'", "").replace("’", ""))
            text = "".join(c for c in text if not unicodedata.combining(c))
            return re.findall(r"[\u3040-\u30ff\u3400-\u9fff]|[^\W_]+", text)

        longest = start = 0
        matcher = difflib.SequenceMatcher(a=words(source), b=words(reply), autojunk=False)
        for block in matcher.get_matching_blocks():
            longest, start = max(longest, block.a - start), block.a + block.size
        return longest

    @classmethod
    def chunk_text(cls, text, max_tokens=800):
        """Split text into chunks at sentence boundaries, under max_tokens each.

        Chunks do not overlap. An overlap gives the model context across the
        boundary, but it cannot be stripped again afterwards: enhancement
        rewrites both copies of it, so no exact match survives to find, and the
        overlap is duplicated into the transcript. Splitting on sentence
        boundaries leaves nothing mid-thought for the context to rescue.
        """
        return cls.chunk_spans(text, max_tokens)[0]

    @classmethod
    def chunk_spans(cls, text, max_tokens=800, count=None):
        """(chunks, seams): chunk_text's chunks, and the exact text between each
        chunk and the next - whitespace, or nothing where a cut had to fall
        inside a word.

        Every chunk is a span of the text as it stands, so a chunk the model
        failed on goes back exactly as it was. Wrapped with textwrap, a word
        longer than the budget was cut and a space put into it, and a script
        without spaces between words, Thai among them, got one at every cut:
        a failed enhancement still changed the words.

        `count` measures a span in tokens, estimate_tokens by default; a
        backend that has the model's own tokenizer passes that instead.
        """
        count = count or cls.estimate_tokens

        def fits(span):
            return count(span) <= max_tokens

        # Hindi ends a sentence with a danda and Arabic a question with its own
        # mark, both followed by a space; Chinese and Japanese use a full-width
        # stop with no space after it. A number opening a line is a list item's,
        # and a cut there left "1." ending one chunk and its item opening the next.
        # The space after each sentence is captured to go back as it was: joined
        # on a space, a chunk kept unrefined lost its line breaks and ran headers
        # into the paragraph before them.
        parts = re.split(r'((?<=[.!?।؟])(?<!^\d\.)(?<!^\d\d\.)\s+|(?<=[。！？])\s*)',
                         text, flags=re.MULTILINE)
        # (span, the whitespace after it); joined, they are the text itself
        pieces = []
        for sentence, space in zip(parts[::2], parts[1::2] + [""]):
            if fits(sentence):
                pieces.append((sentence, space))
                continue
            # Unpunctuated audio yields one giant "sentence": cut it between
            # words, and a word too long for any chunk between characters
            words = re.split(r'(\s+)', sentence)
            for word, gap in zip(words[::2], words[1::2] + [space]):
                pieces += cls._split_word(word, fits) + [("", gap)]

        chunks, seams, current, pending = [], [], "", ""
        for span, space in pieces:
            if not span.strip():
                # Whitespace only: it belongs to the seam, whichever side it is
                pending += span + space
                continue
            lead = span[:len(span) - len(span.lstrip())]
            span, space = span.strip(), span[len(span.rstrip()):] + space
            if current and not fits(current + pending + lead + span):
                chunks.append(current)
                seams.append(pending + lead)
                current = span
            else:
                current += (pending + lead if current else "") + span
            pending = space
        if current:
            chunks.append(current)
        return (chunks, seams) if chunks else ([text], [])

    @staticmethod
    def _split_word(word, fits):
        """A run of text with no whitespace in it, as spans that each fit.

        Cut where the budget runs out, but never between a letter and the mark
        that goes with it - a Thai vowel sign, an accent - which would open the
        next chunk on a mark with nothing to sit on.
        """
        spans = []
        while word and not fits(word):
            low, high = 1, len(word)
            while low < high:
                middle = (low + high + 1) // 2
                low, high = (middle, high) if fits(word[:middle]) else (low, middle - 1)
            cut = low
            while cut > 1 and unicodedata.category(word[cut])[0] == 'M':
                cut -= 1
            spans.append((word[:cut], ""))
            word = word[cut:]
        return spans + [(word, "")]

    def _build_chat_messages(self, prompt_text, chunk):
        """Build the system/user message pair shared by all chat-style backends."""
        return [
            {"role": "system", "content": f"{prompt_text}\n\n{self.ENHANCEMENT_OUTPUT_DIRECTIVE}"},
            {"role": "user", "content": chunk}
        ]

    def _run_chunked_enhancement(self, chunks, backend_label, call_chunk, seams=None):
        """Shared chunk-loop for the enhancement backends.

        call_chunk(chunk) returns enhanced text; a falsy return or a raised
        exception keeps the original chunk. `seams` is chunk_spans' text
        between the chunks, which two chunks kept as they were are joined by,
        so a backend that fails throughout hands back the text it was given.
        """
        enhanced_chunks = []
        unchanged = []
        for i, chunk in enumerate(chunks):
            try:
                print(f"  Processing chunk {i+1}/{len(chunks)}...")
                enhanced = call_chunk(chunk)
            except Exception as e:
                print(f"  Warning: {backend_label} error on chunk {i+1}: {str(e)}")
                enhanced = None
            # A small model wraps its reply in a code block though every prompt says
            # not to, and each fence landed in the file - unless the chunk opened one
            fenced = re.fullmatch(r"```[\w-]*\n(.*?)\n?```", (enhanced or "").strip(), re.DOTALL)
            if fenced and not chunk.startswith("```"):
                enhanced = fenced.group(1).strip()
            if not enhanced:
                unchanged.append(str(i + 1))
            enhanced_chunks.append(enhanced or chunk)
        # A chunk kept as transcribed sits in the file looking like the rest, so
        # the run has to say which, or a partial refinement reads as a whole one
        if unchanged:
            print(f"  Warning: {len(unchanged)} of {len(chunks)} chunk(s) kept as "
                  f"transcribed, not enhanced: chunk {', '.join(unchanged)}.")
        # chunk_text leaves no overlap to strip. Each reply is laid out on its own,
        # so after a chunk that ended a sentence a blank line keeps its last
        # paragraph off the next reply's header. A transcript with no punctuation
        # to cut at is cut mid-sentence, and a blank line there would split the
        # sentence in two, so that seam closes as the text was - on a space, or on
        # nothing in a script without spaces - unless a header follows.
        # Between two chunks kept as they were, the seam is the text's own.
        # Where one was cut mid-word, no reply is laid out around the cut either,
        # so an unended seam closes as the text did there, and not on a space
        # a cut word would take in.
        merged = enhanced_chunks[0].strip() if enhanced_chunks else ""
        for i, (chunk, reply) in enumerate(zip(chunks, enhanced_chunks[1:])):
            reply = reply.strip()
            seam = seams[i] if seams is not None and i < len(seams) else None
            kept = str(i + 1) in unchanged and str(i + 2) in unchanged
            ended = chunk.rstrip()[-1:] in ".!?।؟。！？"
            if seam is not None and kept:
                merged += seam + reply
            elif ended or reply.startswith("#"):
                merged += "\n\n" + reply
            else:
                merged += (self.rejoin(merged) if seam is None else seam) + reply
        return merged.strip()

    def enhance_with_openai_compatible(self, text, prompt_text, api_key, provider):
        """Enhance transcript text via an OpenAI-compatible endpoint.

        Covers OPENAI and OPENROUTER, plus anything else reachable by overriding the
        provider's base URL (Groq, Together, DeepSeek, Azure). Returns `text` on failure.
        """
        try:
            import openai
        except ImportError:
            print("Warning: 'openai' package not installed. Skipping AI enhancement.")
            print("Install with: pip install openai")
            return text

        model = provider.resolve_model()
        base_url = provider.resolve_base_url()
        client_kwargs = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        client = openai.OpenAI(**client_kwargs)
        chunks, seams = self.chunk_spans(text, max_tokens=3000)

        print(f"Enhancing transcript with {provider.key} ({model}, {len(chunks)} chunk(s))...")

        def call_chunk(chunk):
            response = client.chat.completions.create(
                model=model,
                messages=self._build_chat_messages(prompt_text, chunk),
                temperature=0.3
            )
            choice = response.choices[0]
            if choice.finish_reason == "length":
                # Cut off mid-reply, as the Anthropic path guards against too: the
                # original chunk is worth more than the half of it that came back
                print("  Warning: response truncated at the output limit; "
                      "keeping original chunk to avoid content loss.")
                return ""
            # A refusal can arrive with no content at all
            return (choice.message.content or "").strip()

        result = self._run_chunked_enhancement(chunks, provider.key, call_chunk, seams)
        print(f"{provider.key} enhancement complete.")
        return result

    def enhance_with_anthropic(self, text, prompt_text, api_key, provider):
        """Enhance transcript text via Anthropic's Messages API. Returns `text` on failure."""
        try:
            import anthropic
        except ImportError:
            print("Warning: 'anthropic' package not installed. Skipping AI enhancement.")
            print("Install with: pip install anthropic")
            return text

        model = provider.resolve_model()
        base_url = provider.resolve_base_url()
        client_kwargs = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        client = anthropic.Anthropic(**client_kwargs)
        chunks, seams = self.chunk_spans(text, max_tokens=3000)

        print(f"Enhancing transcript with anthropic ({model}, {len(chunks)} chunk(s))...")

        def call_chunk(chunk):
            # Size the output budget off the chunk itself, twice the estimate chunk_text
            # sized it by, so expansion-style prompts still have headroom. Characters
            # over three left a Chinese reply less room than the chunk it answers.
            max_tokens = min(max(self.estimate_tokens(chunk) * 2, 1024),
                             self.ANTHROPIC_MAX_OUTPUT_TOKENS)
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=f"{prompt_text}\n\n{self.ENHANCEMENT_OUTPUT_DIRECTIVE}",
                messages=[{"role": "user", "content": chunk}],
            )
            if response.stop_reason == "max_tokens":
                # Output was cut off mid-sentence; keep the original chunk rather
                # than silently save truncated text.
                print(f"  Warning: response truncated at {max_tokens} tokens; "
                      "keeping original chunk to avoid content loss.")
                return ""
            return "".join(
                block.text for block in response.content if block.type == "text"
            ).strip()

        result = self._run_chunked_enhancement(chunks, "anthropic", call_chunk, seams)
        print("anthropic enhancement complete.")
        return result

    def enhance_with_local(self, text, prompt_text, local_model, keeps="all"):
        """Enhance transcript text with a local HuggingFace model. Returns `text` on failure.

        keeps is what a reply holds of its chunk, and so how it is checked:
        "words" for a refinement, the speaker's own words; "all" for a prompt
        that carries the whole of it in other words, a translation; "some" for
        a summary, shorter on purpose, which a check for a model that stopped
        early would refuse chunk by chunk.
        """
        try:
            from transformers import AutoTokenizer, pipeline
        except ImportError:
            print("Warning: 'transformers' package not installed. Skipping local enhancement.")
            print("Install with: pip install transformers torch")
            return text

        try:
            import torch
        except ImportError:
            print("Warning: 'torch' package not installed or not available. "
                  "Skipping local enhancement.")
            print("Install with: pip install torch")
            return text

        try:
            torch_version = torch.__version__.split('+')[0]
            major, minor = (int(p) for p in torch_version.split('.')[:2])
            if (major, minor) < (2, 2):
                print(f"Note: PyTorch {torch.__version__} is older than the recommended 2.2+. "
                      "Attempting local enhancement anyway; upgrade torch if model loading fails.")
        except Exception:
            print("Note: Unable to determine PyTorch version. Attempting local enhancement anyway.")

        if isinstance(local_model, LocalModel):
            model_id = local_model.hf_model_id
        else:
            model_id = str(local_model)
        print(f"Loading local model: {model_id} (this may take a moment on first run)...")

        try:
            tokenizer = AutoTokenizer.from_pretrained(model_id)
            max_length = getattr(tokenizer, 'model_max_length', 1024)
            # The prompt shares the context with each chunk and its reply. GPT-2
            # reads 1024 tokens and a shipped prompt takes up to 804 of them, so a
            # chunk sized without it failed with "index out of range in self". The
            # 32 covers the chat template's framing.
            prompt_size = len(tokenizer.encode(
                f"{prompt_text}\n\n{self.ENHANCEMENT_OUTPUT_DIRECTIVE}")) + 32
            # A chunk and a reply twice its size in what is left, and each chunk
            # short: Qwen2.5-1.5B returned a 550-word chunk cut down, commented on
            # or swapped for the prompt's example in 5 of 12 runs, a 200-word one
            # in 1 of 6, and a short passage in none; more, shorter calls took
            # about the same time.
            # ponytail: sized for a 1.5B model on CPU; a larger local model can take more
            chunk_max = min((max_length - prompt_size) // 3, 300)
            if chunk_max < 32:
                print(f"Warning: {model_id} reads {max_length} tokens and the prompt takes "
                      f"{prompt_size} of them, leaving no room for the transcript. Skipping "
                      "local enhancement; use a model with a longer context.")
                return text

            accelerate_available = importlib.util.find_spec("accelerate") is not None
            if not accelerate_available:
                print("Warning: 'accelerate' not installed. Loading model without device_map.")

            # transformers called it torch_dtype until 4.56, which renamed it
            # dtype; older ones passed an unknown dtype on to generate(), which
            # refused it for every chunk, and nothing was enhanced
            dtype_argument = ('dtype' if 'dtype' in inspect.signature(pipeline).parameters
                              else 'torch_dtype')
            generator = pipeline(
                'text-generation',
                model=model_id,
                tokenizer=tokenizer,
                device_map="auto" if accelerate_available else None,
                **{dtype_argument: "auto"}
            )
        except Exception as e:
            error(f"Error loading local model '{model_id}': {str(e)}")
            print("Skipping local enhancement.")
            return text

        # Measured by the model's own tokenizer, as chunk_max itself was: the
        # estimate runs high for most models and low for some, and a chunk
        # over its share leaves the reply too little of the context
        chunks, seams = self.chunk_spans(
            text, max_tokens=chunk_max,
            count=lambda span: len(tokenizer.encode(span, add_special_tokens=False)))
        # Instruct/chat models define a chat template; base models (gpt2 etc.) don't
        has_chat_template = getattr(tokenizer, 'chat_template', None) is not None

        print(f"Enhancing transcript with local model ({len(chunks)} chunk(s))...")

        def call_chunk(chunk):
            # Not words: Chinese has no spaces to count them by, and a whole chunk
            # counted as one word, capping the reply at a third of the chunk
            max_new_tokens = max(self.estimate_tokens(chunk) * 2, 256)
            # but never past the end of the context, where the model fails outright
            max_new_tokens = min(max_new_tokens,
                                 max_length - prompt_size - len(tokenizer.encode(chunk)))

            if has_chat_template:
                full_prompt = tokenizer.apply_chat_template(
                    self._build_chat_messages(prompt_text, chunk),
                    tokenize=False, add_generation_prompt=True
                )
                result = generator(
                    full_prompt,
                    max_new_tokens=max_new_tokens,
                    do_sample=True,
                    temperature=0.3,
                    num_return_sequences=1,
                    return_full_text=False
                )
                enhanced = result[0]['generated_text'].strip()
            else:
                full_prompt = f"{prompt_text}\n\n{chunk}\n\nEnhanced version:"
                result = generator(
                    full_prompt,
                    max_new_tokens=max_new_tokens,
                    do_sample=True,
                    temperature=0.3,
                    num_return_sequences=1
                )
                generated = result[0]['generated_text']
                if "Enhanced version:" in generated:
                    enhanced = generated.split("Enhanced version:")[-1].strip()
                else:
                    enhanced = generated[len(full_prompt):].strip()

            # Out of room is a cut-off reply whatever the prompt, as the cloud
            # backends check. Counted before <think> blocks go, and re-encoded
            # from text, which can come out a token short
            if len(tokenizer.encode(enhanced, add_special_tokens=False)) >= max_new_tokens - 1:
                print("  Warning: response truncated at the output limit; "
                      "keeping original chunk to avoid content loss.")
                return ""

            # Reasoning models (e.g., DeepSeek-R1 distills) emit <think> blocks; drop them
            enhanced = re.sub(r'<think>.*?</think>', '', enhanced, flags=re.DOTALL).strip()
            if not enhanced:
                return ""

            # A reply that should be the whole chunk but is under a third of it is
            # usually a model that stopped early. In bytes, not characters: a
            # faithful Chinese translation of English runs to 27% of its characters
            size, whole_size = len(enhanced.encode("utf-8")), len(chunk.encode("utf-8"))
            if keeps != "some" and size < whole_size * 0.3:
                print(f"  The reply was {size * 100 // whole_size}% the size of the chunk, "
                      "too little to be the whole of it.")
                return ""

            # A refinement long enough can still have dropped a paragraph. Clean
            # replies from Qwen2.5-1.5B left out at most 7 words in a row, to filler
            # and misheard words; ones that dropped sentences, 23 and 132.
            # ponytail: measured on English and Spanish; a few dropped words pass
            gap = self.longest_missing_run(chunk, enhanced) if keeps == "words" else 0
            if gap >= 15:
                print(f"  The reply left out {gap} words of the chunk in a row.")
                return ""
            return enhanced

        result = self._run_chunked_enhancement(chunks, "Local model", call_chunk, seams)
        print("Local model enhancement complete.")
        return result

    def enhance_text(self, text, mode, prompt_text, api_key=None, provider=None, local_model=None,
                     keeps="all"):
        """Dispatch enhancement to the cloud or local backend.

        api_key/provider apply to API mode, local_model and keeps to LOCAL mode.
        Returns `text` unchanged if enhancement is skipped or fails.
        """
        if not text or not text.strip():
            print("Warning: No text to enhance.")
            return text

        if not prompt_text:
            print("Warning: No prompt loaded. Skipping enhancement.")
            return text

        if mode == AIEnhancementMode.API:
            if not api_key:
                print("Warning: No API key provided. Skipping enhancement.")
                return text
            provider = provider or Provider.default()
            if provider == Provider.ANTHROPIC:
                return self.enhance_with_anthropic(text, prompt_text, api_key, provider)
            return self.enhance_with_openai_compatible(text, prompt_text, api_key, provider)

        elif mode == AIEnhancementMode.LOCAL:
            if not local_model:
                local_model = LocalModel.default().hf_model_id
            return self.enhance_with_local(text, prompt_text, local_model, keeps=keeps)

        else:
            print("Warning: Unknown enhancement mode. Skipping.")
            return text

    def startfile(self, fn):
        """Open file with system default app (cross-platform)."""
        try:
            if os.name == 'nt':
                os.startfile(fn)
            elif os.name == 'posix':
                opener = 'open' if sys.platform == 'darwin' else 'xdg-open'
                # a non-zero exit from the opener is not our problem
                subprocess.run([opener, fn], check=False)
        except OSError as e:
            # A headless box has no xdg-open. The transcript is already saved,
            # and the rest of a batch is still owed.
            print(f"Note: could not open {os.path.basename(fn)}: {str(e)}")

    def sanitize_filename(self, text):
        """Strip invalid characters from filename; never returns an empty name."""
        cleaned = "".join(c for c in text if c.isalnum() or c in "._- ").strip()
        return cleaned or "untitled"

    def save_transcript(self, text, filename, output_dir, open_after=True):
        """Write transcript text to output_dir/filename; open it unless told not to.

        The Transcript/Raw/ original is saved with open_after=False - only the
        finished transcript is worth putting in front of the user.
        """
        # cwd-relative like the Audio/Video dirs, so all outputs land together
        if not self.ensure_directory_exists(output_dir):
            error(f"Error: Cannot create transcript directory {output_dir}")
            return False

        file_path = os.path.join(output_dir, filename)

        if not self.verify_file_writable(file_path):
            error(f"Error: Cannot write to transcript file {file_path}")
            return False

        required_space = max(len(text) * 2, 1024 * 1024)
        free_space = self.get_free_disk_space(output_dir)
        if free_space is not None and free_space < required_space:
            error(f"Error: Not enough disk space to save transcript. "
                  f"Need {required_space/1024/1024:.1f}MB, "
                  f"have {free_space/1024/1024:.1f}MB free.")
            return False

        try:
            self.write_text_atomically(file_path, text)
        except (OSError, UnicodeError) as e:
            error(f"Error writing transcript file: {str(e)}")
            return False

        # Opening is a convenience; failing to open must not report the file as lost.
        if open_after:
            try:
                self.startfile(file_path)
            except OSError as e:
                print(f"Note: could not open the transcript automatically: {str(e)}")
        return True

    @staticmethod
    def write_text_atomically(path, text):
        """Write `text` to `path` so that a failed write leaves the file there whole.

        The text goes to a file beside it and is swapped in. Opened with 'w', a
        refinement named onto its own source truncated the source before a byte
        of the refinement had landed, and a full disk then lost both.
        """
        target = os.path.realpath(path)
        folder, name = os.path.split(target)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_BINARY', 0)
        for attempt in itertools.count():
            temp = os.path.join(folder, f".{name}.{os.getpid()}-{attempt}.tmp")
            try:
                # 0o666 less the umask, as open() would have made it
                handle = os.open(temp, flags, 0o666)
                break
            except FileExistsError:
                continue
        try:
            with os.fdopen(handle, 'w', encoding='utf-8') as file:
                file.write(text)
            if os.path.exists(target):
                shutil.copymode(target, temp)
            os.replace(temp, target)
        except BaseException:
            try:
                os.remove(temp)
            except OSError:
                pass
            raise

    @staticmethod
    def quality_tag(*qualities):
        """Bracketed quality tag for a media filename, e.g. " [720p low]".

        The best available needs no label, so "highest" and blanks are dropped
        and a file is only marked where it differs from the default. The tag
        also keeps a second run at another quality from silently reusing the
        first run's file, which yt-dlp skips as already downloaded.
        """
        parts = [str(quality) for quality in qualities
                 if quality and str(quality) != Resolution.HIGHEST.value]
        return f" [{' '.join(parts)}]" if parts else ""

    def prompt_suffix(self, prompt_label):
        """The " - desc" filename tag for the prompt that refined a transcript.

        Follows the profile naming convention, prompt<digits>-<desc>.txt, but
        Prompt/ is not restricted to it: a file named otherwise contributes its
        whole stem. A prompt with no describable name - typed inline, or
        prompt.txt and prompt-.txt, which are all convention and no desc -
        falls back to " - Refined". No prompt may tag with nothing: an untagged
        refinement is named exactly like the transcript it refined, and would
        land on top of it.
        """
        if not prompt_label or not prompt_label.endswith(self.TXT_EXT):
            return self.REFINED_TAG
        stem = os.path.basename(prompt_label)[:-len(self.TXT_EXT)]
        match = re.match(r'^prompt(?:\d+)?(?:-(?P<desc>.*))?$', stem)
        desc = (match.group('desc') if match else stem) or ""
        desc = desc.strip()
        if not any(char.isalnum() for char in desc):
            return self.REFINED_TAG
        return f" - {desc}"

    def tagged_prompts(self, prompts):
        """(text, label, tag) per prompt, with the filename tags made distinct.

        Two prompts can want the same tag - prompt0-translator.txt and
        prompt1-translator.txt both read as "translator" - and the second would
        otherwise overwrite the first.
        """
        tagged, seen = [], set()
        for text, label in prompts or []:
            tag = self.prompt_suffix(label)
            base, n = tag, 2
            while tag in seen:
                tag, n = f"{base} {n}", n + 1
            seen.add(tag)
            tagged.append((text, label, tag))
        return tagged

    @staticmethod
    def is_refinement(original_text, text):
        """Did enhancement actually change the words?

        Compared on words rather than characters: the chunker rejoins on blank
        lines or spaces, and whitespace alone is not a refinement.
        """
        return original_text is not None and original_text.split() != text.split()

    def save_final_transcript(self, text, filename, original_text=None,
                              original_filename=None, keep_original=True,
                              open_after=True, output_dir=None):
        """Save the finished transcript to Transcript/. Returns True on success.

        original_text is the text before enhancement, passed under
        original_filename (the untagged name). It is kept in Transcript/Raw/
        unless the user declined, or unless enhancement returned the text
        unchanged - a failed or skipped enhancement would otherwise leave two
        identical files. A run can save a dozen downloaded transcripts at once,
        so open_after=False leaves them where they landed.

        output_dir sends both somewhere else, the unrefined copy to a Raw/
        beside its refinement rather than back in the project folder: a
        transcript and the text it came from belong together.
        """
        final_dir = output_dir or self.TRANSCRIPT_DIR
        raw_dir = (os.path.join(output_dir, "Raw") if output_dir
                   else self.RAW_TRANSCRIPT_DIR)
        # The original first: the refinement can be named onto the very file it
        # was read from, and written second, a Raw/ save that failed left the
        # words that file held nowhere at all
        if keep_original and self.is_refinement(original_text, text):
            raw_name = original_filename or filename
            if self.save_transcript(original_text, raw_name, raw_dir,
                                    open_after=False):
                kept = os.path.join(raw_dir, raw_name)
                print(f"Kept the unrefined transcript at {os.path.abspath(kept)}")

        if not self.save_transcript(text, filename, final_dir,
                                    open_after=open_after):
            return False
        print(f"Saved transcript to "
              f"{os.path.abspath(os.path.join(final_dir, filename))}")
        return True

    def fetch_video_info(self, url):
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
    def caption_language(info, language):
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
    def caption_tracks(info):
        """Every caption track on offer, key -> the name YouTube gives it.

        The uploader's own tracks win a key from the machine ones, being the
        better text where both exist.
        """
        tracks = {}
        for source in ('subtitles', 'automatic_captions'):
            for key, entries in (info.get(source) or {}).items():
                if key not in tracks and entries:
                    tracks[key] = entries[0].get('name') or key
        return tracks

    @classmethod
    def original_caption(cls, info):
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

    def fetch_caption_text(self, info, key):
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

    @staticmethod
    def captions_to_text(payload, ext):
        """A caption file's text, as prose.

        YouTube's rolling captions restate the line before them so a viewer can
        finish reading it, so a line that arrives twice running is one line.
        """
        if ext == '.json3':
            cues = [''.join(seg.get('utf8', '') for seg in (event.get('segs') or []))
                    for event in json.loads(payload).get('events') or []]
        else:
            cues = YouTubeTranscriber.vtt_cue_lines(payload)
        lines = []
        for cue in cues:
            cue = ' '.join(cue.split())
            if cue and (not lines or cue != lines[-1]):
                lines.append(cue)
        return ' '.join(lines)

    @staticmethod
    def vtt_cue_lines(payload):
        """The spoken lines of a WebVTT file, block by block.

        A WebVTT file is blocks between blank lines, and only a cue's payload -
        the lines after its timing line - is speech. Read line by line, a cue's
        numeric identifier and all but the first line of a NOTE were kept as
        speech, and '&amp;' stayed encoded. A header, NOTE, STYLE or REGION
        block has no timing line and so contributes nothing.
        """
        lines = []
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
    def available_resolutions(info):
        """Unique '1080p'-style resolutions offered for a video, highest first."""
        heights = {stream.get('height') for stream in info.get('formats', [])
                   if stream.get('vcodec') not in (None, 'none') and stream.get('height')}
        return [f"{height}p" for height in sorted(heights, reverse=True)]

    @staticmethod
    def video_format(resolution):
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

    @staticmethod
    def _audio_streams(info):
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
    def _audio_tiers(cls, info):
        """Map each audio quality tier a video offers to its best bitrate.

        The tier word is matched by name, not position: format_note reads
        "medium, DRC" on a plain video but "English (US) original (default),
        medium" on a dubbed one, where a dub's note is its language.
        """
        tiers = {}
        for stream in cls._audio_streams(info):
            parts = [p.strip().lower()
                     for p in (stream.get('format_note') or '').split(',')]
            label = next((p for p in parts if p in cls.AUDIO_TIERS),
                         f"{round(stream['abr'])}k")
            tiers[label] = max(tiers.get(label, 0), stream['abr'])
        return tiers

    @classmethod
    def available_audio_qualities(cls, info):
        """Distinct audio tiers offered for a video, best first."""
        tiers = cls._audio_tiers(info)
        return sorted(tiers, key=tiers.get, reverse=True)

    @classmethod
    def resolved_bitrate(cls, quality, info):
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
    def selected_format(cls, selector, info):
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
    def selected_bitrate(cls, quality, info):
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
    def audio_bitrate_label(cls, quality, info):
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
    def audio_format(cls, quality, info):
        """Build the yt-dlp audio selector for a tier name, bitrate, or keyword.

        Every branch keeps a bare "bestaudio" fallback: a filter that matches
        nothing must degrade rather than fail the download, and yt-dlp's own
        ordering is what keeps the original-language track ahead of any dub.
        """
        ceiling = cls.resolved_bitrate(quality, info)
        if not ceiling:
            return 'bestaudio/best'
        return f'bestaudio[abr<={ceiling}]/bestaudio'

    def download_format(self, url, format_selector, output_dir, filename_stem, reuse=False):
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

    def download_audio_stream(self, info, filename_stem, is_temp=False,
                              format_selector='bestaudio/best', keep_in=None):
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
                                     capture_output=True, check=True, **FFMPEG_TEXT).stdout
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
                                         capture_output=True, check=True, **FFMPEG_TEXT).stdout
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
                capture_output=True, check=True, **FFMPEG_TEXT).stdout.strip()
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
                           capture_output=True, check=True, **FFMPEG_TEXT)
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
                subprocess.run(command, capture_output=True, check=True, **FFMPEG_TEXT)
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
                subprocess.run(command, capture_output=True, check=True, **FFMPEG_TEXT)
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

    def transcribe_audio_file(self, file_path, model_name, target_language,
                              source_language=None):
        """Transcribe with Whisper into target_language, the language to write.

        Whisper's own `language` is the language spoken, not the one to write:
        handed the target, it decoded English speech as if it were French. So
        the spoken language is source_language, or detected, and the target
        picks the task - 'auto' or the spoken language itself is a
        transcription, English is Whisper's translation, and any other language
        Whisper cannot write, so the transcription stands in for it, said so.

        Returns (text, language_code), the code being the language the text is
        actually in, or (None, code) on failure or no speech. Never an error
        string, which callers would otherwise save as a transcript.
        """
        if not os.path.exists(file_path):
            error(f"Error: Audio file not found: {file_path}")
            return None, "en"

        # Several target languages ask for the same weights in turn. Keeping
        # one model saves reloading them; keeping two would double the memory a
        # large model already takes
        if getattr(self, '_loaded_model_name', None) == model_name:
            model = self._loaded_model
        else:
            # The last model is let go before the next is loaded: held while it
            # loaded, the two took twice the memory a large model already does
            self._loaded_model_name = self._loaded_model = None
            try:
                print(f"Loading Whisper model: {model_name}")
                model = whisper.load_model(model_name)
            # Whisper reports an unknown name, a corrupt download and a checksum
            # mismatch as RuntimeError, as torch does running out of memory
            except (OSError, ValueError, RuntimeError) as load_error:
                error(f"Error loading Whisper model: {str(load_error)}")
                print("Falling back to base model")
                try:
                    model = whisper.load_model("base")
                except (OSError, ValueError, RuntimeError) as fallback_error:
                    error(f"Error loading fallback model: {str(fallback_error)}")
                    return None, "en"
            # Kept under the name asked for, fallback or not: a model that ran
            # out of memory once does again, and every later target and source
            # of a batch spent gigabytes failing to load it before falling back
            self._loaded_model_name, self._loaded_model = model_name, model

        auto = target_language in (None, "", self.AUTO_LANGUAGE)
        absolute_path = os.path.abspath(file_path)
        wanted = ("in the language spoken" if auto
                  else f"into {self.language_name(target_language)}")
        print(f"Transcribing audio from {absolute_path} ({wanted})...")

        # The passes already made over this audio, and over no other: a batch
        # moves on to the next file, and has no use for the last one's
        cache = getattr(self, '_whisper_results', None) or {}
        if cache.get('path') != absolute_path:
            cache = {'path': absolute_path}
        self._whisper_results = cache
        # The spoken language, once any target has found it out
        heard_key = ('spoken', model_name)

        spoken = source_language or cache.get(heard_key)
        if target_language == 'en' and not spoken:
            # English is a transcription of English speech and a translation of
            # anything else, so this is the one target that needs to know first
            spoken = cache[heard_key] = self.spoken_language(model, file_path)

        def run(language, translate=False):
            """One Whisper pass, once per audio however many targets want it."""
            key = (model_name, language, translate)
            if key not in cache:
                # The task only where it is not the default, so a stand-in model
                # need take no more than Whisper's own first two arguments
                options = {'task': 'translate'} if translate else {}
                result = model.transcribe(file_path, language=language, **options)
                # The text and its language, not the segments and their tokens
                cache[key] = {'text': result['text'], 'language': result.get('language')}
                heard = cache[key]['language']
                if language is None and not translate and heard:
                    # What Whisper detected is what a hint of it would decode:
                    # 'auto' then 'en' on English speech ran a second, identical
                    # full pass, and threw it away as already saved
                    cache.setdefault((model_name, heard, False), cache[key])
                    cache[heard_key] = cache.get(heard_key) or heard
            return cache[key]

        try:
            translated = target_language == 'en' and spoken not in (None, 'en')
            if translated:
                print(f"Whisper heard {self.language_name(spoken)}; translating it into English.")
            result = run(spoken, translated)
            heard = result.get('language')
            if target_language == 'en' and not translated and heard not in (None, 'en'):
                # Detection could not be had beforehand, and Whisper's own says
                # this was not English
                print(f"Whisper heard {self.language_name(heard)}; translating it into English.")
                result, translated = run(heard, True), True
            transcribed_text = result["text"]

            if not transcribed_text.strip():
                print("Warning: Transcription produced empty text. "
                      "The audio might be silent or not contain speech.")
                return None, target_language

        except (RuntimeError, ValueError) as e:
            error(f"Error during transcription: {str(e)}")
            return None, "en"

        print("\nTranscription:\n" + transcribed_text + "\n")

        try:
            detected_language = detect(transcribed_text)
        except LangDetectException as e:
            error(f"Error detecting language: {str(e)}")
            detected_language = "unknown"

        # Named for the language the text is in, which Whisper knows: English
        # for a translation, else the language it transcribed. langdetect only
        # stands in for a model that does not say.
        fallback = self.DEFAULT_LANGUAGE if auto else target_language
        language = ('en' if translated else result.get('language') or spoken
                    or self.resolve_transcript_language(detected_language, fallback))
        read_as = self.resolve_transcript_language(detected_language, None)
        if read_as == language:
            print(f"Verified {self.language_name(language)}")
        elif read_as:
            print(f"Note: Whisper wrote {self.language_name(language)}, but the text reads "
                  f"as {self.language_name(read_as)}.")
        if not auto and language != target_language:
            # Whisper writes the language spoken, or English, and nothing else
            print(f"Whisper translates into English only, so this is the "
                  f"{self.language_name(language)} transcript. For "
                  f"{self.language_name(target_language)}, refine it with "
                  f"prompt0-translator.txt, naming the language on its first line.")
        return transcribed_text, language

    @staticmethod
    def language_name(code):
        """'fr' as 'French', for a message."""
        return whisper.tokenizer.LANGUAGES.get(code, code or "an unknown language").capitalize()

    def spoken_language(self, model, file_path):
        """The language spoken in the audio, by Whisper's own detection, or None.

        One 30-second window, as transcribe() itself decides by, rather than a
        whole transcription just to find out. An English-only model can hear
        nothing else; one that cannot detect leaves it to transcribe().
        """
        if not getattr(model, 'is_multilingual', True):
            return 'en'
        if not hasattr(model, 'detect_language'):
            return None
        try:
            audio = whisper.pad_or_trim(self.load_opening(file_path))
            mel = whisper.log_mel_spectrogram(audio, n_mels=model.dims.n_mels)
            _tokens, probabilities = model.detect_language(mel.to(model.device))
            return max(probabilities, key=probabilities.get)
        except (subprocess.CalledProcessError, OSError, RuntimeError, ValueError,
                AttributeError, TypeError) as e:
            print(f"Note: could not detect the spoken language first ({str(e)}).")
            return None

    @staticmethod
    def load_opening(file_path, seconds=30):
        """The first `seconds` of a file's audio, as whisper.load_audio returns
        all of it: mono float32 at Whisper's sample rate.

        Detection hears only the first 30 seconds, and load_audio decoded the
        whole file for them - hundreds of megabytes of a three-hour lecture -
        before transcribe() decoded it all again. -t ahead of -i stops ffmpeg
        reading at that point.
        """
        import numpy
        command = ['ffmpeg', '-nostdin', '-threads', '0', '-t', str(seconds), '-i', file_path,
                   '-f', 's16le', '-ac', '1', '-acodec', 'pcm_s16le',
                   '-ar', str(whisper.audio.SAMPLE_RATE), '-']
        pcm = subprocess.run(command, capture_output=True, check=True).stdout
        return numpy.frombuffer(pcm, numpy.int16).flatten().astype(numpy.float32) / 32768.0

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

    def list_profiles(self):
        """List profile files in the Profile/ directory, sorted by name.

        Accepts: profile.txt, profile<number>.txt, profile-<desc>.txt,
        profile<number>-<desc>.txt
        """
        if not os.path.exists(self.PROFILE_DIR):
            return []
        pattern = rf"^{re.escape(self.PROFILE_PREFIX)}(?:\d+)?(?:-.*)?{re.escape(self.ENV_EXT)}$"
        return sorted(f for f in os.listdir(self.PROFILE_DIR) if re.match(pattern, f))

    def create_profile(self, profile_fields):
        """Save current session settings as a reusable profile file."""
        if not os.path.exists(self.PROFILE_DIR):
            print(f"Creating profile directory: {self.PROFILE_DIR}")
            os.makedirs(self.PROFILE_DIR, exist_ok=True)

        existing_profiles = self.list_profiles()
        num_pattern = (rf"^{re.escape(self.PROFILE_PREFIX)}(?P<num>\d+)"
                       rf"(?:-.*)?{re.escape(self.ENV_EXT)}$")
        existing_numbers = []
        for f in existing_profiles:
            m = re.match(num_pattern, f)
            if m:
                try:
                    existing_numbers.append(int(m.group('num')))
                except (ValueError, TypeError):
                    continue

        if not existing_profiles:
            profile_name = self.DEFAULT_PROFILE
        else:
            next_number = 0
            while next_number in existing_numbers:
                next_number += 1
            profile_name = self.PROFILE_NAME_TEMPLATE.format(next_number)

        profile_path = os.path.join(self.PROFILE_DIR, profile_name)

        field_order = list(self.DEFAULT_FIELDS)
        with open(profile_path, "w", encoding='utf-8') as profile_file:
            profile_file.write("# Edit values after the = sign\n\n")
            for i, field_name in enumerate(field_order):
                value = profile_fields.get(field_name)
                if field_name not in profile_fields or (
                        not value and field_name in self.CONFIG_OVERRIDE_FIELDS):
                    continue
                newline = "" if i == len(field_order) - 1 else "\n"
                profile_file.write(f"{field_name}={self.env_value(value)}{newline}")

        print(f"Created profile: {os.path.abspath(profile_path)}")

        # Only now that the profile has a name: written first, config.txt named
        # profile.txt while the profile itself went to profile0.txt, and the
        # next run loaded nothing, or an older profile.txt in its place
        config_path = os.path.join(self.PROFILE_DIR, self.CONFIG_ENV)
        if not os.path.exists(config_path):
            with open(config_path, "w", encoding='utf-8') as config_file:
                config_file.write(f"LOAD_PROFILE={profile_name}\n" + self.CONFIG_TEMPLATE)
            print(f"Created {self.CONFIG_ENV}: {os.path.abspath(config_path)}")
        else:
            print(f"{self.CONFIG_ENV} already exists: {os.path.abspath(config_path)}. "
                  "No changes were made to it.")

    @staticmethod
    def env_value(value):
        """A profile value written so that dotenv reads back exactly it.

        Unquoted, " #" starts a comment, ${...} expands and edge spaces are
        dropped: "/tmp/Part #2.mp3" came back as "/tmp/Part". Such a value is
        single-quoted, which _load_profile reads literally, with its
        backslashes and quotes escaped; anything else is left as it was, so
        a profile stays as plain to edit as before.
        """
        text = "" if value is None else str(value)
        if text == text.strip() and not re.search(r"[#'\"$\n\r]", text):
            return text
        return "'" + text.replace("\\", "\\\\").replace("'", "\\'") + "'"

    def verify_file_writable(self, file_path):
        """Check if file path is writable (creates parent dirs if needed)."""
        try:
            if os.path.exists(file_path):
                return os.access(file_path, os.W_OK)

            parent_dir = os.path.dirname(file_path)
            if not parent_dir:
                parent_dir = '.'

            if not os.path.exists(parent_dir):
                try:
                    os.makedirs(parent_dir, exist_ok=True)
                except OSError:
                    return False

            return os.access(parent_dir, os.W_OK)
        except OSError:
            return False

    def get_free_disk_space(self, directory):
        """Get available disk space in bytes for the given directory."""
        try:
            if os.path.exists(directory):
                target_dir = directory
            else:
                target_dir = os.path.dirname(directory)
                if not target_dir:
                    target_dir = '.'

            if not os.path.exists(target_dir):
                target_dir = '.'

            return shutil.disk_usage(target_dir).free
        except (OSError, ValueError) as e:
            error(f"Error checking disk space: {str(e)}")
            return None


@dataclass
class SessionConfig:
    """Settings gathered for one transcription session (interactively or from a profile)."""
    url: str = None
    is_local_file: bool = False
    # Every pass this session makes, in order: (url, is_local_file,
    # refine_sources). The two fields above are whichever pass is running.
    sources: list = None
    # Transcripts already on disk to refine. Set means this pass downloads and
    # transcribes nothing: it is the refinement.
    refine_sources: list = None
    info: dict = None
    video_title: str = ""
    download_video: bool = False
    video_only: bool = False
    video_resolution: str = None
    video_audio_resolution: str = None
    video_rename: str = None
    video_path: str = None
    video_format: str = None
    video_only_resolution: str = None
    video_only_rename: str = None
    video_only_path: str = None
    video_only_format: str = None
    download_audio: bool = False
    audio_resolution: str = None
    audio_rename: str = None
    audio_path: str = None
    audio_format: str = None
    transcribe_audio_quality: str = None
    transcribe_audio: bool = True
    yt_transcript_raw: str = ""
    yt_transcript_languages: list = None
    yt_transcript_all: bool = False
    model_choice: str = ""
    model_name: str = ModelSize.BASE.value
    # The language spoken in the audio; None has Whisper detect it
    source_language: str = None
    target_language: str = ""
    target_languages: list = None
    use_en_model: bool = False
    ai_mode: AIEnhancementMode = None
    provider: Provider = None
    local_model: str = None
    prompts: list = None
    api_key: str = None
    transcript_rename: str = None
    transcript_path: str = None
    # Whether this session wants to name or rehouse anything, asked once at the
    # first deliverable rather than twice per deliverable. Not a profile field:
    # a profile carries the answers themselves.
    ask_placement: bool = None
    keep_transcript: bool = True
    used_fields: dict = field(default_factory=dict)
    # The filename each source of this batch writes under, casefolded, and the
    # source it belongs to: two sources with one title must not share one
    claimed_names: dict = field(default_factory=dict)
    # The folder this pass fetches merge-only video streams into, its own
    video_scratch: str = None
    # Every file this batch writes or has yet to read, by _file_key, and whose
    # it is: (source identity, deliverable). See _take_path.
    taken: dict = field(default_factory=dict)
    # The source the running pass is about, as _source_identity has it
    identity: object = None


# The deliverables that can be renamed and rehoused. Both questions are the
# same shape for all four, so one walk settles them for either configure path
# rather than eight blocks in each.
_PLACEMENTS = (
    ("video", "VIDEO", "the merged video", "VIDEO_DIR"),
    ("video_only", "VIDEO_ONLY", "the video-only file", "VIDEO_WITHOUT_AUDIO_DIR"),
    ("audio", "AUDIO", "the audio file", "AUDIO_DIR"),
    ("transcript", "TRANSCRIPT", "the transcript", "TRANSCRIPT_DIR"),
)


# Session-scoped environment keys used to carry state across "Run again?" repeats
_SESSION_ENV_KEYS = (
    "_REPEAT_INVOCATION", "_REPEAT_PROFILE_NAME", "_REPEAT_ASK_COUNT",
    "LAST_DOWNLOAD_VIDEO", "LAST_VIDEO_ONLY", "LAST_VIDEO_RESOLUTION",
    "LAST_VIDEO_AUDIO_RESOLUTION", "LAST_VIDEO_ONLY_RESOLUTION",
    "LAST_AUDIO_RESOLUTION", "LAST_TRANSCRIBE_AUDIO_QUALITY",
    "LAST_VIDEO_FORMAT", "LAST_VIDEO_ONLY_FORMAT", "LAST_AUDIO_FORMAT",
    "LAST_KEEP_TRANSCRIPT",
    "LAST_DOWNLOAD_AUDIO", "LAST_TRANSCRIBE_AUDIO", "LAST_MODEL_CHOICE",
    "LAST_SOURCE_LANGUAGE", "LAST_TARGET_LANGUAGE", "LAST_USE_EN_MODEL", "LAST_AI_REFINEMENT",
    "LAST_DOWNLOAD_YT_TRANSCRIPT", "LAST_PLACEMENT"
) + tuple(f"LAST_{prefix}_{suffix}"
          for _stem, prefix, _label, _dir in _PLACEMENTS
          for suffix in ("RENAME", "PATH"))


def _clear_session_env():
    """Remove all repeat-session environment variables."""
    for key in _SESSION_ENV_KEYS:
        os.environ.pop(key, None)


# A gap the question is asked for, rather than one taken as a stated answer
ASK = object()


@dataclass(frozen=True)
class Setting:
    """One profile field, and what a profile that leaves it out or blank means.

    A profile and a repeated interactive round are read through the same table
    and settled by the same code in _configure, so a field cannot come to mean
    one thing typed and another written down. Where the answers are kept is
    all that differs between them: see _Answers.
    """
    field: str
    # What a profile without the field at all means: ASK, or the answer it is
    # taken as. One written before the field existed does not carry it, and a
    # field that turns something on is off there, as it was then.
    absent: object = ASK
    # What the field left blank means, the same way
    blank: object = ASK
    # The field's pre-1.2 name, read when this one is not set
    legacy: str = None
    # Whether a value names one video's own file, which the next video of a
    # repeat would be written over
    one_video: bool = False


SETTINGS = {setting.field: setting for setting in (
    Setting("DOWNLOAD_VIDEO"),
    Setting("VIDEO_ONLY", absent="n", blank="n"),
    # The pre-1.2 VIDEO_ONLY, which replaced the merged video rather than
    # adding to it: see _configure
    Setting("NO_AUDIO_IN_VIDEO", absent="n", blank="n"),
    Setting("DOWNLOAD_AUDIO", absent="n", blank="n"),
    # A blank quality is the list of what the video offers, where the typed
    # question's own Enter leads: a profile asks for the list without it
    Setting("VIDEO_RESOLUTION", absent="", blank="", legacy="RESOLUTION"),
    Setting("VIDEO_AUDIO_RESOLUTION", absent="", blank=""),
    Setting("VIDEO_ONLY_RESOLUTION", absent="", blank=""),
    Setting("AUDIO_RESOLUTION", absent="", blank=""),
    Setting("TRANSCRIBE_AUDIO_QUALITY", absent="", blank=""),
    Setting("VIDEO_FORMAT"),
    Setting("VIDEO_ONLY_FORMAT"),
    Setting("AUDIO_FORMAT"),
    Setting("DOWNLOAD_YT_TRANSCRIPT", absent="n"),
    Setting("TRANSCRIBE_AUDIO"),
    Setting("MODEL_CHOICE"),
    # Whisper detects it, as it did before there was a field to say
    Setting("SOURCE_LANGUAGE", absent=YouTubeTranscriber.AUTO_LANGUAGE),
    Setting("TARGET_LANGUAGE"),
    Setting("USE_EN_MODEL", absent="n", blank="n"),
    Setting("AI_REFINEMENT", legacy="AI_ENHANCEMENT"),
    Setting("PROMPT"),
    Setting("KEEP_TRANSCRIPT"),
    # Not a profile field: a profile carries the placement answers themselves,
    # and this is the one question a session asks in their place
    Setting("PLACEMENT"),
) + tuple(
    # A placement left out keeps the default and one left blank asks, as 'y'
    # does, for the name or the folder itself
    Setting(f"{prefix}_{suffix}", absent="n", blank="", one_video=suffix == "RENAME")
    for _stem, prefix, _label, _dir in _PLACEMENTS for suffix in ("RENAME", "PATH"))}


class _Answers:
    """Where a session's answers are kept: a profile, or the last round's.

    What each setting means is decided once, by SETTINGS and _configure; this
    only reads them. `verb` and `origin` word the line reporting one.
    """
    verb = origin = None

    def lookup(self, setting):
        """(name, value) of the stored answer, the value None if there is none."""
        raise NotImplementedError

    def absent(self, setting):
        """What no stored answer at all means: ASK, or the answer it stands for."""
        return ASK

    def sources(self, transcriber):
        """The session's videos, files and transcripts."""
        return transcriber.prompt_for_sources()

    def report(self, name, shown):
        print(f"{self.verb} {name}: {shown} (from {self.origin})")

    def invalid(self, name, value):
        print(f"Invalid value for {name}: {value} (from {self.origin})")

    def ignored(self, field, why):
        """Say that a stored answer has no part in this run, and why."""
        _name, value = self.lookup(SETTINGS[field])
        value = (value or "").strip()
        # A no turns nothing on, so there is nothing for it to be ignored for
        if value and value.lower() not in YesNo.all_no_and_skip():
            print(f"Ignoring {field}={value} (from {self.origin}): {why}")


class _Profile(_Answers):
    """A profile's fields, which _load_profile put in the environment."""
    verb = "Loaded"

    def __init__(self, name):
        self.origin = name
        self.repeat = os.environ.get("_REPEAT_INVOCATION", "") == "1"

    def lookup(self, setting):
        name, value = setting.field, os.getenv(setting.field)
        if not value and setting.legacy and os.getenv(setting.legacy):
            # Read under its own name rather than copied into the new one,
            # which would leak into the next profile of a repeat
            name, value = setting.legacy, os.getenv(setting.legacy)
        stated = (value or "").strip().lower()
        if (setting.one_video and self.repeat and stated
                and stated not in YesNo.all_no_and_skip()):
            # A repeat takes a new URL and keeps the rest, but a name was for
            # the last round's video, and on this one it overwrote that file.
            # An interactive repeat drops it the same way.
            print(f"Ignoring {name}={value} on a repeat: it named the last round's file.")
            return name, "n"
        return name, value

    def absent(self, setting):
        return setting.absent

    def sources(self, transcriber):
        # A repeat is the same settings over a new job, so the profile's own
        # URL is not reused. Either way the answer is settled here rather than
        # part way through the run: this is the only prompt that takes a list,
        # or 's' to refine a transcript instead of fetching anything.
        named = "" if self.repeat else (os.getenv("URL") or "")
        entries = []
        if named and named != transcriber.URL_PLACEHOLDER:
            # Whether a video exists is settled by the metadata fetch in
            # _create_youtube_with_recovery, which can re-prompt
            entries = transcriber.source_entries(named, self.origin)
            if entries and all(entry[2] for entry in entries):
                self.report("URL", f"{sum(len(entry[2]) for entry in entries)} "
                                   "transcript(s) to refine")
        return entries or super().sources(transcriber)


class _Remembered(_Answers):
    """What the round a "Run again?" repeats was told, kept as LAST_* variables.

    Only the questions that round was asked are there, so a gap is asked.
    """
    verb, origin = "Using previous", "last session"

    def lookup(self, setting):
        # Only what a round remembers: a LAST_ name of anyone else's in the
        # environment answers nothing here
        key = f"LAST_{setting.field}"
        return setting.field, os.environ.get(key) if key in _SESSION_ENV_KEYS else None

    def ignored(self, field, why):
        # The last round's own answer, not a field anyone wrote: a local file
        # after a YouTube video has no stream to pick, and no need to say so
        pass


def _answer(answers, field, ask, valid=None, shown=None):
    """The raw answer to one setting: the stored one, or what a gap in it means.

    A stored answer `valid` refuses is called invalid and asked for again,
    rather than taken for a no. One it accepts is reported, as `shown` words
    it, so a run says what it was told.
    """
    setting = SETTINGS[field]
    name, raw = answers.lookup(setting)
    if raw is None:
        gap = answers.absent(setting)
    elif not raw.strip():
        gap = setting.blank
    elif valid is None or valid(raw.strip()):
        raw = raw.strip()
        answers.report(name, shown(raw) if shown else raw)
        return raw
    else:
        answers.invalid(name, raw)
        gap = ASK
    return ask() if gap is ASK else gap


def _yn(flag):
    """A yes/no as a profile writes it."""
    return "y" if flag else "n"


def _is_yes_no(answer):
    """Whether an answer is a yes or a no. 'skip' declines, as it does elsewhere."""
    return answer.lower() in YesNo.YES.value + YesNo.all_no_and_skip()


def _yes_no(transcriber, answers, field, question, default='n'):
    """Settle a yes/no setting, asking `question` if it has no answer."""
    answer = _answer(answers, field,
                     lambda: _yn(transcriber.get_yes_no_input(question, default=default)),
                     valid=_is_yes_no)
    return answer.lower() in YesNo.YES.value


def _ai_backend(transcriber, named=None):
    """The enhancement backend: (AIEnhancementMode, Provider, local_model_id).

    AI_PROVIDER names it. A blank one is answered by whoever the key on file
    belongs to, so only a run with neither has to ask. `named` overrides it for
    a pre-1.2 AI_ENHANCEMENT, which carried the backend in the same field -
    passed rather than exported, which would leak into the next profile of a
    repeat as NO_AUDIO_IN_VIDEO does.
    """
    named = (named or os.getenv("AI_PROVIDER") or "").strip()
    if named.lower() == 'local':
        return AIEnhancementMode.LOCAL, None, LocalModel.resolve_id()
    provider = Provider.from_string(named)
    if provider is None and named:
        print(f"Unknown AI_PROVIDER: {named}")
    if provider is None:
        provider = Provider.from_api_key(os.getenv("API_KEY"))
    if provider is not None:
        return AIEnhancementMode.API, provider, None
    return transcriber.get_ai_provider_input()


# The label of a prompt typed at the console rather than read from a file
INLINE_PROMPT = "(inline)"


def _select_prompts_interactively(transcriber):
    """Pick prompt files or type one inline. Returns [(text, label), ...]."""
    filenames, inline_prompt = transcriber.get_prompt_input()
    if filenames:
        loaded = ((transcriber.load_prompt_file(name), name) for name in filenames)
        return [(text, label) for text, label in loaded if text]
    if inline_prompt:
        return [(inline_prompt, INLINE_PROMPT)]
    return []


def _load_prompts(transcriber, raw):
    """Parse a PROMPT field into [(text, label), ...].

    Comma- or space-separated, each entry a file in Prompt/ or a path to one
    anywhere. Every prompt runs over every transcript, so two prompts on three
    transcripts is six files.
    """
    available = transcriber.list_available_prompts()

    def named(piece):
        return (piece in available or piece + transcriber.TXT_EXT in available
                or os.path.isfile(os.path.expanduser(piece)))

    loaded = []
    for entry in transcriber.split_entries(raw, named):
        label = next((c for c in (entry, entry + transcriber.TXT_EXT)
                      if c in available), entry)
        text = transcriber.load_prompt_file(label)
        if text:
            loaded.append((text, label))
    return loaded


def _resolve_api_key(provider):
    """Get the API key for `provider` from the environment or prompt for it."""
    api_key = provider.resolve_api_key()
    if not api_key:
        owner = Provider.from_api_key(os.getenv("API_KEY"))
        if owner:
            print(f"API_KEY is a {owner.key} key, so it is not sent to {provider.key}.")
        # Not echoed, and so not left in the scrollback or a terminal log
        api_key = getpass.getpass(f"Enter your {provider.key} API key: ").strip()
    if not api_key:
        print("No API key provided. Disabling AI enhancement.")
        return None
    return api_key


def _prompt_profile_selection(transcriber, profiles):
    """List profiles and return the chosen filename, or None if skipped."""
    print("Available profiles:")
    for i, profile in enumerate(profiles):
        print(f"{i+1}. {profile}")

    while True:
        profile_input = input(
            f"Select a profile (number, name or full path, default 1. {profiles[0]}, "
            f"or 'no' / 'n' / 'false' / 'f' / '0' / 'skip' / 's' to skip): "
        ).strip()
        lower_input = profile_input.lower()
        if profile_input == '' or lower_input == '1':
            return profiles[0]
        if _is_number(profile_input) and 1 <= int(profile_input) <= len(profiles):
            return profiles[int(profile_input) - 1]
        if profile_input in profiles:
            return profile_input
        if profile_input + transcriber.ENV_EXT in profiles:
            return profile_input + transcriber.ENV_EXT
        if lower_input in YesNo.all_no_and_skip():
            return None
        if os.path.isabs(os.path.expanduser(profile_input.strip('"'))):
            found = _profile_file(transcriber, profile_input)
            if found:
                return found[0]
            print(f"No profile found at {profile_input}.")
            continue
        print("Invalid profile selection.")


def _menu_default(options, default):
    """Which listed option Enter lands on, for the prompt to name: the best
    available, or the cheapest where the field asks for it. Shared, so the two
    menus cannot drift apart.
    """
    return options[-1 if default == Resolution.LOWEST.value else 0]


def _valid_entries(transcriber, text, resolve_one):
    """Walk a list answer entry by entry, keeping what resolves.

    A prompt takes the same comma- or space-separated lists the matching
    profile field does, and means the same thing by them: each entry is a
    deliverable of its own. An entry that does not resolve prints its own
    reason and is dropped, so only an answer with nothing usable left in it
    asks again.
    """
    values = []
    for piece in transcriber.split_entries(text):
        value = resolve_one(piece)
        if value and value not in values:
            values.append(value)
    return values


def _prompt_resolution_selection(transcriber, info, default=Resolution.HIGHEST.value):
    """List a video's available resolutions and let the user pick one.

    Ends the pass if the video has no video streams; the rest of a batch of
    sources still runs.
    """
    available_resolutions = transcriber.available_resolutions(info)

    if not available_resolutions:
        error("Error: no video streams found.")
        raise DownloadFailed("no video streams")

    fallback = _menu_default(available_resolutions, default)
    print("Available resolutions:")
    for i, res in enumerate(available_resolutions):
        print(f"{i+1}. {res}")

    def pick(entry):
        """One listed resolution, by number or by name."""
        if _is_number(entry) and 1 <= int(entry) <= len(available_resolutions):
            return available_resolutions[int(entry) - 1]
        if entry in available_resolutions:
            return entry
        if _is_number(entry) and entry + "p" in available_resolutions:
            return entry + "p"
        print("Invalid input. Please enter a valid number or resolution.")
        return None

    while True:
        user_input = input(
            f"Enter desired resolution (number or resolution, or several separated "
            f"by commas or spaces, default {fallback}): ").strip().lower()
        if not user_input:
            # The keyword, not the height it lands on here: recorded as 240p, a
            # profile made from this session fetched 240p of the next video
            return default
        chosen = _valid_entries(transcriber, user_input, pick)
        if chosen:
            return ",".join(chosen)


def _prompt_audio_selection(transcriber, info, default=Resolution.HIGHEST.value):
    """List a video's available audio tiers and let the user pick one.

    `default` is what Enter takes: transcription wants the cheapest stream,
    every other download wants the best.
    """
    available = transcriber.available_audio_qualities(info)
    if not available:
        print("No audio streams found. Using the best available.")
        return Resolution.HIGHEST.value
    fallback = _menu_default(available, default)

    print("Available audio resolutions:")
    for i, tier in enumerate(available):
        # The tier's own headline bitrate is not what gets downloaded, so show
        # the bitrate of the stream this choice actually selects
        bitrate = transcriber.selected_bitrate(tier, info)
        print(f"{i+1}. {tier}" + (f" ({bitrate}k)" if bitrate else ""))

    def pick(entry):
        """One listed tier, by number or name, or a bitrate in kbps."""
        if _is_number(entry) and 1 <= int(entry) <= len(available):
            return available[int(entry) - 1]
        if entry in available:
            return entry
        # The menu prints bitrates as "60k", so take that back as readily as 60
        if entry.endswith('k') and _is_number(entry[:-1]):
            entry = entry[:-1]
        # A number past the end of the list is a bitrate, not a menu choice
        if _is_number(entry):
            return entry
        print("Invalid input. Please enter a valid number or audio resolution.")
        return None

    while True:
        user_input = input(
            f"Enter desired audio resolution (number, name, or a bitrate in kbps, or "
            f"several separated by commas or spaces; default {fallback}): "
        ).strip().lower()
        if not user_input:
            return default
        chosen = _valid_entries(transcriber, user_input, pick)
        if chosen:
            return ",".join(chosen)


def _prompt_audio_resolution_input(transcriber, label):
    """Prompt for a desired audio resolution (tier name, kbps, or fetch keyword).

    An empty answer returns "", which the caller resolves by showing the list
    of what the video actually offers.
    """
    def one(entry):
        quality = Resolution.normalize(entry)
        # A tier name is checked against the video's own list later, which
        # re-prompts if the video does not offer it
        if quality in Resolution.values() or quality.isalnum():
            return quality
        print("Invalid input. Enter a tier name, a bitrate, highest, lowest, or fetch.")
        return None

    while True:
        answer = input(
            f"Enter the desired {label} (e.g., low, medium, 64, highest, lowest, or "
            f"several separated by commas or spaces), "
            f"or press Enter or type fetch to choose from a list: "
        ).strip()
        if not answer:
            return ""
        chosen = _valid_entries(transcriber, answer, one)
        if chosen:
            return ",".join(chosen)


def _prompt_resolution_input(transcriber, label):
    """Prompt for a desired resolution (name, number, or fetch keyword).

    An empty answer returns "", which the caller resolves by showing the list
    of what the video actually offers.
    """
    def one(entry):
        resolution = Resolution.normalize(entry)
        if resolution in Resolution.values():
            return resolution
        if resolution.endswith("p") and _is_number(resolution[:-1]) and int(resolution[:-1]) > 0:
            return resolution
        if _is_number(resolution):
            if int(resolution) > 0:
                return resolution + "p"
            print("Invalid resolution. Please enter a non-zero number.")
        else:
            print("Invalid resolution. Please enter a valid resolution "
                  "(e.g., 720p, 720, highest, lowest).")
        return None

    while True:
        answer = input(
            f"Enter the desired {label} (e.g., 720p, 720, highest, lowest, or several "
            f"separated by commas or spaces), "
            f"or press Enter or type fetch to choose from a list: "
        ).strip()
        if not answer:
            return ""
        chosen = _valid_entries(transcriber, answer, one)
        if chosen:
            return ",".join(chosen)


def _profile_file(transcriber, answer):
    """Find the profile an answer names. Returns (name, path), or None.

    A full path, or one under ~, is read where it is, and its name is that whole
    path: a repeat round looks the name up again, and a bare filename would
    send it to Profile/. Anything else is a file in Profile/. Either may leave
    off the .txt, and the quotes a copied Windows path arrives in are dropped.
    """
    given = os.path.expanduser(answer.strip().strip('"'))
    outside = os.path.isabs(given)
    base = given if outside else os.path.join(transcriber.PROFILE_DIR, given)
    for path in (base, base + transcriber.ENV_EXT):
        if os.path.isfile(path):
            name = (os.path.abspath(path) if outside
                    else os.path.relpath(path, transcriber.PROFILE_DIR))
            return name, path
    return None


def _select_profile(transcriber):
    """Decide whether to run from a profile, and load it if so.

    A repeat round reloads the profile it ran under; otherwise config.txt's
    LOAD_PROFILE answers, and failing that the user picks from a list.
    Returns (load_profile, profile_name).
    """
    repeat_invocation = os.environ.get("_REPEAT_INVOCATION", "") == "1"
    repeat_profile_name = os.environ.get("_REPEAT_PROFILE_NAME")

    # Repeat of a profile-driven session: reload the same profile
    if repeat_invocation and repeat_profile_name:
        found = _profile_file(transcriber, repeat_profile_name)
        if found:
            _load_profile(found[1])
            print(f"Loaded profile (repeat): {found[0]}")
            return True, found[0]
        print(f"Profile not found for repeat: {repeat_profile_name}. Falling back to selection.")
    # Repeat of an interactive session: stay interactive (LAST_* answers apply)
    elif repeat_invocation:
        return False, None

    config_env_path = os.path.join(transcriber.PROFILE_DIR, transcriber.CONFIG_ENV)

    if not os.path.exists(config_env_path):
        print(f"config.txt not found in the {transcriber.PROFILE_DIR} directory.")
        if not os.path.exists(transcriber.PROFILE_DIR):
            print("Switching to default/interactive mode.")
            return False, None

        profiles = transcriber.list_profiles()
        if not profiles:
            print("No profiles found. Switching to default/interactive mode.")
            return False, None

        print("Found existing profiles. Checking if you want to use one of them...")
        profile_name = _prompt_profile_selection(transcriber, profiles)
        if profile_name is None:
            print("Switching to default/interactive mode.")
            return False, None

        _load_profile(_profile_file(transcriber, profile_name)[1])
        print(f"Loaded profile: {profile_name}")
        return True, profile_name

    print(f"config.txt detected in the {transcriber.PROFILE_DIR} directory.")
    load_dotenv(dotenv_path=config_env_path, override=True)
    # LOAD_PROFILE as config.txt itself says it, not as a shell or an earlier
    # profile left it in the environment - and read by dotenv, as the rest of
    # the file is (a BOM included). Split on '=' by hand, the quotes of
    # LOAD_PROFILE='profile0.txt' and the comment of "profile0.txt  # lecture"
    # became part of the name, and no profile was found.
    load_profile_str = dotenv_values(config_env_path).get("LOAD_PROFILE")
    if load_profile_str is not None:
        load_profile_str = load_profile_str.strip()
        os.environ["LOAD_PROFILE"] = load_profile_str

    print(f"LOAD_PROFILE: {load_profile_str} (from config.txt)")
    lower_lp = load_profile_str.lower() if load_profile_str else ''

    # Explicit profile names (not simple yes/no) take precedence
    reserved = YesNo.YES.value + YesNo.NO.value + YesNo.SKIP.value + ('',)
    if load_profile_str and lower_lp not in reserved:
        found = _profile_file(transcriber, load_profile_str)
        if found:
            profile_name, profile_path = found
            print(f"Loading profile: {profile_name}")
            _load_profile(profile_path)
            print(f"Loaded profile: {profile_name}")
            return True, profile_name
        print(f"Profile not found: {load_profile_str}. Using interactive mode.")
        return False, None

    if lower_lp in YesNo.NO.value + YesNo.SKIP.value:
        print("Using default/interactive mode.")
        return False, None

    # LOAD_PROFILE is yes/blank: offer the available profiles
    profiles = transcriber.list_profiles()
    if not profiles:
        print("No profiles found. Switching to default/interactive mode.")
        return False, None

    profile_name = _prompt_profile_selection(transcriber, profiles)
    if profile_name is None:
        return False, None

    _load_profile(_profile_file(transcriber, profile_name)[1])
    print(f"Loaded profile: {profile_name}")
    return True, profile_name


def _single_quoted(line):
    """Whether one KEY=value line of a profile gives its value in single quotes."""
    text = re.sub(r'^export\s+', '', line.lstrip())
    _key, sep, value = text.partition('=')
    return bool(sep) and value.lstrip(' \t').startswith("'")


def _load_profile(path):
    """Load a profile into the environment, a single-quoted value taken literally.

    As load_dotenv(override=True) did, except that dotenv expands ${...} in
    every value however it is quoted: a saved PROMPT=/tmp/prompt-${COURSE}.txt
    came back naming another file. A value the app writes is single-quoted
    wherever dotenv would otherwise change it, and in single quotes it now
    means what it says, as in a shell; unquoted, ${HOME} still expands.
    """
    with open(path, encoding='utf-8') as handle:
        literal = {binding.key: _single_quoted(binding.original.string)
                   for binding in parse_stream(handle) if binding.key}
    raw = dotenv_values(path, interpolate=False)
    for key, value in dotenv_values(path).items():
        value = raw[key] if literal.get(key) else value
        if value is not None:
            os.environ[key] = value


def _prompt_format(transcriber, label, default, kind):
    """Ask for an output format, listing everything this ffmpeg can write."""
    choices = transcriber.ffmpeg_formats(kind)
    print(f"\nAvailable {label} formats ({len(choices)} from ffmpeg):")
    if choices:
        width = max(len(name) for name in choices) + 2
        per_row = max(1, 78 // width)
        for start in range(0, len(choices), per_row):
            print("  " + "".join(n.ljust(width) for n in choices[start:start + per_row]))
    print(f"  {transcriber.FORMAT_ORIGINAL} - keep what YouTube served, no re-encode")
    if kind == 'container':
        print("  (a muxer named after its standard writes its own extension: "
              "matroska gives .mkv)")

    while True:
        answer = input(
            f"Enter the {label} format, or several separated by commas or spaces for "
            f"one file each, or press Enter for {default} "
            f"(re-encodes if it is not already {default}): ").strip().lower()
        if not answer:
            return default
        chosen = _format_entries(transcriber, answer, default, kind)
        if chosen:
            return ",".join(chosen)
        print("Pick a name from the list above.")


def _writes_a_file(transcriber, name, kind):
    """Whether a container name names something with a file extension.

    ffmpeg's muxer list includes sinks like "null" that write no file, and the
    name chosen here becomes the extension of a deliverable.
    """
    return kind != 'container' or transcriber.format_extension(name) is not None


def _format_entries(transcriber, raw, default, kind):
    """The formats a list answer asks for that this ffmpeg can actually write.

    Several formats, separated by commas or spaces, are several files: the
    deliverable is written in each of them. One this ffmpeg cannot write is
    named and dropped; the caller decides what an empty result means.
    """
    def one(piece):
        # ".mp3" is how a person writes a format, and no name ffmpeg reports
        # starts with a dot, so there is nothing for this to shadow
        piece = piece.lstrip(".")
        if piece == transcriber.FORMAT_DEFAULT:
            piece = default
        if piece in (transcriber.FORMAT_ORIGINAL, default):
            return piece
        if piece not in transcriber.ffmpeg_formats(kind):
            print(f"ffmpeg cannot write '{piece}'.")
            return None
        if not _writes_a_file(transcriber, piece, kind):
            print(f"ffmpeg's '{piece}' does not write a media file.")
            return None
        return piece

    return _valid_entries(transcriber, (raw or "").lower(), one)


def _resolve_format(transcriber, raw, label, default, kind):
    """Settle one format field. Blank asks; DEFAULT and Enter mean `default`.

    Only an answer with nothing usable left in it asks again.
    """
    values = _format_entries(transcriber, raw, default, kind)
    if values:
        return ",".join(values)
    return _prompt_format(transcriber, label, default, kind)


def _writable_dir(transcriber, path):
    """True if `path` is a directory this run can write into, saying so if not."""
    if not transcriber.ensure_directory_exists(path):
        return False
    if not os.access(path, os.W_OK):
        error(f"Error: cannot write to {path}.")
        return False
    return True


def _prompt_rename(label):
    """Ask what to call a deliverable. Enter keeps the source's own title."""
    return input(f"Rename {label}? Enter a name, or press Enter to keep the "
                 f"title: ").strip()


def _resolve_rename(transcriber, raw, label):
    """The stem to write a deliverable under, or "" for the source's own title.

    A name in the field is used as it stands, so a profile carrying one still
    runs unattended; `y` and a blank answer ask for a name; `n` leaves the
    title alone, as Enter at that question does. SETTINGS says what a field
    that is not there means. The quality and format tags are still appended,
    so the several files one answer can produce stay distinct.
    """
    answer = raw.strip()
    # 's' and 'skip' decline as 'n' does, as they do everywhere else; taken as
    # a name, TRANSCRIPT_RENAME=skip called every transcript "skip"
    if answer.lower() in YesNo.all_no_and_skip():
        return ""
    if answer and answer.lower() not in YesNo.YES.value:
        return transcriber.sanitize_filename(answer)
    typed = _prompt_rename(label)
    return transcriber.sanitize_filename(typed) if typed else ""


def _prompt_path(transcriber, label, default_dir):
    """Ask where to write a deliverable. Enter keeps the project's own folder."""
    while True:
        answer = os.path.expanduser(
            input(f"Where should {label} be written? Enter an absolute path, "
                  f"or press Enter for {default_dir}: ").strip().strip('"'))
        if not answer:
            return ""
        if not os.path.isabs(answer):
            print("That is not an absolute path. Enter one, or press Enter to "
                  "keep the default.")
        elif _writable_dir(transcriber, answer):
            return answer


def _resolve_path(transcriber, raw, label, default_dir):
    """The directory to write a deliverable into, or "" for the project's own.

    A path in the field is used as it stands, so a profile carrying one still
    runs unattended; `y` and a blank answer ask for one; `n` keeps the default
    folder. Absolute is os.path.isabs, so a drive letter counts as readily as a
    leading slash. A path that cannot be written is refused here rather than
    after the download that would have filled it.
    """
    answer = raw.strip().strip('"')
    if answer.lower() in YesNo.all_no_and_skip():
        return ""
    if answer and answer.lower() not in YesNo.YES.value:
        # ~/Transcripts is absolute once expanded, as a source path already is
        answer = os.path.expanduser(answer)
        if os.path.isabs(answer) and _writable_dir(transcriber, answer):
            return answer
        error(f"Error: '{answer}' is not an absolute path this run can write to.")
        return _prompt_path(transcriber, label, default_dir)
    return _prompt_path(transcriber, label, default_dir)


def _placement_gate(transcriber, cfg, answers):
    """Whether this session wants to name or rehouse anything, asked once.

    Two questions for each of four deliverables is eight an ordinary run does
    not want. One says no to all of them, and the answer is remembered across
    a repeat like every other one. A profile never asks it: it carries the
    placement answers themselves, and a gap in them is not a question.
    """
    if cfg.ask_placement is None:
        cfg.ask_placement = _yes_no(
            transcriber, answers, "PLACEMENT",
            "Rename any of this run's files, or send them somewhere other "
            "than the project folder? (y/N): ")
    return cfg.ask_placement


def _several(cfg):
    """Whether this session has several sources, which one name or one opened
    window cannot serve."""
    return len(cfg.sources or []) > 1 or len(cfg.refine_sources or []) > 1


def _stem_for(cfg, filename_base, which):
    """The name a deliverable is written under. The tags still follow it, so
    the several files one answer can ask for stay distinct.

    One name cannot name several sources, and the second would land on the
    first: given a list, the name leads and each source's own title still
    tells them apart.
    """
    name = getattr(cfg, f"{which}_rename", "")
    if not name:
        return filename_base
    return f"{name} - {filename_base}" if _several(cfg) else name


def _dir_for(cfg, which, default):
    """Where a deliverable is written, the project's own folder by default."""
    return getattr(cfg, f"{which}_path", "") or default


def _settle_placement(transcriber, cfg, stem, answers):
    """Settle what one deliverable is called and where it is written."""
    _stem, prefix, label, dir_attr = next(p for p in _PLACEMENTS if p[0] == stem)
    default_dir = getattr(transcriber, dir_attr)

    def ask():
        # A blank answer asks for the name or folder itself, and a session
        # that declined the one question for all of them keeps the defaults
        return "" if _placement_gate(transcriber, cfg, answers) else "n"

    name = _resolve_rename(
        transcriber, _answer(answers, f"{prefix}_RENAME", ask), label)
    where = _resolve_path(
        transcriber, _answer(answers, f"{prefix}_PATH", ask), label, default_dir)
    setattr(cfg, f"{stem}_rename", name)
    setattr(cfg, f"{stem}_path", where)
    # "n" rather than blank: a profile written from this session must replay
    # unattended, and a blank field is a question
    cfg.used_fields[f"{prefix}_RENAME"] = name or "n"
    cfg.used_fields[f"{prefix}_PATH"] = where or "n"


def _yt_transcript_prompt():
    """Ask what YouTube transcripts to save, if any."""
    return input("Download YouTube's own transcript? (y/N, 'all', 'f' to list, "
                 "or languages like 'en,fr' or 'en fr'): ").strip()


def _prompt_yt_transcript_selection(transcriber, info):
    """List what the video offers and return the keys the user picks."""
    tracks = transcriber.caption_tracks(info)
    original = transcriber.original_caption(info)
    keys = sorted(tracks, key=lambda key: (key != original, key))
    print("Transcripts this video offers:")
    for i, key in enumerate(keys):
        mark = "  (original)" if key == original else ""
        print(f"  {i+1}. {key} - {tracks[key]}{mark}")
    while True:
        answer = input(f"Select transcripts (numbers or codes, separated by "
                       f"commas or spaces, "
                       f"'all', default 1. {keys[0]}): ").strip()
        if not answer:
            return [keys[0]]
        if answer.lower() in ('a', 'all'):
            return keys
        # Track keys never carry spaces, so either separator is unambiguous
        wanted = [part.lower() for part in transcriber.split_entries(answer)]
        chosen = [keys[int(part) - 1] if _is_number(part) and 1 <= int(part) <= len(keys)
                  else next((key for key in keys if key.lower() == part), None)
                  for part in wanted]
        if all(chosen):
            return chosen
        print("Invalid selection. Please try again.")


# The DOWNLOAD_YT_TRANSCRIPT entry that means whichever track a video was
# spoken in, which differs from one video of a list to the next
ORIGINAL_TRACK = "original"


def _track_for(tracks, want):
    """The caption track `want` names, or None: its whole key first, then a key
    in that language. 'en' is not an en-GB listed ahead of it, as
    caption_language already holds.

    A regional key a video does not have - en-US, picked from the first video
    of a list - is answered by another region of the language, en-GB, but
    never by another script: zh-Hans is not zh-Hant.
    """
    want = want.lower()
    exact = next((key for key in tracks if key.lower() == want), None)
    primary = want.split('-')[0]
    same = [key for key in tracks if key.split('-')[0].lower() == primary]
    if exact or want == primary:
        return exact or next(iter(same), None)

    def script(tag):
        return next((part for part in tag.lower().split('-')[1:] if len(part) == 4), None)

    return next((key for key in same if script(key) == script(want)), None)


def _resolve_track(transcriber, info, tracks, want):
    """The track one DOWNLOAD_YT_TRANSCRIPT entry names in this video, or None."""
    if want.strip().lower() == ORIGINAL_TRACK:
        return transcriber.original_caption(info)
    return _track_for(tracks, want)


def _settle_yt_transcripts(transcriber, cfg, raw):
    """Turn a DOWNLOAD_YT_TRANSCRIPT answer into the list of tracks to save."""
    cfg.yt_transcript_raw = raw
    answer = raw.strip().lower()
    # 'f' asks for the listing this prompt advertises, and YesNo.NO spells
    # "false" that way too, so the request is read before the refusals are.
    # A bare 'no' still means no; Norwegian is reachable as 'nb', 'nn', or
    # through the listing.
    listing = answer in (Resolution.FETCH.value, 'f')
    if not listing and (not answer or answer in YesNo.all_no_and_skip()):
        return
    _ensure_metadata(transcriber, cfg)
    if cfg.is_local_file or cfg.info is None:
        return
    tracks = transcriber.caption_tracks(cfg.info)
    if not tracks:
        print("This video publishes no transcript of its own.")
        videos = sum(1 for entry in cfg.sources or [] if not entry[1] and not entry[2])
        if videos > 1 and not listing:
            # The videos after it may, and each is matched against its own
            # tracks as it is saved, so the answer stands for them. Dropped, a
            # list led by a video without captions saved none for any video.
            cfg.yt_transcript_all = answer in ('a', 'all')
            cfg.yt_transcript_languages = transcriber.split_entries(raw)
        return
    if answer in ('a', 'all'):
        cfg.yt_transcript_languages = list(tracks)
        cfg.yt_transcript_all = True
        return
    if answer in YesNo.YES.value:
        original = transcriber.original_caption(cfg.info)
        if original:
            cfg.yt_transcript_languages = [original]
            return
        print("Cannot tell which language this video was spoken in.")
    elif not listing:
        # An explicit language is taken as read: the user asked for that text,
        # whoever or whatever produced it
        chosen, missing = [], []
        for want in transcriber.split_entries(raw):
            found = _resolve_track(transcriber, cfg.info, tracks, want)
            (chosen if found else missing).append(want.lower())
        if missing:
            print(f"This video has no transcript in: {', '.join(missing)}")
        videos = sum(1 for entry in cfg.sources or [] if not entry[1] and not entry[2])
        if chosen or videos > 1:
            # The codes as asked, not the tracks this video answered them with:
            # each video is matched against its own tracks when it is saved.
            # Kept as its en-US, 'en' missed the next video's en-GB, and a
            # language this video lacked was never asked of the videos after it
            cfg.yt_transcript_languages = list(dict.fromkeys(
                chosen + missing if videos > 1 else chosen))
            return
    picked = _prompt_yt_transcript_selection(transcriber, cfg.info)
    if len(picked) > 1 and set(picked) >= set(tracks):
        # Everything on offer is 'all', and the next video's all is its own
        cfg.yt_transcript_all, cfg.yt_transcript_raw = True, "all"
        cfg.yt_transcript_languages = list(tracks)
        return
    # What was picked, not 'f': a profile saved from this would list and wait on
    # every replay, where the quality menus record their concrete picks. The
    # original is recorded as the original, not as this video's key for it:
    # Enter on the listing took the English original, and a Japanese video
    # after it was then given the English machine translation of itself.
    original = transcriber.original_caption(cfg.info)
    cfg.yt_transcript_languages = [ORIGINAL_TRACK if key == original else key
                                   for key in picked]
    cfg.yt_transcript_raw = ",".join(cfg.yt_transcript_languages)


def _settle_target_languages(transcriber, cfg, raw):
    """Fix which languages to transcribe into, re-asking if none survive."""
    codes, unknown = transcriber.normalize_languages(raw)
    if unknown:
        print(f"Not a supported language, so skipped: {', '.join(unknown)}")
    if not codes:
        codes, _unknown = transcriber.normalize_languages(
            transcriber.get_target_language_input())
    cfg.target_languages = codes
    cfg.target_language = codes[0]


def _settle_source_language(transcriber, cfg, raw):
    """Fix the language spoken in the audio: a code, or None to detect it.

    Separate from the target: Whisper takes the spoken language as a hint for
    what it hears, and the target was being handed to it as one.
    """
    answer = (raw or "").strip().lower()
    while answer != transcriber.AUTO_LANGUAGE:
        code = transcriber.normalize_language(answer) if answer else None
        if code:
            cfg.source_language = code
            break
        if answer:
            print(f"Not a supported language: {raw}.")
        answer = raw = transcriber.get_source_language_input()
    else:
        cfg.source_language = None
    cfg.used_fields["SOURCE_LANGUAGE"] = cfg.source_language or transcriber.AUTO_LANGUAGE


def _offers_en_model(transcriber, cfg, model_enum):
    """Whether an English-only model could serve: a size that has one, speech
    that is or may be English, and nothing asked for but English or the
    language spoken."""
    return (model_enum in ModelSize.standard_models()
            and cfg.source_language in (None, transcriber.DEFAULT_LANGUAGE)
            and set(cfg.target_languages or [cfg.target_language])
            <= {transcriber.DEFAULT_LANGUAGE, transcriber.AUTO_LANGUAGE})


def _ensure_metadata(transcriber, cfg):
    """Load cfg.info if it is not already there.

    A quality menu lists what one specific video offers, so it cannot be shown
    until the metadata is in hand. A video given up on here is dropped from the
    list and the next source answers instead: the prompt says it gives up on
    this one, and the batch handler that carries on past a failed source does
    not run until the settings are gathered.
    """
    while not cfg.is_local_file and cfg.info is None:
        try:
            _create_youtube_with_recovery(transcriber, cfg)
        except DownloadFailed:
            _drop_current_source(cfg)


def _drop_current_source(cfg):
    """Give up on the source the settings are being asked about, for the next.

    Raises DownloadFailed if it was the last: then there is no run to set up.
    """
    cfg.sources = [entry for entry in cfg.sources or [] if entry[0] != cfg.url]
    if not cfg.sources:
        raise DownloadFailed(f"{cfg.url} cannot be used")
    _settle_sources(cfg)
    # Its metadata goes with it, or the next video is asked about this one's
    cfg.info, cfg.video_title = None, ""


def _as_height(value):
    """A bare number is a height: 720 and 720p are the same answer."""
    return f"{value}p" if _is_number(value) and int(value) > 0 else value


def _resolve_quality(transcriber, cfg, raw, picker, default=Resolution.HIGHEST.value,
                     normalize=None):
    """Settle one quality field on a concrete answer.

    Blank and "fetch" both mean "show me what this video has", so an unset
    field asks rather than silently taking a default. Keywords and explicit
    values pass through; whether the video actually offers an explicit value is
    settled in _run_one, which re-prompts if it does not. A local file has
    nothing to list, so a blank there means "as it already is".

    Several values, separated by commas or spaces, are several deliverables:
    the field is returned as the list it was given, for _run_one to walk.
    """
    values = []
    for piece in transcriber.split_entries(raw or ""):
        value = Resolution.normalize(piece)
        if normalize:
            value = normalize(value)
        if value and value != Resolution.FETCH.value and value not in values:
            values.append(value)
    if values:
        return ",".join(values)
    while True:
        _ensure_metadata(transcriber, cfg)
        if cfg.is_local_file or cfg.info is None:
            return default
        try:
            return picker(transcriber, cfg.info, default)
        except DownloadFailed:
            # A video with nothing to pick - no video streams - ends its own
            # pass, not the batch: raised here, while the settings were still
            # being asked, it reached main() and the videos after it never ran
            _drop_current_source(cfg)


def _deliverable_asks(is_local):
    """The three deliverable questions, worded for a re-encode or a download.

    A local source is cut with ffmpeg rather than fetched, but it is the same
    three files and the same fields settle them.
    """
    if is_local:
        return ("Re-encode the video? (y/N): ",
                "Save a video-only file, with no audio track? (y/N): ",
                "Save the audio as its own file? (y/N): ")
    return ("Download video? (y/N): ",
            "Download a video-only file, with no audio track? (y/N): ",
            "Download audio? (y/N): ")


def _settle_sources(cfg):
    """Point cfg at the entry the video-specific questions are asked about.

    Resolutions, audio tiers and caption tracks are a menu of what one video
    has, and the answer applies to every entry. A remote entry is the one worth
    asking about; with no media at all cfg.url is left unset, which is what a
    refine-only session looks like.
    """
    media = [entry for entry in cfg.sources if not entry[2]]
    remote = [entry for entry in media if not entry[1]]
    cfg.url, cfg.is_local_file = (remote or media)[0][:2] if media else (None, True)
    if len(cfg.sources) > 1 or not media:
        # One video is a template to point at the next one, but a list is the
        # point of the session: record it so the profile replays the same list
        cfg.used_fields["URL"] = ",".join(
            ",".join(entry[2]) if entry[2] else entry[0] for entry in cfg.sources)


def _settle_quality(transcriber, cfg, answers, field, label, picker,
                    default=Resolution.HIGHEST.value):
    """Settle one quality field: stated, typed, or picked from the video's list."""
    video = picker is _prompt_resolution_selection
    typed = _prompt_resolution_input if video else _prompt_audio_resolution_input
    normalize = _as_height if video else None

    def shown(raw):
        value = Resolution.normalize(raw)
        return normalize(value) if normalize else value

    raw = _answer(answers, field, lambda: typed(transcriber, label), shown=shown)
    value = _resolve_quality(transcriber, cfg, raw, picker, default, normalize)
    cfg.used_fields[field] = value
    return value


def _settle_format(transcriber, cfg, answers, field, label, default, kind):
    """Settle one format field, asking from ffmpeg's own list if it has none."""
    raw = _answer(answers, field, lambda: _prompt_format(transcriber, label, default, kind))
    value = _resolve_format(transcriber, raw, label, default, kind)
    cfg.used_fields[field] = value
    return value


def _configure(transcriber, answers):
    """Gather the session's settings, from `answers` where it has them.

    Every setting is settled here, once, however the session was set up: a
    profile and a repeated interactive round differ only in where they keep
    their answers and in what a gap in them means, which SETTINGS says.
    """
    cfg = SessionConfig(used_fields=transcriber.DEFAULT_FIELDS.copy())
    used_fields = cfg.used_fields

    cfg.sources = answers.sources(transcriber)
    _settle_sources(cfg)
    refining = any(entry[2] for entry in cfg.sources)
    if not cfg.url:
        # Every entry is a refinement, so there is no media to ask about
        cfg.transcribe_audio = False
        used_fields["TRANSCRIBE_AUDIO"] = "n"
        return _settle_refinement(transcriber, cfg, answers, assumed=True)

    asks = _deliverable_asks(cfg.is_local_file)
    cfg.download_video = _yes_no(transcriber, answers, "DOWNLOAD_VIDEO", asks[0])
    if (answers.lookup(SETTINGS["NO_AUDIO_IN_VIDEO"])[1]
            and not answers.lookup(SETTINGS["VIDEO_ONLY"])[1]):
        # The pre-1.2 field replaced the merged download rather than adding
        # to it, so honour that meaning instead of producing both files
        cfg.video_only = _yes_no(transcriber, answers, "NO_AUDIO_IN_VIDEO", asks[1])
        cfg.download_video = cfg.download_video and not cfg.video_only
    else:
        cfg.video_only = _yes_no(transcriber, answers, "VIDEO_ONLY", asks[1])
    used_fields["DOWNLOAD_VIDEO"] = _yn(cfg.download_video)
    used_fields["VIDEO_ONLY"] = _yn(cfg.video_only)

    if cfg.download_video:
        cfg.video_resolution = _settle_quality(
            transcriber, cfg, answers, "VIDEO_RESOLUTION", "video resolution",
            _prompt_resolution_selection)
        cfg.video_audio_resolution = _settle_quality(
            transcriber, cfg, answers, "VIDEO_AUDIO_RESOLUTION",
            "audio resolution for the video", _prompt_audio_selection)
        cfg.video_format = _settle_format(
            transcriber, cfg, answers, "VIDEO_FORMAT", "video container",
            transcriber.DEFAULT_VIDEO_FORMAT, "container")
        _settle_placement(transcriber, cfg, "video", answers)

    if cfg.video_only:
        cfg.video_only_resolution = _settle_quality(
            transcriber, cfg, answers, "VIDEO_ONLY_RESOLUTION", "video-only resolution",
            _prompt_resolution_selection)
        cfg.video_only_format = _settle_format(
            transcriber, cfg, answers, "VIDEO_ONLY_FORMAT", "video-only codec",
            transcriber.DEFAULT_VIDEO_ONLY_CODEC, "video")
        _settle_placement(transcriber, cfg, "video_only", answers)

    cfg.download_audio = _yes_no(transcriber, answers, "DOWNLOAD_AUDIO", asks[2])
    used_fields["DOWNLOAD_AUDIO"] = _yn(cfg.download_audio)

    if cfg.download_audio:
        cfg.audio_resolution = _settle_quality(
            transcriber, cfg, answers, "AUDIO_RESOLUTION", "audio resolution",
            _prompt_audio_selection)
        cfg.audio_format = _settle_format(
            transcriber, cfg, answers, "AUDIO_FORMAT", "audio",
            transcriber.DEFAULT_AUDIO_FORMAT, "container")
        _settle_placement(transcriber, cfg, "audio", answers)

    if not cfg.is_local_file:
        _settle_yt_transcripts(transcriber, cfg, _answer(
            answers, "DOWNLOAD_YT_TRANSCRIPT", _yt_transcript_prompt))
        used_fields["DOWNLOAD_YT_TRANSCRIPT"] = cfg.yt_transcript_raw

    cfg.transcribe_audio = _yes_no(transcriber, answers, "TRANSCRIBE_AUDIO",
                                   "Transcribe the audio? (Y/n): ", default='y')
    used_fields["TRANSCRIBE_AUDIO"] = _yn(cfg.transcribe_audio)
    if not cfg.transcribe_audio:
        # Downloaded transcripts are enhanced whether or not anything is
        # being transcribed here
        return _settle_refinement(transcriber, cfg, answers, assumed=refining)

    # The quality is only settled when nothing else will already have put
    # audio on disk, which transcription reuses rather than fetching twice
    if cfg.download_audio or cfg.download_video:
        moot = ("the audio already being downloaded is transcribed, rather "
                "than fetching a second copy of it.")
    elif cfg.is_local_file:
        # Which the profile alone cannot explain, the reason being the URL
        # rather than a neighbouring field turned off
        moot = "a local file is read as it is, there being no stream to pick."
    else:
        moot = None
    if moot:
        # Never asked here, but a hand-written field would otherwise be
        # dropped without a word
        answers.ignored("TRANSCRIBE_AUDIO_QUALITY", moot)
    else:
        # Speech recognition, not listening: the cheapest stream reads the same
        cfg.transcribe_audio_quality = _settle_quality(
            transcriber, cfg, answers, "TRANSCRIBE_AUDIO_QUALITY",
            "audio quality for transcription", _prompt_audio_selection,
            default=Resolution.LOWEST.value)

    cfg.model_choice = _answer(answers, "MODEL_CHOICE", transcriber.get_model_choice_input,
                               valid=lambda raw: raw.lower() in ModelSize.valid_choices())
    model_enum = ModelSize.from_choice(cfg.model_choice)
    cfg.model_name = model_enum.value
    used_fields["MODEL_CHOICE"] = cfg.model_name

    _settle_source_language(transcriber, cfg, _answer(
        answers, "SOURCE_LANGUAGE", transcriber.get_source_language_input))
    _settle_target_languages(transcriber, cfg, _answer(
        answers, "TARGET_LANGUAGE", transcriber.get_target_language_input))
    used_fields["TARGET_LANGUAGE"] = ",".join(cfg.target_languages)

    if _offers_en_model(transcriber, cfg, model_enum):
        cfg.use_en_model = _yes_no(
            transcriber, answers, "USE_EN_MODEL",
            "Use English-specific model? "
            "(Recommended only if the video is originally in English) (y/N): ")
        used_fields["USE_EN_MODEL"] = _yn(cfg.use_en_model)
    else:
        # An English-only model hears English and nothing else: run on speech
        # the profile says is Japanese, it wrote English-ish nonsense and saved
        # it as the Japanese transcript
        answers.ignored("USE_EN_MODEL", "the English-only model does not serve this "
                                        "model size, SOURCE_LANGUAGE or TARGET_LANGUAGE.")

    return _settle_refinement(transcriber, cfg, answers, assumed=refining)


def _configure_interactive(transcriber):
    """Gather the session's settings by asking, reusing what a repeat's last
    round was told."""
    return _configure(transcriber, _Remembered())


def _configure_from_profile(transcriber, profile_name):
    """Gather the session's settings from the loaded profile, asking for what
    it leaves open and what it gets wrong."""
    return _configure(transcriber, _Profile(profile_name))


def _settle_refinement(transcriber, cfg, answers, assumed=False):
    """Settle enhancement: whether, which backend, which prompts, keep the raw.

    `assumed` is a refine-only run, where naming transcripts already answered
    the question AI_REFINEMENT asks. Returns cfg.
    """
    if not (assumed or cfg.transcribe_audio or cfg.yt_transcript_languages):
        # Nothing is transcribed or downloaded for it to refine
        return cfg
    used_fields = cfg.used_fields

    # AI_REFINEMENT also named the backend before 1.2 - a provider key, 'local',
    # or a model name - so anything that is not yes or no is both the yes and
    # the answer to which, rather than an "invalid value" that stops the run
    name, stated = answers.lookup(SETTINGS["AI_REFINEMENT"])
    stated = (stated or "").strip()
    backend = stated if stated and not _is_yes_no(stated) else None
    if backend:
        answers.report(name, backend)
    if assumed or backend or _yes_no(transcriber, answers, "AI_REFINEMENT",
                                     "Refine the transcript with AI? (y/N): "):
        if backend and backend.lower() != "local" and Provider.from_string(backend) is None:
            # Neither 'local' nor a provider was a local model's name or id,
            # and not an AI_PROVIDER typo to fall back from onto the key's vendor
            named = backend.lower() in LocalModel.all_model_values()
            cfg.ai_mode, cfg.provider = AIEnhancementMode.LOCAL, None
            cfg.local_model = LocalModel.get_by_name(backend).hf_model_id if named else backend
        else:
            cfg.ai_mode, cfg.provider, cfg.local_model = _ai_backend(transcriber, backend)

    if cfg.ai_mode is not None:
        named = _answer(answers, "PROMPT", lambda: "")
        cfg.prompts = _load_prompts(transcriber, named) if named else []
        if not cfg.prompts:
            cfg.prompts = _select_prompts_interactively(transcriber)
        if not cfg.prompts:
            cfg.ai_mode = None
        else:
            used_fields["PROMPT"] = ",".join(label for _text, label in cfg.prompts)

    if cfg.ai_mode == AIEnhancementMode.API:
        cfg.api_key = _resolve_api_key(cfg.provider)
        if cfg.api_key is None:
            cfg.ai_mode = None

    # Where the finished transcript lands, asked after the prompt that makes it
    # and before the question about the copy left behind
    _settle_placement(transcriber, cfg, "transcript", answers)

    # Nothing to keep when enhancement is not running, so the field is ignored
    if cfg.ai_mode is not None:
        cfg.keep_transcript = _yes_no(
            transcriber, answers, "KEEP_TRANSCRIPT",
            "Keep the unrefined transcript in Transcript/Raw/? "
            "n keeps only the refined one (Y/n): ", default='y')
        used_fields["KEEP_TRANSCRIPT"] = _yn(cfg.keep_transcript)
        # Which backend, not just that there was one: AI_REFINEMENT carries a
        # bare y, so without this a profile made from a local session replays
        # against whatever API key happens to be on file, and bills for it
        used_fields["AI_PROVIDER"] = cfg.provider.key if cfg.provider else "local"
        if cfg.local_model:
            used_fields["MODEL"] = cfg.local_model

    used_fields["AI_REFINEMENT"] = _yn(cfg.ai_mode is not None)
    return cfg


def _create_youtube_with_recovery(transcriber, cfg):
    """Fetch video metadata for cfg.url, re-prompting on failure.

    Sets cfg.info and cfg.video_title on success. May flip cfg.is_local_file
    to True (leaving cfg.info unset) if the user switches to a local file.
    """
    retry_prompt = ("\nEnter a different YouTube video URL, video ID, or local file path, "
                    "or press Enter to give up on this one: ")
    while True:
        try:
            # extract_info fails for private, removed and region-blocked
            # videos, so this doubles as the availability check
            info = transcriber.fetch_video_info(cfg.url)
            cfg.video_title = info['title']
            cfg.info = info
            return
        except (yt_dlp.utils.DownloadError, KeyError, TypeError,
                OSError, ValueError) as e:
            error(f"\nError with URL '{cfg.url}': {str(e)}")
            print("The URL appears to be invalid or the video is unavailable.")
            # A replacement is the point of the prompt, but it must be possible
            # to decline one: a list of sources would otherwise park here on the
            # unavailable video rather than going on to the ones after it
            replacement = transcriber.prompt_for_source(retry_prompt, allow_skip=True)
            if replacement is None:
                raise DownloadFailed(f"{cfg.url} is unavailable") from e
            dead = cfg.url
            cfg.url, cfg.is_local_file = replacement
            # The list is what _run_pipeline hands each pass, so a replacement
            # settled here - which a quality menu can do, before the run has
            # begun - has to reach it, or the dead URL is asked about again
            cfg.sources = [(cfg.url, cfg.is_local_file, entry[2])
                           if entry[0] == dead else entry
                           for entry in cfg.sources or []]
            if cfg.is_local_file:
                return


def _enhance_and_save(transcriber, cfg, text, stem, enhance=True, open_after=True,
                      source=None):
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
    outputs, replaced_by = [], None
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
        in_place = bool(source) and _same_file(path, source)
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


def _holds_words(transcriber, path, text):
    """Whether the file at `path` says what `text` says, word for word."""
    try:
        with open(path, 'rb') as handle:
            return transcriber.decode_text(handle.read()).split() == text.split()
    except (OSError, UnicodeDecodeError):
        return False


def _same_file(one, other):
    """Whether two paths name one file, which need not exist yet."""
    try:
        return os.path.samefile(one, other)
    except OSError:
        def canonical(path):
            return os.path.normcase(os.path.realpath(os.path.expanduser(path)))
        return canonical(one) == canonical(other)


def _settle_source(transcriber, cfg, source, raw_path, outputs, replaced_by):
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


def _retire_source(transcriber, cfg, source, raw):
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


def _refine_transcripts(transcriber, cfg):
    """Refine transcripts already on disk. Nothing is downloaded or transcribed.

    _enhance_and_save already writes the untouched text to Transcript/Raw/ when
    KEEP_TRANSCRIPT says so, so a source in Transcript/ is a duplicate of it by
    the time the refinement lands, and is retired there rather than here.
    """
    if cfg.ai_mode is None or not cfg.prompts:
        print("No refinement backend or prompt, so there is nothing to refine.")
        return
    for source in cfg.refine_sources:
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


def _save_yt_transcripts(transcriber, cfg, filename_base):
    """Save YouTube's own transcripts to Transcript/.

    Enhancement is charged per transcript, so asking for every language YouTube
    knows enhances only the one the video was spoken in; a list the user wrote
    out is enhanced in full, because they named each one.
    """
    original = transcriber.original_caption(cfg.info)
    # The answer was settled on the first video of a list, and each video after
    # it has tracks of its own: 'all' is this one's, 'y' this one's original,
    # and a named track the same name here. Settled once, a Japanese video
    # after an English one got the English translation and never its original.
    tracks = transcriber.caption_tracks(cfg.info)
    if cfg.yt_transcript_all:
        keys = list(tracks)
    elif cfg.yt_transcript_raw.strip().lower() in YesNo.YES.value:
        keys = [original] if original else []
        if not original:
            print("Cannot tell which language this video was spoken in, so its "
                  "transcript is skipped.")
    else:
        keys = []
        for want in cfg.yt_transcript_languages:
            key = _resolve_track(transcriber, cfg.info, tracks, want)
            if not key:
                print(f"This video has no transcript in: {want}")
            elif key not in keys:
                # 'en' and 'en-US' can name one track, fetched and billed once
                keys.append(key)
    enhancing = []
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
        text = transcriber.fetch_caption_text(cfg.info, key)
        if not text:
            print(f"Nothing came back for the {key} transcript.")
            continue
        # The language the video was spoken in is the transcript; the rest say
        # in their name that they are something else
        stem = filename_base if key == original else f"{filename_base} [{key}]"
        _enhance_and_save(transcriber, cfg, text, stem, enhance=key in enhancing,
                          open_after=False)


def _local_quality(source, quality, reader, unit):
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


def _container_of(transcriber, target_format, kind):
    """The extension convert_media writes a format into.

    Which is what says whether two formats need telling apart in the filename:
    h264 and mpeg4 both land in .mp4, mp3 and flac do not.
    """
    if kind == 'video':
        return transcriber.CODEC_CONTAINERS.get(target_format,
                                                transcriber.FALLBACK_CONTAINER)
    return transcriber.format_extension(target_format) or target_format


def _shared_container(transcriber, chosen, kind):
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


def _local_deliverables(transcriber, cfg, filename_base):
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

    def each(raw, fallback=None):
        """The values a field asks for. One deliverable per combination."""
        return transcriber.split_entries(raw or "") or [fallback]

    def container_for(chosen, default):
        """FORMAT_ORIGINAL keeps the source's own container: there is no
        YouTube stream to keep instead."""
        if chosen == transcriber.FORMAT_ORIGINAL:
            return os.path.splitext(source)[1].lstrip('.') or default
        return chosen or default

    def make(output_dir, stem, target_format, kind, height=None, bitrate=None):
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

    def height_for(quality):
        return _local_quality(source, quality, transcriber.source_height, 'p')

    def bitrate_for(quality):
        return _local_quality(source, quality, transcriber.source_bitrate, 'k')

    def tag(height=None, bitrate=None, codec=None):
        return transcriber.quality_tag(f"{height}p" if height else None,
                                       f"{bitrate}k" if bitrate else None, codec)

    if cfg.video_only and transcriber.stream_codec(source, 'video') is None:
        print("Skipping the video-only file: this one has no video stream.")
    elif cfg.video_only:
        codecs = each(cfg.video_only_format, transcriber.DEFAULT_VIDEO_ONLY_CODEC)
        share = _shared_container(transcriber, codecs, 'video')
        done = set()
        for res in each(cfg.video_only_resolution):
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
        for res in each(cfg.video_resolution):
            height = height_for(res)
            for rate in each(cfg.video_audio_resolution):
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
        for rate in each(cfg.audio_resolution):
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


def _run_pipeline(transcriber, cfg):
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
              f"{len(cfg.prompts)} prompt(s)).")

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


def _claim_name(cfg, base, identity, video_id=None):
    """The name one source's files are written under, its own across the batch.

    Two videos can share a title, two titles can clean to one name, and two
    local files in different folders share a basename: downloads overwrite, so
    the second source's files replaced the first's. The video's ID tells a
    video apart, and a number anything else. The same source named twice keeps
    the one name - that is a repeat, not a collision.
    """
    candidates = itertools.chain(
        [base], [f"{base} [{video_id}]"] if video_id else [],
        (f"{base} ({n})" for n in itertools.count(2)))
    for candidate in candidates:
        # Casefolded: Windows and macOS file systems do not tell "A" from "a"
        if cfg.claimed_names.setdefault(candidate.casefold(), identity) == identity:
            return candidate
    return base  # unreachable: the numbered names never run out


def _source_identity(cfg):
    """What one source is, however it was written: a video by its ID, a file by
    where it really is."""
    if cfg.is_local_file:
        return _path_identity(cfg.url)
    return (cfg.info or {}).get('id') or cfg.url


def _path_identity(path):
    """A file source's identity: where it really is, as the file system compares."""
    return os.path.normcase(os.path.realpath(os.path.expanduser(path)))


def _file_key(path):
    """Where a path puts its file, to tell two paths to one file apart.

    The folder is resolved through symlinks, and the name compared without
    regard to case, which Windows and macOS do not tell apart. Treating two
    names that differ only in case as one file costs a suffix at worst.
    """
    folder, name = os.path.split(os.path.abspath(os.path.expanduser(path)))
    return os.path.normcase(os.path.realpath(folder)), name.casefold()


# The deliverable a batch source holds its own path as, until it is read
_SOURCE = "source"


def _reserve_sources(cfg):
    """Hold every file source of the batch, so no pass writes over one still to come.

    A refinement named onto the next queued transcript, or a Whisper transcript
    onto a queued one of the same name, replaced it before it was read.
    """
    cfg.taken = {}
    for url, is_local, refine in cfg.sources or []:
        for path in refine or ([url] if is_local else []):
            cfg.taken[_file_key(path)] = (_path_identity(path), _SOURCE)


def _take_path(cfg, path, what, discriminator=None):
    """The path one deliverable is written to: `path`, unless the batch has
    given it to another.

    The one place every deliverable's name is settled, so that none is written
    over another: the merged video and the audio in one folder and container,
    two outputs whose folders are one through a symlink, a refinement and the
    transcript queued after it. The same deliverable of the same source keeps
    its path - a source named twice is a repeat - and a source's own outputs
    may land on the source itself. Otherwise `discriminator` is tried, then a
    number.
    """
    owner = (cfg.identity, what)
    stem, ext = os.path.splitext(path)
    variants = itertools.chain(
        [path], [f"{stem}{discriminator}{ext}"] if discriminator else [],
        (f"{stem} ({n}){ext}" for n in itertools.count(2)))
    for candidate in variants:
        key = _file_key(candidate)
        holder = cfg.taken.get(key)
        if holder in (None, owner, (cfg.identity, _SOURCE)):
            cfg.taken[key] = owner
            return candidate
    return path  # unreachable: the numbered names never run out


def _clear_video_scratch(transcriber, cfg):
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


def _run_one(transcriber, cfg):
    """Execute one pass: download streams, transcribe, enhance, and save."""
    if cfg.refine_sources:
        _refine_transcripts(transcriber, cfg)
        return

    if not cfg.is_local_file and cfg.info is None:
        _create_youtube_with_recovery(transcriber, cfg)

    if cfg.is_local_file:
        cfg.video_title = os.path.splitext(os.path.basename(cfg.url))[0]

    cfg.identity = _source_identity(cfg)
    filename_base = _claim_name(cfg, transcriber.sanitize_filename(cfg.video_title),
                                cfg.identity,
                                None if cfg.is_local_file else (cfg.info or {}).get('id'))
    display_source = os.path.abspath(cfg.url) if cfg.is_local_file else cfg.url
    print(f"\nProcessing: {display_source}...")
    stem_for = functools.partial(_stem_for, cfg, filename_base)
    dir_for = functools.partial(_dir_for, cfg)

    audio_path = None
    # Audio fetched only to merge or to transcribe, rather than to keep
    temp_audio_paths = []
    transcription_failed = False

    # Three independent downloads, each with its own quality: the merged file,
    # a muxer-free copy of the raw video stream, and a standalone audio file
    remote = not cfg.is_local_file

    def settle_video(quality):
        """Check a resolution against this video, and resolve "lowest"."""
        available = transcriber.available_resolutions(cfg.info)
        if not available:
            # Nothing to pick from, and the keywords would sail past the check
            # below into a selector that cannot match. The picker says so.
            return _prompt_resolution_selection(transcriber, cfg.info)
        if quality not in (Resolution.HIGHEST.value, Resolution.LOWEST.value) \
                and quality not in available:
            print("Requested resolution not found, left null, or invalid.")
            quality = _prompt_resolution_selection(transcriber, cfg.info)
        # Name the file after what is downloaded, not the word asked for, which
        # also puts "lowest" on the same footing as the bottom of the menu
        if quality == Resolution.LOWEST.value and available:
            quality = available[-1]
        # ...and the top of the menu on the same footing as "highest", which
        # carries no tag because it is the default
        if available and quality == available[0]:
            quality = Resolution.HIGHEST.value
        return quality

    def settle_audio(quality, default=Resolution.HIGHEST.value):
        """Check an audio quality against this video.

        bestaudio[abr<=N] degrades silently rather than failing, so this is the
        only thing that reports a request the video cannot satisfy. `default`
        is the field's own, so a re-prompt for transcription still offers the
        cheapest stream rather than the largest.
        """
        if (quality and quality not in (Resolution.HIGHEST.value, Resolution.LOWEST.value)
                and not _is_number(str(quality))
                and quality not in transcriber.available_audio_qualities(cfg.info)):
            print("Requested audio resolution not found, left null, or invalid.")
            quality = _prompt_audio_selection(transcriber, cfg.info, default)
        return quality

    def audio_label_for(quality):
        # selected_bitrate caches per video, so the repeated lookups behind a
        # label cost a dict read
        return transcriber.audio_bitrate_label(quality, cfg.info)

    def audio_marks(quality):
        """What an audio stream's name says of it: its bitrate, and its format
        id too where another stream this pass fetches rounds to that bitrate.
        Named by the bitrate alone, the second download landed on the first
        and both deliverables were then made from one of them.
        """
        label, stream = audio_label_for(quality), audio_stream_for(quality)
        shared = any(audio_label_for(other) == label and audio_stream_for(other) != stream
                     for other in saved_audio + merge_audio + [speech_audio] if other)
        return (label, stream) if shared else (label,)

    def audio_stem_for(quality):
        return stem_for("audio") + transcriber.quality_tag(*audio_marks(quality))

    def audio_stream_for(quality):
        """Which stream a request lands on, so that two wordings for one stream
        are fetched once. "medium" and "highest" name the same audio on a video
        whose best tier is medium, and their selectors do not look alike.
        Falls back to the selector if yt-dlp's resolver cannot be run.
        """
        selector = transcriber.audio_format(quality, cfg.info)
        chosen = transcriber.selected_format(selector, cfg.info) or {}
        return chosen.get('format_id') or selector

    def qualities(raw, settle):
        """The resolved, deduplicated qualities a field asks for.

        Several, separated by commas or spaces, are several deliverables. Two
        wordings can still land on one quality - "medium" and "highest" on a
        video whose best tier is medium - and that is one of them, not two.
        """
        seen = []
        for piece in transcriber.split_entries(raw or "") or [raw]:
            value = settle(piece)
            # A re-prompt can be answered with a list of its own, which is as
            # many deliverables as if the field had named them. Each is settled
            # in its own right, so the top tier still goes untagged either way.
            parts = transcriber.split_entries(value or "")
            for one in (map(settle, parts) if len(parts) > 1 else [value]):
                if one not in seen:
                    seen.append(one)
        return seen

    def formats(raw, default):
        """The formats a field asks for; the deliverable is written in each."""
        return list(dict.fromkeys(transcriber.split_entries(raw or "") or [raw or default]))

    video_res = (qualities(cfg.video_resolution, settle_video)
                 if cfg.download_video and remote else [])
    only_res = (qualities(cfg.video_only_resolution, settle_video)
                if cfg.video_only and remote else [])
    merge_audio = (qualities(cfg.video_audio_resolution, settle_audio)
                   if cfg.download_video and remote else [])
    saved_audio = (qualities(cfg.audio_resolution, settle_audio)
                   if cfg.download_audio and remote else [])
    # One copy of the audio is transcribed however many deliverables there are,
    # so a list in this field names that copy rather than several of them
    speech_raw = (transcriber.split_entries(cfg.transcribe_audio_quality or "")
                  or [cfg.transcribe_audio_quality])[0]
    speech_audio = (qualities(speech_raw,
                              lambda q: settle_audio(q, Resolution.LOWEST.value))[0]
                    if cfg.transcribe_audio and remote else None)

    if cfg.is_local_file:
        _local_deliverables(transcriber, cfg, filename_base)

    # One download per distinct stream, shared by every deliverable that wants
    # it, and kept as downloaded until the last of them has been written
    video_only_files = {}
    video_files = {}
    audio_files = {}
    merge_files = {}
    saved_audio_files = []

    for res in only_res:
        print(f"Downloading video stream ({res} without audio)...")
        downloaded = transcriber.download_format(
            cfg.url, transcriber.video_format(res),
            dir_for("video_only", transcriber.VIDEO_WITHOUT_AUDIO_DIR),
            stem_for("video_only") + transcriber.quality_tag(res) + " - Video Only")
        video_only_files[res] = transcriber.strip_audio(downloaded)
        print(f"Video downloaded to {os.path.abspath(video_only_files[res])}")

    for res in video_res:
        if res in video_only_files:
            # The merge wants the very stream just saved, so use that copy
            # rather than fetching it a second time
            video_files[res] = video_only_files[res]
            continue
        if cfg.video_scratch is None:
            # A folder of this pass's own inside Video/Temp, so that clearing
            # it afterwards touches nothing this pass did not put there
            scratch_root = os.path.join(transcriber.VIDEO_DIR, transcriber.TEMP_DIR)
            os.makedirs(scratch_root, exist_ok=True)
            cfg.video_scratch = tempfile.mkdtemp(prefix="merge-", dir=scratch_root)
        video_files[res] = transcriber.download_format(
            cfg.url, transcriber.video_format(res), cfg.video_scratch,
            stem_for("video") + transcriber.quality_tag(res))
        print(f"Video downloaded to {video_files[res]}")
    if not cfg.download_video and not cfg.video_only:
        print("Skipping video download...")

    # Compare the streams, not the words: "low", "lowest" and "60" are one
    # request when they land on one stream, and so are "medium" and "highest"
    # on a video whose best tier is medium
    for tier in saved_audio:
        stream = audio_stream_for(tier)
        if stream in audio_files:
            continue
        audio_files[stream], _ = transcriber.download_audio_stream(
            cfg.info, audio_stem_for(tier), is_temp=False,
            format_selector=transcriber.audio_format(tier, cfg.info),
            keep_in=dir_for("audio", transcriber.AUDIO_DIR))
        saved_audio_files.append((tier, audio_files[stream]))

    for tier in merge_audio:
        stream = audio_stream_for(tier)
        if stream not in audio_files:
            audio_files[stream], _ = transcriber.download_audio_stream(
                cfg.info, audio_stem_for(tier), is_temp=True,
                format_selector=transcriber.audio_format(tier, cfg.info))
            temp_audio_paths.append(audio_files[stream])
        merge_files[tier] = audio_files[stream]

    audio_path = next(iter(audio_files.values()), None)

    # Two containers that write one extension would write one filename, so the
    # format joins the name - the same rule convert_all applies to the others
    merge_formats = formats(cfg.video_format, transcriber.DEFAULT_VIDEO_FORMAT)
    merge_shares = _shared_container(transcriber, merge_formats, "container")
    for res in video_res:
        for tier in merge_audio:
            for chosen in merge_formats:
                container = (os.path.splitext(video_files[res])[1].lstrip('.')
                             if chosen == transcriber.FORMAT_ORIGINAL
                             else transcriber.format_extension(chosen) or chosen)
                for fmt in (chosen if merge_shares else None, chosen):
                    output = os.path.join(dir_for("video", transcriber.VIDEO_DIR),
                                          stem_for("video") + transcriber.quality_tag(
                                              res, *audio_marks(tier), fmt)
                                          + f".{container}")
                    # The audio saved to the same folder in the same container
                    # can have this very name: ffmpeg refused to write over its
                    # own input, and the failed merge's cleanup deleted that
                    # input. The format tag tells the merge apart.
                    if not (os.path.exists(output) and any(
                            os.path.samefile(output, audio) for audio in audio_files.values()
                            if os.path.exists(audio))):
                        break
                # Taken before the audio converted after it can take it
                output = _take_path(cfg, output, ("merge", res, tier, chosen))
                # Every merge reads the streams as downloaded, so the scratch
                # copies are cleared once below rather than by the first of them
                if transcriber.combine_audio_video(video_files[res], merge_files[tier],
                                                   output) is None:
                    error(f"Error: the merged video was not created at {output}")

    _clear_video_scratch(transcriber, cfg)

    # A list can mix a video with a local file, and DOWNLOAD_YT_TRANSCRIPT was
    # answered for the video: this pass has no metadata to read captions out of
    if cfg.yt_transcript_languages and not cfg.is_local_file:
        _save_yt_transcripts(transcriber, cfg, stem_for("transcript"))

    if cfg.transcribe_audio:
        speech_file = None

        def speech_audio_file():
            """The audio to recognise, fetched once however many languages want it."""
            nonlocal speech_file, audio_path
            if speech_file is not None:
                return speech_file
            if not cfg.is_local_file:
                if audio_path is None:
                    # Any audio already on disk is reused: fetching a second copy
                    # to save bandwidth would defeat the point
                    audio_path, _ = transcriber.download_audio_stream(
                        cfg.info, audio_stem_for(speech_audio), is_temp=True,
                        format_selector=transcriber.audio_format(speech_audio, cfg.info))
                    temp_audio_paths.append(audio_path)
                speech_file = audio_path
            elif transcriber.is_valid_media_file(cfg.url):
                # Whisper reads a video container as readily as an audio one,
                # both being an ffmpeg call to it
                speech_file = cfg.url
            else:
                # is_local_file is only ever set after this same check passed,
                # so getting here means the file went away mid-run
                error(f"Error: {cfg.url} is no longer a readable media file.")
                raise DownloadFailed(f"{cfg.url} is no longer readable")
            return speech_file

        wanted = cfg.target_languages or [cfg.target_language]
        written = set()
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
                speech_audio_file(), model_name, target, cfg.source_language
            )

            if not transcribed_text:
                # Don't pay to "enhance" a failure, and don't save one as a transcript
                transcription_failed = True
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
                                     f"{stem_for('transcript')} [Whisper {language}]"):
                # Nothing was saved, so the audio is still needed for a retry
                transcription_failed = True
    else:
        print("Skipping transcription.")

    # Re-encode the standalone files last, so the merge and the transcription
    # both worked from the stream as downloaded rather than a second-generation
    # copy of it
    def convert_all(made, raw, default, kind, folder, stem_for):
        """Write every deliverable in every format asked for.

        The download is kept until the last format has been written, and the
        format joins the filename only where it must - two codecs can share one
        container, and would otherwise share one name.
        """
        chosen = formats(raw, default) if made else []
        share = _shared_container(transcriber, chosen, kind)
        for quality, source in made:
            written = []
            for fmt in chosen:
                if fmt == transcriber.FORMAT_ORIGINAL:
                    written.append(source)
                    continue
                stem = stem_for(quality, fmt if share else None)
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

    convert_all(list(video_only_files.items()), cfg.video_only_format,
                transcriber.DEFAULT_VIDEO_ONLY_CODEC, "video",
                dir_for("video_only", transcriber.VIDEO_WITHOUT_AUDIO_DIR),
                lambda res, fmt: (stem_for("video_only")
                                  + transcriber.quality_tag(res, fmt)
                                  + " - Video Only"))
    convert_all(saved_audio_files, cfg.audio_format, transcriber.DEFAULT_AUDIO_FORMAT,
                "audio", dir_for("audio", transcriber.AUDIO_DIR),
                lambda tier, fmt: stem_for("audio") + transcriber.quality_tag(
                    *audio_marks(tier), fmt))

    # The audio fetched only to merge or to transcribe, kept when transcription
    # failed so that the retryable step does not cost a second download
    for path in dict.fromkeys(temp_audio_paths):
        if not os.path.exists(path):
            continue
        if transcription_failed:
            print(f"Keeping downloaded audio for retry: {os.path.abspath(path)}")
            continue
        try:
            os.remove(path)
        except OSError as e:
            # Windows can still hold the file open just after transcription
            print(f"Note: could not delete the temp audio: {str(e)}")
        else:
            print(f"Deleted audio residual in {path}")

    temp_audio_path = os.path.join(transcriber.AUDIO_DIR, transcriber.TEMP_DIR)
    try:
        if os.path.exists(temp_audio_path) and not os.listdir(temp_audio_path):
            os.rmdir(temp_audio_path)
    except OSError:
        # The directory is recreated on demand, so leaving the empty one behind
        # is not worth reporting
        pass

    print("Tasks complete.")


def _save_inline_prompts(transcriber, cfg):
    """Give each prompt typed at the console a file, so a profile can name it.

    PROMPT holds names, and a typed prompt has none: the profile said
    PROMPT=(inline), which named nothing, and replaying it asked for a prompt
    again. The text goes into Prompt/ as prompt<N>.txt, which tags its output
    " - Refined" as the typed prompt did; one already saved there is reused.
    """
    if not any(label == INLINE_PROMPT for _text, label in cfg.prompts or []):
        return
    folders = transcriber.prompt_dirs() + [transcriber.PROMPT_DIR]
    labels = []
    for text, label in cfg.prompts:
        if label == INLINE_PROMPT:
            label = next((name for name in transcriber.list_available_prompts()
                          if transcriber.load_prompt_file(name) == text.strip()), None)
        if label is None:
            label = next(name for name in (f"prompt{n}{transcriber.TXT_EXT}"
                                           for n in itertools.count())
                         if not any(os.path.exists(os.path.join(folder, name))
                                    for folder in folders))
            path = os.path.join(transcriber.PROMPT_DIR, label)
            try:
                os.makedirs(transcriber.PROMPT_DIR, exist_ok=True)
                transcriber.write_text_atomically(path, text.strip() + "\n")
            except OSError as e:
                error(f"Error: could not save the typed prompt to {path}: {str(e)}")
                continue
            print(f"Saved the typed prompt to {os.path.abspath(path)}")
        labels.append(label)
    cfg.used_fields["PROMPT"] = ",".join(labels)


def _ask_repeat(transcriber):
    """Ask the user whether to run again; the default flips to yes after the first repeat."""
    repeat_ask_count = int(os.environ.get("_REPEAT_ASK_COUNT", "0"))
    default_repeat = 'y' if repeat_ask_count > 0 else 'n'
    prompt_text = ("Run again? (Y/n): " if default_repeat == 'y'
                   else "Run again? Hit Enter to repeat (y/N): ")
    repeat = transcriber.get_yes_no_input(prompt_text, default=default_repeat)
    os.environ["_REPEAT_ASK_COUNT"] = str(repeat_ask_count + 1)
    return repeat, ("y" if repeat else "n")


def _finish_session(transcriber, cfg, load_profile, profile_name):
    """Offer to save a profile, then say whether to run again.

    A repeat leaves this session's answers in the environment for the next
    round to pick up; main() is what goes round.
    """
    did_something_useful = (cfg.download_audio or cfg.download_video
                            or cfg.video_only or cfg.transcribe_audio
                            or bool(cfg.yt_transcript_languages)
                            or any(e[2] for e in cfg.sources or []))
    is_repeat = os.environ.get("_REPEAT_INVOCATION", "") == "1"

    repeat = False
    repeat_value = ""
    try:
        repeat_setting = (os.getenv("REPEAT", "") or "") if load_profile else ""
        if load_profile and repeat_setting.lower() in YesNo.YES.value:
            repeat, repeat_value = True, "y"
        elif load_profile and repeat_setting.lower() in YesNo.NO.value:
            repeat, repeat_value = False, "n"
        else:
            # Blank or invalid REPEAT setting, or interactive mode -> ask the user
            repeat, repeat_value = _ask_repeat(transcriber)
    except Exception:
        repeat, repeat_value = False, ""

    cfg.used_fields["REPEAT"] = repeat_value

    if not load_profile and did_something_useful and not is_repeat:
        if transcriber.get_yes_no_input(
                "Do you want to create a profile from this session? (y/N): ", default='n'):
            _save_inline_prompts(transcriber, cfg)
            transcriber.create_profile(cfg.used_fields)

    # The work is done either way, and main() decides what happens next
    transcriber.release_caches()

    if repeat:
        if not load_profile:
            # Remember this session's answers so the repeat run can reuse them -
            # only the ones it was asked. A refine-only round asks nothing about
            # media, and a local file nothing about YouTube's transcripts; an "n"
            # remembered for a question never put answered it in the next round,
            # and a YouTube URL given then was neither downloaded nor transcribed
            fields, media = cfg.used_fields, bool(cfg.url)
            remembered = {
                "LAST_DOWNLOAD_VIDEO": media and fields.get("DOWNLOAD_VIDEO"),
                "LAST_VIDEO_ONLY": media and fields.get("VIDEO_ONLY"),
                "LAST_DOWNLOAD_AUDIO": media and fields.get("DOWNLOAD_AUDIO"),
                "LAST_TRANSCRIBE_AUDIO": media and fields.get("TRANSCRIBE_AUDIO"),
                "LAST_DOWNLOAD_YT_TRANSCRIPT": (media and not cfg.is_local_file
                                                and cfg.yt_transcript_raw),
                # The model, not the answer: Enter for base is "", and a blank
                # answer asked again every round
                "LAST_MODEL_CHOICE": media and cfg.transcribe_audio and cfg.model_name,
                "LAST_SOURCE_LANGUAGE": (media and cfg.transcribe_audio
                                         and fields.get("SOURCE_LANGUAGE")),
                "LAST_TARGET_LANGUAGE": (cfg.transcribe_audio
                                         and ",".join(cfg.target_languages or [])),
                "LAST_USE_EN_MODEL": fields.get("USE_EN_MODEL"),
                "LAST_KEEP_TRANSCRIPT": fields.get("KEEP_TRANSCRIPT"),
                "LAST_AI_REFINEMENT": media and fields.get("AI_REFINEMENT"),
                "LAST_PLACEMENT": (None if cfg.ask_placement is None
                                   else "y" if cfg.ask_placement else "n"),
            }
            for key, value in remembered.items():
                if value:
                    os.environ[key] = value
                else:
                    os.environ.pop(key, None)
            # Where files go carries over, but not what they are called: a name
            # was for that video, and on the next it overwrites that video's file
            for _stem, prefix, _label, _dir in _PLACEMENTS:
                os.environ.pop(f"LAST_{prefix}_RENAME", None)
                path = getattr(cfg, f"{_stem}_path", "")
                if path:
                    os.environ[f"LAST_{prefix}_PATH"] = path
                else:
                    os.environ.pop(f"LAST_{prefix}_PATH", None)
            # Storing "" would make the next run skip the prompt, then filter on ""
            for key, value in (
                    ("LAST_VIDEO_RESOLUTION", cfg.video_resolution),
                    ("LAST_VIDEO_AUDIO_RESOLUTION", cfg.video_audio_resolution),
                    ("LAST_VIDEO_ONLY_RESOLUTION", cfg.video_only_resolution),
                    ("LAST_AUDIO_RESOLUTION", cfg.audio_resolution),
                    ("LAST_TRANSCRIBE_AUDIO_QUALITY",
                     cfg.transcribe_audio_quality),
                    ("LAST_VIDEO_FORMAT", cfg.video_format),
                    ("LAST_VIDEO_ONLY_FORMAT", cfg.video_only_format),
                    ("LAST_AUDIO_FORMAT", cfg.audio_format)):
                if value:
                    os.environ[key] = value
                else:
                    os.environ.pop(key, None)
        os.environ["_REPEAT_INVOCATION"] = "1"
        if load_profile and profile_name:
            os.environ["_REPEAT_PROFILE_NAME"] = profile_name
        print("Repeating session as requested...")
    return repeat


def main():
    """Run sessions until the user stops asking for another."""
    # Redirected to a file on Windows, stdout is cp1252: a Japanese title, path
    # or transcript raised mid-run, before the transcript it printed was saved
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    transcriber = YouTubeTranscriber()

    if not transcriber.check_dependencies():
        print("Missing required dependencies. Please install them and try again.")
        sys.exit(1)

    # The only place the working directories are made: constructing a
    # transcriber reads and writes nothing
    for directory in (transcriber.AUDIO_DIR, transcriber.VIDEO_DIR,
                      transcriber.TRANSCRIPT_DIR, transcriber.VIDEO_WITHOUT_AUDIO_DIR,
                      transcriber.PROMPT_DIR):
        if not transcriber.ensure_directory_exists(directory):
            error(f"Error: Cannot create required directory {directory}")
            print("Please check permissions and try again.")
            sys.exit(1)
    # An installed copy's first run: its sample profiles, where profiles live
    transcriber.seed_sample_profiles()

    try:
        # "Run again?" comes round here rather than re-entering main(), so a
        # long batch is one frame however many rounds it runs
        while True:
            # How far this round got, for the exit code if input runs out
            stage = "asking"
            try:
                load_profile, profile_name = _select_profile(transcriber)
                if load_profile:
                    cfg = _configure_from_profile(transcriber, profile_name)
                else:
                    cfg = _configure_interactive(transcriber)

                stage = "running"
                _run_pipeline(transcriber, cfg)
                stage = "finished"
                if not _finish_session(transcriber, cfg, load_profile, profile_name):
                    return
            except (DownloadFailed, yt_dlp.utils.DownloadError):
                # Already reported where it happened, and the only source is
                # gone: one exit code for the run rather than one per step.
                # yt-dlp prints its own error before raising.
                sys.exit(1)
            except EOFError:
                # Input ran out: an unattended run was asked something nobody
                # is there to answer. That ended in a traceback. After a round
                # that finished - the offer to save a profile, or a REPEAT=y
                # profile asking for the next round's sources - the work asked
                # for is done, and it ends as a success.
                repeating = os.environ.get("_REPEAT_INVOCATION", "") == "1"
                done = stage == "finished" or (stage == "asking" and repeating)
                print("\nNo more input." + ("" if done else " The run is incomplete."))
                sys.exit(0 if done else 1)
    finally:
        # Whatever ends the session, its answers must not reach the next one
        _clear_session_env()


if __name__ == "__main__":
    main()

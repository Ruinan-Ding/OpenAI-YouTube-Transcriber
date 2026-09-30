"""The words everything else is written in, and the helpers they all use."""

import os
import subprocess
import sys
from enum import Enum

# How ffmpeg and ffprobe are run. Their output is read as UTF-8: text=True
# decoded it in the locale's encoding - cp1252 on Windows - and ffmpeg writes
# UTF-8, so a Japanese filename in its log raised UnicodeDecodeError and ended
# the batch. Only ever printed or parsed for ASCII, so a byte that does not
# decode is replaced rather than fatal. And they are given no stdin: ffmpeg
# reads its keyboard commands there as it works - q stops it - so it took the
# first character of the answer waiting after it, and a path piped to the next
# round arrived without its leading slash.
FFMPEG_RUN = {'stdin': subprocess.DEVNULL, 'encoding': 'utf-8', 'errors': 'replace'}


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


def _same_file(one, other):
    """Whether two paths name one file, which need not exist yet."""
    try:
        return os.path.samefile(one, other)
    except OSError:
        def canonical(path):
            return os.path.normcase(os.path.realpath(os.path.expanduser(path)))
        return canonical(one) == canonical(other)

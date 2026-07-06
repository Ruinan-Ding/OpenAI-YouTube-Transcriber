# Downloads audio/video from YouTube and transcribes it using OpenAI's Whisper
# Author: Ruinan Ding

# Run with: python OpenAIYouTubeTranscriber.py

#########################################
## IMPORTS
#########################################

# Standard library imports
import importlib.util
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from enum import Enum
from urllib.parse import urlparse

# Third-party imports
import whisper
import moviepy
from langdetect import detect, LangDetectException
from pytubefix import YouTube
from pytubefix.exceptions import RegexMatchError, VideoUnavailable, VideoPrivate, VideoRegionBlocked
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type

#########################################
## ENUMS
#########################################

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
    def large_models(cls):
        return [cls.LARGE_V1, cls.LARGE_V2, cls.LARGE_V3]

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
        return cls.BASE  # Default to BASE if not found

    @classmethod
    def from_choice(cls, choice):
        """Resolve a menu number, model name, or blank string to a ModelSize."""
        if not choice:
            return cls.BASE
        if choice in cls.choice_numbers():
            return cls.get_model_by_number(choice)
        return cls.get_model_by_name(choice)


class Provider(Enum):
    """Cloud providers for AI transcript enhancement.

    OPENAI and OPENROUTER speak the OpenAI-compatible chat completions API
    (as does any OpenAI-compatible endpoint reached by overriding the
    provider's *_BASE_URL env var, e.g. Groq, Together, DeepSeek, Azure).
    ANTHROPIC uses Anthropic's native Messages API.
    """
    OPENAI = ('openai', 'OPENAI_API_KEY', 'OPENAI_BASE_URL', 'OPENAI_MODEL', None, 'gpt-4o-mini')
    OPENROUTER = ('openrouter', 'OPENROUTER_API_KEY', 'OPENROUTER_BASE_URL', 'OPENROUTER_MODEL',
                  'https://openrouter.ai/api/v1', 'openai/gpt-4o-mini')
    ANTHROPIC = ('anthropic', 'ANTHROPIC_API_KEY', 'ANTHROPIC_BASE_URL', 'ANTHROPIC_MODEL', None, 'claude-opus-4-8')

    def __init__(self, key, api_key_env, base_url_env, model_env, default_base_url, default_model):
        self.key = key
        self.api_key_env = api_key_env
        self.base_url_env = base_url_env
        self.model_env = model_env
        self.default_base_url = default_base_url
        self.default_model = default_model

    @classmethod
    def default(cls):
        """The provider used when the user just answers 'y' with no provider name."""
        return cls.OPENROUTER

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
        """Base URL for this provider: env override, else the built-in default (None = SDK default)."""
        return os.getenv(self.base_url_env) or self.default_base_url

    def resolve_model(self):
        """Model ID for this provider: env override, else the built-in default."""
        return os.getenv(self.model_env) or self.default_model


class AIEnhancementMode(Enum):
    """Modes for AI-powered transcript enhancement."""
    API = ('y', 'yes', 'true', 't', '1') + tuple(p.key for p in Provider)
    LOCAL = ('local',)
    DISABLED = ('n', 'no', 'false', 'f', '0')

    @classmethod
    def from_string(cls, value):
        """Parse a string into an AIEnhancementMode. Returns None if invalid."""
        if not value:
            return None
        lower = value.lower().strip()
        for mode in cls:
            if lower in mode.value:
                return mode
        # Check if it matches a known local model name
        if lower in LocalModel.all_model_values():
            return cls.LOCAL
        return None


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
    def get_by_number(cls, number):
        """Look up a LocalModel by 1-based index."""
        models = list(cls)
        idx = int(number) - 1
        if 0 <= idx < len(models):
            return models[idx]
        return cls.default()

#########################################
## TRANSCRIBER CLASS
#########################################

class YouTubeTranscriber:
    """Handles YouTube downloads, Whisper transcription, and AI enhancement."""

    # Data directories
    DATA_DIR = "OpenAIYouTubeTranscriber"
    AUDIO_DIR = os.path.join(DATA_DIR, "Audio")
    TEMP_DIR = "Temp"
    VIDEO_DIR = os.path.join(DATA_DIR, "Video")
    TRANSCRIPT_DIR = os.path.join(DATA_DIR, "Transcript")
    VIDEO_WITHOUT_AUDIO_DIR = os.path.join(DATA_DIR, "VideoWithoutAudio")
    PROFILE_DIR = os.path.join(DATA_DIR, "Profile")
    PROMPT_DIR = os.path.join(DATA_DIR, "Prompt")
    DEFAULT_PROMPT = "prompt.txt"
    MP3_EXT = ".mp3"
    MP4_EXT = ".mp4"
    TXT_EXT = ".txt"
    PROFILE_PREFIX = "profile"
    ENV_EXT = ".txt"
    CONFIG_ENV = f"config{ENV_EXT}"
    PROFILE_NAME_TEMPLATE = f"{PROFILE_PREFIX}{{}}{ENV_EXT}"
    DEFAULT_PROFILE = f"{PROFILE_PREFIX}{ENV_EXT}"
    URL_PLACEHOLDER = "<Insert_YouTube_link_or_local_path_to_audio_or_video>"
    DEFAULT_LANGUAGE = 'en'
    DEFAULT_SOURCE_PROMPT = "Enter the YouTube video URL, video ID, or local file path: "
    # Appended to the enhancement prompt so chat models don't add "Sure! Here's..." preambles
    ENHANCEMENT_OUTPUT_DIRECTIVE = "Output only the enhanced text, with no preamble, headers, or commentary."
    # max_tokens is required by the Anthropic API (no SDK default); per-chunk value
    # is sized off the chunk itself (see enhance_with_anthropic), capped here
    ANTHROPIC_MAX_OUTPUT_TOKENS = 8192

    # Default field values for profile creation (declaration order == profile file order)
    DEFAULT_FIELDS = {
        "URL": URL_PLACEHOLDER,
        "DOWNLOAD_VIDEO": "",
        "NO_AUDIO_IN_VIDEO": "",
        "RESOLUTION": "",
        "DOWNLOAD_AUDIO": "",
        "TRANSCRIBE_AUDIO": "",
        "MODEL_CHOICE": "",
        "TARGET_LANGUAGE": "",
        "USE_EN_MODEL": "",
        "AI_ENHANCEMENT": "",
        "PROMPT": "",
        "REPEAT": ""
    }

    def __init__(self):
        self._create_required_dirs()

    def _create_required_dirs(self):
        """Make directories we need."""
        required_dirs = [
            self.AUDIO_DIR,
            self.VIDEO_DIR,
            self.TRANSCRIPT_DIR,
            self.VIDEO_WITHOUT_AUDIO_DIR,
            self.PROMPT_DIR
        ]
        for directory in required_dirs:
            os.makedirs(directory, exist_ok=True)

    def ensure_directory_exists(self, directory_path):
        """Create directory if it doesn't exist. Returns True on success."""
        try:
            os.makedirs(directory_path, exist_ok=True)
            return True
        except (PermissionError, OSError) as e:
            print(f"Error creating directory {directory_path}: {str(e)}")
            return False

    #####################################
    ## Input validation
    #####################################

    def is_web_url(self, input_str):
        """Check if string is a valid http/https URL (no network calls)."""
        try:
            result = urlparse(input_str)
            return all([result.scheme in ['http', 'https'], result.netloc])
        except ValueError:
            return False

    def is_youtube_video_id(self, text):
        """Check if text is a valid 11-character YouTube video ID (letters, numbers, dash, underscore only)."""
        if len(text) != 11:
            return False
        return bool(re.match(r'^[a-zA-Z0-9_-]{11}$', text))

    def construct_youtube_url(self, video_id):
        """Build full YouTube URL from video ID. Query params get stripped by pytubefix automatically."""
        return f"https://www.youtube.com/watch?v={video_id}"

    def is_youtube_url(self, url):
        """Validate YouTube URL using pytubefix. Extracts video ID from any format (standard, short, embed URLs)."""
        try:
            YouTube(url, "WEB")
            return True
        except (RegexMatchError, VideoUnavailable, VideoPrivate, VideoRegionBlocked):
            return False
        except (ValueError, OSError) as e:
            print(f"Warning: Error checking YouTube URL: {str(e)}")
            return False

    def is_valid_media_file(self, path):
        """Check if path is a supported audio/video file."""
        if not os.path.exists(path):
            return False

        format_name = self.get_file_format(path)
        if format_name is not None:
            return True

        valid_extensions = ['.mp3', '.mp4', '.wav', '.avi', '.mov', '.mkv', '.flac', '.ogg', '.m4a', '.webm']
        file_ext = os.path.splitext(path)[1].lower()
        return file_ext in valid_extensions

    def get_file_format(self, file_path):
        """Get media format using ffprobe."""
        try:
            cmd = [
                'ffprobe', '-v', 'error',
                '-show_entries', 'format=format_name',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                file_path
            ]
            result = subprocess.run(
                cmd, capture_output=True, text=True, check=True
            )
            return result.stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print(f"Error with ffprobe: {str(e)}")
            return None

    #####################################
    ## Interactive prompts
    #####################################

    def get_yes_no_input(self, prompt_text, default="y"):
        """Prompt user for yes/no input with validation."""
        while True:
            user_input = input(prompt_text).lower()
            if user_input in YesNo.YES.value:
                return True
            elif user_input in YesNo.NO.value:
                return False
            elif user_input == "":
                return default == 'y'
            else:
                print(f"Invalid input. Please enter one of {YesNo.YES.value + YesNo.NO.value}.")

    def prompt_for_source(self, prompt_text=None):
        """Prompt until the user enters a valid YouTube URL, video ID, or local media path.

        Returns:
            tuple: (url, is_local_file)
        """
        if prompt_text is None:
            prompt_text = self.DEFAULT_SOURCE_PROMPT
        while True:
            url = input(prompt_text).strip()
            if self.is_youtube_video_id(url):
                url = self.construct_youtube_url(url)
                print(f"Detected video ID, using: {url}")
                return url, False
            if self.is_web_url(url):
                if self.is_youtube_url(url):
                    return url, False
                print("Error: Only YouTube URLs supported for web inputs")
            elif self.is_valid_media_file(url):
                return url, True
            else:
                print("Invalid input. Please enter valid YouTube URL, video ID, or local file path")

    def get_model_choice_input(self):
        """Prompt for Whisper model selection (1-7 or name)."""
        while True:
            model_choice = input("Select Whisper model:\n"
                               "1. Tiny\n"
                               "2. Base\n"
                               "3. Small\n"
                               "4. Medium\n"
                               "5. Large-v1\n"
                               "6. Large-v2\n"
                               "7. Large-v3\n"
                               "Enter your choice (1-7 or model name, default Base): ").lower()
            if model_choice in ModelSize.valid_choices() + ('',):
                return model_choice
            else:
                print("Invalid input. Please enter a valid model choice or number (1-7).")

    def get_target_language_input(self):
        """Prompt for target language (validates against Whisper's supported list)."""
        while True:
            prompt = (
                "Enter the target language for transcription (e.g., 'es' or 'spanish', "
                f"default '{self.DEFAULT_LANGUAGE}'). See supported languages at "
                "https://github.com/openai/whisper#supported-languages): "
            )
            target_language = input(prompt).lower()

            if not target_language:
                return self.DEFAULT_LANGUAGE

            in_codes = target_language in whisper.tokenizer.LANGUAGES
            in_names = target_language in whisper.tokenizer.LANGUAGES.values()

            if in_codes or in_names:
                return target_language
            else:
                print("Invalid language code or name. Please refer to the supported "
                      "languages list and try again.")

    def _validate_hf_model(self, model_name):
        """Check if a HuggingFace model exists and is accessible.

        Args:
            model_name: HuggingFace model ID (e.g., 'distilgpt2', 'microsoft/phi-2').

        Returns:
            bool: True if model exists, False otherwise.
        """
        try:
            from huggingface_hub import model_info
            model_info(model_name)
            return True
        except ImportError:
            # Can't validate without huggingface_hub; allow it through
            print("Note: Cannot validate model name (huggingface_hub not available). Proceeding anyway.")
            return True
        except Exception:
            return False

    def get_ai_enhancement_input(self):
        """Prompt user for AI enhancement mode.

        Returns:
            tuple: (AIEnhancementMode, Provider_or_None, model_id_string_or_None)
            - (API, Provider, None) if user picks a cloud provider
            - (LOCAL, None, 'model_id') if user picks a local model
            - (None, None, None) if user declines
        """
        while True:
            suggestions = ", ".join(m.display_name for m in LocalModel)
            provider_names = "/".join(p.key for p in Provider)
            prompt = (
                "Enhance transcript with AI?\n"
                f" - Enter 'y' for the default cloud API ({Provider.default().key})\n"
                f" - Enter a provider name for a specific cloud API: {provider_names}\n"
                f" - Enter 'local' to use default local model ({LocalModel.default().display_name})\n"
                f" - Enter a model name (e.g., {suggestions})\n"
                "   or any HuggingFace model ID (e.g., microsoft/phi-2)\n"
                " - Enter 'n' to skip\n"
                "Choice (default n): "
            )
            user_input = input(prompt).strip()
            user_lower = user_input.lower()

            if not user_input or user_lower in AIEnhancementMode.DISABLED.value:
                return None, None, None

            provider = Provider.from_string(user_lower)
            if provider is not None:
                return AIEnhancementMode.API, provider, None

            if user_lower in AIEnhancementMode.API.value:
                return AIEnhancementMode.API, Provider.default(), None

            if user_lower == 'local':
                return AIEnhancementMode.LOCAL, None, LocalModel.default().hf_model_id

            # Check if it's a known local model display name
            if user_lower in LocalModel.all_model_values():
                model = LocalModel.get_by_name(user_lower)
                return AIEnhancementMode.LOCAL, None, model.hf_model_id

            # Treat as arbitrary HuggingFace model ID - validate it
            model_id = user_input  # preserve original case for HF model IDs
            print(f"Checking if model '{model_id}' exists on HuggingFace...")
            if self._validate_hf_model(model_id):
                print(f"Model '{model_id}' found.")
                return AIEnhancementMode.LOCAL, None, model_id
            else:
                print(f"Model '{model_id}' not found on HuggingFace. Please try again.")

    def get_prompt_input(self):
        """Prompt user to select a prompt file or enter a custom prompt.

        Returns:
            tuple: (prompt_filename, prompt_text)
                - (filename, None) if a file was selected
                - (None, text) if the user entered an inline prompt
                - (None, None) if no prompts available or user cancelled
        """
        prompts = self.list_available_prompts()
        if not prompts:
            print("No prompt files found in Prompt/ directory.")
            print("You can enter a custom prompt instead.")
            print("  E. Enter custom prompt")
            while True:
                user_input = input("Select option (E to enter custom prompt, or press Enter to skip): ").strip()
                if not user_input:
                    return (None, None)
                elif user_input.lower() == 'e':
                    return self._get_inline_prompt()
                else:
                    print("Invalid selection. Please try again.")

        print("Available prompt files:")
        for i, p in enumerate(prompts):
            print(f"  {i+1}. {p}")
        print("  E. Enter custom prompt")

        while True:
            user_input = input(f"Select prompt file (number, name, or E for custom; default 1. {prompts[0]}): ").strip()
            if not user_input:
                return (prompts[0], None)
            elif user_input.lower() == 'e':
                return self._get_inline_prompt()
            elif user_input.isdigit() and 1 <= int(user_input) <= len(prompts):
                return (prompts[int(user_input) - 1], None)
            elif user_input in prompts:
                return (user_input, None)
            elif user_input + self.TXT_EXT in prompts:
                return (user_input + self.TXT_EXT, None)
            else:
                print("Invalid selection. Please try again.")

    def _get_inline_prompt(self):
        """Prompt the user to enter a custom prompt in the console.

        Returns:
            tuple: (None, prompt_text) or (None, None) if empty.
        """
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

    def list_available_prompts(self):
        """List non-empty .txt files in the Prompt/ directory."""
        prompt_dir = os.path.join(os.path.dirname(__file__), self.PROMPT_DIR)
        if not os.path.exists(prompt_dir):
            return []
        return sorted([
            f for f in os.listdir(prompt_dir)
            if f.endswith(self.TXT_EXT) and os.path.getsize(os.path.join(prompt_dir, f)) > 0
        ])

    def load_prompt_file(self, filename):
        """Load prompt text from a file in the Prompt/ directory.

        Args:
            filename: Name of the prompt file (e.g., 'prompt.txt').

        Returns:
            str: The prompt text, or empty string if file not found/empty.
        """
        prompt_path = os.path.join(os.path.dirname(__file__), self.PROMPT_DIR, filename)
        if not os.path.exists(prompt_path):
            print(f"Warning: Prompt file not found: {prompt_path}")
            return ""
        try:
            with open(prompt_path, "r", encoding='utf-8') as f:
                content = f.read().strip()
            if not content:
                print(f"Warning: Prompt file is empty: {prompt_path}")
                return ""
            return content
        except (PermissionError, OSError) as e:
            print(f"Error reading prompt file: {str(e)}")
            return ""

    #####################################
    ## AI transcript enhancement
    #####################################

    def chunk_text(self, text, max_tokens=800, overlap_tokens=50):
        """Split text into chunks at sentence boundaries, respecting token limits.

        Args:
            text: The full transcript text.
            max_tokens: Max tokens per chunk (leave room for prompt/output).
            overlap_tokens: Tokens to overlap between chunks for continuity.

        Returns:
            list[str]: List of text chunks.
        """
        sentences = re.split(r'(?<=[.!?])\s+', text)

        chunks = []
        current_chunk = ""

        for sentence in sentences:
            # Rough token estimate: 1 token ≈ 4 characters
            estimated_tokens = len(current_chunk) // 4
            sentence_tokens = len(sentence) // 4

            if estimated_tokens + sentence_tokens > max_tokens and current_chunk:
                chunks.append(current_chunk.strip())
                # Start new chunk with overlap from end of previous
                overlap_chars = overlap_tokens * 4
                if len(current_chunk) > overlap_chars:
                    current_chunk = current_chunk[-overlap_chars:] + " " + sentence
                else:
                    current_chunk = sentence
            else:
                current_chunk = (current_chunk + " " + sentence).strip()

        if current_chunk.strip():
            chunks.append(current_chunk.strip())

        return chunks if chunks else [text]

    def merge_chunks(self, enhanced_chunks):
        """Merge enhanced text chunks, deduplicating overlaps.

        Args:
            enhanced_chunks: List of enhanced text strings.

        Returns:
            str: Merged text.
        """
        if not enhanced_chunks:
            return ""
        if len(enhanced_chunks) == 1:
            return enhanced_chunks[0]

        merged = enhanced_chunks[0]
        for chunk in enhanced_chunks[1:]:
            # Try to find overlap between end of merged and start of chunk
            # Check last 100 chars of merged against start of chunk
            overlap_window = min(100, len(merged))
            tail = merged[-overlap_window:]

            best_overlap = 0
            for j in range(len(tail), 0, -1):
                if chunk.startswith(tail[-j:]):
                    best_overlap = j
                    break

            if best_overlap > 10:  # Only deduplicate if overlap is meaningful
                merged += " " + chunk[best_overlap:].strip()
            else:
                merged += " " + chunk.strip()

        return merged.strip()

    def _build_chat_messages(self, prompt_text, chunk):
        """Build the system/user message pair shared by all chat-style backends."""
        return [
            {"role": "system", "content": f"{prompt_text}\n\n{self.ENHANCEMENT_OUTPUT_DIRECTIVE}"},
            {"role": "user", "content": chunk}
        ]

    def _run_chunked_enhancement(self, chunks, backend_label, call_chunk):
        """Shared chunk-loop for cloud enhancement backends.

        Args:
            chunks: list of text chunks to enhance.
            backend_label: name used in progress/warning messages (e.g. provider.key).
            call_chunk: callable(chunk) -> enhanced text. Returning an empty/falsy
                string signals "no usable output" and keeps the original chunk;
                raising falls back to the original chunk and logs the error.

        Returns:
            str: merged, enhanced text.
        """
        enhanced_chunks = []
        for i, chunk in enumerate(chunks):
            try:
                print(f"  Processing chunk {i+1}/{len(chunks)}...")
                enhanced = call_chunk(chunk)
                enhanced_chunks.append(enhanced if enhanced else chunk)
            except Exception as e:
                print(f"  Warning: {backend_label} error on chunk {i+1}: {str(e)}")
                enhanced_chunks.append(chunk)  # Fallback to original chunk
        return self.merge_chunks(enhanced_chunks)

    def enhance_with_openai_compatible(self, text, prompt_text, api_key, provider):
        """Enhance transcript text via an OpenAI-API-compatible endpoint.

        Covers OPENAI and OPENROUTER (and, via base_url overrides, any other
        provider that speaks the same chat completions API - Groq, Together,
        DeepSeek's direct API, Azure OpenAI, etc.).

        Args:
            text: The raw transcript text.
            prompt_text: The enhancement prompt (from prompt file).
            api_key: API key for `provider`.
            provider: Provider enum (OPENAI or OPENROUTER).

        Returns:
            str: Enhanced text, or original text on failure.
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
        chunks = self.chunk_text(text, max_tokens=3000, overlap_tokens=100)

        print(f"Enhancing transcript with {provider.key} ({model}, {len(chunks)} chunk(s))...")

        def call_chunk(chunk):
            response = client.chat.completions.create(
                model=model,
                messages=self._build_chat_messages(prompt_text, chunk),
                temperature=0.3
            )
            return response.choices[0].message.content.strip()

        result = self._run_chunked_enhancement(chunks, provider.key, call_chunk)
        print(f"{provider.key} enhancement complete.")
        return result

    def enhance_with_anthropic(self, text, prompt_text, api_key, provider):
        """Enhance transcript text using Anthropic's native Messages API with chunking.

        Args:
            text: The raw transcript text.
            prompt_text: The enhancement prompt (from prompt file).
            api_key: Anthropic API key.
            provider: Provider.ANTHROPIC (carries the resolved model/base_url).

        Returns:
            str: Enhanced text, or original text on failure.
        """
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
        chunks = self.chunk_text(text, max_tokens=3000, overlap_tokens=100)

        print(f"Enhancing transcript with anthropic ({model}, {len(chunks)} chunk(s))...")

        def call_chunk(chunk):
            # Size the output budget off the chunk itself (chars/3, vs. chunk_text's
            # chars/4 input estimate) so expansion-style prompts still have headroom.
            max_tokens = min(max(len(chunk) // 3, 1024), self.ANTHROPIC_MAX_OUTPUT_TOKENS)
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=f"{prompt_text}\n\n{self.ENHANCEMENT_OUTPUT_DIRECTIVE}",
                messages=[{"role": "user", "content": chunk}],
            )
            if response.stop_reason == "max_tokens":
                # Output was cut off mid-sentence; keep the original chunk rather
                # than silently save truncated text.
                print(f"  Warning: response truncated at {max_tokens} tokens; keeping original chunk to avoid content loss.")
                return ""
            return "".join(
                block.text for block in response.content if block.type == "text"
            ).strip()

        result = self._run_chunked_enhancement(chunks, "anthropic", call_chunk)
        print("anthropic enhancement complete.")
        return result

    def enhance_with_local(self, text, prompt_text, local_model):
        """Enhance transcript text using a local model with chunking.

        Args:
            text: The raw transcript text.
            prompt_text: The enhancement prompt (from prompt file).
            local_model: LocalModel enum or HuggingFace model ID string.

        Returns:
            str: Enhanced text, or original text on failure.
        """
        try:
            from transformers import pipeline, AutoTokenizer
        except ImportError:
            print("Warning: 'transformers' package not installed. Skipping local enhancement.")
            print("Install with: pip install transformers torch")
            return text

        try:
            import torch
        except ImportError:
            print("Warning: 'torch' package not installed or not available. Skipping local enhancement.")
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

        # Accept both LocalModel enum and plain string model IDs
        if isinstance(local_model, LocalModel):
            model_id = local_model.hf_model_id
        else:
            model_id = str(local_model)
        print(f"Loading local model: {model_id} (this may take a moment on first run)...")

        try:
            tokenizer = AutoTokenizer.from_pretrained(model_id)
            max_length = getattr(tokenizer, 'model_max_length', 1024)
            # Use 60% of max length for input, leave room for generation
            chunk_max = min(int(max_length * 0.6), 800)

            accelerate_available = importlib.util.find_spec("accelerate") is not None
            if not accelerate_available:
                print("Warning: 'accelerate' not installed. Loading model without device_map.")

            generator = pipeline(
                'text-generation',
                model=model_id,
                tokenizer=tokenizer,
                dtype="auto",
                device_map="auto" if accelerate_available else None
            )
        except Exception as e:
            print(f"Error loading local model '{model_id}': {str(e)}")
            print("Skipping local enhancement.")
            return text

        chunks = self.chunk_text(text, max_tokens=chunk_max, overlap_tokens=50)
        # Instruct/chat models define a chat template; base models (gpt2 etc.) don't
        has_chat_template = getattr(tokenizer, 'chat_template', None) is not None

        print(f"Enhancing transcript with local model ({len(chunks)} chunk(s))...")

        def call_chunk(chunk):
            max_new_tokens = max(len(chunk.split()) * 2, 256)  # Allow roughly 2x input length

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
                # Strip the prompt from the output
                if "Enhanced version:" in generated:
                    enhanced = generated.split("Enhanced version:")[-1].strip()
                else:
                    enhanced = generated[len(full_prompt):].strip()

            # Reasoning models (e.g., DeepSeek-R1 distills) emit <think> blocks; drop them
            enhanced = re.sub(r'<think>.*?</think>', '', enhanced, flags=re.DOTALL).strip()

            # If model produced nothing useful, signal the caller to keep the original
            if not enhanced or len(enhanced) < len(chunk) * 0.3:
                return ""
            return enhanced

        result = self._run_chunked_enhancement(chunks, "Local model", call_chunk)
        print("Local model enhancement complete.")
        return result

    def enhance_text(self, text, mode, prompt_text, api_key=None, provider=None, local_model=None):
        """Main dispatcher for transcript enhancement.

        Args:
            text: The raw transcript text.
            mode: AIEnhancementMode enum (API or LOCAL).
            prompt_text: The enhancement prompt text.
            api_key: Cloud API key (required if mode is API).
            provider: Provider enum selecting which cloud API to call (used if mode is API).
            local_model: HuggingFace model ID string or LocalModel enum (required if mode is LOCAL).

        Returns:
            str: Enhanced text, or original text if enhancement fails/skipped.
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
            return self.enhance_with_local(text, prompt_text, local_model)

        else:
            print("Warning: Unknown enhancement mode. Skipping.")
            return text

    #####################################
    ## Files and transcripts
    #####################################

    def startfile(self, fn):
        """Open file with system default app (cross-platform)."""
        if os.name == 'nt':  # Windows
            os.startfile(fn)
        elif os.name == 'posix':  # macOS or Linux
            opener = 'open' if sys.platform == 'darwin' else 'xdg-open'
            subprocess.run([opener, fn], check=True)

    def sanitize_filename(self, text):
        """Strip invalid characters from filename."""
        return "".join(c for c in text if c.isalnum() or c in "._- ")

    def create_and_open_txt(self, text, filename):
        """Write transcript text to the Transcript/ directory and open it."""
        output_dir = os.path.join(os.path.dirname(__file__), self.TRANSCRIPT_DIR)

        if not self.ensure_directory_exists(output_dir):
            print(f"Error: Cannot create transcript directory {output_dir}")
            return False

        file_path = os.path.join(output_dir, filename)

        if not self.verify_file_writable(file_path):
            print(f"Error: Cannot write to transcript file {file_path}")
            return False

        required_space = max(len(text) * 2, 1024 * 1024)
        free_space = self.get_free_disk_space(output_dir)
        if free_space is not None and free_space < required_space:
            print(f"Error: Not enough disk space to save transcript. Need {required_space/1024/1024:.1f}MB, have {free_space/1024/1024:.1f}MB free.")
            return False

        try:
            with open(file_path, "w", encoding='utf-8') as file:
                file.write(text)
            self.startfile(file_path)
            return True
        except (PermissionError, OSError) as e:
            print(f"Error writing transcript file: {str(e)}")
            return False

    #####################################
    ## YouTube streams
    #####################################

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2),
           retry=retry_if_exception_type(Exception))
    def create_youtube_object(self, url):
        """Create YouTube object (retries up to 3 times on failures)."""
        try:
            return YouTube(url, "WEB")
        except (RegexMatchError, VideoUnavailable, VideoPrivate, VideoRegionBlocked, ValueError, OSError) as e:
            print(f"Error creating YouTube object: {str(e)}")
            raise

    @staticmethod
    def sort_streams_by_resolution(streams):
        """Sort video streams by resolution, highest first."""
        return sorted(
            streams,
            key=lambda stream: int(stream.resolution[:-1]) if stream.resolution else 0,  # [:-1] strips 'p' from '1080p'
            reverse=True
        )

    def get_sorted_video_streams(self, yt):
        """Get available video streams sorted by resolution (highest first)."""
        try:
            return self.sort_streams_by_resolution(yt.streams.filter(only_video=True))
        except RegexMatchError as e:
            print(f"Error retrieving video streams: {str(e)}")
            print("YouTube may have changed something. Try: pip install --upgrade pytubefix")
            return []
        except (AttributeError, ValueError, OSError) as e:
            print(f"Error retrieving video streams: {str(e)}")
            return []

    def get_sorted_audio_streams(self, yt):
        """Get available audio streams sorted by bitrate (highest first)."""
        try:
            audio_streams = yt.streams.filter(only_audio=True)
            return sorted(
                audio_streams,
                key=lambda stream: int(stream.abr[:-4]) if stream.abr else 0,  # [:-4] strips 'kbps' from '128kbps'
                reverse=True
            )
        except RegexMatchError as e:
            print(f"Error retrieving audio streams: {str(e)}")
            print("YouTube may have changed something. Try: pip install --upgrade pytubefix")
            return []
        except (AttributeError, ValueError) as e:
            print(f"Error retrieving audio streams: {str(e)}")
            return []

    def get_unique_sorted_resolutions(self, streams):
        """Extract unique resolutions from streams and sort by quality (highest first)."""
        resolutions = set([stream.resolution for stream in streams if stream.resolution])

        return sorted(
            resolutions,
            key=lambda res: int(res[:-1]) if res else 0,  # Strip 'p' suffix for numeric sorting
            reverse=True
        )

    def download_audio_stream(self, yt, filename_base, is_temp=False):
        """Download highest quality audio stream (optionally to temp directory)."""
        print("Downloading the audio stream (highest quality)...")

        audio_streams = self.get_sorted_audio_streams(yt)

        if not audio_streams:
            raise ValueError("No audio streams available for this video")

        audio_stream = audio_streams[0]

        audio_filename = filename_base + self.MP3_EXT
        output_dir = os.path.join(self.AUDIO_DIR, self.TEMP_DIR) if is_temp else self.AUDIO_DIR
        os.makedirs(output_dir, exist_ok=True)

        relative_path = os.path.join(output_dir, audio_filename)

        @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
        def download_with_retry():
            audio_stream.download(output_path=output_dir, filename=audio_filename)
            if not os.path.exists(relative_path):
                raise FileNotFoundError(f"Failed to download audio stream to {relative_path}")
            return True

        download_with_retry()

        absolute_path = os.path.abspath(relative_path)
        print(f"Audio downloaded to {absolute_path}")

        return relative_path, absolute_path

    def combine_audio_video(self, video_path, audio_path, output_path, cleanup_temp=True, temp_video_dir=None):
        """Merge separate video and audio files using ffmpeg."""
        output_dir = os.path.dirname(output_path)
        if not self.ensure_directory_exists(output_dir):
            print(f"Error: Cannot create video output directory {output_dir}")
            return None

        if not self.verify_file_writable(output_path):
            print(f"Error: Cannot write to output video file {output_path}")
            return None

        try:
            video_size = os.path.getsize(video_path)
            audio_size = os.path.getsize(audio_path)
            required_space = (video_size + audio_size) * 1.5

            free_space = self.get_free_disk_space(output_dir)
            if free_space is not None and free_space < required_space:
                print(f"Error: Not enough disk space to combine video. Need {required_space/1024/1024:.1f}MB, have {free_space/1024/1024:.1f}MB free.")
                return None
        except (OSError, IOError) as e:
            print(f"Warning: Could not verify file sizes: {str(e)}")

        if not os.path.exists(video_path):
            print(f"Error: Video file not found: {video_path}")
            return None

        if not os.path.exists(audio_path):
            print(f"Error: Audio file not found: {audio_path}")
            return None

        command = f'ffmpeg -y -i "{video_path}" -i "{audio_path}" -c:v copy -c:a aac "{output_path}"'

        try:
            subprocess.run(command, shell=True, capture_output=True, text=True, check=True)
        except subprocess.CalledProcessError as e:
            print(f"Error combining audio and video: {e.stderr}")
            return None
        except OSError:
            print("Error running ffmpeg")
            return None

        if not os.path.exists(output_path):
            print("Error: Failed to create combined video file")
            return None

        if cleanup_temp:
            try:
                if os.path.exists(video_path):
                    os.remove(video_path)
                if temp_video_dir and os.path.exists(temp_video_dir):
                    os.rmdir(temp_video_dir)
            except (PermissionError, OSError) as e:
                print(f"Warning: Could not clean up temporary files: {str(e)}")

        print(f"Combined video saved to {output_path}")
        return output_path

    def transcribe_audio_file(self, file_path, model_name, target_language):
        """Transcribe audio file using Whisper and detect the language."""
        if not os.path.exists(file_path):
            error_msg = f"Error: Audio file not found: {file_path}"
            print(error_msg)
            return error_msg, "en"

        try:
            print(f"Loading Whisper model: {model_name}")
            model = whisper.load_model(model_name)
        except (OSError, ValueError) as load_error:
            print(f"Error loading Whisper model: {str(load_error)}")
            print("Falling back to base model")
            try:
                model = whisper.load_model("base")
            except (OSError, ValueError) as fallback_error:
                print(f"Error loading fallback model: {str(fallback_error)}")
                return "Error: Unable to load Whisper model", "en"

        target_language_full = whisper.tokenizer.LANGUAGES.get(target_language, target_language)
        target_language_full = target_language_full.capitalize()

        absolute_path = os.path.abspath(file_path)
        print(f"Transcribing audio from {absolute_path} into {target_language_full}...")

        try:
            result = model.transcribe(file_path, language=target_language)
            transcribed_text = result["text"]

            if not transcribed_text.strip():
                print("Warning: Transcription produced empty text. The audio might be silent or not contain speech.")
                return "No speech detected in audio.", target_language

        except (RuntimeError, ValueError) as e:
            error_msg = f"Error during transcription: {str(e)}"
            print(error_msg)
            return error_msg, "en"

        print("\nTranscription:\n" + transcribed_text + "\n")

        try:
            detected_language = detect(transcribed_text)
            detected_language_full = whisper.tokenizer.LANGUAGES.get(detected_language, detected_language)
            detected_language_full = detected_language_full.capitalize()

            if detected_language_full == target_language_full:
                print(f"Verified {detected_language_full}")
            else:
                print("Transcription/translation mismatch")
        except LangDetectException as e:
            print(f"Error detecting language: {str(e)}")
            detected_language = "unknown"

        return transcribed_text, detected_language

    def check_dependencies(self):
        """Verify required system dependencies (ffmpeg) are installed."""
        # ffmpeg needed for format detection (ffprobe) and combining video/audio streams
        if shutil.which("ffmpeg") is None:
            print("ERROR: ffmpeg is not found in the system PATH.")
            print("Please install ffmpeg and make sure it's in your PATH:")
            print("- Windows: https://ffmpeg.org/download.html")
            print("- macOS: brew install ffmpeg")
            print("- Linux: apt-get install ffmpeg")
            return False

        return True

    #####################################
    ## Profiles
    #####################################

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

        config_path = os.path.join(self.PROFILE_DIR, self.CONFIG_ENV)
        if not os.path.exists(config_path):
            with open(config_path, "w", encoding='utf-8') as config_file:
                config_file.write("# Configuration file for YouTube Transcriber\n")
                config_file.write(f"LOAD_PROFILE={self.DEFAULT_PROFILE}")
            print(f"Created {self.CONFIG_ENV}: {os.path.abspath(config_path)}")
        else:
            print(f"{self.CONFIG_ENV} already exists: {os.path.abspath(config_path)}. "
                  "No changes were made to it.")

        existing_profiles = self.list_profiles()
        num_pattern = rf"^{re.escape(self.PROFILE_PREFIX)}(?P<num>\d+)(?:-.*)?{re.escape(self.ENV_EXT)}$"
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

        # DEFAULT_FIELDS declaration order defines the field order in the file
        field_order = list(self.DEFAULT_FIELDS)
        with open(profile_path, "w", encoding='utf-8') as profile_file:
            profile_file.write("# Edit values after the = sign\n\n")
            for i, field_name in enumerate(field_order):
                if field_name in profile_fields:
                    newline = "" if i == len(field_order) - 1 else "\n"
                    profile_file.write(f"{field_name}={profile_fields[field_name]}{newline}")

        print(f"Created profile: {os.path.abspath(profile_path)}")

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
                except (PermissionError, OSError):
                    return False

            return os.access(parent_dir, os.W_OK)
        except (OSError, IOError):
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
        except (OSError, IOError, ValueError) as e:
            print(f"Error checking disk space: {str(e)}")
            return None

#########################################
## SESSION CONFIGURATION
#########################################

@dataclass
class SessionConfig:
    """Settings gathered for one transcription session (interactively or from a profile)."""
    url: str = None
    is_local_file: bool = False
    yt: object = None
    video_title: str = ""
    download_video: bool = False
    no_audio_in_video: bool = False
    resolution: str = None
    selected_res: str = None
    download_audio: bool = False
    transcribe_audio: bool = True
    model_choice: str = ""
    model_name: str = ModelSize.BASE.value
    target_language: str = ""
    use_en_model: bool = False
    ai_mode: AIEnhancementMode = None
    provider: Provider = None
    local_model: str = None
    prompt_text: str = ""
    api_key: str = None
    used_fields: dict = field(default_factory=dict)


# Session-scoped environment keys used to carry state across "Run again?" repeats
_SESSION_ENV_KEYS = (
    "_REPEAT_INVOCATION", "_REPEAT_PROFILE_NAME", "_REPEAT_ASK_COUNT",
    "LAST_DOWNLOAD_VIDEO", "LAST_NO_AUDIO_IN_VIDEO", "LAST_RESOLUTION",
    "LAST_DOWNLOAD_AUDIO", "LAST_TRANSCRIBE_AUDIO", "LAST_MODEL_CHOICE",
    "LAST_TARGET_LANGUAGE", "LAST_USE_EN_MODEL", "LAST_AI_ENHANCEMENT"
)


def _clear_session_env():
    """Remove all repeat-session environment variables."""
    for key in _SESSION_ENV_KEYS:
        os.environ.pop(key, None)


def _bool_from_last(env_key, prompt_fn):
    """Reuse a yes/no answer remembered from the previous repeat run, else prompt."""
    last = os.environ.get(env_key)
    if last is not None:
        print(f"Using previous {env_key[len('LAST_'):]}: {last} (from last session)")
        return last.lower() in YesNo.YES.value
    return prompt_fn()


def _value_from_last(env_key, prompt_fn):
    """Reuse a string answer remembered from the previous repeat run, else prompt."""
    last = os.environ.get(env_key)
    if last is not None:
        print(f"Using previous {env_key[len('LAST_'):]}: {last} (from last session)")
        return last
    return prompt_fn()


def _bool_from_profile_env(transcriber, var_name, profile_name, prompt_text,
                           default='n', prompt_if_missing=True, missing=False):
    """Read a yes/no profile field, falling back to an interactive prompt.

    Invalid values always fall back to the prompt; missing values fall back to
    the prompt only when prompt_if_missing is True (else return `missing`).
    """
    value = os.getenv(var_name)
    if not value:
        if prompt_if_missing:
            return transcriber.get_yes_no_input(prompt_text, default=default)
        return missing
    if value.lower() in YesNo.YES.value:
        print(f"Loaded {var_name}: {value} (from {profile_name})")
        return True
    if value.lower() in YesNo.NO.value:
        print(f"Loaded {var_name}: {value} (from {profile_name})")
        return False
    print(f"Invalid value for {var_name} in .env: {value}")
    return transcriber.get_yes_no_input(prompt_text, default=default)


def _ai_mode_from_setting(value):
    """Map a stored AI_ENHANCEMENT setting to (AIEnhancementMode, Provider, local_model_id).

    Exactly one of Provider/local_model_id is non-None, depending on mode.
    Unrecognized values are treated as local model names/IDs.
    """
    mode = AIEnhancementMode.from_string(value)
    if mode == AIEnhancementMode.API:
        provider = Provider.from_string(value) or Provider.default()
        return AIEnhancementMode.API, provider, None
    if mode == AIEnhancementMode.LOCAL:
        stripped = value.strip()
        if stripped.lower() == 'local':
            return AIEnhancementMode.LOCAL, None, LocalModel.default().hf_model_id
        return AIEnhancementMode.LOCAL, None, LocalModel.get_by_name(stripped.lower()).hf_model_id
    if mode == AIEnhancementMode.DISABLED:
        return None, None, None
    return AIEnhancementMode.LOCAL, None, value.strip()


def _select_prompt_interactively(transcriber):
    """Have the user pick a prompt file or type an inline prompt.

    Returns:
        tuple: (prompt_text, used_fields_label) or (None, None) if cancelled.
    """
    prompt_filename, inline_prompt = transcriber.get_prompt_input()
    if prompt_filename:
        return transcriber.load_prompt_file(prompt_filename), prompt_filename
    if inline_prompt:
        return inline_prompt, "(inline)"
    return None, None


def _resolve_api_key(provider):
    """Get the API key for `provider` from the environment or prompt for it."""
    api_key = os.getenv(provider.api_key_env)
    if not api_key:
        api_key = input(f"Enter your {provider.key} API key: ").strip()
    if not api_key:
        print("No API key provided. Disabling AI enhancement.")
        return None
    return api_key


def _prompt_profile_selection(transcriber, profiles):
    """List profiles and let the user pick one.

    Returns:
        str or None: The selected profile filename, or None if skipped.
    """
    print("Available profiles:")
    for i, profile in enumerate(profiles):
        print(f"{i+1}. {profile}")

    while True:
        profile_input = input(
            f"Select a profile (number or name, default 1. {profiles[0]}, "
            f"or 'no' / 'n' / 'false' / 'f' / '0' / 'skip' / 's' to skip): "
        )
        lower_input = profile_input.lower()
        if profile_input == '' or lower_input == '1':
            return profiles[0]
        if profile_input.isdigit() and 1 <= int(profile_input) <= len(profiles):
            return profiles[int(profile_input) - 1]
        if profile_input in profiles:
            return profile_input
        if profile_input + transcriber.ENV_EXT in profiles:
            return profile_input + transcriber.ENV_EXT
        if lower_input in YesNo.all_no_and_skip():
            return None
        print("Invalid profile selection.")


def _prompt_resolution_selection(transcriber, yt):
    """List a video's available resolutions and let the user pick one.

    Exits the program if the video has no video streams.
    """
    available_streams = transcriber.get_sorted_video_streams(yt)
    available_resolutions = transcriber.get_unique_sorted_resolutions(available_streams)

    if not available_resolutions:
        print("No video streams found. Exiting...")
        sys.exit()

    print("Available resolutions:")
    for i, res in enumerate(available_resolutions):
        print(f"{i+1}. {res}")

    while True:
        user_input = input("Enter desired resolution (number or resolution, default highest): ").lower()
        if not user_input:
            return available_resolutions[0]  # Default to highest
        if user_input.isdigit() and 1 <= int(user_input) <= len(available_resolutions):
            return available_resolutions[int(user_input) - 1]
        if user_input in available_resolutions or (user_input.isdigit() and user_input + "p" in available_resolutions):
            return user_input if user_input in available_resolutions else user_input + "p"
        print("Invalid input. Please enter a valid number or resolution.")


def _prompt_resolution_input(transcriber, used_fields):
    """Prompt for a desired resolution (name, number, or fetch keyword)."""
    while True:
        resolution = input(
            "... enter desired resolution (e.g., 720p, 720, highest, lowest, "
            "default get the highest resolutions), or enter fetch or f to get "
            "a list of available resolutions: "
        )

        if not resolution:
            # Default to highest if input is empty
            return Resolution.HIGHEST.value

        resolution = resolution.lower()

        if resolution in Resolution.values():
            if resolution == Resolution.F.value:
                resolution = Resolution.FETCH.value
            used_fields["RESOLUTION"] = resolution
            return resolution
        if resolution.endswith("p"):
            used_fields["RESOLUTION"] = resolution
            return resolution
        if resolution.isdigit():
            if int(resolution) > 0:
                resolution += "p"
                used_fields["RESOLUTION"] = resolution
                return resolution
            print("Invalid resolution. Please enter a non-zero number.")
        else:
            print("Invalid resolution. Please enter a valid resolution "
                  "(e.g., 720p, 720, highest, lowest).")


#########################################
## PROFILE SELECTION
#########################################

def _select_profile(transcriber):
    """Determine whether to run from a profile and load it if so.

    Handles repeat invocations, config.txt discovery, and interactive
    profile selection.

    Returns:
        tuple: (load_profile, profile_name)
    """
    repeat_invocation = os.environ.get("_REPEAT_INVOCATION", "") == "1"
    repeat_profile_name = os.environ.get("_REPEAT_PROFILE_NAME")

    # Repeat of a profile-driven session: reload the same profile
    if repeat_invocation and repeat_profile_name:
        profile_path = os.path.join(transcriber.PROFILE_DIR, repeat_profile_name)
        if os.path.exists(profile_path):
            load_dotenv(dotenv_path=profile_path, override=True)
            print(f"Loaded profile (repeat): {repeat_profile_name}")
            return True, repeat_profile_name
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

        load_dotenv(dotenv_path=os.path.join(transcriber.PROFILE_DIR, profile_name), override=True)
        print(f"Loaded profile: {profile_name}")
        return True, profile_name

    print(f"config.txt detected in the {transcriber.PROFILE_DIR} directory.")
    load_dotenv(dotenv_path=config_env_path, override=True)
    # Manually read LOAD_PROFILE from config.txt to ensure accurate value
    # (utf-8-sig tolerates a BOM, which editors on Windows often add)
    load_profile_str = None
    with open(config_env_path, 'r', encoding='utf-8-sig') as cf:
        for line in cf:
            if line.strip().startswith("LOAD_PROFILE"):
                _, val = line.split("=", 1)
                load_profile_str = val.strip()
                os.environ["LOAD_PROFILE"] = load_profile_str
                break

    print(f"LOAD_PROFILE: {load_profile_str} (from config.txt)")
    lower_lp = load_profile_str.lower() if load_profile_str else ''

    # Explicit profile names (not simple yes/no) take precedence
    if load_profile_str and lower_lp not in YesNo.YES.value + YesNo.NO.value + YesNo.SKIP.value + ('',):
        if not load_profile_str.endswith(transcriber.ENV_EXT):
            load_profile_str += transcriber.ENV_EXT
        profile_path = os.path.join(transcriber.PROFILE_DIR, load_profile_str)
        if os.path.exists(profile_path):
            profile_name = os.path.basename(profile_path)
            print(f"Loading profile: {profile_name}")
            load_dotenv(dotenv_path=profile_path, override=True)
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

    load_dotenv(dotenv_path=os.path.join(transcriber.PROFILE_DIR, profile_name), override=True)
    print(f"Loaded profile: {profile_name}")
    return True, profile_name


#########################################
## INTERACTIVE CONFIGURATION
#########################################

def _configure_interactive(transcriber):
    """Gather all session settings by prompting the user.

    Answers remembered from a previous "Run again?" repeat (LAST_* environment
    variables) are reused instead of re-prompting.
    """
    cfg = SessionConfig(used_fields=transcriber.DEFAULT_FIELDS.copy())
    used_fields = cfg.used_fields

    cfg.url, cfg.is_local_file = transcriber.prompt_for_source()

    if not cfg.is_local_file:
        cfg.download_video = _bool_from_last(
            "LAST_DOWNLOAD_VIDEO",
            lambda: transcriber.get_yes_no_input("Download video? (y/N): ", default='n'))
        used_fields["DOWNLOAD_VIDEO"] = "y" if cfg.download_video else "n"

        if cfg.download_video:
            cfg.no_audio_in_video = _bool_from_last(
                "LAST_NO_AUDIO_IN_VIDEO",
                lambda: transcriber.get_yes_no_input("... without the audio in the video? (y/N): ", "n"))
            used_fields["NO_AUDIO_IN_VIDEO"] = "y" if cfg.no_audio_in_video else "n"

            cfg.resolution = _value_from_last(
                "LAST_RESOLUTION",
                lambda: _prompt_resolution_input(transcriber, used_fields))
            if cfg.resolution != Resolution.FETCH.value:
                print(f"Using resolution: {cfg.resolution}")
            else:
                print("Loading available resolution...")

        if cfg.resolution == Resolution.FETCH.value:
            try:
                yt = YouTube(cfg.url, "WEB")
            except RegexMatchError:
                print("Error: Invalid YouTube URL.")
                sys.exit()
            cfg.selected_res = _prompt_resolution_selection(transcriber, yt)

        cfg.download_audio = _bool_from_last(
            "LAST_DOWNLOAD_AUDIO",
            lambda: transcriber.get_yes_no_input("Download audio? (y/N): ", default='n'))
        used_fields["DOWNLOAD_AUDIO"] = "y" if cfg.download_audio else "n"

    cfg.transcribe_audio = _bool_from_last(
        "LAST_TRANSCRIBE_AUDIO",
        lambda: transcriber.get_yes_no_input("Transcribe the audio? (Y/n): "))
    used_fields["TRANSCRIBE_AUDIO"] = "y" if cfg.transcribe_audio else "n"

    if not cfg.transcribe_audio:
        return cfg

    cfg.model_choice = _value_from_last("LAST_MODEL_CHOICE", transcriber.get_model_choice_input)
    model_enum = ModelSize.from_choice(cfg.model_choice)
    cfg.model_name = model_enum.value
    used_fields["MODEL_CHOICE"] = cfg.model_name

    cfg.target_language = _value_from_last("LAST_TARGET_LANGUAGE", transcriber.get_target_language_input)
    used_fields["TARGET_LANGUAGE"] = cfg.target_language

    if model_enum in ModelSize.standard_models() and cfg.target_language == transcriber.DEFAULT_LANGUAGE:
        cfg.use_en_model = _bool_from_last(
            "LAST_USE_EN_MODEL",
            lambda: transcriber.get_yes_no_input(
                "Use English-specific model? (Recommended only if the video is originally in English) (y/N): ",
                default='n'))
        used_fields["USE_EN_MODEL"] = "y" if cfg.use_en_model else "n"

    # --- AI Enhancement ---
    last_ai = os.environ.get("LAST_AI_ENHANCEMENT")
    if last_ai is not None:
        cfg.ai_mode, cfg.provider, cfg.local_model = _ai_mode_from_setting(last_ai)
        print(f"Using previous AI_ENHANCEMENT: {last_ai} (from last session)")
    else:
        cfg.ai_mode, cfg.provider, cfg.local_model = transcriber.get_ai_enhancement_input()

    if cfg.ai_mode is not None:
        prompt_text, prompt_label = _select_prompt_interactively(transcriber)
        if prompt_text is None:
            cfg.ai_mode = None
        else:
            cfg.prompt_text = prompt_text
            used_fields["PROMPT"] = prompt_label

    if cfg.ai_mode == AIEnhancementMode.API:
        cfg.api_key = _resolve_api_key(cfg.provider)
        if cfg.api_key is None:
            cfg.ai_mode = None

    if cfg.ai_mode == AIEnhancementMode.API:
        used_fields["AI_ENHANCEMENT"] = cfg.provider.key
    elif cfg.ai_mode == AIEnhancementMode.LOCAL:
        used_fields["AI_ENHANCEMENT"] = cfg.local_model if cfg.local_model else "local"
    else:
        used_fields["AI_ENHANCEMENT"] = "n"

    return cfg

#########################################
## PROFILE-DRIVEN CONFIGURATION
#########################################

def _configure_from_profile(transcriber, profile_name):
    """Gather all session settings from the loaded profile's environment variables.

    Missing or invalid values fall back to interactive prompts.
    """
    cfg = SessionConfig(used_fields=transcriber.DEFAULT_FIELDS.copy())

    repeat_invocation = os.environ.get("_REPEAT_INVOCATION", "") == "1"
    # On repeat, ignore the profile URL so the user is asked for a fresh one
    cfg.url = transcriber.URL_PLACEHOLDER if repeat_invocation else os.getenv("URL")

    if cfg.url and cfg.url != transcriber.URL_PLACEHOLDER:
        if transcriber.is_youtube_video_id(cfg.url):
            cfg.url = transcriber.construct_youtube_url(cfg.url)
            print(f"Detected video ID from profile, using: {cfg.url}")
            try:
                YouTube(cfg.url, "WEB")
                print(f"Loaded YOUTUBE_URL: {cfg.url} (from {profile_name})")
            except RegexMatchError:
                print("Error creating YouTube object. Please enter a valid URL or video ID.")
                cfg.url = input()
        elif transcriber.is_web_url(cfg.url):
            if transcriber.is_youtube_url(cfg.url):
                try:
                    YouTube(cfg.url, "WEB")
                    print(f"Loaded YOUTUBE_URL: {cfg.url} (from {profile_name})")
                except RegexMatchError:
                    # Use ffprobe to determine if it's a valid audio/video file
                    if transcriber.get_file_format(cfg.url):
                        cfg.is_local_file = True
                        print(f"Loaded local file: {cfg.url} (from {profile_name})")
                    else:
                        print("Incorrect value for YOUTUBE_URL in config.env. "
                              "Please enter a valid YouTube video URL, video ID, or local file path: ")
                        cfg.url = input()
            else:
                print("Error: Only YouTube URLs supported for web inputs")
        elif transcriber.is_valid_media_file(cfg.url):
            cfg.is_local_file = True
            print(f"Loaded local file: {cfg.url} (from {profile_name})")
        else:
            print("Invalid input. Please enter valid YouTube URL, video ID, or local file path")
            cfg.url, cfg.is_local_file = transcriber.prompt_for_source()

    if not cfg.is_local_file:
        cfg.download_video = _bool_from_profile_env(
            transcriber, "DOWNLOAD_VIDEO", profile_name,
            "Download video stream? (y/N): ", default='n')

        if cfg.download_video:
            cfg.no_audio_in_video = _bool_from_profile_env(
                transcriber, "NO_AUDIO_IN_VIDEO", profile_name,
                "Download the video without audio? (y/N): ", default='n', prompt_if_missing=False)

            resolution = os.getenv("RESOLUTION")
            if resolution:
                resolution = resolution.lower()  # Convert to lowercase for easier comparison
                if resolution not in Resolution.values():
                    if resolution.isdigit():
                        if int(resolution) > 0:
                            resolution += "p"
                            print(f"Loaded RESOLUTION: {resolution} (from {profile_name})")
                        else:
                            print(f"Invalid value for RESOLUTION in .env: {resolution}")
                            resolution = None
                    elif not (resolution.endswith("p") and resolution[:-1].isdigit()):
                        print(f"Invalid value for RESOLUTION in .env: {resolution}")
                        resolution = Resolution.FETCH.value
                else:
                    print(f"Loaded RESOLUTION: {resolution} (from {profile_name})")
            cfg.resolution = resolution

    if cfg.download_video and not cfg.is_local_file and cfg.resolution == Resolution.FETCH.value:
        try:
            yt = YouTube(cfg.url, "WEB")
        except RegexMatchError:
            print("Error: Invalid YouTube URL.")
            sys.exit()
        cfg.selected_res = _prompt_resolution_selection(transcriber, yt)

    if not cfg.is_local_file:
        cfg.download_audio = _bool_from_profile_env(
            transcriber, "DOWNLOAD_AUDIO", profile_name,
            "Download audio only? (y/N): ", default='n', prompt_if_missing=False)

    cfg.transcribe_audio = _bool_from_profile_env(
        transcriber, "TRANSCRIBE_AUDIO", profile_name,
        "Transcribe the audio? (Y/n): ", default='y')

    model_choice = os.getenv("MODEL_CHOICE")
    if model_choice and cfg.transcribe_audio:
        # Validate model_choice from .env
        if model_choice.lower() not in ModelSize.valid_choices():
            print(f"Invalid value for MODEL_CHOICE in .env: {model_choice}")
            model_choice = transcriber.get_model_choice_input()  # Prompt for valid input
        else:
            print(f"Loaded MODEL_CHOICE: {model_choice} (from {profile_name})")
    elif cfg.transcribe_audio:
        model_choice = transcriber.get_model_choice_input()
    cfg.model_choice = model_choice or ""

    if cfg.transcribe_audio:
        model_enum = ModelSize.from_choice(cfg.model_choice)
        cfg.model_name = model_enum.value

        if cfg.url == transcriber.URL_PLACEHOLDER:
            cfg.url, cfg.is_local_file = transcriber.prompt_for_source()

        target_language = os.getenv("TARGET_LANGUAGE")
        if target_language:
            if target_language.lower() not in whisper.tokenizer.LANGUAGES:
                print(f"Invalid value for TARGET_LANGUAGE in .env: {target_language}")
                target_language = transcriber.get_target_language_input()
            else:
                print(f"Loaded TARGET_LANGUAGE: {target_language} (from {profile_name})")
        else:
            target_language = transcriber.get_target_language_input()
        cfg.target_language = target_language

        use_en_model_str = os.getenv("USE_EN_MODEL")
        if use_en_model_str:
            if use_en_model_str.lower() in YesNo.YES.value:
                cfg.use_en_model = True
                print(f"Loaded USE_EN_MODEL: {use_en_model_str} (from {profile_name})")
            elif use_en_model_str.lower() in YesNo.NO.value:
                cfg.use_en_model = False
                print(f"Loaded USE_EN_MODEL: {use_en_model_str} (from {profile_name})")
            else:
                print(f"Invalid value for USE_EN_MODEL in .env: {use_en_model_str}")
                if model_enum in ModelSize.standard_models() and cfg.target_language == transcriber.DEFAULT_LANGUAGE:
                    cfg.use_en_model = transcriber.get_yes_no_input(
                        "Use English-specific model? (Recommended only if the video is originally in English) (y/N): ",
                        default='n')

    # --- AI Enhancement ---
    ai_enhancement_str = os.getenv("AI_ENHANCEMENT")
    if ai_enhancement_str and cfg.transcribe_audio:
        cfg.ai_mode, cfg.provider, cfg.local_model = _ai_mode_from_setting(ai_enhancement_str)
        print(f"Loaded AI_ENHANCEMENT: {ai_enhancement_str} (from {profile_name})")
    elif cfg.transcribe_audio:
        cfg.ai_mode, cfg.provider, cfg.local_model = transcriber.get_ai_enhancement_input()

    if cfg.ai_mode is not None and cfg.transcribe_audio:
        prompt_env = (os.getenv("PROMPT") or "").strip()
        available_prompts = transcriber.list_available_prompts()
        if prompt_env and prompt_env in available_prompts:
            cfg.prompt_text = transcriber.load_prompt_file(prompt_env)
            print(f"Loaded PROMPT: {prompt_env} (from {profile_name})")
        elif prompt_env and prompt_env + transcriber.TXT_EXT in available_prompts:
            cfg.prompt_text = transcriber.load_prompt_file(prompt_env + transcriber.TXT_EXT)
            print(f"Loaded PROMPT: {prompt_env} (from {profile_name})")
        else:
            if prompt_env:
                print(f"Prompt file not found: {prompt_env}")
            prompt_text, _ = _select_prompt_interactively(transcriber)
            if prompt_text is None:
                cfg.ai_mode = None
            else:
                cfg.prompt_text = prompt_text

    if cfg.ai_mode == AIEnhancementMode.API and cfg.transcribe_audio:
        cfg.api_key = _resolve_api_key(cfg.provider)
        if cfg.api_key is None:
            cfg.ai_mode = None

    return cfg


#########################################
## PIPELINE EXECUTION
#########################################

def _create_youtube_with_recovery(transcriber, cfg):
    """Create the YouTube object for cfg.url, re-prompting on failure.

    Sets cfg.yt and cfg.video_title on success. May flip cfg.is_local_file to
    True (leaving cfg.yt unset) if the user switches to a local file.
    """
    retry_prompt = "\nEnter a different YouTube video URL, video ID, or local file path: "
    while True:
        try:
            yt = transcriber.create_youtube_object(cfg.url)
            try:
                video_title = yt.title
                yt.check_availability()
            except (AttributeError, OSError, VideoUnavailable, VideoPrivate, VideoRegionBlocked) as e:
                print(f"\nError with URL '{cfg.url}': {str(e)}")
                print("The video is unavailable or inaccessible.")
                cfg.url, cfg.is_local_file = transcriber.prompt_for_source(retry_prompt)
                if cfg.is_local_file:
                    return
                continue
            cfg.yt = yt
            cfg.video_title = video_title
            return
        except (RegexMatchError, VideoUnavailable, VideoPrivate, VideoRegionBlocked, OSError, ValueError) as e:
            print(f"\nError with URL '{cfg.url}': {str(e)}")
            print("The URL appears to be invalid or the video is unavailable.")
            cfg.url, cfg.is_local_file = transcriber.prompt_for_source(retry_prompt)
            if cfg.is_local_file:
                return


def _run_pipeline(transcriber, cfg):
    """Execute the session: download streams, transcribe, enhance, and save."""
    if not cfg.is_local_file and cfg.url == transcriber.URL_PLACEHOLDER:
        cfg.url, cfg.is_local_file = transcriber.prompt_for_source()

    if not cfg.is_local_file:
        _create_youtube_with_recovery(transcriber, cfg)

    if cfg.is_local_file:
        cfg.video_title = os.path.splitext(os.path.basename(cfg.url))[0]

    filename_base = transcriber.sanitize_filename(cfg.video_title)
    display_source = os.path.abspath(cfg.url) if cfg.is_local_file else cfg.url
    print(f"\nProcessing: {display_source}...")

    video_filename = filename_base + transcriber.MP4_EXT
    audio_filename = filename_base + transcriber.MP3_EXT
    video_temp_dir = None
    video_path = None

    if cfg.download_video and not cfg.is_local_file:
        yt = cfg.yt
        match cfg.resolution:
            case Resolution.HIGHEST.value:
                streams = transcriber.get_sorted_video_streams(yt)
                stream = streams[0] if streams else None

            case Resolution.LOWEST.value:
                streams = transcriber.get_sorted_video_streams(yt)
                stream = streams[-1] if streams else None

            case Resolution.FETCH.value:
                stream = yt.streams.filter(only_video=True, resolution=cfg.selected_res).first()

            case _:
                streams = transcriber.sort_streams_by_resolution(
                    yt.streams.filter(only_video=True, resolution=cfg.resolution))
                stream = streams[0] if streams else None

        # If the requested resolution is not found, prompt the user
        if stream is None:
            print("Requested resolution not found, left null, or invalid.")
            cfg.selected_res = _prompt_resolution_selection(transcriber, yt)
            stream = yt.streams.filter(only_video=True, resolution=cfg.selected_res).first()
            if stream is None:
                print(f"Error: No suitable stream found for resolution {cfg.selected_res}. Exiting...")
                sys.exit()

        if cfg.no_audio_in_video:
            print(f"Downloading video stream ({stream.resolution} without audio)...")
            stream.download(output_path=transcriber.VIDEO_WITHOUT_AUDIO_DIR, filename=video_filename)
            file_path = os.path.abspath(os.path.join(transcriber.VIDEO_WITHOUT_AUDIO_DIR, video_filename))
            print(f"Video downloaded to {file_path}")
        else:
            video_temp_dir = os.path.join(transcriber.VIDEO_DIR, transcriber.TEMP_DIR)
            os.makedirs(video_temp_dir, exist_ok=True)
            stream.download(output_path=video_temp_dir, filename=video_filename)
            video_path = os.path.join(video_temp_dir, video_filename)
            print(f"Video downloaded to {video_path}")
    else:
        print("Skipping video download...")

    if cfg.download_audio:
        transcriber.download_audio_stream(cfg.yt, filename_base, is_temp=False)

    if cfg.download_video and not cfg.is_local_file and not cfg.no_audio_in_video:
        if not cfg.download_audio:
            audio_path, _ = transcriber.download_audio_stream(cfg.yt, filename_base, is_temp=True)
        else:
            audio_path = os.path.join(transcriber.AUDIO_DIR, audio_filename)

        output_path_combined = os.path.join(transcriber.VIDEO_DIR, video_filename)
        transcriber.combine_audio_video(video_path, audio_path, output_path_combined,
                cleanup_temp=not cfg.no_audio_in_video, temp_video_dir=video_temp_dir)

    if cfg.transcribe_audio:
        if cfg.is_local_file:
            if transcriber.is_valid_media_file(cfg.url):
                audio_file = cfg.url
            else:
                # Extract the audio track from a local video file
                try:
                    video = moviepy.editor.VideoFileClip(cfg.url)
                    audio_file = f"{filename_base}.mp3"
                    try:
                        video.audio.write_audiofile(audio_file)
                    finally:
                        video.close()
                except (IOError, OSError, ValueError) as e:
                    print(f"Error processing video file: {str(e)}")
                    sys.exit(1)
            file_path = cfg.url
        else:  # If it's not a local file, it's a YouTube video
            audio_file = os.path.join(transcriber.AUDIO_DIR, audio_filename)
            if not cfg.download_audio:
                # Download the audio stream to a temp location for transcription
                audio_file, _ = transcriber.download_audio_stream(cfg.yt, filename_base, is_temp=True)
            file_path = audio_file

        transcribed_text, language = transcriber.transcribe_audio_file(
            file_path, cfg.model_name, cfg.target_language
        )

        # --- AI Enhancement ---
        if cfg.ai_mode is not None and transcribed_text and transcribed_text.strip():
            print(f"\nEnhancing transcript with AI ({cfg.ai_mode.name.lower()})...")
            transcribed_text = transcriber.enhance_text(
                transcribed_text,
                cfg.ai_mode,
                cfg.prompt_text,
                api_key=cfg.api_key,
                provider=cfg.provider,
                local_model=cfg.local_model
            )

        # Create and open a txt file with the text
        if language == transcriber.DEFAULT_LANGUAGE:
            transcript_name = f"{filename_base}{transcriber.TXT_EXT}"
        else:
            transcript_name = f"{filename_base} [{language}]{transcriber.TXT_EXT}"
        transcriber.create_and_open_txt(transcribed_text, transcript_name)
        print(f"Saved transcript to {os.path.abspath(os.path.join(transcriber.TRANSCRIPT_DIR, transcript_name))}")
    else:
        print("Skipping transcription.")

    # Clean up the temp audio downloaded solely for transcription/combining
    temp_audio_path = os.path.join(transcriber.AUDIO_DIR, transcriber.TEMP_DIR)
    temp_audio_file = os.path.join(temp_audio_path, filename_base + transcriber.MP3_EXT)
    if (not cfg.is_local_file and not cfg.download_audio
            and (cfg.transcribe_audio or cfg.download_video)
            and not cfg.no_audio_in_video and os.path.exists(temp_audio_file)):
        os.remove(temp_audio_file)
        if os.path.exists(temp_audio_path) and not os.listdir(temp_audio_path):
            os.rmdir(temp_audio_path)
        print(f"Deleted audio residual in {temp_audio_file}")

    print("Tasks complete.")


#########################################
## SESSION WRAP-UP AND REPEAT
#########################################

def _ask_repeat(transcriber):
    """Ask the user whether to run again; the default flips to yes after the first repeat."""
    repeat_ask_count = int(os.environ.get("_REPEAT_ASK_COUNT", "0"))
    # On first ask (count 0), default to 'n'; on subsequent asks, default to 'y'
    default_repeat = 'y' if repeat_ask_count > 0 else 'n'
    prompt_text = "Run again? (Y/n): " if default_repeat == 'y' else "Run again? Hit Enter to repeat (y/N): "
    repeat = transcriber.get_yes_no_input(prompt_text, default=default_repeat)
    os.environ["_REPEAT_ASK_COUNT"] = str(repeat_ask_count + 1)
    return repeat, ("y" if repeat else "n")


def _finish_session(transcriber, cfg, load_profile, profile_name):
    """Handle profile creation and the "Run again?" repeat loop."""
    did_something_useful = cfg.download_audio or cfg.download_video or cfg.transcribe_audio
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
        if transcriber.get_yes_no_input("Do you want to create a profile from this session? (y/N): ", default='n'):
            transcriber.create_profile(cfg.used_fields)

    try:
        if repeat:
            if not load_profile:
                # Remember this session's answers so the repeat run can reuse them
                if cfg.ai_mode == AIEnhancementMode.API:
                    last_ai = cfg.provider.key
                elif cfg.ai_mode == AIEnhancementMode.LOCAL:
                    last_ai = cfg.local_model if cfg.local_model else "local"
                else:
                    last_ai = "n"
                os.environ.update({
                    "LAST_DOWNLOAD_VIDEO": "y" if cfg.download_video else "n",
                    "LAST_NO_AUDIO_IN_VIDEO": "y" if cfg.no_audio_in_video else "n",
                    "LAST_RESOLUTION": cfg.resolution or "",
                    "LAST_DOWNLOAD_AUDIO": "y" if cfg.download_audio else "n",
                    "LAST_TRANSCRIBE_AUDIO": "y" if cfg.transcribe_audio else "n",
                    "LAST_MODEL_CHOICE": cfg.model_choice or "",
                    "LAST_TARGET_LANGUAGE": cfg.target_language or "",
                    "LAST_USE_EN_MODEL": "y" if cfg.use_en_model else "n",
                    "LAST_AI_ENHANCEMENT": last_ai,
                })
            os.environ["_REPEAT_INVOCATION"] = "1"
            os.environ["URL"] = transcriber.URL_PLACEHOLDER
            if load_profile and profile_name:
                os.environ["_REPEAT_PROFILE_NAME"] = profile_name
            print("Repeating session as requested...")
            main()
        else:
            _clear_session_env()
    except Exception:
        _clear_session_env()


#########################################
## MAIN EXECUTION
#########################################

def main():
    """Main entry point - handles user interaction and orchestrates the transcription workflow."""
    transcriber = YouTubeTranscriber()

    if not transcriber.check_dependencies():
        print("Missing required dependencies. Please install them and try again.")
        sys.exit(1)

    for directory in (transcriber.AUDIO_DIR, transcriber.VIDEO_DIR,
                      transcriber.TRANSCRIPT_DIR, transcriber.VIDEO_WITHOUT_AUDIO_DIR):
        if not transcriber.ensure_directory_exists(directory):
            print(f"Error: Cannot create required directory {directory}")
            print("Please check permissions and try again.")
            sys.exit(1)

    load_profile, profile_name = _select_profile(transcriber)

    if load_profile:
        cfg = _configure_from_profile(transcriber, profile_name)
    else:
        cfg = _configure_interactive(transcriber)

    _run_pipeline(transcriber, cfg)
    _finish_session(transcriber, cfg, load_profile, profile_name)


if __name__ == "__main__":
    main()

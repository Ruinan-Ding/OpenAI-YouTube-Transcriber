"""What the user is asked, and what an answer names: a video, a file, a language."""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from typing import cast
from urllib.parse import parse_qs, urlparse

import whisper

from .base import TranscriberBase
from .common import (AIEnhancementMode, LocalModel, ModelSize, Provider,
                     SourceEntry, YesNo, _is_number, error)


class InputsMixin(TranscriberBase):
    """What the user is asked, and what an answer names."""

    YOUTUBE_HOSTS = ('youtube.com', 'www.youtube.com', 'm.youtube.com',
                     'music.youtube.com', 'youtube-nocookie.com',
                     'www.youtube-nocookie.com', 'youtu.be', 'www.youtu.be')
    # Paths naming one video. Playlist and channel URLs must not match: yt-dlp
    # would download every entry into the single output path we hand it.
    # /embed/videoseries is a playlist wearing an embed path, so it is excluded
    # here rather than left to YDL_OPTS' noplaylist to catch.
    YOUTUBE_VIDEO_PATH = re.compile(r'^/(shorts|embed|live|v)/(?!videoseries)[^/]')
    DEFAULT_SOURCE_PROMPT = ("Enter the YouTube video URL, video ID, local file path, "
                             "or S to refine a transcript (several separated by "
                             "commas or spaces run in turn): ")

    def is_web_url(self, input_str: str) -> bool:
        """Check if string is a valid http/https URL (no network calls)."""
        try:
            result = urlparse(input_str)
            return all([result.scheme in ['http', 'https'], result.netloc])
        except ValueError:
            return False

    def add_scheme_if_missing(self, text: str) -> str:
        """Accept a YouTube address typed without 'https://'.

        Matching the whole host keeps local file paths out of it.
        """
        if text.split('/', 1)[0].lower() in self.YOUTUBE_HOSTS:
            return 'https://' + text
        return text

    def is_youtube_video_id(self, text: str) -> bool:
        """Check for a valid 11-character video ID (alphanumerics, dash, underscore)."""
        if len(text) != 11:
            return False
        return bool(re.match(r'^[a-zA-Z0-9_-]{11}$', text))

    def construct_youtube_url(self, video_id: str) -> str:
        """Build a full YouTube URL from a video ID."""
        return f"https://www.youtube.com/watch?v={video_id}"

    def is_youtube_url(self, url: str) -> bool:
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

    def get_yes_no_input(self, prompt_text: str, default: str = "y") -> bool:
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

    def resolve_source(self, text: str, origin: str | None = None) -> tuple[str, bool] | None:
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

    def source_entries(self, text: str, origin: str | None = None) -> list[SourceEntry]:
        """Resolve a source answer into the passes it asks for. [] if one fails.

        An answer is a list: videos, media files and transcripts in any order,
        each done in turn. An entry is (url, is_local_file, refine_sources),
        and a set refine_sources is a pass with no media at all - 's', which
        asks which transcripts, or a .txt path naming them outright.
        """
        entries: list[SourceEntry] = []
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

    def prompt_for_sources(self, prompt_text: str | None = None) -> list[SourceEntry]:
        """Prompt until every entry of the answer is usable. Returns the entries."""
        while True:
            entries = self.source_entries(
                input(prompt_text or self.DEFAULT_SOURCE_PROMPT).strip())
            if entries:
                return entries

    def prompt_for_source(self, prompt_text: str,
                          allow_skip: bool = False) -> tuple[str, bool] | None:
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

    def get_model_choice_input(self) -> str:
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
    def resolve_transcript_language(detected: str | None,
                                    fallback: str | None) -> str | None:
        """Reduce a langdetect code to one Whisper knows, else `fallback`.

        Keeps region tags ('zh-cn') and detection failures out of the filename.
        """
        base = (detected or "").split('-')[0]
        return base if base in whisper.tokenizer.LANGUAGES else fallback

    @staticmethod
    def normalize_language(text: str) -> str | None:
        """Resolve a language code or name to Whisper's 2-letter code, or None.

        Must return a code: callers compare against DEFAULT_LANGUAGE to pick .en models.
        """
        lower = text.strip().lower()
        code = whisper.tokenizer.TO_LANGUAGE_CODE.get(lower, lower)
        return code if code in whisper.tokenizer.LANGUAGES else None

    @staticmethod
    def split_entries(text: str | None,
                      is_whole: Callable[[str], object] | None = None) -> list[str]:
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
        entries: list[str] = []
        for part in text.split(','):
            part = part.strip()
            if not part:
                continue
            if is_whole and is_whole(part):
                entries.append(part)
            else:
                entries.extend(part.split())
        return entries

    def normalize_languages(self, text: str | None) -> tuple[list[str], list[str]]:
        """Split a comma- or space-separated answer into Whisper codes.

        Returns (codes, unknown). Order is kept and repeats collapse, so
        "en, English, fr" asks for two transcripts rather than three. 'auto',
        the language spoken, is kept as it is.
        """
        def code_of(piece: str) -> str | None:
            if piece.strip().lower() == self.AUTO_LANGUAGE:
                return self.AUTO_LANGUAGE
            return self.normalize_language(piece)

        codes: list[str] = []
        unknown: list[str] = []
        for part in self.split_entries(text, lambda piece: code_of(piece) is not None):
            code = code_of(part)
            if code is None:
                unknown.append(part)
            elif code not in codes:
                codes.append(code)
        return codes, unknown

    def get_target_language_input(self) -> str:
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

    def get_source_language_input(self) -> str:
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

    def _validate_hf_model(self, model_name: str) -> bool:
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

    def get_ai_provider_input(self) -> tuple[AIEnhancementMode, Provider | None, str | None]:
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

    def _resolve_prompt_choice(self, token: str, prompts: list[str]) -> str | None:
        """One entry of a selection: a number, a name in Prompt/, or a path."""
        token = token.strip()
        if _is_number(token) and 1 <= int(token) <= len(prompts):
            return prompts[int(token) - 1]
        for candidate in (token, token + self.TXT_EXT):
            if candidate in prompts:
                return candidate
        return token if os.path.exists(os.path.expanduser(token)) else None

    def get_prompt_input(self) -> tuple[list[str] | None, str | None]:
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
                return (cast('list[str]', chosen), None)
            print("Invalid selection. Please try again.")

    def _get_inline_prompt(self) -> tuple[None, str | None]:
        """Read a multi-line prompt from the console; (None, text) or (None, None)."""
        print("Enter your custom prompt (press Enter twice to finish):")
        lines: list[str] = []
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

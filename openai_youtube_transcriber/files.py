"""The app's folders, and the text files it reads and writes in them."""

from __future__ import annotations

import codecs
import importlib.util
import itertools
import os
import re
import shutil
import subprocess
import sys
from typing import cast

from .base import TranscriberBase
from .common import Prompt, Resolution, _is_number, error


class FilesMixin(TranscriberBase):
    """The app's folders, and the text files it keeps in them."""

    # Filename tag for a prompt that names no description of its own
    REFINED_TAG = " - Refined"

    def ensure_directory_exists(self, directory_path: str) -> bool:
        """Create directory if it doesn't exist. Returns True on success."""
        try:
            os.makedirs(directory_path, exist_ok=True)
            return True
        except OSError as e:
            error(f"Error creating directory {directory_path}: {str(e)}")
            return False

    def prompt_dirs(self) -> list[str]:
        """Where Prompt/ may be: beside the script, under the working directory,
        and where an installed copy keeps the prompts it shipped with.

        Every other folder is made relative to the working directory, and that
        is where an installed `openai-youtube-transcriber` keeps the user's own
        prompts; the copy beside the script is the repo's own, and still comes
        first. The shipped ones come last, so a prompt edited in the working
        directory is not shadowed by the original it was copied from.
        """
        # The script, and the repo's OpenAIYouTubeTranscriber/ beside it, are
        # one folder up from this package: beside this file is inside it
        package = os.path.dirname(os.path.abspath(__file__))
        beside = os.path.join(os.path.dirname(package), self.PROMPT_DIR)
        return [d for d in dict.fromkeys((beside, os.path.abspath(self.PROMPT_DIR),
                                          self.installed_prompt_dir()))
                if d and os.path.isdir(d)]

    @classmethod
    def installed_prompt_dir(cls) -> str | None:
        """The folder an installed copy's shipped prompts are in, or None."""
        return cls.installed_data_dir(cls.PROMPT_PACKAGE)

    @staticmethod
    def installed_data_dir(package: str) -> str | None:
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

    def seed_sample_profiles(self) -> None:
        """Copy the shipped sample profiles into a Profile/ that does not exist yet.

        An installed copy has them in site-packages, and a profile is loaded,
        listed and saved in the working directory's Profile/. Copied there on
        first run, they are the user's to edit as a checkout's are. A Profile/
        that exists is never touched, so one the user emptied stays empty.
        """
        if os.path.exists(self.PROFILE_DIR):
            return
        source = self.installed_data_dir(self.PROFILE_PACKAGE)
        if source is None:
            return
        samples = sorted(name for name in os.listdir(source)
                         if name.startswith(self.PROFILE_PREFIX)
                         and name.endswith(self.ENV_EXT))
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

    def list_available_prompts(self) -> list[str]:
        """List non-empty .txt files in the Prompt/ directory."""
        found: dict[str, bool] = {}
        for prompt_dir in self.prompt_dirs():
            for f in os.listdir(prompt_dir):
                if (f.endswith(self.TXT_EXT) and f not in found
                        and os.path.getsize(os.path.join(prompt_dir, f)) > 0):
                    found[f] = True
        return sorted(found)

    def load_prompt_file(self, filename: str) -> str:
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
    def decode_text(data: bytes) -> str:
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

    def read_text_file(self, path: str, what: str) -> str | None:
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

    def is_transcript_file(self, path: str) -> bool:
        """Is this an existing .txt file, i.e. a transcript rather than media?"""
        return bool(path) and path.lower().endswith(self.TXT_EXT) and \
            os.path.isfile(os.path.expanduser(path))

    def transcript_sources(self, text: str) -> list[str] | None:
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

    def named_transcripts(self, text: str | None) -> list[str] | None:
        """The transcripts a source answer names, or None if it names media.

        's' asks which; a path to a .txt, or several of them, names them
        outright. Both are refine-only runs: nothing is downloaded and
        nothing is transcribed.
        """
        text = (text or "").strip()
        if text.lower() in self.SKIP_SOURCE and not os.path.exists(text):
            return self.select_transcripts() or None
        return self.transcript_sources(text)

    def list_available_transcripts(self) -> list[str]:
        """Transcripts to refine, Transcript/Raw/ first.

        Raw/ holds the originals earlier refinements moved out of the way, so
        it is the first place to look for something to try another prompt on.
        """
        found: list[str] = []
        for folder in (self.RAW_TRANSCRIPT_DIR, self.TRANSCRIPT_DIR):
            if not os.path.isdir(folder):
                continue
            found.extend(os.path.join(folder, name) for name in sorted(os.listdir(folder))
                         if name.endswith(self.TXT_EXT)
                         and os.path.isfile(os.path.join(folder, name)))
        return found

    def _resolve_transcript_choice(self, token: str, found: list[str]) -> str | None:
        """One entry of a selection: a number in the list, or a path."""
        token = token.strip()
        if _is_number(token) and 1 <= int(token) <= len(found):
            return found[int(token) - 1]
        return token if self.is_transcript_file(token) else None

    def select_transcripts(self) -> list[str]:
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
                return [os.path.expanduser(path) for path in cast('list[str]', chosen)]
            print("Invalid selection. Please try again.")

    def read_transcript(self, path: str) -> str:
        """Read a transcript to refine. Empty string if unreadable or empty."""
        content = self.read_text_file(path, "transcript")
        if content is None:
            return ""
        content = content.strip()
        if not content:
            print(f"Warning: Transcript is empty: {path}")
        return content

    def startfile(self, fn: str) -> None:
        """Open file with system default app (cross-platform)."""
        try:
            # sys.platform rather than os.name: the same test, and the one a
            # type checker knows os.startfile exists behind
            if sys.platform == 'win32':
                os.startfile(fn)
            elif os.name == 'posix':
                opener = 'open' if sys.platform == 'darwin' else 'xdg-open'
                # a non-zero exit from the opener is not our problem
                subprocess.run([opener, fn], check=False)
        except OSError as e:
            # A headless box has no xdg-open. The transcript is already saved,
            # and the rest of a batch is still owed.
            print(f"Note: could not open {os.path.basename(fn)}: {str(e)}")

    def sanitize_filename(self, text: str) -> str:
        """Strip invalid characters from filename; never returns an empty name."""
        cleaned = "".join(c for c in text if c.isalnum() or c in "._- ").strip()
        return cleaned or "untitled"

    def save_transcript(self, text: str, filename: str, output_dir: str,
                        open_after: bool = True) -> bool:
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
    def write_text_atomically(path: str, text: str) -> None:
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
    def quality_tag(*qualities: str | None) -> str:
        """Bracketed quality tag for a media filename, e.g. " [720p low]".

        The best available needs no label, so "highest" and blanks are dropped
        and a file is only marked where it differs from the default. The tag
        also keeps a second run at another quality from silently reusing the
        first run's file, which yt-dlp skips as already downloaded.
        """
        parts = [str(quality) for quality in qualities
                 if quality and str(quality) != Resolution.HIGHEST.value]
        return f" [{' '.join(parts)}]" if parts else ""

    def prompt_suffix(self, prompt_label: str | None) -> str:
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

    def tagged_prompts(self, prompts: list[Prompt] | None) -> list[tuple[str, str, str]]:
        """(text, label, tag) per prompt, with the filename tags made distinct.

        Two prompts can want the same tag - prompt0-translator.txt and
        prompt1-translator.txt both read as "translator" - and the second would
        otherwise overwrite the first.
        """
        tagged: list[tuple[str, str, str]] = []
        seen: set[str] = set()
        for text, label in prompts or []:
            tag = self.prompt_suffix(label)
            base, n = tag, 2
            while tag in seen:
                tag, n = f"{base} {n}", n + 1
            seen.add(tag)
            tagged.append((text, label, tag))
        return tagged

    @staticmethod
    def is_refinement(original_text: str | None, text: str) -> bool:
        """Did enhancement actually change the words?

        Compared on words rather than characters: the chunker rejoins on blank
        lines or spaces, and whitespace alone is not a refinement.
        """
        return original_text is not None and original_text.split() != text.split()

    def save_final_transcript(self, text: str, filename: str, original_text: str | None = None,
                              original_filename: str | None = None, keep_original: bool = True,
                              open_after: bool = True, output_dir: str | None = None) -> bool:
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
        if (keep_original and original_text is not None
                and self.is_refinement(original_text, text)):
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

    def list_profiles(self) -> list[str]:
        """List profile files in the Profile/ directory, sorted by name.

        Accepts: profile.txt, profile<number>.txt, profile-<desc>.txt,
        profile<number>-<desc>.txt
        """
        if not os.path.exists(self.PROFILE_DIR):
            return []
        pattern = rf"^{re.escape(self.PROFILE_PREFIX)}(?:\d+)?(?:-.*)?{re.escape(self.ENV_EXT)}$"
        return sorted(f for f in os.listdir(self.PROFILE_DIR) if re.match(pattern, f))

    def create_profile(self, profile_fields: dict[str, str]) -> None:
        """Save current session settings as a reusable profile file."""
        if not os.path.exists(self.PROFILE_DIR):
            print(f"Creating profile directory: {self.PROFILE_DIR}")
            os.makedirs(self.PROFILE_DIR, exist_ok=True)

        existing_profiles = self.list_profiles()
        num_pattern = (rf"^{re.escape(self.PROFILE_PREFIX)}(?P<num>\d+)"
                       rf"(?:-.*)?{re.escape(self.ENV_EXT)}$")
        existing_numbers: list[int] = []
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
    def env_value(value: str | None) -> str:
        """A profile value written so that dotenv reads back exactly it.

        Unquoted, " #" starts a comment, ${...} expands and edge spaces are
        dropped: "/tmp/Part #2.mp3" came back as "/tmp/Part". Such a value is
        single-quoted, which _read_profile reads literally, with its
        backslashes and quotes escaped; anything else is left as it was, so
        a profile stays as plain to edit as before.
        """
        text = "" if value is None else str(value)
        if text == text.strip() and not re.search(r"[#'\"$\n\r]", text):
            return text
        return "'" + text.replace("\\", "\\\\").replace("'", "\\'") + "'"

    def verify_file_writable(self, file_path: str) -> bool:
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

    def get_free_disk_space(self, directory: str) -> int | None:
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

"""Choosing a profile, and reading one."""

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING

from dotenv import dotenv_values, load_dotenv
from dotenv.parser import parse_stream

from .answers import _Answers, _Profile, _Remembered
from .common import YesNo, _is_number
from .config import Session

if TYPE_CHECKING:
    from .transcriber import YouTubeTranscriber


def _prompt_profile_selection(transcriber: YouTubeTranscriber, profiles: list[str]) -> str | None:
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


def _profile_file(transcriber: YouTubeTranscriber, answer: str) -> tuple[str, str] | None:
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


def _select_profile(transcriber: YouTubeTranscriber, session: Session) -> _Answers:
    """Decide whether to run from a profile, and load it if so.

    A repeat round reloads the profile it ran under; otherwise config.txt's
    LOAD_PROFILE answers, and failing that the user picks from a list.
    Returns where the round's answers come from: a _Profile, or what the
    round before remembered.
    """
    def load(name: str, path: str) -> _Profile:
        return _Profile(name, _read_profile(path), session)

    def chosen(name: str) -> _Answers:
        """The profile picked from the list, loaded."""
        found = _profile_file(transcriber, name)
        if found is None:
            # Listed, but not a file to read: a folder named like a profile,
            # or one deleted while the list was on screen
            print(f"Profile not found: {name}. Using interactive mode.")
            return _Remembered(session)
        answers = load(*found)
        print(f"Loaded profile: {name}")
        return answers

    # Repeat of a profile-driven session: reload the same profile
    if session.repeat and session.profile:
        found = _profile_file(transcriber, session.profile)
        if found:
            answers = load(*found)
            print(f"Loaded profile (repeat): {found[0]}")
            return answers
        print(f"Profile not found for repeat: {session.profile}. Falling back to selection.")
    # Repeat of an interactive session: stay interactive, with its answers
    elif session.repeat:
        return _Remembered(session)

    config_env_path = os.path.join(transcriber.PROFILE_DIR, transcriber.CONFIG_ENV)

    if not os.path.exists(config_env_path):
        print(f"config.txt not found in the {transcriber.PROFILE_DIR} directory.")
        if not os.path.exists(transcriber.PROFILE_DIR):
            print("Switching to default/interactive mode.")
            return _Remembered(session)

        profiles = transcriber.list_profiles()
        if not profiles:
            print("No profiles found. Switching to default/interactive mode.")
            return _Remembered(session)

        print("Found existing profiles. Checking if you want to use one of them...")
        profile_name = _prompt_profile_selection(transcriber, profiles)
        if profile_name is None:
            print("Switching to default/interactive mode.")
            return _Remembered(session)

        return chosen(profile_name)

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
            answers = load(profile_name, profile_path)
            print(f"Loaded profile: {profile_name}")
            return answers
        print(f"Profile not found: {load_profile_str}. Using interactive mode.")
        return _Remembered(session)

    if lower_lp in YesNo.NO.value + YesNo.SKIP.value:
        print("Using default/interactive mode.")
        return _Remembered(session)

    # LOAD_PROFILE is yes/blank: offer the available profiles
    profiles = transcriber.list_profiles()
    if not profiles:
        print("No profiles found. Switching to default/interactive mode.")
        return _Remembered(session)

    profile_name = _prompt_profile_selection(transcriber, profiles)
    if profile_name is None:
        return _Remembered(session)

    return chosen(profile_name)


def _single_quoted(line: str) -> bool:
    """Whether one KEY=value line of a profile gives its value in single quotes."""
    text = re.sub(r'^export\s+', '', line.lstrip())
    _key, sep, value = text.partition('=')
    return bool(sep) and value.lstrip(' \t').startswith("'")


def _read_profile(path: str) -> dict[str, str]:
    """A profile's lines as a dict, a single-quoted value taken literally.

    As dotenv reads them, except that dotenv expands ${...} in
    every value however it is quoted: a saved PROMPT=/tmp/prompt-${COURSE}.txt
    came back naming another file. A value the app writes is single-quoted
    wherever dotenv would otherwise change it, and in single quotes it now
    means what it says, as in a shell; unquoted, ${HOME} still expands.
    """
    with open(path, encoding='utf-8') as handle:
        literal = {binding.key: _single_quoted(binding.original.string)
                   for binding in parse_stream(handle) if binding.key}
    raw = dotenv_values(path, interpolate=False)
    values = {key: raw[key] if literal.get(key) else value
              for key, value in dotenv_values(path).items()}
    return {key: value for key, value in values.items() if value is not None}

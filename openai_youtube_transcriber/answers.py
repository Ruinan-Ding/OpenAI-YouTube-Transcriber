"""Where a setting's answer comes from, and what a gap in it means."""

from __future__ import annotations

import enum
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Final

from .common import SourceEntry, YesNo
from .config import _PLACEMENTS, Session, SessionConfig
from .transcriber import YouTubeTranscriber


class _Gap(enum.Enum):
    """What a gap in the answers can mean besides an answer: ASK."""
    ASK = enum.auto()


# A gap the question is asked for, rather than one taken as a stated answer.
# One member of its own enum, so that a type checker tells it from the
# answers it stands beside.
ASK: Final = _Gap.ASK


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
    absent: str | _Gap = ASK
    # What the field left blank means, the same way
    blank: str | _Gap = ASK
    # The field's pre-1.2 name, read when this one is not set
    legacy: str | None = None
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
    # Settled after the round rather than before it
    Setting("REPEAT"),
    # Not a profile field: a profile carries the placement answers themselves,
    # and this is the one question a session asks in their place
    Setting("PLACEMENT"),
) + tuple(
    # A placement left out keeps the default and one left blank asks, as 'y'
    # does, for the name or the folder itself
    Setting(f"{prefix}_{suffix}", absent="n", blank="", one_video=suffix == "RENAME")
    for _stem, prefix, _label, _dir in _PLACEMENTS for suffix in ("RENAME", "PATH"))}


# What a profile describes a session with. Anything else in one is
# configuration, as config.txt's lines are: see _Profile.
_PROFILE_FIELDS = frozenset(SETTINGS) | {"URL"} | {
    setting.legacy for setting in SETTINGS.values() if setting.legacy}


class _Answers:
    """Where a session's answers are kept: a profile, or the last round's.

    What each setting means is decided once, by SETTINGS and _configure; this
    only reads them. `verb` and `origin` word the line reporting one.
    """
    verb: str
    origin: str
    session: Session
    # Whether a round answered this way is offered to be saved as a profile:
    # one run from a profile already is one
    offers_profile = False

    def lookup(self, setting: Setting) -> tuple[str, str | None]:
        """(name, value) of the stored answer, the value None if there is none."""
        raise NotImplementedError

    def absent(self, setting: Setting) -> str | _Gap:
        """What no stored answer at all means: ASK, or the answer it stands for."""
        return ASK

    def sources(self, transcriber: YouTubeTranscriber) -> list[SourceEntry]:
        """The session's videos, files and transcripts."""
        return transcriber.prompt_for_sources()

    def report(self, name: str, shown: str) -> None:
        print(f"{self.verb} {name}: {shown} (from {self.origin})")

    def invalid(self, name: str, value: str) -> None:
        print(f"Invalid value for {name}: {value} (from {self.origin})")

    def ignored(self, field: str, why: str) -> None:
        """Say that a stored answer has no part in this run, and why."""
        _name, value = self.lookup(SETTINGS[field])
        value = (value or "").strip()
        # A no turns nothing on, so there is nothing for it to be ignored for
        if value and value.lower() not in YesNo.all_no_and_skip():
            print(f"Ignoring {field}={value} (from {self.origin}): {why}")

    def carry(self, cfg: SessionConfig) -> None:
        """Hand the "Run again?" round what it needs from this one."""
        raise NotImplementedError


class _Profile(_Answers):
    """A profile: the fields it describes a session with.

    Its other lines - AI_PROVIDER, MODEL, API_KEY, whatever config.txt could
    carry - are configuration, which the enhancement backends read from the
    environment, and go there, over config.txt's own, as the whole profile
    used to. Only configuration does: a field read from the environment was
    whoever's had set it, so a shell's URL answered for a profile naming none,
    and a field's meaning when left out was never reached.
    """
    verb = "Loaded"

    def __init__(self, name: str, values: Mapping[str, str],
                 session: Session | None = None) -> None:
        self.origin = name
        self.session = session or Session()
        self.fields: dict[str, str] = {}
        for key, value in values.items():
            if key in _PROFILE_FIELDS:
                self.fields[key] = value
            else:
                os.environ[key] = value

    def lookup(self, setting: Setting) -> tuple[str, str | None]:
        name, value = setting.field, self.fields.get(setting.field)
        if not value and setting.legacy and self.fields.get(setting.legacy):
            # Read under its own name, so what is reported is what the profile
            # says, rather than copied into the new one
            name, value = setting.legacy, self.fields[setting.legacy]
        stated = (value or "").strip().lower()
        if (setting.one_video and self.session.repeat and stated
                and stated not in YesNo.all_no_and_skip()):
            # A repeat takes a new URL and keeps the rest, but a name was for
            # the last round's video, and on this one it overwrote that file.
            # An interactive repeat drops it the same way: as if not there.
            print(f"Ignoring {name}={value} on a repeat: it named the last round's file.")
            return name, None
        return name, value

    def absent(self, setting: Setting) -> str | _Gap:
        return setting.absent

    def sources(self, transcriber: YouTubeTranscriber) -> list[SourceEntry]:
        # A repeat is the same settings over a new job, so the profile's own
        # URL is not reused. Either way the answer is settled here rather than
        # part way through the run: this is the only prompt that takes a list,
        # or 's' to refine a transcript instead of fetching anything.
        named = "" if self.session.repeat else (self.fields.get("URL") or "")
        entries: list[SourceEntry] = []
        if named and named != transcriber.URL_PLACEHOLDER:
            # Whether a video exists is settled by the metadata fetch in
            # _create_youtube_with_recovery, which can re-prompt
            entries = transcriber.source_entries(named, self.origin)
            if entries and all(entry[2] for entry in entries):
                self.report("URL", f"{sum(len(entry[2] or []) for entry in entries)} "
                                   "transcript(s) to refine")
        return entries or super().sources(transcriber)

    def carry(self, cfg: SessionConfig) -> None:
        # The next round reloads the profile, and asks for its sources
        self.session.profile = self.origin


class _Remembered(_Answers):
    """What an interactive round was told, for the "Run again?" round after it.

    Only the questions that round was asked are kept, so a gap is asked.
    """
    verb, origin = "Using previous", "last session"
    offers_profile = True

    def __init__(self, session: Session | None = None) -> None:
        self.session = session or Session()

    def lookup(self, setting: Setting) -> tuple[str, str | None]:
        return setting.field, self.session.remembered.get(setting.field)

    def ignored(self, field: str, why: str) -> None:
        # The last round's own answer, not a field anyone wrote: a local file
        # after a YouTube video has no stream to pick, and no need to say so
        pass

    def carry(self, cfg: SessionConfig) -> None:
        """Remember this round's answers for the next - only the ones it was
        asked. A refine-only round asks nothing about media, and a local file
        nothing about YouTube's transcripts; an "n" remembered for a question
        never put answered it in the next round, and a YouTube URL given then
        was neither downloaded nor transcribed."""
        fields, media = cfg.used_fields, bool(cfg.url)
        remembered: dict[str, str | bool | None] = {
            "DOWNLOAD_VIDEO": media and fields.get("DOWNLOAD_VIDEO"),
            "VIDEO_ONLY": media and fields.get("VIDEO_ONLY"),
            "DOWNLOAD_AUDIO": media and fields.get("DOWNLOAD_AUDIO"),
            "TRANSCRIBE_AUDIO": media and fields.get("TRANSCRIBE_AUDIO"),
            "DOWNLOAD_YT_TRANSCRIPT": media and not cfg.is_local_file and cfg.yt_transcript_raw,
            # The model, not the answer: Enter for base is "", and a blank
            # answer asked again every round
            "MODEL_CHOICE": media and cfg.transcribe_audio and cfg.model_name,
            "SOURCE_LANGUAGE": media and cfg.transcribe_audio and fields.get("SOURCE_LANGUAGE"),
            "TARGET_LANGUAGE": cfg.transcribe_audio and ",".join(cfg.target_languages or []),
            "USE_EN_MODEL": fields.get("USE_EN_MODEL"),
            "KEEP_TRANSCRIPT": fields.get("KEEP_TRANSCRIPT"),
            "AI_REFINEMENT": media and fields.get("AI_REFINEMENT"),
            "PLACEMENT": None if cfg.ask_placement is None else _yn(cfg.ask_placement),
            "VIDEO_RESOLUTION": cfg.video_resolution,
            "VIDEO_AUDIO_RESOLUTION": cfg.video_audio_resolution,
            "VIDEO_ONLY_RESOLUTION": cfg.video_only_resolution,
            "AUDIO_RESOLUTION": cfg.audio_resolution,
            "TRANSCRIBE_AUDIO_QUALITY": cfg.transcribe_audio_quality,
            "VIDEO_FORMAT": cfg.video_format,
            "VIDEO_ONLY_FORMAT": cfg.video_only_format,
            "AUDIO_FORMAT": cfg.audio_format,
        }
        # Where files go carries over, but not what they are called: a name
        # was for that video, and on the next it overwrites that video's file
        for stem, prefix, _label, _dir in _PLACEMENTS:
            remembered[f"{prefix}_PATH"] = getattr(cfg, f"{stem}_path", "")
        # An empty answer is no answer: kept, it skipped the question and then
        # filtered on "". What is left is the answers, which are text: a
        # False above is a question this round was not asked.
        self.session.remembered = {key: value for key, value in remembered.items()
                                   if isinstance(value, str) and value}
        self.session.profile = None


def _answer(answers: _Answers, field: str, ask: Callable[[], str],
            valid: Callable[[str], object] | None = None,
            shown: Callable[[str], str] | None = None) -> str:
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


def _yn(flag: object) -> str:
    """A yes/no as a profile writes it."""
    return "y" if flag else "n"


def _is_yes_no(answer: str) -> bool:
    """Whether an answer is a yes or a no. 'skip' declines, as it does elsewhere."""
    return answer.lower() in YesNo.YES.value + YesNo.all_no_and_skip()


def _yes_no(transcriber: YouTubeTranscriber, answers: _Answers, field: str, question: str,
            default: str = 'n') -> bool:
    """Settle a yes/no setting, asking `question` if it has no answer."""
    answer = _answer(answers, field,
                     lambda: _yn(transcriber.get_yes_no_input(question, default=default)),
                     valid=_is_yes_no)
    return answer.lower() in YesNo.YES.value

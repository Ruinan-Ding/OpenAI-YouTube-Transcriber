"""A session: its rounds, "Run again?", and the entry point."""

from __future__ import annotations

import itertools
import os
import sys

import yt_dlp

from .answers import _answer, _Answers, _is_yes_no, _yn
from .common import DownloadFailed, YesNo, error
from .config import Session, SessionConfig
from .pipeline import _run_pipeline
from .profiles import _select_profile
from .settings import INLINE_PROMPT, _configure
from .transcriber import YouTubeTranscriber


def _save_inline_prompts(transcriber: YouTubeTranscriber, cfg: SessionConfig) -> None:
    """Give each prompt typed at the console a file, so a profile can name it.

    PROMPT holds names, and a typed prompt has none: the profile said
    PROMPT=(inline), which named nothing, and replaying it asked for a prompt
    again. The text goes into Prompt/ as prompt<N>.txt, which tags its output
    " - Refined" as the typed prompt did; one already saved there is reused.
    """
    if not any(label == INLINE_PROMPT for _text, label in cfg.prompts or []):
        return
    folders = transcriber.prompt_dirs() + [transcriber.PROMPT_DIR]
    labels: list[str] = []
    # None while a typed prompt has no file of its own
    label: str | None
    for text, label in cfg.prompts or []:
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


def _ask_repeat(transcriber: YouTubeTranscriber, session: Session) -> bool:
    """Ask whether to run again; the default flips to yes after the first repeat."""
    default_repeat = 'y' if session.asked else 'n'
    prompt_text = ("Run again? (Y/n): " if default_repeat == 'y'
                   else "Run again? Hit Enter to repeat (y/N): ")
    repeat = transcriber.get_yes_no_input(prompt_text, default=default_repeat)
    session.asked += 1
    return repeat


def _finish_session(transcriber: YouTubeTranscriber, cfg: SessionConfig, answers: _Answers,
                    session: Session) -> bool:
    """Offer to save a profile, then say whether to run again.

    A repeat hands the next round what it needs through `session`; main() is
    what goes round.
    """
    did_something_useful = (cfg.download_audio or cfg.download_video
                            or cfg.video_only or cfg.transcribe_audio
                            or bool(cfg.yt_transcript_languages)
                            or any(e[2] for e in cfg.sources or []))

    try:
        # A profile's REPEAT answers it, as any field is answered; else asked
        answer = _answer(answers, "REPEAT", lambda: _yn(_ask_repeat(transcriber, session)),
                         valid=_is_yes_no)
        repeat = answer.lower() in YesNo.YES.value
        repeat_value = _yn(repeat)
    except Exception:
        repeat, repeat_value = False, ""

    cfg.used_fields["REPEAT"] = repeat_value

    if answers.offers_profile and did_something_useful and not session.repeat:
        if transcriber.get_yes_no_input(
                "Do you want to create a profile from this session? (y/N): ", default='n'):
            _save_inline_prompts(transcriber, cfg)
            transcriber.create_profile(cfg.used_fields)

    # The work is done either way, and main() decides what happens next
    transcriber.release_caches()

    if repeat:
        answers.carry(cfg)
        session.repeat = True
        print("Repeating session as requested...")
    return repeat


def main() -> None:
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

    session = Session()
    # "Run again?" comes round here rather than re-entering main(), so a long
    # batch is one frame however many rounds it runs
    while True:
        # How far this round got, for the exit code if input runs out
        stage = "asking"
        try:
            answers = _select_profile(transcriber, session)
            cfg = _configure(transcriber, answers)

            stage = "running"
            _run_pipeline(transcriber, cfg)
            stage = "finished"
            if not _finish_session(transcriber, cfg, answers, session):
                return
        except (DownloadFailed, yt_dlp.utils.DownloadError):
            # Already reported where it happened, and the only source is
            # gone: one exit code for the run rather than one per step.
            # yt-dlp prints its own error before raising.
            sys.exit(1)
        except EOFError:
            # Input ran out: an unattended run was asked something nobody is
            # there to answer. That ended in a traceback. After a round that
            # finished - the offer to save a profile, or a REPEAT=y profile
            # asking for the next round's sources - the work asked for is
            # done, and it ends as a success.
            done = stage == "finished" or (stage == "asking" and session.repeat)
            print("\nNo more input." + ("" if done else " The run is incomplete."))
            sys.exit(0 if done else 1)

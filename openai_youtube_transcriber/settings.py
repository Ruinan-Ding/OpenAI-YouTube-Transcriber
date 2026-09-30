"""Settling every setting of a session, from a profile or a person alike."""

import getpass
import os

import yt_dlp

from .answers import SETTINGS, _answer, _is_yes_no, _yes_no, _yn
from .common import (AIEnhancementMode, DownloadFailed, LocalModel, ModelSize,
                     Provider, Resolution, YesNo, _is_number, error)
from .config import _PLACEMENTS, SessionConfig
from .questions import (_prompt_audio_resolution_input,
                        _prompt_audio_selection, _prompt_format,
                        _prompt_resolution_input, _prompt_resolution_selection,
                        _resolve_format, _resolve_path, _resolve_rename)


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

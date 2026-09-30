"""What a session is set to do, and what a run carries from one round to the next."""

from dataclasses import dataclass, field

from .common import AIEnhancementMode, ModelSize, Provider


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


@dataclass
class Session:
    """What one run of the app carries from a round into the next.

    Whether this round repeats the one before, the profile a repeat reloads,
    what an interactive round was told, and how often "Run again?" has been
    asked. It lived in the process environment as _REPEAT_* and LAST_*
    variables: one a shell happened to set was read as the app's own, and
    every way out of main() had to remember to clear them.
    """
    repeat: bool = False
    profile: str = None
    remembered: dict = field(default_factory=dict)
    asked: int = 0

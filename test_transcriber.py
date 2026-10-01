# Self-check for the parsing/chunking logic. Run with: python test_transcriber.py

import ast
import builtins
import codecs
import getpass
import importlib
import inspect
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from contextlib import redirect_stderr, redirect_stdout
from types import SimpleNamespace
from unittest.mock import patch

import whisper
from dotenv import dotenv_values

import OpenAIYouTubeTranscriber as module
from OpenAIYouTubeTranscriber import ModelSize, Resolution, YouTubeTranscriber

# input() as the console gives it. Every module reads the builtin, so a test
# answering the prompts replaces that, and puts this back when it is done.
REAL_INPUT = builtins.input


def test_is_youtube_url_accepts_videos_and_rejects_collections():
    u = YouTubeTranscriber().is_youtube_url
    for url in ('https://www.youtube.com/watch?v=jNQXAC9IVRw',
                'https://m.youtube.com/watch?list=PL1&v=jNQXAC9IVRw',
                'https://youtu.be/jNQXAC9IVRw',
                'https://www.youtube.com/shorts/abc123',
                'https://www.youtube-nocookie.com/embed/jNQXAC9IVRw',
                'https://www.youtube.com/live/jNQXAC9IVRw'):
        assert u(url), url
    # A playlist or channel URL makes yt-dlp download every entry into the one
    # output path we hand it, each overwriting the last
    for url in ('https://www.youtube.com/playlist?list=PLxxxx',
                'https://www.youtube.com/embed/videoseries?list=PLxxxx',
                'https://www.youtube.com/@SomeChannel',
                'https://www.youtube.com/watch?list=PLxxxx',
                'https://www.youtube.com/',
                'https://vimeo.com/123456789',
                'https://notyoutube.com/watch?v=jNQXAC9IVRw'):
        assert not u(url), url


def test_add_scheme_if_missing_leaves_paths_alone():
    t = YouTubeTranscriber()
    assert (t.add_scheme_if_missing('www.youtube.com/watch?v=UuZ7pZ_1JDE')
            == 'https://www.youtube.com/watch?v=UuZ7pZ_1JDE')
    assert t.add_scheme_if_missing('youtu.be/jNQXAC9IVRw') == 'https://youtu.be/jNQXAC9IVRw'
    for text in ('https://www.youtube.com/watch?v=jNQXAC9IVRw', 'Audio/clip.mp3',
                 'UuZ7pZ_1JDE', 'C:/Users/me/clip.mp3'):
        assert t.add_scheme_if_missing(text) == text, text


def test_available_resolutions_ignores_audio_formats():
    # yt-dlp reports audio formats with vcodec 'none' and no height
    info = {'formats': [
        {'vcodec': 'vp9', 'height': 720},
        {'vcodec': 'avc1', 'height': 1080},
        {'vcodec': 'vp9', 'height': 720},   # same height, different codec
        {'vcodec': 'none', 'acodec': 'opus'},
        {'vcodec': 'avc1'},                 # storyboard-style entry, no height
    ]}
    assert YouTubeTranscriber.available_resolutions(info) == ['1080p', '720p']
    assert YouTubeTranscriber.available_resolutions({}) == []


def _dubbed_info():
    """A dubbed video's audio formats, shaped as yt-dlp reports them.

    The original language carries language_preference 10; every dub is -1 and
    names itself in format_note, where a plain video would put the tier word.
    Order matters: yt-dlp hands formats over worst-first, with the original
    language last, and a selector takes the last match.
    """
    formats = [
        {'format_id': '233-0', 'vcodec': 'none', 'acodec': 'aac',
         'language': 'ar', 'language_preference': -1, 'format_note': 'Arabic'},
        {'format_id': '251-5', 'vcodec': 'none', 'acodec': 'opus', 'abr': 129.5,
         'language': 'de', 'language_preference': -1, 'format_note': 'German, medium'},
        {'format_id': '251-9', 'vcodec': 'none', 'acodec': 'opus', 'abr': 129.5,
         'language': 'ja', 'language_preference': -1, 'format_note': 'Japanese, medium'},
        {'format_id': '250-23', 'vcodec': 'none', 'acodec': 'opus', 'abr': 64.3,
         'language': 'en-US', 'language_preference': 10,
         'format_note': 'English (US) original (default), low'},
        {'format_id': '251-23-drc', 'vcodec': 'none', 'acodec': 'opus', 'abr': 125.0,
         'language': 'en-US', 'language_preference': 10,
         'format_note': 'English (US) original (default), medium, DRC'},
        {'format_id': '251-23', 'vcodec': 'none', 'acodec': 'opus', 'abr': 129.5,
         'language': 'en-US', 'language_preference': 10,
         'format_note': 'English (US) original (default), medium'},
        {'format_id': '137', 'vcodec': 'avc1', 'acodec': 'none', 'height': 1080},
    ]
    return {'formats': formats, 'language': 'en-US'}


def test_download_format_takes_the_extension_from_the_stream():
    """Forcing .mp3 on an Opus/WebM stream produced files players reject."""
    import yt_dlp

    seen = {}

    class FakeYDL:
        def __init__(self, options):
            seen['outtmpl'] = options['outtmpl']['default']
            seen['format'] = options['format']
            seen['overwrites'] = options.get('overwrites')

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def extract_info(self, url, download=False):
            # yt-dlp resolves %(ext)s from the format it actually chose
            path = seen['outtmpl'].replace('%(ext)s', 'webm')
            with open(path, 'w', encoding='utf-8') as f:
                f.write('x')
            return {'requested_downloads': [{'filepath': path}]}

    real = yt_dlp.YoutubeDL
    yt_dlp.YoutubeDL = FakeYDL
    try:
        with tempfile.TemporaryDirectory() as tmp:
            with redirect_stdout(io.StringIO()):
                path = YouTubeTranscriber().download_format(
                    'https://example/v', 'bestaudio/best', tmp, 'My Clip')
            assert seen['outtmpl'].endswith('My Clip.%(ext)s'), seen['outtmpl']
            assert os.path.basename(path) == 'My Clip.webm', path
            assert os.path.exists(path)

            # A file already under a deliverable's name is fetched over: the name
            # is a title or a RENAME, and yt-dlp handed back another video's file
            t = YouTubeTranscriber()
            t.AUDIO_DIR = tmp
            info = {'webpage_url': 'https://example/v', 'id': 'abc123'}
            with redirect_stdout(io.StringIO()):
                t.download_audio_stream(info, 'lecture', keep_in=tmp)
                assert seen['overwrites'] is True, seen
                # Scratch audio is reused for a retry, but only under this video's id
                t.download_audio_stream(info, 'lecture', is_temp=True)
            assert seen['overwrites'] is False and '[abc123]' in seen['outtmpl'], seen
    finally:
        yt_dlp.YoutubeDL = real


def test_audio_tiers_ignore_dubs_and_drc():
    info = _dubbed_info()
    # Dubs are published at the original's bitrate and name themselves in
    # format_note; treating those as tiers would offer a way to transcribe the
    # wrong language
    assert YouTubeTranscriber._audio_tiers(info) == {'low': 64.3, 'medium': 129.5}
    assert YouTubeTranscriber.available_audio_qualities(info) == ['medium', 'low']
    assert YouTubeTranscriber.available_audio_qualities({}) == []


def test_quality_field_asks_when_blank_and_passes_values_through():

    t = YouTubeTranscriber()
    cfg = module.SessionConfig(used_fields={})
    cfg.info = _dubbed_info()
    asked = []

    def picker(transcriber, info, default):
        asked.append(default)
        return 'picked'

    # Blank and 'fetch' both mean "show me what this video has", so an unset
    # field asks instead of silently taking a default
    for raw in ('', 'fetch', 'f'):
        assert module._resolve_quality(t, cfg, raw, picker) == 'picked', raw
    # Transcription asks with a different Enter-default
    module._resolve_quality(t, cfg, '', picker, default=Resolution.LOWEST.value)
    assert asked == ['highest', 'highest', 'highest', 'lowest'], asked

    # An explicit answer passes through; whether the video offers it is settled
    # against the format list later
    for value in ('720p', 'low', '64', 'highest', 'lowest'):
        assert module._resolve_quality(t, cfg, value, picker) == value, value
    assert len(asked) == 4


def test_the_prompts_take_the_same_lists_the_profile_fields_take():
    """VIDEO_RESOLUTION=144p,720p in a profile is two videos. Typed at the
    prompt it used to be an invalid answer, which made "every resolution, in
    every format" a thing only a profile could ask for.
    """

    t = YouTubeTranscriber()
    info = {'formats': [
        {'vcodec': 'h264', 'acodec': 'none', 'height': 720, 'format_id': '1'},
        {'vcodec': 'h264', 'acodec': 'none', 'height': 144, 'format_id': '2'},
        {'vcodec': 'none', 'acodec': 'opus', 'abr': 106, 'format_id': '3'},
        {'vcodec': 'none', 'acodec': 'opus', 'abr': 60, 'format_id': '4'},
    ]}

    def answer(text, call):
        """Run one prompt with a scripted answer, and only one."""
        script = [text]
        builtins.input = lambda prompt='': script.pop(0)
        try:
            with redirect_stdout(io.StringIO()):
                return call()
        finally:
            builtins.input = REAL_INPUT

    # Typed, and picked from the menu, for both a video and an audio field
    assert answer('144p,720p', lambda: module._prompt_resolution_input(t, 'r')) \
        == '144p,720p'
    assert answer('low,highest', lambda: module._prompt_audio_resolution_input(t, 'a')) \
        == 'low,highest'
    assert answer('2,1', lambda: module._prompt_resolution_selection(t, info)) \
        == '144p,720p'
    assert answer('60,106', lambda: module._prompt_audio_selection(t, info)) \
        == '60,106'
    assert answer('mp4,mkv', lambda: module._prompt_format(t, 'c', 'mp4', 'container')) \
        == 'mp4,mkv'

    # One bad entry is dropped with its reason, like the profile path; a single
    # answer is unchanged, and repeats collapse
    assert answer('720p,nope', lambda: module._prompt_resolution_input(t, 'r')) == '720p'
    assert answer('720', lambda: module._prompt_resolution_input(t, 'r')) == '720p'
    assert answer('2,144p', lambda: module._prompt_resolution_selection(t, info)) == '144p'

    # Nothing usable in the whole answer still re-asks rather than returning it
    script = ['no,pe', '720p']
    builtins.input = lambda prompt='': script.pop(0)
    try:
        with redirect_stdout(io.StringIO()):
            assert module._prompt_resolution_input(t, 'r') == '720p'
    finally:
        builtins.input = REAL_INPUT
    assert not script


def test_bare_height_in_a_profile_is_a_resolution():

    # A profile documented as accepting 720 must not be handed to the format
    # check as '720', which no video offers
    assert module._as_height('720') == '720p'
    assert module._as_height('1080') == '1080p'
    for text in ('720p', 'highest', 'lowest', 'low', '0', ''):
        assert module._as_height(text) == text, text


def test_transcription_quality_yields_to_audio_already_being_downloaded():
    """The cheapest stream is for when transcription is the only reason to
    download at all. Any other download already puts audio on disk, which is
    transcribed instead of fetching a second copy - and saying so beats
    dropping a hand-written field without a word.
    """

    t = YouTubeTranscriber()
    t.fetch_video_info = lambda url: dict(_plain_info(), title='clip')
    base = {'URL': 'https://www.youtube.com/watch?v=jNQXAC9IVRw',
            'DOWNLOAD_VIDEO': 'n', 'VIDEO_ONLY': 'n', 'DOWNLOAD_AUDIO': 'n',
            'TRANSCRIBE_AUDIO': 'y', 'AI_REFINEMENT': 'n', 'MODEL_CHOICE': 'tiny',
            'TARGET_LANGUAGE': 'en', 'USE_EN_MODEL': 'n', 'REPEAT': 'n',
            'TRANSCRIBE_AUDIO_QUALITY': 'lowest',
            'DOWNLOAD_YT_TRANSCRIPT': 'n'}

    def configure(**over):
        log = io.StringIO()
        with redirect_stdout(log):
            cfg = module._configure(t, module._Profile('test.txt', dict(base, **over)))
        return cfg, log.getvalue()

    # Transcription is the only reason to touch the network: honour it
    cfg, log = configure()
    assert cfg.transcribe_audio_quality == Resolution.LOWEST.value
    assert 'Ignoring TRANSCRIBE_AUDIO_QUALITY' not in log

    # An audio download already supplies the audio, so the field is dropped
    cfg, log = configure(DOWNLOAD_AUDIO='y', AUDIO_RESOLUTION='highest',
                         AUDIO_FORMAT='original')
    assert cfg.transcribe_audio_quality is None
    assert 'Ignoring TRANSCRIBE_AUDIO_QUALITY=lowest' in log

    # ...and so does the audio fetched to build a merged video
    cfg, log = configure(DOWNLOAD_VIDEO='y', VIDEO_RESOLUTION='144p',
                         VIDEO_AUDIO_RESOLUTION='highest', VIDEO_FORMAT='mp4')
    assert cfg.transcribe_audio_quality is None
    assert 'Ignoring TRANSCRIBE_AUDIO_QUALITY=lowest' in log

    # A local file has no stream to pick at all, and the profile alone does
    # not explain that: the reason is the URL, not a field turned off
    with tempfile.TemporaryDirectory() as tmp:
        local = os.path.join(tmp, 'clip.mp3')
        io.open(local, 'w', encoding='utf-8').write('words')
        cfg, log = configure(URL=local)
    assert cfg.transcribe_audio_quality is None
    assert 'Ignoring TRANSCRIBE_AUDIO_QUALITY=lowest' in log, log


def test_unchanged_enhancement_is_not_treated_as_a_refinement():
    """Every chunk failing leaves the same words, whatever the whitespace."""
    t = YouTubeTranscriber()
    original = ' Hello there. This is a test.  Extra  spaces here.'
    with redirect_stdout(io.StringIO()):
        rejoined = t._run_chunked_enhancement(
            t.chunk_text(original, max_tokens=800), 'x',
            lambda chunk: (_ for _ in ()).throw(RuntimeError))
    assert rejoined != original, 'the premise of this test has changed'

    opened = []
    t.startfile = opened.append
    with tempfile.TemporaryDirectory() as tmp:
        t.TRANSCRIPT_DIR = os.path.join(tmp, 'Transcript')
        t.RAW_TRANSCRIPT_DIR = os.path.join(t.TRANSCRIPT_DIR, 'Raw')
        with redirect_stdout(io.StringIO()):
            assert t.save_final_transcript(rejoined, 'clip.txt', original_text=original)
        # Whitespace alone is not a refinement, so no near-duplicate is kept
        assert not os.path.exists(os.path.join(t.RAW_TRANSCRIPT_DIR, 'clip.txt'))


def test_format_field_keeps_defaults_and_original_without_asking():

    t = YouTubeTranscriber()
    resolve = module._resolve_format
    # None of these reach a prompt, so the test cannot block waiting for input
    assert resolve(t, 'DEFAULT', 'video container', 'mp4', 'container') == 'mp4'
    assert resolve(t, 'mp4', 'video container', 'mp4', 'container') == 'mp4'
    assert resolve(t, 'original', 'video container', 'mp4', 'container') == 'original'
    assert resolve(t, 'ORIGINAL', 'video container', 'mp4', 'container') == 'original'

    # 'original' is whichever container the download already has, so a
    # re-encode asked for beside it could land on that very file and overwrite
    # the untouched copy 'original' asked to keep
    assert module._shared_container(t, ['original', 'h264'], 'video') is True
    assert module._shared_container(t, ['mp4', 'original'], 'container') is True
    assert module._shared_container(t, ['original'], 'container') is False
    assert module._shared_container(t, ['mp4', 'webm'], 'container') is False

    containers = YouTubeTranscriber.ffmpeg_formats('container')
    if not containers:
        return                      # no ffmpeg here; the rest needs its lists
    assert {'mp4', 'webm', 'mp3'} <= set(containers)
    # ffmpeg names the muxer 'matroska'; people type the extension
    assert 'mkv' in containers
    assert resolve(t, 'webm', 'video container', 'mp4', 'container') == 'webm'
    assert 'h264' in YouTubeTranscriber.ffmpeg_formats('video')

    # A format is how a person writes an extension, so the dot they write it
    # with is not a different answer. It used to be "ffmpeg cannot write
    # '.mp3'", which stopped an unattended profile on a field that was right
    assert resolve(t, '.webm', 'video container', 'mp4', 'container') == 'webm'
    assert resolve(t, '.DEFAULT', 'video container', 'mp4', 'container') == 'mp4'
    assert resolve(t, '.original', 'video container', 'mp4', 'container') == 'original'
    # ...and one of a list carrying it is still its own file, not a dropped one
    assert resolve(t, 'mp4, .mkv', 'video container', 'mp4', 'container') == 'mp4,mkv'
    assert resolve(t, '.h264', 'video-only codec', 'h264', 'video') == 'h264'


def test_audio_format_selectors():
    f = YouTubeTranscriber.audio_format
    info = _dubbed_info()
    assert f(Resolution.HIGHEST.value, info) == 'bestaudio/best'
    assert f('', info) == 'bestaudio/best'
    assert f(None, info) == 'bestaudio/best'
    assert f('medium', info) == 'bestaudio[abr<=129.5]/bestaudio'
    # 'worstaudio' would take the bitrate-less HLS manifest, in whatever
    # language it happens to sit in; the lowest real tier is what is meant
    assert f(Resolution.LOWEST.value, info) == 'bestaudio[abr<=64.3]/bestaudio'
    # A bitrate is passed through as the budget, so it can land between tiers;
    # a budget under every stream falls to the cheapest, never to the best
    assert f('100', info) == 'bestaudio[abr<=100]/bestaudio'
    assert f('32', info) == 'bestaudio[abr<=64.3]/bestaudio'
    # A tier the video does not offer falls back rather than failing
    assert f('high', info) == 'bestaudio/best'
    assert f('low', {}) == 'bestaudio/best'


def test_audio_label_names_the_stream_that_was_downloaded():
    label = YouTubeTranscriber.audio_bitrate_label
    info = _dubbed_info()
    # The same stream, asked for three ways, gets one name
    assert label('low', info) == '64k'
    assert label(Resolution.LOWEST.value, info) == '64k'
    assert label('100', info) == '64k'
    # 'medium' is the best this video has, so naming it, pressing Enter at the
    # menu and asking for 'highest' are one request and get one filename
    assert label('medium', info) == ''
    # The default is unlabelled
    assert label(Resolution.HIGHEST.value, info) == ''
    assert label(None, info) == ''
    assert label('low', {}) == ''


def test_selected_format_stays_on_the_original_language():
    """A filter must never move the pick onto a dub, whatever the bitrate."""
    info = _dubbed_info()
    for quality in ('low', 'medium', Resolution.LOWEST.value, '100'):
        selector = YouTubeTranscriber.audio_format(quality, info)
        chosen = YouTubeTranscriber.selected_format(selector, info)
        assert chosen is not None, quality
        assert chosen['language'] == 'en-US', (quality, chosen['format_id'])


def test_video_format_selectors():
    f = YouTubeTranscriber.video_format
    assert f(Resolution.HIGHEST.value) == 'bestvideo/best'
    assert f(Resolution.LOWEST.value) == 'worstvideo/worst'
    # A resolution reaches this both as '720p' (prompt/profile) and bare '720'
    assert f('720p') == 'bestvideo[height=720]/best[height=720]/best'
    assert f('720') == 'bestvideo[height=720]/best[height=720]/best'

    # A video with only progressive streams matches no video-only filter, and
    # available_resolutions offers its heights, so every branch has to degrade
    # to a muxed stream rather than fail the download
    progressive = {'formats': [{'format_id': '18', 'height': 360, 'width': 640,
                                'vcodec': 'avc1', 'acodec': 'mp4a', 'abr': 96,
                                'ext': 'mp4'}]}
    assert YouTubeTranscriber.available_resolutions(progressive) == ['360p']
    for quality in (Resolution.HIGHEST.value, Resolution.LOWEST.value, '360p'):
        chosen = YouTubeTranscriber.selected_format(f(quality), progressive)
        assert chosen and chosen['format_id'] == '18', quality


def test_quality_tag_marks_only_what_differs_from_the_default():
    q = YouTubeTranscriber.quality_tag
    # The best available is the default, so it earns no label
    assert q(None, None) == ''
    assert q('highest', 'highest') == ''
    assert q('720p', 'highest') == ' [720p]'
    assert q('highest', 'low') == ' [low]'
    assert q('720p', 'low') == ' [720p low]'
    # Whatever it is handed becomes the label; the pipeline resolves 'lowest'
    # to a concrete quality first, so a real filename reads [144p], not [lowest]
    assert q('144p', None) == ' [144p]'
    assert q(None, '64') == ' [64]'


def test_prompt_suffix_follows_the_prompt_naming_convention():
    f = YouTubeTranscriber().prompt_suffix
    assert f('prompt-refinement.txt') == ' - refinement'
    assert f('prompt0-translator.txt') == ' - translator'
    # Prompt/ is not restricted to the convention, so an off-pattern name
    # contributes its whole stem rather than nothing
    assert f('my-cleanup.txt') == ' - my-cleanup'
    # Nothing left after the prefix, nothing but punctuation, or no filename at
    # all (a prompt typed inline) falls back to the default tag. Never '': an
    # untagged refinement is named exactly like the transcript it refined.
    for label in ('prompt.txt', 'prompt0.txt', 'prompt-.txt', 'prompt--.txt',
                  'prompt42.txt', '(inline)', '', None):
        assert f(label) == ' - Refined', label


def test_finished_transcript_goes_to_output_and_original_is_kept():
    t = YouTubeTranscriber()
    opened = []
    t.startfile = opened.append

    with tempfile.TemporaryDirectory() as tmp:
        t.TRANSCRIPT_DIR = os.path.join(tmp, 'Transcript')
        t.RAW_TRANSCRIPT_DIR = os.path.join(t.TRANSCRIPT_DIR, 'Raw')
        out = os.path.join(t.TRANSCRIPT_DIR, 'clip.txt')
        tagged = os.path.join(t.TRANSCRIPT_DIR, 'clip - refinement.txt')
        kept = os.path.join(t.RAW_TRANSCRIPT_DIR, 'clip.txt')

        def read(path):
            with open(path, encoding='utf-8') as f:
                return f.read()

        def run(**kwargs):
            for path in (out, tagged, kept):
                if os.path.exists(path):
                    os.remove(path)
            opened.clear()
            with redirect_stdout(io.StringIO()):
                assert t.save_final_transcript('refined', 'clip.txt', **kwargs)

        # No enhancement: the transcript is final, so nothing is held back
        run(original_text=None)
        assert read(out) == 'refined'
        assert not os.path.exists(kept)

        # Enhanced: Transcript/ gets the result, Transcript/Raw/ the original
        run(original_text='raw', keep_original=True)
        assert read(out) == 'refined' and read(kept) == 'raw'
        # Only the finished one is opened for the user
        assert opened == [out]

        # KEEP_TRANSCRIPT=n
        run(original_text='raw', keep_original=False)
        assert not os.path.exists(kept)

        # The refined file carries the prompt's tag; the original keeps the
        # plain name, so a second prompt cannot clobber the first one's output
        for path in (out, tagged, kept):
            if os.path.exists(path):
                os.remove(path)
        with redirect_stdout(io.StringIO()):
            assert t.save_final_transcript('refined', 'clip - refinement.txt',
                                           original_text='raw',
                                           original_filename='clip.txt')
        assert read(tagged) == 'refined' and read(kept) == 'raw'
        assert not os.path.exists(out)

        # Enhancement that failed returns the text unchanged; two identical
        # files would be noise, so the original is not kept
        run(original_text='refined')
        assert not os.path.exists(kept)


def test_menu_default_decides_what_enter_takes():
    """Enter at a menu takes the field's own default.

    Every field wants the best available except the audio fetched to
    transcribe, which wants the cheapest. Only the audio picker is asked for a
    lowest default today; the video picker's is pinned here so that collapsing
    it to "always the top" is a test failure rather than a silent wrong answer.
    """

    t = YouTubeTranscriber()
    info = _plain_info()

    def enter(picker, default):
        asked = []
        builtins.input = lambda prompt: asked.append(prompt) or ''
        try:
            with redirect_stdout(io.StringIO()):
                return picker(t, info, default), asked[0]
        finally:
            builtins.input = REAL_INPUT

    # The menu names what Enter lands on for this video, but the answer is the
    # keyword: recorded as 720p, a profile made from it fetched 720p of a 4K
    # video, and asked again - unattended, crashed - on one without 720p
    for picker, default, shown in (
            (module._prompt_resolution_selection, Resolution.HIGHEST.value, '720p'),
            (module._prompt_resolution_selection, Resolution.LOWEST.value, '144p'),
            (module._prompt_audio_selection, Resolution.HIGHEST.value, 'medium'),
            (module._prompt_audio_selection, Resolution.LOWEST.value, 'low')):
        answer, prompt = enter(picker, default)
        assert answer == default and f'default {shown}' in prompt, (answer, prompt)


def test_model_choice_is_case_insensitive():
    # _configure validates model_choice.lower() but passes the raw
    # value on, so 'Large-v3' from a hand-edited profile must not become 'base'
    for choice in ('large-v3', 'Large-v3', 'LARGE-V3'):
        assert ModelSize.from_choice(choice).value == 'large-v3', choice
    assert ModelSize.from_choice('7').value == 'large-v3'
    assert ModelSize.from_choice('').value == 'base'
    assert ModelSize.from_choice(None).value == 'base'
    assert ModelSize.from_choice('nonsense').value == 'base'


def test_language_names_normalize_to_codes():
    n = YouTubeTranscriber.normalize_language
    # Must come back as a code: callers compare against DEFAULT_LANGUAGE to
    # decide whether the .en model applies
    assert n('english') == YouTubeTranscriber.DEFAULT_LANGUAGE
    assert n('English') == 'en'
    assert n('spanish') == 'es'
    assert n('es') == 'es'
    assert n(' ES ') == 'es'
    assert n('klingon') is None


def test_detected_language_never_leaks_into_filename():
    r = YouTubeTranscriber.resolve_transcript_language
    # langdetect region tags and its failure sentinel must not reach the filename
    assert r('zh-cn', 'en') == 'zh'
    assert r('unknown', 'en') == 'en'
    assert r('', 'es') == 'es'
    assert r(None, 'en') == 'en'
    assert r('es', 'en') == 'es'  # a real detection still wins over the target


def test_chunk_text_respects_budget():
    t = YouTubeTranscriber.chunk_text

    def est(chunks):
        return max(len(c) // 4 for c in chunks)

    punctuated_source = 'This is a sentence. ' * 2000
    punctuated = t(punctuated_source, max_tokens=800)
    assert len(punctuated) > 1
    assert est(punctuated) <= 800

    # Whisper on noisy audio emits no terminal punctuation: one giant "sentence"
    blob = 'so anyway I was walking down the street and then ' * 400
    unpunctuated = t(blob, max_tokens=800)
    assert len(unpunctuated) > 1
    assert est(unpunctuated) <= 800
    # Splitting must land on word boundaries, not mid-word
    assert not any('any way' in c for c in unpunctuated)
    assert all(w in blob for c in unpunctuated for w in c.split())

    # A budget too small for one sentence must not shred text into characters
    degenerate = t('hello world this is a test of the emergency system', max_tokens=2)
    assert 'hello' in degenerate[0]

    assert t('Short.', max_tokens=800) == ['Short.']

    # Chunks must not overlap: the duplicate text cannot be removed again once
    # the model has rewritten both copies of it
    assert ' '.join(punctuated).split() == punctuated_source.split()

    # Chinese and Japanese end a sentence with 。 and no space, and take three bytes
    # a character: sized by characters, a chunk held 2.4 times its budget
    def size(chunks):
        return max(len(c.encode('utf-8')) // 4 for c in chunks)

    zh_source = '今天我们来谈谈如何在家里做面包。首先把面粉和温水混合在一起。' * 200
    zh = t(zh_source, max_tokens=300)
    assert len(zh) > 1 and size(zh) <= 300, size(zh)
    assert all(c.endswith('。') for c in zh), 'a cut landed mid-sentence'
    assert ''.join(zh) == zh_source, 'characters lost, doubled or spaced apart'
    zh_blob = '所以我那天走在街上然后' * 400
    wrapped = t(zh_blob, max_tokens=300)
    assert len(wrapped) > 1 and size(wrapped) <= 300 and ''.join(wrapped) == zh_blob

    # Hindi ends a sentence with । and Arabic a question with ؟ - with a space
    for stop, sentence in (('।', 'आज हम घर पर रोटी बनाने के तरीके के बारे में बात करेंगे।'),
                           ('؟', 'هل تعرف كيف تصنع الخبز في المنزل؟')):
        source = ' '.join([sentence] * 150)
        pieces = t(source, max_tokens=300)
        assert len(pieces) > 1 and all(c.endswith(stop) for c in pieces), stop
        assert ' '.join(pieces) == source

    # Line breaks go back as they were, so a chunk kept unrefined is not run into
    # one line with its headers; and a list number stays with its item, where a
    # cut after "1." ended one chunk on it and opened the next with the item
    doc = ''.join(f'## Part {i}\n\nThe first point is here. The second follows.\n'
                  f'1.\nAn item.\n2. Another item.\n\n' for i in range(40))
    parts = t(doc, max_tokens=60)
    assert len(parts) > 1 and all(c in doc for c in parts), parts[:2]
    assert not any(re.fullmatch(r'\d\.', c.splitlines()[-1]) for c in parts), parts


def test_enhancement_round_trip_neither_duplicates_nor_drops():
    """A rewriting model must not cost or duplicate a single sentence."""
    t = YouTubeTranscriber()
    sentences = [f'sentence number {i} went by.' for i in range(600)]
    chunks = t.chunk_text(' '.join(sentences), max_tokens=200)
    assert len(chunks) > 1

    # What a real model returns: rewritten, so the seam text never matches
    # byte-for-byte between one enhanced chunk and the next
    def rewrite(chunk):
        return chunk[0].upper() + chunk[1:].replace(' went by', ' passed')

    log = io.StringIO()

    def run(call_chunk):
        log.seek(0)
        log.truncate()
        with redirect_stdout(log):
            return t._run_chunked_enhancement(chunks, 'fake', call_chunk).lower()

    for label, call_chunk in (('rewritten', rewrite),
                              ('verbatim', lambda c: c),
                              ('backend down', lambda c: (_ for _ in ()).throw(RuntimeError))):
        merged = run(call_chunk)
        for i in range(600):
            assert merged.count(f'sentence number {i} ') == 1, (label, i)
        # A chunk left as it was is named, not passed off as enhanced
        failed = len(chunks) if label == 'backend down' else 0
        assert (f'{failed} of {len(chunks)} chunk(s) kept' in log.getvalue()) == bool(failed), label

    # One reply short enough to be refused among good ones is the one reported
    run(lambda chunk: '' if chunk is chunks[1] else chunk)
    assert (f'1 of {len(chunks)} chunk(s) kept as transcribed, not enhanced: chunk 2.'
            in log.getvalue()), log.getvalue()

    # A reply laid out with a header must still open a line once the replies
    # are joined, not trail the paragraph the chunk before ended on
    merged = run(lambda chunk: '# Part\n' + chunk)
    assert merged.count('\n\n# part\n') == len(chunks) - 1, merged[:300]

    # A reply wrapped whole in a code block, as a small model does though told
    # not to, loses the fence - unless the chunk opened with one of its own
    assert run(lambda chunk: f'```markdown\n{chunk}\n```') == run(lambda chunk: chunk)
    block = '```\ncode\n```'
    with redirect_stdout(io.StringIO()):
        assert t._run_chunked_enhancement([block], 'fake', lambda c: c) == block

    # Speech recognition with no punctuation is cut mid-sentence. That seam
    # closes on a space, or the sentence would be split across two paragraphs
    unpunctuated = ' '.join(f'word{i}' for i in range(3000))
    cut = t.chunk_text(unpunctuated, max_tokens=200)
    assert len(cut) > 1 and not cut[0].endswith('.')
    with redirect_stdout(io.StringIO()):
        assert t._run_chunked_enhancement(cut, 'fake', lambda c: c) == unpunctuated
        headed = t._run_chunked_enhancement(cut, 'fake', lambda c: '# Part\n' + c)
    assert headed.count('\n\n# Part\n') == len(cut) - 1, headed[:300]

    # Nor may a seam put a space into a script written without them
    zh_blob = '所以我那天走在街上然后' * 400
    with redirect_stdout(io.StringIO()):
        assert t._run_chunked_enhancement(
            t.chunk_text(zh_blob, max_tokens=300), 'fake', lambda c: c) == zh_blob
    zh_sentences = '今天我们来谈谈如何在家里做面包。' * 300
    zh_split = t.chunk_text(zh_sentences, max_tokens=300)
    with redirect_stdout(io.StringIO()):
        joined = t._run_chunked_enhancement(zh_split, 'fake', lambda c: c)
    assert joined.count('\n\n') == len(zh_split) - 1
    assert joined.replace('\n\n', '') == zh_sentences

    # Korean is as wide as Chinese but spaces its words; they must not be glued
    ko_blob = ' '.join(['오늘은 집에서 빵을 만드는 방법에 대해 이야기해 보겠습니다'] * 150)
    ko_cut = t.chunk_text(ko_blob, max_tokens=300)
    assert len(ko_cut) > 1
    with redirect_stdout(io.StringIO()):
        assert t._run_chunked_enhancement(ko_cut, 'fake', lambda c: c) == ko_blob


def test_a_reply_cut_off_at_the_output_limit_keeps_its_chunk():
    """An OpenAI-compatible reply that ran out of room was saved half-finished.

    The Anthropic path checked its stop reason and kept the original chunk; this
    one never looked at finish_reason, and a refusal with no content at all
    raised rather than being kept as the chunk it failed to refine.
    """
    import sys
    import types

    t = YouTubeTranscriber()
    text = ' '.join(f'sentence number {i} went by.' for i in range(1500))
    chunks = t.chunk_text(text, max_tokens=3000)
    assert len(chunks) >= 3
    calls = []

    class Completions:
        def create(self, **kwargs):
            calls.append(kwargs['messages'][-1]['content'])
            chunk = calls[-1]
            # The first reply is cut off, the third comes back empty, the rest refine
            reason, content = {1: ('length', chunk[:40]), 3: ('stop', None)}.get(
                len(calls), ('stop', chunk.upper()))
            return types.SimpleNamespace(choices=[types.SimpleNamespace(
                finish_reason=reason, message=types.SimpleNamespace(content=content))])

    openai = types.SimpleNamespace(OpenAI=lambda **kwargs: types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=Completions())))
    saved = sys.modules.get('openai')
    sys.modules['openai'] = openai
    log = io.StringIO()
    try:
        with redirect_stdout(log):
            result = t.enhance_with_openai_compatible(text, 'tidy', 'key', module.Provider.OPENAI)
    finally:
        sys.modules.pop('openai', None) if saved is None else sys.modules.update(openai=saved)

    expected = [chunks[0], chunks[1].upper(), chunks[2]] + [c.upper() for c in chunks[3:]]
    assert result == '\n\n'.join(expected), result[:200]
    assert 'truncated' in log.getvalue()
    assert (f'2 of {len(chunks)} chunk(s) kept as transcribed, not enhanced: chunk 1, 3.'
            in log.getvalue()), log.getvalue()


def test_a_chinese_chunk_gets_the_output_budget_it_needs():
    """Both output caps were sized in a way Chinese breaks.

    The local cap counted words by spaces, so a chunk was one word and the reply
    stopped at the 256-token floor, about a third of it - long enough to pass
    the length check and be saved. Anthropic's was characters over three, less
    room than a Chinese reply the length of its chunk needs, so a full chunk was
    cut off and kept unrefined.
    """
    import sys
    import types

    t = YouTubeTranscriber()
    text = '今天我们来谈谈如何在家里做面包。首先把面粉和温水混合在一起。' * 60
    asked = {}
    respond = {'with': lambda prompt: prompt}

    class Tokenizer:
        model_max_length = 32768
        chat_template = 'yes'

        def apply_chat_template(self, messages, **kwargs):
            return messages[-1]['content']

        def encode(self, text, **kwargs):
            return range(len(text.encode('utf-8')) // 4)

    def pipeline(*args, **kwargs):
        def generate(prompt, **options):
            asked.setdefault('local', []).append((prompt, options['max_new_tokens']))
            return [{'generated_text': respond['with'](prompt)}]
        return generate

    transformers = types.SimpleNamespace(
        AutoTokenizer=types.SimpleNamespace(from_pretrained=lambda _id: Tokenizer()),
        pipeline=pipeline)

    class Messages:
        def create(self, **kwargs):
            asked.setdefault('anthropic', []).append(
                (kwargs['messages'][0]['content'], kwargs['max_tokens']))
            return types.SimpleNamespace(stop_reason='end_turn', content=[
                types.SimpleNamespace(type='text', text=kwargs['messages'][0]['content'])])

    anthropic = types.SimpleNamespace(
        Anthropic=lambda **kwargs: types.SimpleNamespace(messages=Messages()))
    saved = {name: sys.modules.get(name) for name in ('transformers', 'anthropic')}
    sys.modules.update(transformers=transformers, anthropic=anthropic)
    try:
        with redirect_stdout(io.StringIO()):
            t.enhance_with_local(text, 'tidy', 'any/model')
            t.enhance_with_anthropic(text, 'tidy', 'key', module.Provider.ANTHROPIC)
    finally:
        for name, value in saved.items():
            sys.modules.pop(name, None) if value is None else sys.modules.update({name: value})

    # About a token and a half a character: Qwen's tokenizer needed about 0.6, and
    # this leaves room for one that splits Chinese finer
    for backend in ('local', 'anthropic'):
        assert asked.get(backend), backend
        for chunk, budget in asked[backend]:
            assert budget >= len(chunk) * 1.4, (backend, len(chunk), budget)

    # A faithful Chinese translation of English has 27% of its characters - under
    # the length check, when it counted characters - but 81% of its bytes
    def local(source, reply, keeps='all'):
        respond['with'] = lambda prompt: reply
        saved = sys.modules.get('transformers')
        sys.modules['transformers'] = transformers
        try:
            with redirect_stdout(io.StringIO()):
                return t.enhance_text(source, module.AIEnhancementMode.LOCAL, 'any prompt',
                                      local_model='any/model', keeps=keeps)
        finally:
            (sys.modules.pop('transformers', None) if saved is None
             else sys.modules.update(transformers=saved))

    english = 'Today we are going to talk about how to make bread at home. ' * 20
    translated = local(english, '今天我们来谈谈如何在家里做面包。' * 20)
    assert '面包' in translated and 'bread' not in translated, translated[:120]

    # A summary is short on purpose, and was refused chunk by chunk as a model
    # that stopped early; a reply that should be the whole chunk still is
    summary = local(english, 'Homemade loaf.', keeps='some')
    assert 'Homemade loaf.' in summary and 'talk about' not in summary, summary[:120]
    kept = local(english, 'Homemade loaf.')
    assert 'talk about' in kept and 'Homemade' not in kept, kept[:120]
    # and a reply that ran out of room is cut off, whatever the prompt
    cut = local(english, 'Homemade loaf. ' * 2000, keeps='some')
    assert 'talk about' in cut and 'Homemade' not in cut, cut[:120]

    # A refinement that dropped a sentence was long enough to pass as whole and
    # was saved; one that only lost filler and fixed misheard words is kept
    talk = ('So um today I want to show you how sour dough starter works. Basically its '
            'just flour and water and the wild yeast does the rest. You feed it a little '
            'flour and water every single day and after about a week or so its finally '
            'active enough to bake a loaf with. The key thing the key thing is temperature.')
    tidy = ("So today I want to show you how sourdough starter works. Basically, it's just "
            "flour and water, and the wild yeast does the rest. You feed it a little flour "
            "and water every single day, and after about a week or so, it's finally active "
            "enough to bake a loaf with. The key thing is **temperature**.")
    dropped = tidy.replace(tidy[tidy.index('You feed'):tidy.index('The key')], '')
    assert local(talk, tidy, keeps='words') == tidy
    refused = local(talk, dropped, keeps='words')
    assert 'sour dough' in refused and 'sourdough' not in refused, refused[:120]
    # Only a refinement answers for the speaker's words: a translation has none of them
    assert local(talk, dropped) == dropped


def test_a_small_local_context_holds_the_prompt_a_chunk_and_its_reply():
    """GPT-2 reads 1024 tokens, and a shipped prompt takes up to 804 of them.

    Chunks were sized without counting the prompt, so every full-size chunk
    failed with "index out of range in self". A prompt that leaves no room at
    all skips enhancement rather than loading the model to fail on each chunk.
    """
    import sys
    import types

    t = YouTubeTranscriber()
    calls, loaded = [], []

    class Tokenizer:
        model_max_length = 1024
        chat_template = None

        def encode(self, text, **kwargs):
            return range(len(text.encode('utf-8')) // 4)

    def pipeline(*args, **kwargs):
        loaded.append(True)

        def generate(prompt, **options):
            calls.append((prompt, options['max_new_tokens']))
            # A base model continues the prompt: here, with the chunk it was given
            return [{'generated_text': f"{prompt} {prompt.split(chr(10) * 2)[-2]}"}]
        return generate

    transformers = types.SimpleNamespace(
        AutoTokenizer=types.SimpleNamespace(from_pretrained=lambda _id: Tokenizer()),
        pipeline=pipeline)
    text = ' '.join(f'sentence number {i} went by.' for i in range(200))
    saved = sys.modules.get('transformers')
    sys.modules['transformers'] = transformers
    try:
        with redirect_stdout(io.StringIO()):
            result = t.enhance_with_local(text, 'x ' * 1600, 'gpt2')
        log = io.StringIO()
        with redirect_stdout(log):
            skipped = t.enhance_with_local(text, 'x ' * 2000, 'gpt2')
    finally:
        sys.modules.pop('transformers', None) if saved is None else sys.modules.update(
            transformers=saved)

    assert len(calls) > 1 and result.split() == text.split(), (len(calls), result[:100])
    for prompt, budget in calls:
        assert 0 < budget <= 1024 - len(Tokenizer().encode(prompt)), (len(prompt), budget)
    assert skipped == text and len(loaded) == 1, len(loaded)
    assert 'no room for the transcript' in log.getvalue(), log.getvalue()


def test_a_whisper_model_that_will_not_load_falls_back_to_base():
    """Whisper reports a corrupt download or a checksum mismatch as RuntimeError,
    which the fallback to base did not catch: the batch ended in a traceback."""

    asked = []

    class Model:
        def transcribe(self, path, language=None):
            return {'text': 'the fallback model heard every word of this'}

    def load_model(name):
        asked.append(name)
        if name != 'base':
            raise RuntimeError('SHA256 checksum does not not match')
        return Model()

    saved = whisper.load_model
    whisper.load_model = load_model
    with tempfile.TemporaryDirectory() as tmp:
        audio = os.path.join(tmp, 'clip.mp3')
        io.open(audio, 'wb').close()
        try:
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                text, _language = YouTubeTranscriber().transcribe_audio_file(
                    audio, 'large-v3', 'en')
        finally:
            whisper.load_model = saved
    assert asked == ['large-v3', 'base'] and text.startswith('the fallback'), (asked, text)


def test_transcription_failures_cover_supported_exception_types():
    """A file Whisper cannot decode fails its own transcription, not the batch.

    Whisper reports ffmpeg's failure as a RuntimeError; ffmpeg's own
    CalledProcessError is caught as well, should one ever arrive unwrapped.
    """
    failures = (
        RuntimeError('decoder failed'),
        ValueError('invalid audio'),
        subprocess.CalledProcessError(1, ['ffmpeg'], stderr='no audio stream'),
    )

    for failure in failures:
        class Model:
            def transcribe(self, path, language=None, failure=failure):
                raise failure

        with tempfile.TemporaryDirectory() as tmp:
            audio = os.path.join(tmp, 'clip.mp3')
            io.open(audio, 'wb').close()
            with patch.object(whisper, 'load_model', return_value=Model()):
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    result = YouTubeTranscriber().transcribe_audio_file(
                        audio, 'base', 'fr', 'en')
        assert result == (None, 'en'), (type(failure).__name__, result)


def test_whisper_transcription_flow_covers_language_and_model_combinations():
    """Each target reaches Whisper as the right pass on the right weights, and
    the transcript is named for the language it came out in."""
    cases = (
        # Target, source, English-only weights, Whisper language, options,
        # model selected, and the language written into the transcript name.
        ('auto', None, False, None, {}, 'base', 'fr'),
        ('fr', 'ja', False, 'ja', {}, 'base', 'ja'),
        ('en', 'ja', False, 'ja', {'task': 'translate'}, 'base', 'en'),
        ('en', 'en', True, 'en', {}, 'base.en', 'en'),
    )

    for (target, source_language, use_en_model, whisper_language, options,
         model_name, written) in cases:
        t = YouTubeTranscriber()
        with tempfile.TemporaryDirectory() as tmp:
            source_path = os.path.join(tmp, 'lecture.mp4')
            io.open(source_path, 'wb').close()
            t.TRANSCRIPT_DIR = os.path.join(tmp, 'Transcript')
            t.RAW_TRANSCRIPT_DIR = os.path.join(t.TRANSCRIPT_DIR, 'Raw')
            t.startfile = lambda _path: None

            class Model:
                def transcribe(self, path, language=None, source_path=source_path,
                               whisper_language=whisper_language, target=target,
                               options=options, written=written, **actual_options):
                    assert path == source_path
                    assert language == whisper_language, (target, language)
                    assert actual_options == options, (target, actual_options)
                    return {'text': 'recognized words', 'language': written}

            cfg = module.SessionConfig(
                url=source_path, is_local_file=True, sources=[(source_path, True, None)],
                used_fields={}, transcribe_audio=True, target_language=target,
                target_languages=[target], source_language=source_language,
                use_en_model=use_en_model)
            with patch.object(t, 'is_valid_media_file', return_value=True):
                with patch.object(whisper, 'load_model', return_value=Model()) as load_model:
                    with redirect_stdout(io.StringIO()):
                        module._run_pipeline(t, cfg)

            transcript = os.path.join(t.TRANSCRIPT_DIR, f'lecture [Whisper {written}].txt')
            assert io.open(transcript, encoding='utf-8').read() == 'recognized words'
            load_model.assert_called_once_with(model_name)


def test_a_refined_transcript_is_not_deleted_before_its_raw_copy_is_saved():
    """A refine-only run retires the source from Transcript/ once its text is in
    Raw/. A Raw/ save that failed still let the refinement report success, and
    the source was deleted with no copy of it anywhere."""

    t = YouTubeTranscriber()
    t.startfile = lambda *a: None
    t.enhance_text = lambda text, *a, **k: text.upper()
    with tempfile.TemporaryDirectory() as tmp:
        t.TRANSCRIPT_DIR = os.path.join(tmp, 'Transcript')
        t.RAW_TRANSCRIPT_DIR = os.path.join(t.TRANSCRIPT_DIR, 'Raw')
        os.makedirs(t.TRANSCRIPT_DIR)
        source = os.path.join(t.TRANSCRIPT_DIR, 'talk.txt')
        io.open(source, 'w', encoding='utf-8').write('the only words')
        cfg = module.SessionConfig(used_fields={}, ai_mode=module.AIEnhancementMode.LOCAL,
                                   prompts=[('TIDY', 'prompt-refinement.txt')])
        real_save = t.save_transcript

        def refine(save):
            t.save_transcript = save
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                module._enhance_and_save(t, cfg, 'the only words', 'talk',
                                         open_after=False, source=source)

        refine(lambda text, name, folder, **k: (
            folder != t.RAW_TRANSCRIPT_DIR and real_save(text, name, folder, **k)))
        assert os.path.exists(source), 'the only copy was deleted'
        # Once the copy is there, the source is retired as before
        cfg.used_fields['URL'] = f'{source},https://youtu.be/other'
        refine(real_save)
        assert not os.path.exists(source)
        raw = os.path.join(t.RAW_TRANSCRIPT_DIR, 'talk.txt')
        assert io.open(raw).read() == 'the only words'
        # ...and a profile made from the session names the copy: it named the
        # file just moved, and replayed as "Invalid input" and a crash
        assert cfg.used_fields['URL'] == f'{raw},https://youtu.be/other', cfg.used_fields

        # TRANSCRIPT_RENAME names a refine-only run's output too, and was ignored
        io.open(source, 'w', encoding='utf-8').write('the only words')
        cfg.refine_sources, cfg.transcript_rename = [source], 'meeting'
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            module._refine_transcripts(t, cfg)
        assert os.path.exists(os.path.join(t.TRANSCRIPT_DIR, 'meeting - refinement.txt'))
        assert not os.path.exists(source), 'renamed, and its Raw/ copy with it'
        cfg.transcript_rename = None

        # A refinement that changed nothing writes nothing: not the text back
        # over its source, nor a copy of a transcript from elsewhere
        elsewhere = os.path.join(tmp, 'call.txt')
        io.open(elsewhere, 'w', encoding='utf-8').write('said and done')
        t.enhance_text = lambda text, *a, **k: text
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            module._enhance_and_save(t, cfg, 'said and done', 'call', open_after=False,
                                     source=elsewhere)
        assert not os.path.exists(os.path.join(t.TRANSCRIPT_DIR, 'call.txt'))
        assert os.path.exists(elsewhere)

        # KEEP_TRANSCRIPT=n retires a source a refinement replaced, but a summary
        # does not say what it said: the source was the last copy of the words
        t.enhance_text = lambda text, *a, **k: text.upper()
        cfg.keep_transcript = False
        for prompt, survives in (('prompt-summary.txt', True), ('prompt-refinement.txt', False)):
            io.open(source, 'w', encoding='utf-8').write('the only words')
            cfg.prompts = [('DO IT', prompt)]
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                module._enhance_and_save(t, cfg, 'the only words', 'talk',
                                         open_after=False, source=source)
            assert os.path.exists(source) == survives, prompt


class _Skipped(Exception):
    """A test that cannot run here: no ffmpeg, no symlinks."""


def _skip(reason):
    """Skip the running test, where the old print-and-return passed it quietly.

    pytest is told, so it reports a skip rather than a pass; without pytest the
    runner at the bottom of this file prints it.
    """
    if 'pytest' in sys.modules:
        import pytest
        pytest.skip(reason)
    raise _Skipped(reason)


def _ffmpeg_available():
    try:
        subprocess.run(['ffmpeg', '-hide_banner', '-version'],
                       capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, OSError):
        return False


def _make_clip(path, kind):
    """A fraction of a second of real media, so the ffmpeg paths run for real."""
    source = ('testsrc=duration=0.2:size=160x120:rate=10' if kind == 'video'
              else 'sine=frequency=440:duration=0.2')
    codec = (['-c:v', 'libx264', '-pix_fmt', 'yuv420p'] if kind == 'video'
             else ['-c:a', 'libmp3lame'])
    subprocess.run(['ffmpeg', '-y', '-v', 'error', '-f', 'lavfi', '-i', source]
                   + codec + [path], capture_output=True, check=True)
    return path


def test_ffmpeg_leaves_stdin_to_the_prompts():
    """ffmpeg reads its keyboard commands from stdin as it works - q stops it -
    and so took the first character of whatever answer was waiting there: a
    path piped to a profile's next round arrived without its leading slash."""
    if not _ffmpeg_available():
        _skip('no ffmpeg')
    t = YouTubeTranscriber()
    with tempfile.TemporaryDirectory() as tmp:
        clip = _make_clip(os.path.join(tmp, 'clip.mp3'), 'audio')
        read_end, write_end = os.pipe()
        os.write(write_end, b'/next/answer\n')
        os.close(write_end)
        saved = os.dup(0)
        os.dup2(read_end, 0)
        try:
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                converted = t.convert_media(clip, 'wav', 'audio', tmp, 'converted',
                                            replace_source=False)
        finally:
            os.dup2(saved, 0)
            os.close(saved)
        left = os.read(read_end, 64)
        os.close(read_end)
    assert converted, 'the conversion itself failed'
    assert left == b'/next/answer\n', left


def _plain_info():
    """A plain video's formats, shaped as yt-dlp reports them: worst first."""
    return {'webpage_url': 'https://youtu.be/x', 'formats': [
        {'format_id': '160', 'vcodec': 'avc1', 'acodec': 'none', 'height': 144},
        {'format_id': '136', 'vcodec': 'avc1', 'acodec': 'none', 'height': 720},
        {'format_id': '249', 'vcodec': 'none', 'acodec': 'opus', 'abr': 60.0,
         'format_note': 'low', 'language_preference': 10},
        {'format_id': '251', 'vcodec': 'none', 'acodec': 'opus', 'abr': 106.0,
         'format_note': 'medium', 'language_preference': 10},
    ]}


def test_a_video_only_file_has_no_audio_however_the_stream_was_served():
    """The progressive fallback, which arrives with the audio still in it.

    A height YouTube publishes only as a muxed stream matches no "bestvideo"
    filter, so video_format ends every branch in a fallback that can select
    one. The file called "Video Only" has to be exactly that, and the merge has
    to carry the audio tier it fetched rather than the one it was handed.
    """
    if not _ffmpeg_available():
        _skip('no ffmpeg')
    t = YouTubeTranscriber()
    assert t.video_format('144p').endswith('/best')

    with tempfile.TemporaryDirectory() as tmp:
        muxed = os.path.join(tmp, 'served.mp4')
        subprocess.run(
            ['ffmpeg', '-y', '-v', 'error',
             '-f', 'lavfi', '-i', 'testsrc=duration=0.2:size=160x120:rate=10',
             '-f', 'lavfi', '-i', 'sine=frequency=440:duration=0.2:sample_rate=44100',
             '-ac', '2', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac',
             '-shortest', muxed], capture_output=True, check=True)
        assert t.stream_codec(muxed, 'audio') is not None

        # The wanted audio is mono, the muxed one stereo: ffmpeg left to choose
        # takes the stream with more channels, which is the wrong one
        wanted = os.path.join(tmp, 'wanted.mp3')
        subprocess.run(
            ['ffmpeg', '-y', '-v', 'error', '-f', 'lavfi',
             '-i', 'sine=frequency=880:duration=0.2:sample_rate=44100',
             '-ac', '1', '-c:a', 'libmp3lame', wanted],
            capture_output=True, check=True)

        merged = os.path.join(tmp, 'merged.mp4')
        assert t.combine_audio_video(muxed, wanted, merged)
        assert t.stream_property(merged, 'audio', 'channels') == '1'

        # Copied, not re-encoded: FORMAT_ORIGINAL promises no second generation
        assert t.strip_audio(muxed) == muxed
        assert t.stream_codec(muxed, 'audio') is None
        assert t.stream_codec(muxed, 'video') == 'h264'
        assert not os.path.exists(os.path.join(tmp, 'served.silent.mp4'))
        # Nothing to strip is not a failure, and costs no second ffmpeg run
        assert t.strip_audio(muxed) == muxed


def _video_only_pass(t, folder):
    """A pass set up just far enough for fetch_video to fetch one 144p
    video-only stream, as 'served', into `folder`."""
    video_pass = object.__new__(module._Pass)
    video_pass.transcriber = t
    video_pass.cfg = SimpleNamespace(download_video=False, video_only=True,
                                     video_scratch=None, url='https://youtu.be/example')
    video_pass.only_res = ['144p']
    video_pass.video_res = []
    video_pass.video_only_files = {}
    video_pass.video_files = {}
    video_pass.dir_for = lambda *_args: folder
    video_pass.stem_for = lambda *_args: 'served'
    return video_pass


def test_failed_audio_stripping_is_not_reported_as_video_only():
    """A muxed download whose audio could not be removed stayed under the
    "Video Only" name and was reported as downloaded."""
    t = YouTubeTranscriber()
    with tempfile.TemporaryDirectory() as tmp:
        muxed = os.path.join(tmp, 'served.mp4')
        io.open(muxed, 'wb').close()
        video_pass = _video_only_pass(t, tmp)

        output = io.StringIO()
        with patch.object(t, 'download_format', return_value=muxed):
            with patch.object(t, 'stream_codec', return_value='aac'):
                with patch.object(module.subprocess, 'run',
                                  side_effect=subprocess.CalledProcessError(
                                      1, ['ffmpeg'], stderr='disk full')):
                    with redirect_stdout(output), redirect_stderr(io.StringIO()):
                        video_pass.fetch_video()
        assert not video_pass.video_only_files
        assert 'Video downloaded to' not in output.getvalue()
        assert not os.path.exists(muxed)
        assert not os.path.exists(os.path.join(tmp, 'served.silent.mp4'))


def test_audio_stripping_handles_all_ffmpeg_failure_shapes():
    """However ffmpeg fails - it raises, writes nothing, or its copy cannot
    take the download's place - neither the download nor the copy is left."""
    failures = (
        ('nonzero exit', 'raise', subprocess.CalledProcessError(
            1, ['ffmpeg'], stderr='decode failed')),
        ('missing ffmpeg', 'raise', OSError('ffmpeg not found')),
        ('missing output', 'no_output', None),
        ('empty output', 'empty_output', None),
        ('rename failure', 'rename', OSError('permission denied')),
    )

    for label, behavior, exception in failures:
        t = YouTubeTranscriber()
        with tempfile.TemporaryDirectory() as tmp:
            media = os.path.join(tmp, 'served.mp4')
            silent = os.path.join(tmp, 'served.silent.mp4')
            io.open(media, 'wb').write(b'muxed media')

            def ffmpeg(command, behavior=behavior, exception=exception, **_kwargs):
                if behavior == 'raise':
                    raise exception
                if behavior in ('empty_output', 'rename'):
                    with open(command[-1], 'wb') as output:
                        if behavior == 'rename':
                            output.write(b'video only')

            with patch.object(t, 'stream_codec', return_value='aac'):
                with patch.object(module.subprocess, 'run', side_effect=ffmpeg):
                    if behavior == 'rename':
                        with patch.object(module.os, 'replace', side_effect=exception):
                            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                                result = t.strip_audio(media)
                    else:
                        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                            result = t.strip_audio(media)
            assert result is None, (label, result)
            assert not os.path.exists(media), label
            assert not os.path.exists(silent), label


def test_audio_probe_failures_never_publish_a_video_only_file():
    """An ffprobe that could not run read as "no audio", so the muxed download
    was published as video only without its audio ever being looked at."""
    failures = (
        subprocess.CalledProcessError(1, ['ffprobe'], stderr='invalid container'),
        OSError('ffprobe not found'),
    )

    for failure in failures:
        t = YouTubeTranscriber()
        with tempfile.TemporaryDirectory() as tmp:
            media = os.path.join(tmp, 'served.mp4')
            io.open(media, 'wb').write(b'muxed media')
            video_pass = _video_only_pass(t, tmp)

            def failed_probe(command, failure=failure, **_kwargs):
                assert command[0] == 'ffprobe', command
                raise failure

            output = io.StringIO()
            with patch.object(t, 'download_format', return_value=media):
                with patch.object(module.subprocess, 'run', side_effect=failed_probe):
                    with redirect_stdout(output), redirect_stderr(io.StringIO()):
                        video_pass.fetch_video()
            assert not video_pass.video_only_files, (type(failure).__name__, output.getvalue())
            assert 'Video downloaded to' not in output.getvalue()
            assert not os.path.exists(media)


def test_conversion_copies_what_it_can_and_leaves_nothing_behind():
    """The ffmpeg paths, on real streams.

    What ffmpeg is asked for is not what a user types: the muxer behind .mkv is
    called "matroska", and asking for the codec something already is has to
    cost a remux rather than a generation of quality loss.
    """
    if not _ffmpeg_available():
        _skip('no ffmpeg')
    t = YouTubeTranscriber()

    assert t.format_extension('matroska') == 'mkv'
    assert t.format_extension('mkv') == 'mkv'
    # The ipod muxer writes .m4v, .m4a and .m4b; a typed name that is already
    # one of them stays itself
    assert t.format_extension('m4a') == 'm4a'
    assert t.format_extension('mp4') == 'mp4'
    # ffmpeg lists muxers that write no file at all
    assert t.format_extension('null') is None

    with tempfile.TemporaryDirectory() as tmp:
        video = _make_clip(os.path.join(tmp, 'clip.mp4'), 'video')
        audio = _make_clip(os.path.join(tmp, 'clip.mp3'), 'audio')

        def bitstream(path, kind):
            return subprocess.run(
                ['ffmpeg', '-v', 'error', '-i', path, '-map',
                 '0:v:0' if kind == 'video' else '0:a:0', '-c', 'copy', '-f', 'md5', '-'],
                capture_output=True, text=True).stdout

        before = bitstream(video, 'video')
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            same = t.convert_media(video, 'h264', 'video', tmp, 'clip')
        assert t.stream_codec(same, 'video') == 'h264'
        # Byte-identical: it was copied, not re-encoded
        assert bitstream(same, 'video') == before

        # The extension follows the container, whatever the container is called
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            remuxed = t.convert_media(audio, 'matroska', 'audio', tmp, 'as_mkv')
        assert remuxed.endswith('.mkv'), remuxed
        assert t.stream_codec(remuxed, 'audio') == 'mp3'

        # What the container will take is copied; what it will not is not.
        # MP4 may legally hold Opus, but the reason anyone asks for MP4 is that
        # everything plays it, so its audio is brought into line instead.
        opus = os.path.join(tmp, 'clip.opus.webm')
        subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', audio,
                        '-c:a', 'libopus', opus], capture_output=True, check=True)
        for container, want in (('mp4', 'aac'), ('mkv', 'opus')):
            merged = os.path.join(tmp, f'merged.{container}')
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                assert t.combine_audio_video(video, opus, merged)
            assert t.stream_codec(merged, 'audio') == want, (container, want)
            # The video stream is copied either way
            assert bitstream(merged, 'video') == before, container

        # ffmpeg's -y opens the output before it discovers it cannot write it,
        # so a failed merge must not leave a 0-byte file posing as the result
        doomed = os.path.join(tmp, 'doomed.matroska')
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            assert t.combine_audio_video(video, audio, doomed) is None
        assert not os.path.exists(doomed)
        # ...and the inputs survive, so the run can be retried
        assert os.path.exists(video) and os.path.exists(audio)


def test_pipeline_fetches_each_stream_once_and_names_what_it_saved():
    """Every download combination, end to end with real ffmpeg merges.

    Only the two network calls are faked. What is asserted is which files a
    combination leaves behind, what they are called, and how many streams were
    fetched to produce them.
    """
    if not _ffmpeg_available():
        _skip('no ffmpeg')

    info = _plain_info()
    with tempfile.TemporaryDirectory() as tmp:
        t = YouTubeTranscriber()
        t.startfile = lambda *a: None
        t.transcribe_audio_file = lambda *a: ('spoken words', 'en')
        dirs = {'AUDIO_DIR': 'Audio', 'VIDEO_DIR': 'Video',
                'VIDEO_WITHOUT_AUDIO_DIR': 'VideoWithoutAudio',
                'TRANSCRIPT_DIR': 'Transcript'}
        for attr, name in dirs.items():
            setattr(t, attr, os.path.join(tmp, name))
        t.RAW_TRANSCRIPT_DIR = os.path.join(t.TRANSCRIPT_DIR, 'Raw')

        seed_video = _make_clip(os.path.join(tmp, 'seed.mp4'), 'video')
        seed_audio = _make_clip(os.path.join(tmp, 'seed.mp3'), 'audio')
        fetched = []

        def fake_video(url, selector, output_dir, stem):
            fetched.append(selector)
            os.makedirs(output_dir, exist_ok=True)
            path = os.path.join(output_dir, stem + '.mp4')
            shutil.copyfile(seed_video, path)
            return path

        def fake_audio(video_info, stem, is_temp=False, format_selector='',
                       keep_in=None):
            fetched.append(format_selector)
            out = (os.path.join(t.AUDIO_DIR, t.TEMP_DIR) if is_temp
                   else (keep_in or t.AUDIO_DIR))
            os.makedirs(out, exist_ok=True)
            path = os.path.join(out, stem + '.mp3')
            shutil.copyfile(seed_audio, path)
            return path, os.path.abspath(path)

        t.download_format = fake_video
        t.download_audio_stream = fake_audio

        def run(**settings):
            for attr in dirs:
                shutil.rmtree(getattr(t, attr), ignore_errors=True)
            fetched.clear()
            settings.setdefault('transcribe_audio', False)
            cfg = module.SessionConfig(url='https://youtu.be/x', info=info,
                                       video_title='clip', used_fields={}, **settings)
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                module._run_pipeline(t, cfg)
            found = []
            for attr in dirs:
                for base, _sub, names in os.walk(getattr(t, attr)):
                    found += [os.path.relpath(os.path.join(base, n), tmp).replace('\\', '/')
                              for n in names]
            return sorted(found)

        # A merged video: one video stream, one audio stream, nothing left over
        assert run(download_video=True, video_resolution='144p',
                   video_audio_resolution='low', video_format='mp4') == [
            'Video/clip [144p 60k].mp4']
        assert fetched == ['bestvideo[height=144]/best[height=144]/best',
                           'bestaudio[abr<=60.0]/bestaudio']

        # The best of each carries no tag, because it is what you get by default
        assert run(download_video=True, video_resolution='720p',
                   video_audio_resolution='highest', video_format='mp4') == [
            'Video/clip.mp4']

        # Video-only, re-encoded to the codec it already is: same name, no copy
        assert run(video_only=True, video_only_resolution='144p',
                   video_only_format='h264') == [
            'VideoWithoutAudio/clip [144p] - Video Only.mp4']
        assert len(fetched) == 1

        # Both, at one resolution: the stream is fetched once and the
        # video-only deliverable is not eaten by the merge's cleanup
        assert run(download_video=True, video_resolution='144p', video_only=True,
                   video_only_resolution='144p', video_audio_resolution='highest',
                   video_format='mp4', video_only_format='original') == [
            'Video/clip [144p].mp4', 'VideoWithoutAudio/clip [144p] - Video Only.mp4']
        assert fetched == ['bestvideo[height=144]/best[height=144]/best',
                           'bestaudio/best']

        # Both, at different resolutions: two video streams, and the merge's
        # scratch copy is cleaned up while the deliverable stays
        assert run(download_video=True, video_resolution='720p', video_only=True,
                   video_only_resolution='144p', video_audio_resolution='highest',
                   video_format='mp4', video_only_format='original') == [
            'Video/clip.mp4', 'VideoWithoutAudio/clip [144p] - Video Only.mp4']
        # 720p is the best this video has, so it is asked for as "bestvideo"
        assert fetched == ['bestvideo[height=144]/best[height=144]/best',
                           'bestvideo/best', 'bestaudio/best']

        # "low" and "lowest" are one request here, so the audio is fetched once
        # and serves both the saved file and the merge
        assert run(download_video=True, video_resolution='144p',
                   video_audio_resolution='lowest', download_audio=True,
                   audio_resolution='low', video_format='mp4',
                   audio_format='original') == [
            'Audio/clip [60k].mp3', 'Video/clip [144p 60k].mp4']
        assert fetched.count('bestaudio[abr<=60.0]/bestaudio') == 1

        # "medium" is this video's best tier, so asking for it and asking for
        # "highest" name one stream, however unalike the two selectors look
        assert run(download_video=True, video_resolution='144p',
                   video_audio_resolution='highest', download_audio=True,
                   audio_resolution='medium', video_format='mp4',
                   audio_format='original') == ['Audio/clip.mp3',
                                                'Video/clip [144p].mp4']
        assert len([s for s in fetched if 'audio' in s]) == 1, fetched

        # A format change rewrites the deliverable and leaves no predecessor
        assert run(download_audio=True, audio_resolution='highest',
                   audio_format='wav') == ['Audio/clip.wav']

        # Transcription alone: the audio is scratch and is cleaned up after
        assert run(transcribe_audio=True, transcribe_audio_quality='lowest',
                   target_language='en') == ['Transcript/clip [Whisper en].txt']
        assert fetched == ['bestaudio[abr<=60.0]/bestaudio']

        # ...but audio that was asked for is a deliverable, and transcription
        # reuses it rather than fetching a second copy
        assert run(download_audio=True, audio_resolution='low',
                   audio_format='original', transcribe_audio=True,
                   transcribe_audio_quality='lowest',
                   target_language='en') == [
            'Audio/clip [60k].mp3', 'Transcript/clip [Whisper en].txt']
        assert fetched == ['bestaudio[abr<=60.0]/bestaudio']

        # Several formats are several files off ONE download, the merge reading
        # the streams as fetched rather than a re-encode of them
        assert run(download_video=True, video_resolution='144p',
                   video_audio_resolution='low', video_format='mp4,mkv') == [
            'Video/clip [144p 60k].mkv', 'Video/clip [144p 60k].mp4']
        assert fetched == ['bestvideo[height=144]/best[height=144]/best',
                           'bestaudio[abr<=60.0]/bestaudio']

        # Several resolutions cannot share a download, and do not try to
        assert run(download_video=True, video_resolution='144p,720p',
                   video_audio_resolution='low', video_format='mp4') == [
            'Video/clip [144p 60k].mp4', 'Video/clip [60k].mp4']
        # 720p is the top of this video, so it settles to "highest" and its
        # selector says so - one request, not a height lookup
        assert fetched == ['bestvideo[height=144]/best[height=144]/best',
                           'bestvideo/best',
                           'bestaudio[abr<=60.0]/bestaudio']

        # The full product: two resolutions by two audio tiers by two containers
        assert len(run(download_video=True, video_resolution='144p,720p',
                       video_audio_resolution='low,highest',
                       video_format='mp4,mkv')) == 8
        assert len(fetched) == 4, fetched

        # Two codecs share one container, so the codec joins the name rather
        # than the second file landing on the first
        assert run(video_only=True, video_only_resolution='144p',
                   video_only_format='h264,mpeg4') == [
            'VideoWithoutAudio/clip [144p h264] - Video Only.mp4',
            'VideoWithoutAudio/clip [144p mpeg4] - Video Only.mp4']
        assert fetched == ['bestvideo[height=144]/best[height=144]/best']

        # One format still names the file exactly as it always did
        assert run(video_only=True, video_only_resolution='144p',
                   video_only_format='h264') == [
            'VideoWithoutAudio/clip [144p] - Video Only.mp4']

        # Audio multiplies the same way, and transcription does not: one copy
        # is recognised however many deliverables were asked for
        assert run(download_audio=True, audio_resolution='low',
                   audio_format='mp3,flac', transcribe_audio=True,
                   target_language='en') == [
            'Audio/clip [60k].flac', 'Audio/clip [60k].mp3',
            'Transcript/clip [Whisper en].txt']
        assert fetched == ['bestaudio[abr<=60.0]/bestaudio']

        # Every format failing is no reason to lose the download as well: the
        # single-format path has always kept it, and a list of them does too
        real_convert = t.convert_media
        t.convert_media = lambda *a, **kw: None
        try:
            assert run(download_audio=True, audio_resolution='low',
                       audio_format='mp3,flac') == ['Audio/clip [60k].mp3']
        finally:
            t.convert_media = real_convert

        # A resolution this video does not offer re-prompts, and the menu takes
        # a list as readily as the field does: two videos off one answer
        script = ['144p,720p']
        builtins.input = lambda prompt='': script.pop(0)
        try:
            assert run(download_video=True, video_resolution='480p',
                       video_audio_resolution='highest', video_format='mp4') == [
                'Video/clip [144p].mp4', 'Video/clip.mp4']
        finally:
            builtins.input = REAL_INPUT
        assert not script

        # A source that cannot be fetched costs its own pass and no more: the
        # second entry still produces its video, through the real _run_one
        attempts = []

        def flaky(url, selector, output_dir, stem):
            attempts.append(url)
            if len(attempts) == 1:
                raise module.DownloadFailed('unavailable')
            return fake_video(url, selector, output_dir, stem)

        t.download_format = flaky
        try:
            assert run(sources=[('https://youtu.be/x', False, None)] * 2,
                       download_video=True, video_resolution='144p',
                       video_audio_resolution='highest', video_format='mp4') == [
                'Video/clip [144p].mp4']
        finally:
            t.download_format = fake_video
        assert len(attempts) == 2, attempts

        # A rename replaces the title and a path replaces the folder. The tags
        # still follow, so two resolutions are still two files - just elsewhere,
        # which is why nothing is left in the project's own Video/
        elsewhere = os.path.join(tmp, 'elsewhere')
        assert run(download_video=True, video_resolution='144p,720p',
                   video_audio_resolution='highest', video_format='mp4',
                   video_rename='lecture', video_path=elsewhere) == []
        assert sorted(os.listdir(elsewhere)) == [
            'lecture [144p].mp4', 'lecture.mp4'], sorted(os.listdir(elsewhere))


def test_youtube_publishes_a_transcript_only_for_the_language_it_was_spoken_in():
    """YouTube offers three kinds of caption and only two are transcripts.

    The author's own text and YouTube's machine transcript both report the
    audio; a translation of that transcript reports words nobody said, so it
    is left to Whisper, which at least listens.
    """
    t = YouTubeTranscriber()
    info = {
        'subtitles': {'en': [{'ext': 'json3', 'url': 'https://x/timedtext?lang=en'}]},
        'automatic_captions': {
            'en': [{'ext': 'vtt', 'url': 'https://x/timedtext?lang=en&caps=asr'}],
            'es': [{'ext': 'vtt', 'url': 'https://x/timedtext?lang=en&tlang=es'}],
        },
    }
    assert t.caption_language(info, 'en') == 'en'
    assert t.caption_language(info, 'es') is None
    assert t.caption_language(info, 'de') is None
    # A regional track is still the language it is a region of
    assert t.caption_language({'subtitles': {'en-US': [{'url': 'u'}]}}, 'en') == 'en-US'
    # A machine transcript on its own counts; a video with nothing does not
    assert t.caption_language({'automatic_captions': {'de': [{'url': 'u'}]}}, 'de') == 'de'
    assert t.caption_language({}, 'en') is None

    # A caption track is timed fragments; a transcript is prose
    payload = json.dumps({'events': [
        {'segs': [{'utf8': 'in front of the\nelephants'}]},
        {'segs': [{'utf8': ' and that is'}, {'utf8': ' cool'}]},
        {'segs': [{'utf8': 'and that is cool'}]},
    ]})
    assert t.captions_to_text(payload, '.json3') == (
        'in front of the elephants and that is cool')
    rolling = json.dumps({'events': [
        {'segs': [{'utf8': 'we have some'}]},
        {'segs': [{'utf8': 'we have some text'}]},
        {'segs': [{'utf8': 'some text to say'}]},
    ]})
    assert t.captions_to_text(rolling, '.json3') == 'we have some text to say'

    vtt = '\n'.join([
        'WEBVTT', 'Kind: captions', 'Language: en', '',
        '00:00:01.199 --> 00:00:03.359 align:start position:0%',
        'all right so here<00:00:01.679><c> we are</c>', '',
        '00:00:03.359 --> 00:00:05.000',
        'all right so here we are',
        'in front of<00:00:04.000><c> the elephants</c>', '',
    ])
    assert t.captions_to_text(vtt, '.vtt') == (
        'all right so here we are in front of the elephants')

    # Exercise cue-boundary overlaps of different lengths and ensure unrelated
    # repeated words are not treated as rolling-cue duplication.
    cases = (
        ('we have some', 'we have some text', 'we have some text'),
        ('once upon a time', 'time passed', 'once upon a time passed'),
        ('birds are here', 'some birds flew', 'birds are here some birds flew'),
        ('same words', 'same words', 'same words'),
    )
    for previous, current, expected in cases:
        json3 = json.dumps({'events': [
            {'segs': [{'utf8': previous}]}, {'segs': [{'utf8': current}]},
        ]})
        assert t.captions_to_text(json3, '.json3') == expected
        vtt = '\n'.join([
            'WEBVTT', '',
            '00:00:00.000 --> 00:00:01.000', previous, '',
            '00:00:01.000 --> 00:00:02.000', current, '',
        ])
        assert t.captions_to_text(vtt, '.vtt') == expected


def _caption_info(**over):
    """A video's caption listing, shaped as yt-dlp reports one."""
    info = {
        'language': 'en-US',
        'subtitles': {'en': [{'ext': 'json3', 'url': 'https://x/t?lang=en', 'name': 'English'}]},
        'automatic_captions': {
            'en': [{'ext': 'vtt', 'url': 'https://x/t?lang=en&caps=asr', 'name': 'English'}],
            'en-orig': [{'ext': 'vtt', 'url': 'https://x/t?lang=en&caps=asr',
                         'name': 'English (Original)'}],
            'de': [{'ext': 'vtt', 'url': 'https://x/t?lang=en&tlang=de', 'name': 'German'}],
        },
    }
    info.update(over)
    return info


def test_the_track_the_video_was_spoken_in_is_the_one_without_a_tag():
    """Which of a hundred tracks is the transcript, and which are about it.

    YouTube marks the source track `-orig` and also reports the video's own
    language; either identifies it, and the uploader's hand-written text for
    that language beats the machine's.
    """
    t = YouTubeTranscriber()
    info = _caption_info()
    # The uploader's own 'en' wins the key from the machine's 'en'
    assert t.caption_tracks(info)['en'] == 'English'
    assert set(t.caption_tracks(info)) == {'en', 'en-orig', 'de'}
    # '-orig' names the language; the best track in it is the uploader's
    assert t.original_caption(info) == 'en'
    # Without the marker, the declared language does the same job
    assert t.original_caption(_caption_info(automatic_captions={})) == 'en'
    # With neither, the uploader's own track is the closest thing to a source
    assert t.original_caption({'subtitles': {'ja': [{'url': 'u'}]}}) == 'ja'
    assert t.original_caption({}) is None

    # A script variant is its own transcript, not a synonym for its language:
    # zh-Hant is a different text from zh-Hans, and only one is the original
    chinese = {'automatic_captions': {
        'zh-Hant': [{'url': 'https://x/t?lang=zh-Hant'}],
        'zh-Hans': [{'url': 'https://x/t?lang=zh-Hans'}],
        'zh-Hans-orig': [{'url': 'https://x/t?lang=zh-Hans'}]}}
    assert t.original_caption(chinese) == 'zh-Hans'
    assert t.caption_language(chinese, 'zh-Hant') == 'zh-Hant'
    # An unqualified language still matches whatever variant is on offer
    assert t.caption_language(chinese, 'zh') in ('zh-Hant', 'zh-Hans')


def test_downloaded_transcripts_are_named_and_enhanced_by_what_was_asked_for():
    """Naming and the cost of `all`.

    The spoken-language transcript is the transcript, so it carries no tag.
    Enhancement is charged per file, so `all` enhances only that one, while a
    list the user wrote out is enhanced in full.
    """

    t = YouTubeTranscriber()
    t.startfile = lambda *a: None
    t.fetch_caption_text = lambda url, key: f'the {key} words'
    t.enhance_text = lambda text, *a, **kw: text.upper()

    def run(**settings):
        with tempfile.TemporaryDirectory() as tmp:
            t.TRANSCRIPT_DIR = os.path.join(tmp, 'Transcript')
            t.RAW_TRANSCRIPT_DIR = os.path.join(t.TRANSCRIPT_DIR, 'Raw')
            cfg = module.SessionConfig(url='https://youtu.be/x', info=_caption_info(),
                                       ai_mode=module.AIEnhancementMode.LOCAL,
                                       used_fields={}, **settings)
            with redirect_stdout(io.StringIO()):
                module._save_yt_transcripts(t, cfg, 'clip')
            found = {os.path.relpath(os.path.join(b, n), t.TRANSCRIPT_DIR)
                     .replace(os.sep, '/'):
                     io.open(os.path.join(b, n), encoding='utf-8').read()
                     for b, _s, ns in os.walk(t.TRANSCRIPT_DIR) for n in ns}
            return dict(sorted(found.items()))

    # No enhancement: the spoken language untagged, everything else tagged
    found = run(yt_transcript_languages=['en', 'de'])
    assert found == {'clip [de].txt': 'the de words', 'clip.txt': 'the en words'}, found

    # `all` pays for one enhancement, on the transcript the rest translate
    found = run(yt_transcript_languages=['en', 'en-orig', 'de'], yt_transcript_all=True,
                prompts=[('translate this', 'prompt0-translator.txt')])
    assert list(found) == ['Raw/clip.txt', 'clip - translator.txt',
                           'clip [de].txt', 'clip [en-orig].txt'], found
    # ...and the German one is the text as it came, not shouted at by the model
    assert found['clip [de].txt'] == 'the de words'
    assert found['clip - translator.txt'] == 'THE EN WORDS'

    # A list the user wrote out is enhanced in full
    found = run(yt_transcript_languages=['en', 'de'],
                prompts=[('translate this', 'prompt0-translator.txt')])
    assert list(found) == ['Raw/clip [de].txt', 'Raw/clip.txt',
                           'clip - translator.txt',
                           'clip [de] - translator.txt'], found

    # ...and the untouched copies can be turned off
    found = run(yt_transcript_languages=['en'], keep_transcript=False,
                prompts=[('translate this', 'prompt0-translator.txt')])
    assert list(found) == ['clip - translator.txt'], found


def test_a_list_answer_takes_commas_spaces_or_both():
    """One separator rule for every list field: PROMPT, TARGET_LANGUAGE, URL.

    Entries can contain spaces themselves, so a piece that is already a whole
    entry is never split further - which is what keeps a path and a two-word
    language name intact.
    """
    t = YouTubeTranscriber()
    for text in ('en,fr,ja', 'en, fr, ja', 'en fr ja', 'en , fr  ja'):
        assert t.split_entries(text) == ['en', 'fr', 'ja'], text
    # Any run of separators, in any mix, is one separation - including at the
    # ends, so a stray comma is not an entry that fails to be a language
    for text in ('en    ,   ,,,   fr', '  ,, en ,,,  fr ,, ',
                 'en\t,\t\tfr', ',,,en,,fr,,,', 'en \n fr'):
        assert t.split_entries(text) == ['en', 'fr'], repr(text)
    for text in ('', None, '   ', ',', '  ,,,  '):
        assert t.split_entries(text) == [], repr(text)

    # is_whole stops a spaced entry being torn apart, whole answer tried first
    known = ('Chinese Simplified', 'French').__contains__
    assert t.split_entries('Chinese Simplified', known) == ['Chinese Simplified']
    assert t.split_entries('Chinese Simplified, French', known) == [
        'Chinese Simplified', 'French']
    # ...and the languages themselves go through the same rule
    assert t.normalize_languages('English French')[0] == ['en', 'fr']
    assert t.normalize_languages('en, English, fr')[0] == ['en', 'fr']


def test_a_url_answer_is_a_list_of_passes():
    """URL is a list, done in order: videos, media files, and - for 's' or a
    .txt path - a pass that refines instead of downloading anything.
    """
    t = YouTubeTranscriber()
    log = io.StringIO()
    with tempfile.TemporaryDirectory() as tmp:
        txt = os.path.join(tmp, 'one.txt')
        clip = os.path.join(tmp, 'clip.mp3')
        spaced = os.path.join(tmp, 'my clip.mp3')
        for path in (txt, clip, spaced):
            io.open(path, 'w', encoding='utf-8').write('words')

        with redirect_stdout(log):
            entries = t.source_entries(f'{clip}, youtu.be/abc, {txt}')
        assert entries == [(clip, True, None),
                           ('https://youtu.be/abc', False, None),
                           (None, False, [txt])], entries
        # A path with a space in it is one entry, not two
        with redirect_stdout(log):
            assert t.source_entries(spaced) == [(spaced, True, None)]
        # One unusable entry disqualifies the whole answer rather than quietly
        # doing the part of the list the user got right
        with redirect_stdout(log):
            assert t.source_entries(f'{clip} ./nowhere/missing.mp3') == []

        # Each 's' is its own pass, so two of them refine twice
        t.select_transcripts = lambda: [txt]
        with redirect_stdout(log):
            entries = t.source_entries(f's {clip} s')
        assert [bool(entry[2]) for entry in entries] == [True, False, True], entries


def test_a_profile_without_a_url_asks_the_question_that_takes_a_list():
    """A repeat, or a template profile, asks for the source up front.

    The answer used to be deferred to a single-source prompt part way through
    the run: it advertised `S to refine` and a list, then rejected both and
    asked again, which a repeated refinement could never get past.
    """

    t = YouTubeTranscriber()
    t.fetch_video_info = lambda url: dict(_plain_info(), title='clip')
    t.prompt_for_source = lambda *a, **kw: (_ for _ in ()).throw(
        AssertionError('asked for one source, so a list and S were refused'))
    asked = []

    def one_video(*a, **kw):
        asked.append('sources')
        return [('https://youtu.be/x', False, None)]

    t.prompt_for_sources = one_video
    base = {'DOWNLOAD_VIDEO': 'n', 'VIDEO_ONLY': 'n', 'DOWNLOAD_AUDIO': 'n',
            'DOWNLOAD_YT_TRANSCRIPT': 'n', 'TRANSCRIBE_AUDIO': 'y',
            'MODEL_CHOICE': 'tiny', 'TARGET_LANGUAGE': 'en', 'USE_EN_MODEL': 'n',
            'AI_REFINEMENT': 'n', 'REPEAT': 'n',
            'TRANSCRIBE_AUDIO_QUALITY': 'lowest'}

    def configure(repeat=False, **over):
        asked.clear()
        profile = module._Profile('test.txt', dict(base, **over), module.Session(repeat=repeat))
        with redirect_stdout(io.StringIO()):
            return module._configure(t, profile)

    # A template profile leaves URL blank, or on the placeholder
    for blank in ('', YouTubeTranscriber.URL_PLACEHOLDER):
        cfg = configure(URL=blank)
        assert asked == ['sources'], (blank, asked)
        assert cfg.url == 'https://youtu.be/x'

    # A repeat ignores the URL the profile does name, and asks the same way
    cfg = configure(repeat=True, URL='https://youtu.be/from-the-profile')
    assert asked == ['sources'], asked
    assert cfg.url == 'https://youtu.be/x'


def test_each_pass_is_named_after_its_own_source():
    """A later entry reusing the prefetched metadata gets the title back with it.

    The video's title is fetched once, to build the menus; a local entry ahead
    of it in the list renames the run after itself, and the video's own pass
    used to keep that name and save its transcript under it.
    """

    t = YouTubeTranscriber()
    seen = []

    def note(transcriber, cfg):
        seen.append((cfg.url, cfg.video_title, cfg.info is not None))
        # A local pass names itself after the file, as the real one does
        if cfg.is_local_file:
            cfg.video_title = os.path.splitext(os.path.basename(cfg.url))[0]

    real = module._run_one
    module._run_one = note
    try:
        cfg = module.SessionConfig(url='https://youtu.be/x', info={'title': 'Video Three'},
                                   video_title='Video Three', used_fields={})
        cfg.sources = [('clip.mp4', True, None), ('https://youtu.be/x', False, None)]
        with redirect_stdout(io.StringIO()):
            module._run_pipeline(t, cfg)
    finally:
        module._run_one = real

    assert seen == [('clip.mp4', '', False),
                    ('https://youtu.be/x', 'Video Three', True)], seen


def test_a_mixed_list_asks_its_questions_about_a_video():
    """Resolutions and caption tracks are a menu of what one video offers, so a
    list that mixes a local file with a video asks about the video.
    """

    cfg = module.SessionConfig(used_fields={})
    cfg.sources = [('clip.mp4', True, None), ('https://youtu.be/x', False, None),
                   (None, False, ['a.txt'])]
    module._settle_sources(cfg)
    assert (cfg.url, cfg.is_local_file) == ('https://youtu.be/x', False)
    # The list is the point of the session, so a profile records it verbatim
    assert cfg.used_fields['URL'] == 'clip.mp4,https://youtu.be/x,a.txt'

    # One video stays a template to point at the next one
    cfg = module.SessionConfig(used_fields={})
    cfg.sources = [('https://youtu.be/x', False, None)]
    module._settle_sources(cfg)
    assert 'URL' not in cfg.used_fields

    # Nothing but refinements: no media to ask any of it about
    cfg = module.SessionConfig(used_fields={})
    cfg.sources = [(None, False, ['a.txt']), (None, False, ['b.txt'])]
    module._settle_sources(cfg)
    assert cfg.url is None and cfg.is_local_file is True
    assert cfg.used_fields['URL'] == 'a.txt,b.txt'


def test_a_source_answer_names_transcripts_or_media():
    """A .txt on disk is a transcript to refine; anything else is a source to fetch.

    Commas separate several, as PROMPT does - sanitize_filename strips commas,
    so nothing this script writes carries one, and a hand-named file that does
    still wins over being split.
    """
    t = YouTubeTranscriber()
    with tempfile.TemporaryDirectory() as tmp:
        made = []
        for name in ('one.txt', 'two.txt', 'Meeting, Q3.txt', 'clip.mp3'):
            path = os.path.join(tmp, name)
            io.open(path, 'w', encoding='utf-8').write('words')
            made.append(path)
        one, two, comma, media = made

        assert t.transcript_sources(one) == [one]
        # Comma, comma and space, or space alone all say the same thing
        for text in (f'{one},{two}', f'{one}, {two}', f'{one} {two}',
                     f'{one} , {two}'):
            assert t.transcript_sources(text) == [one, two], text
        # A path with a space in it is one entry, not several
        spaced = os.path.join(tmp, 'Me at the zoo.txt')
        io.open(spaced, 'w', encoding='utf-8').write('words')
        assert t.transcript_sources(spaced) == [spaced]
        assert t.transcript_sources(f'{spaced},{one}') == [spaced, one]
        # The file that is really called that beats splitting on its comma
        assert t.transcript_sources(comma) == [comma]
        # Media, a URL, the placeholder and a .txt that is not there are not
        assert t.transcript_sources(media) is None
        assert t.transcript_sources('https://youtu.be/x') is None
        assert t.transcript_sources(t.URL_PLACEHOLDER) is None
        assert t.transcript_sources(os.path.join(tmp, 'gone.txt')) is None
        # One missing entry disqualifies the whole list rather than half of it
        assert t.transcript_sources(f'{one},{os.path.join(tmp, "gone.txt")}') is None


def test_only_a_transcript_in_transcript_is_retired_after_refining():
    """The source leaves Transcript/ because its text is now in Transcript/Raw/.

    That reasoning holds nowhere else: a file already in Raw/, or one named
    from outside the project, was read rather than taken over. And a run where
    every prompt left the text alone has no refinement to replace it with.
    """

    t = YouTubeTranscriber()
    t.startfile = lambda *a: None

    def refine(tmp, name, folder, enhance=True):
        t.TRANSCRIPT_DIR = os.path.join(tmp, 'Transcript')
        t.RAW_TRANSCRIPT_DIR = os.path.join(t.TRANSCRIPT_DIR, 'Raw')
        t.enhance_text = ((lambda text, mode, prompt, **kw: f'{prompt}: {text}')
                          if enhance else (lambda text, mode, prompt, **kw: text))
        source = os.path.join(folder, name)
        os.makedirs(folder, exist_ok=True)
        io.open(source, 'w', encoding='utf-8').write('the words')
        cfg = module.SessionConfig(
            used_fields={}, ai_mode=module.AIEnhancementMode.LOCAL,
            refine_sources=[source],
            prompts=[('TIDY', 'prompt-refinement.txt')])
        with redirect_stdout(io.StringIO()):
            module._refine_transcripts(t, cfg)
        return source

    with tempfile.TemporaryDirectory() as tmp:
        source = refine(tmp, 'a.txt', os.path.join(tmp, 'Transcript'))
        assert not os.path.exists(source)
        assert io.open(os.path.join(tmp, 'Transcript', 'Raw', 'a.txt'),
                       encoding='utf-8').read() == 'the words'
        assert os.path.exists(os.path.join(tmp, 'Transcript', 'a - refinement.txt'))

    with tempfile.TemporaryDirectory() as tmp:
        source = refine(tmp, 'b.txt', os.path.join(tmp, 'Transcript', 'Raw'))
        assert os.path.exists(source), 'a source already in Raw/ stays there'

    with tempfile.TemporaryDirectory() as tmp:
        source = refine(tmp, 'c.txt', os.path.join(tmp, 'elsewhere'))
        assert os.path.exists(source), 'a file outside the project is never ours'

    with tempfile.TemporaryDirectory() as tmp:
        source = refine(tmp, 'd.txt', os.path.join(tmp, 'Transcript'), enhance=False)
        assert os.path.exists(source), 'nothing was refined, so nothing replaces it'


def test_every_prompt_runs_over_every_transcript():
    """PROMPT is a list, and each entry earns its own file.

    Two prompts over two transcripts is four files, and the untouched text is
    kept once rather than rewritten per prompt.
    """

    t = YouTubeTranscriber()
    t.startfile = lambda *a: None
    t.fetch_caption_text = lambda url, key: f'the {key} words'
    keeps = {}
    t.enhance_text = lambda text, mode, prompt, **kw: (
        keeps.update({prompt: kw['keeps']}) or f'{prompt}: {text}')

    with tempfile.TemporaryDirectory() as tmp:
        t.TRANSCRIPT_DIR = os.path.join(tmp, 'Transcript')
        t.RAW_TRANSCRIPT_DIR = os.path.join(t.TRANSCRIPT_DIR, 'Raw')
        cfg = module.SessionConfig(
            url='https://youtu.be/x', info=_caption_info(), used_fields={},
            ai_mode=module.AIEnhancementMode.LOCAL,
            yt_transcript_languages=['en', 'de'],
            prompts=[('SHOUT', 'prompt0-translator.txt'),
                     ('TIDY', 'prompt-refinement.txt')])
        with redirect_stdout(io.StringIO()):
            module._save_yt_transcripts(t, cfg, 'clip')
        found = {os.path.relpath(os.path.join(b, n), t.TRANSCRIPT_DIR)
                 .replace(os.sep, '/'):
                 io.open(os.path.join(b, n), encoding='utf-8').read()
                 for b, _s, ns in os.walk(t.TRANSCRIPT_DIR) for n in ns}

    assert sorted(found) == [
        'Raw/clip [de].txt', 'Raw/clip.txt',
        'clip - refinement.txt', 'clip - translator.txt',
        'clip [de] - refinement.txt', 'clip [de] - translator.txt'], sorted(found)
    assert found['clip - translator.txt'] == 'SHOUT: the en words'
    assert found['clip - refinement.txt'] == 'TIDY: the en words'
    # Kept once, and it is the text as it came rather than either enhancement
    assert found['Raw/clip.txt'] == 'the en words'

    # Only a summary is let off the local check for a reply too short to be whole,
    # and only a refinement is held to the speaker's words
    assert keeps == {'SHOUT': 'all', 'TIDY': 'words'}, keeps
    with tempfile.TemporaryDirectory() as tmp:
        t.TRANSCRIPT_DIR = t.RAW_TRANSCRIPT_DIR = tmp
        # A prompt outside Prompt/ is labelled by its path, and only its filename counts
        cfg.prompts = [('BRIEF', 'prompt1-summarizer.txt'),
                       ('ELSEWHERE', os.path.join(tmp, 'summaries', 'translate.txt'))]
        with redirect_stdout(io.StringIO()):
            module._enhance_and_save(t, cfg, 'the words', 'clip', open_after=False)
    assert keeps['BRIEF'] == 'some' and keeps['ELSEWHERE'] == 'all', keeps

    # Two prompts that read as the same word still get a file each
    tags = [tag for _t, _l, tag in t.tagged_prompts(
        [('a', 'prompt0-translator.txt'), ('b', 'prompt1-translator.txt')])]
    assert tags == [' - translator', ' - translator 2'], tags


def test_listing_the_transcripts_is_not_read_as_a_refusal():
    """'f' is what the prompt offers for "show me what this video has".

    YesNo.NO spells "false" that way too, so reading the refusals first made
    the advertised answer do nothing at all.
    """

    t = YouTubeTranscriber()
    listed = []

    def picker(transcriber, info):
        listed.append(info)
        return ['de']

    real_picker = module._prompt_yt_transcript_selection
    module._prompt_yt_transcript_selection = picker
    try:
        for answer in ('f', 'fetch', 'F'):
            cfg = module.SessionConfig(url='https://youtu.be/x', info=_caption_info(),
                                       used_fields={})
            with redirect_stdout(io.StringIO()):
                module._settle_yt_transcripts(t, cfg, answer)
            assert cfg.yt_transcript_languages == ['de'], answer
            # and what is recorded is the pick, or a saved profile lists and waits
            assert cfg.yt_transcript_raw == 'de', cfg.yt_transcript_raw

        # ...while a refusal is still a refusal, and never reaches the listing
        for answer in ('n', 'no', 'skip', ''):
            cfg = module.SessionConfig(url='https://youtu.be/x', info=_caption_info(),
                                       used_fields={})
            with redirect_stdout(io.StringIO()):
                module._settle_yt_transcripts(t, cfg, answer)
            assert cfg.yt_transcript_languages is None, answer
    finally:
        module._prompt_yt_transcript_selection = real_picker
    assert len(listed) == 3, listed


def test_all_enhances_nothing_when_no_track_is_the_original():
    """`all` enhances the one transcript the rest translate. With no way to
    tell which that is, it used to announce enhancing "(None)" and enhance
    nothing - the announcement is the bug, the restraint is right."""

    t = YouTubeTranscriber()
    t.startfile = lambda *a: None
    t.fetch_caption_text = lambda url, key: f'the {key} words'
    t.enhance_text = lambda text, *a, **kw: text.upper()
    # Every track is a machine translation of something unnamed
    info = {'automatic_captions': {
        'de': [{'url': 'https://x/t?lang=de&tlang=de'}],
        'fr': [{'url': 'https://x/t?lang=fr&tlang=fr'}]}}

    with tempfile.TemporaryDirectory() as tmp:
        t.TRANSCRIPT_DIR = os.path.join(tmp, 'Transcript')
        t.RAW_TRANSCRIPT_DIR = os.path.join(t.TRANSCRIPT_DIR, 'Raw')
        cfg = module.SessionConfig(
            url='https://youtu.be/x', info=info, used_fields={},
            ai_mode=module.AIEnhancementMode.LOCAL, yt_transcript_all=True,
            yt_transcript_languages=['de', 'fr'],
            prompts=[('translate this', 'prompt0-translator.txt')])
        log = io.StringIO()
        with redirect_stdout(log):
            module._save_yt_transcripts(t, cfg, 'clip')
        found = sorted(n for _b, _s, ns in os.walk(t.TRANSCRIPT_DIR) for n in ns)

    assert found == ['clip [de].txt', 'clip [fr].txt'], found
    assert 'None' not in log.getvalue()
    assert 'Cannot tell which language' in log.getvalue()


def test_each_video_of_a_list_gets_its_own_transcript_tracks():
    """The answer was settled on the first video and its tracks used for every
    video after it: a Japanese video after an English one got 'en', the
    English translation, and never the Japanese original 'y' asks for."""

    t = YouTubeTranscriber()
    t.startfile = lambda *a: None
    fetched = []
    t.fetch_caption_text = lambda url, key: fetched.append(key) or f'the {key} words'
    japanese = {'language': 'ja', 'automatic_captions': {
        'ja-orig': [{'url': 'https://x/t?lang=ja', 'name': 'Japanese (Original)'}],
        'ja': [{'url': 'https://x/t?lang=ja', 'name': 'Japanese'}],
        'en': [{'url': 'https://x/t?lang=ja&tlang=en', 'name': 'English'}]}}
    with tempfile.TemporaryDirectory() as tmp:
        t.TRANSCRIPT_DIR = os.path.join(tmp, 'Transcript')
        t.RAW_TRANSCRIPT_DIR = os.path.join(t.TRANSCRIPT_DIR, 'Raw')
        for raw, settled, want in (('y', ['en'], ['ja']),
                                   ('all', ['en', 'en-orig', 'de'], ['ja-orig', 'ja', 'en']),
                                   ('en,de', ['en', 'de'], ['en'])):
            fetched.clear()
            cfg = module.SessionConfig(url='https://youtu.be/second', info=japanese,
                                       used_fields={}, yt_transcript_raw=raw,
                                       yt_transcript_all=raw == 'all',
                                       yt_transcript_languages=settled)
            with redirect_stdout(io.StringIO()):
                module._save_yt_transcripts(t, cfg, 'clip')
            assert fetched == want, (raw, fetched)

    # A list led by a video with no captions settled nothing, and the videos
    # after it saved no transcript at all
    videos = [('https://youtu.be/first', False, None), ('https://youtu.be/second', False, None)]
    for sources, raw, want in ((videos, 'y', ['ja']), (videos, 'all', ['ja-orig', 'ja', 'en']),
                               (videos, 'JA', ['ja']), (videos[:1], 'y', None)):
        fetched.clear()
        cfg = module.SessionConfig(url=sources[0][0], info={'language': 'en'},
                                   used_fields={}, sources=sources)
        with redirect_stdout(io.StringIO()):
            module._settle_yt_transcripts(t, cfg, raw)
            if cfg.yt_transcript_languages:
                cfg.info = japanese
                module._save_yt_transcripts(t, cfg, 'clip')
        assert (fetched or None) == want, (raw, fetched)


def test_a_local_file_never_writes_two_deliverables_to_one_name():
    """The download path tags a format that shares an extension with another;
    the local re-encode did not, so mkv beside matroska, or original beside the
    mp4 a file already is, wrote one file twice. Highest and lowest, both the
    file as it is, encoded it twice under one name too."""

    t = YouTubeTranscriber()
    written = []

    def convert_media(source, target, kind, folder, stem, **kwargs):
        ext = (os.path.splitext(source)[1].lstrip('.') if target == 'original'
               else t.format_extension(target) or target)
        written.append(os.path.join(folder, f'{stem}.{ext}'))
        return written[-1]

    t.convert_media = convert_media
    t.stream_codec = lambda source, kind: 'h264' if kind == 'video' else 'aac'
    t.source_height = lambda source: 720
    t.source_bitrate = lambda source: 128
    cfg = module.SessionConfig(
        url='clip.mp4', is_local_file=True, used_fields={}, sources=[('clip.mp4', True, None)],
        download_video=True, video_format='mkv,matroska', video_resolution='highest,lowest',
        download_audio=True, audio_format='mp3', audio_resolution='highest,lowest')
    with redirect_stdout(io.StringIO()):
        module._local_deliverables(t, cfg, 'clip')
        cfg.video_format, cfg.download_audio = 'mp4,original', False
        module._local_deliverables(t, cfg, 'clip')
    assert len(written) == len(set(written)), written
    assert len(written) == 5, written  # mkv, matroska, mp3, then mp4 and original

    # An audio file is not a video: it was re-encoded into Video/ as an mp4
    # with no picture in it
    written.clear()
    t.stream_codec = lambda source, kind: None if kind == 'video' else 'aac'
    with redirect_stdout(io.StringIO()):
        module._local_deliverables(t, cfg, 'clip')
    assert written == [], written


def test_a_profile_records_which_backend_the_session_used():
    """AI_REFINEMENT carries a bare y, so a profile without the backend
    replays a local session against whatever API key is on file."""

    t = YouTubeTranscriber()
    t.get_prompt_input = lambda: (['prompt0-translator.txt'], None)
    cfg = module.SessionConfig(used_fields=t.DEFAULT_FIELDS.copy(), transcribe_audio=True)
    last_round = module.Session(remembered={'AI_REFINEMENT': 'y', 'KEEP_TRANSCRIPT': 'y',
                                            'PLACEMENT': 'n'})
    # Configuration, which config.txt puts in the environment
    env = {'AI_PROVIDER': 'local', 'MODEL': 'microsoft/phi-2'}
    saved = {k: os.environ.get(k) for k in env}
    os.environ.update(env)
    try:
        with redirect_stdout(io.StringIO()):
            module._settle_refinement(t, cfg, module._Remembered(last_round))
    finally:
        for key, value in saved.items():
            os.environ.pop(key, None) if value is None else os.environ.update({key: value})

    assert cfg.used_fields['AI_REFINEMENT'] == 'y'
    assert cfg.used_fields['AI_PROVIDER'] == 'local'
    assert cfg.used_fields['MODEL'] == 'microsoft/phi-2'

    with tempfile.TemporaryDirectory() as tmp:
        t.PROFILE_DIR = tmp
        with redirect_stdout(io.StringIO()):
            t.create_profile(cfg.used_fields)
            # A session that settled no backend must not write blank lines that
            # would override config.txt with nothing
            t.create_profile(dict(t.DEFAULT_FIELDS, AI_REFINEMENT='n'))
        written = sorted(n for n in os.listdir(tmp) if n.startswith('profile'))
        first = io.open(os.path.join(tmp, written[0]), encoding='utf-8').read()
        second = io.open(os.path.join(tmp, written[1]), encoding='utf-8').read()
        config_txt = dotenv_values(os.path.join(tmp, t.CONFIG_ENV))

    assert 'AI_PROVIDER=local' in first.splitlines(), first
    assert 'MODEL=microsoft/phi-2' in first.splitlines(), first
    # The first save writes config.txt, comment and all, where there is none;
    # the comment must not read as a field
    assert config_txt == {'LOAD_PROFILE': t.DEFAULT_PROFILE, 'AI_PROVIDER': '',
                          'API_KEY': '', 'MODEL': ''}, config_txt
    # MODEL_CHOICE is a different field, so the check is on whole lines
    assert not [ln for ln in second.splitlines()
                if ln.startswith(('AI_PROVIDER', 'MODEL='))], second


def test_the_config_txt_git_holds_is_blank():
    """Profile/config.txt is tracked, so a key filled into it is a commit away
    from being published. The copy git holds must stay the blank template.

    Read from git's index, never from disk, where the file may hold that key,
    and no value is ever put in a failure message.
    """
    shipped = subprocess.run(
        ['git', 'show', ':OpenAIYouTubeTranscriber/Profile/config.txt'],
        cwd=os.path.dirname(os.path.abspath(__file__)), capture_output=True,
        text=True, encoding='utf-8')
    if shipped.returncode:
        return  # not a git checkout
    fields = dotenv_values(stream=io.StringIO(shipped.stdout))
    filled = [name for name, value in fields.items() if value]
    assert not filled, f'config.txt in git has a value in {filled}'
    assert shipped.stdout == 'LOAD_PROFILE=\n' + YouTubeTranscriber.CONFIG_TEMPLATE, \
        'config.txt in git has drifted from CONFIG_TEMPLATE'


def test_a_profile_can_be_named_by_its_full_path():
    """A profile kept outside Profile/, named in LOAD_PROFILE or at the prompt.

    An absolute LOAD_PROFILE loaded before, because os.path.join drops Profile/
    in front of one - but the name kept was the bare filename, so the repeat
    round looked in Profile/, missed, and only reached the file again by
    falling back to reading LOAD_PROFILE a second time.
    """
    keys = ('LOAD_PROFILE',)
    saved = {key: os.environ.get(key) for key in keys}
    t = YouTubeTranscriber()
    log = io.StringIO()

    def picked(answers):
        return answers.origin, answers.fields.get('URL')

    with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as elsewhere:
        t.PROFILE_DIR = os.path.join(home, 'Profile')
        os.makedirs(t.PROFILE_DIR)
        io.open(os.path.join(t.PROFILE_DIR, 'profile.txt'), 'w').write('URL=inside' + chr(10))
        far = os.path.join(elsewhere, 'profile-far.txt')
        io.open(far, 'w').write('URL=far' + chr(10))
        config_txt = os.path.join(t.PROFILE_DIR, t.CONFIG_ENV)
        try:
            for key in keys:
                os.environ.pop(key, None)
            # Quoted, as a copied Windows path is, and without its .txt
            io.open(config_txt, 'w').write(f'LOAD_PROFILE="{far[:-4]}"' + chr(10))
            with redirect_stdout(log):
                assert picked(module._select_profile(t, module.Session())) == (far, 'far'), \
                    log.getvalue()

            with redirect_stdout(log):
                answers = module._select_profile(t, module.Session(repeat=True, profile=far))
            assert picked(answers) == (far, 'far')
            assert 'not found' not in log.getvalue().lower(), log.getvalue()

            # At the prompt, beside the profiles it lists; a path to nothing asks again
            for key in keys:
                os.environ.pop(key, None)
            io.open(config_txt, 'w').write('LOAD_PROFILE=' + chr(10))
            script = [os.path.join(elsewhere, 'nothing.txt'), far]
            builtins.input = lambda prompt='': script.pop(0)
            try:
                with redirect_stdout(log):
                    assert picked(module._select_profile(t, module.Session())) == (far, 'far')
            finally:
                builtins.input = REAL_INPUT
            assert not script
            assert 'No profile found at' in log.getvalue()
        finally:
            for key, value in saved.items():
                os.environ.pop(key, None) if value is None else os.environ.update({key: value})


def test_probing_a_file_that_is_not_media_says_so_quietly():
    """is_valid_media_file asks a question; "no" is the answer, not an error.

    ffprobe's exit status was printed raw, so mistyping a path put a
    traceback-shaped line ahead of the message that actually helps.
    """
    t = YouTubeTranscriber()
    log = io.StringIO()
    with redirect_stdout(log):
        assert t.get_file_format(__file__) is None
        assert t.is_valid_media_file(__file__) is False
        assert t.is_valid_media_file('no-such-file-anywhere.mp3') is False
    assert log.getvalue() == "", log.getvalue()


def test_a_local_media_file_goes_straight_to_whisper():
    """Whisper reads a video container itself, and is_local_file is only ever
    set after is_valid_media_file passed - so there is no third case where the
    audio has to be extracted first."""

    source = inspect.getsource(module._run_one) + inspect.getsource(module._Pass)
    assert 'VideoFileClip' not in source, "the unreachable extraction branch is back"
    assert not hasattr(module, 'VideoFileClip'), "moviepy is imported but unused"
    # One place turns a path into a local source, and it checks it first
    assert 'is_valid_media_file' in inspect.getsource(YouTubeTranscriber.resolve_source)


def test_a_local_pass_skips_youtubes_own_transcripts():
    """A URL list can mix a video with a local file, and DOWNLOAD_YT_TRANSCRIPT
    was answered for the video. The local pass has no metadata to read captions
    out of, and reading them anyway is an AttributeError.
    """

    t = YouTubeTranscriber()
    t.startfile = lambda *a: None
    with tempfile.TemporaryDirectory() as tmp:
        for attr in ('AUDIO_DIR', 'VIDEO_DIR', 'TRANSCRIPT_DIR',
                     'VIDEO_WITHOUT_AUDIO_DIR'):
            setattr(t, attr, os.path.join(tmp, attr))
        cfg = module.SessionConfig(url=os.path.join(tmp, 'clip.mp4'),
                                   is_local_file=True, video_title='clip',
                                   transcribe_audio=False,
                                   yt_transcript_languages=['en'], used_fields={})
        with redirect_stdout(io.StringIO()):
            module._run_one(t, cfg)


def test_a_local_media_source_runs_through_transcription_and_saves_transcript():
    """A local path can enter as a source, reach Whisper, and save its output."""

    t = YouTubeTranscriber()
    opened = []
    t.startfile = opened.append
    model_calls = []

    class Model:
        def transcribe(self, path, language=None):
            model_calls.append((path, language))
            return {'text': 'A complete local transcription flow.', 'language': 'en'}

    with tempfile.TemporaryDirectory() as tmp:
        source = os.path.join(tmp, 'lecture recording.mp4')
        io.open(source, 'wb').close()
        t.TRANSCRIPT_DIR = os.path.join(tmp, 'Transcript')
        t.RAW_TRANSCRIPT_DIR = os.path.join(t.TRANSCRIPT_DIR, 'Raw')
        with patch.object(t, 'is_valid_media_file', return_value=True) as valid_media:
            sources = t.source_entries(source)
            assert sources == [(source, True, None)], sources
            cfg = module.SessionConfig(
                url=source, is_local_file=True, sources=sources, used_fields={},
                transcribe_audio=True, target_language='auto', target_languages=['auto'])
            with patch.object(whisper, 'load_model', return_value=Model()) as load_model:
                with redirect_stdout(io.StringIO()):
                    module._run_pipeline(t, cfg)

        transcript = os.path.join(
            t.TRANSCRIPT_DIR, 'lecture recording [Whisper en].txt')
        assert io.open(transcript, encoding='utf-8').read() == (
            'A complete local transcription flow.')
        assert model_calls == [(source, None)], model_calls
        load_model.assert_called_once_with('base')
        assert valid_media.call_count == 2, valid_media.call_count
        assert opened == [transcript], opened


def test_a_failed_local_transcription_does_not_abort_later_sources():
    """A source Whisper cannot decode saves nothing, and the batch goes on to
    transcribe the next one."""
    t = YouTubeTranscriber()
    calls = []

    class Model:
        def transcribe(self, path, language=None):
            calls.append(path)
            if path.endswith('failed.mp4'):
                raise subprocess.CalledProcessError(
                    1, ['ffmpeg', '-i', path], stderr='No audio stream found')
            return {'text': 'The later source succeeded.', 'language': 'en'}

    with tempfile.TemporaryDirectory() as tmp:
        failed = os.path.join(tmp, 'failed.mp4')
        good = os.path.join(tmp, 'good.mp4')
        for path in (failed, good):
            io.open(path, 'wb').close()
        t.TRANSCRIPT_DIR = os.path.join(tmp, 'Transcript')
        t.RAW_TRANSCRIPT_DIR = os.path.join(t.TRANSCRIPT_DIR, 'Raw')
        sources = [(failed, True, None), (good, True, None)]
        cfg = module.SessionConfig(
            url=failed, is_local_file=True, sources=sources, used_fields={},
            transcribe_audio=True, target_language='auto', target_languages=['auto'])
        with patch.object(t, 'is_valid_media_file', return_value=True):
            with patch.object(whisper, 'load_model', return_value=Model()):
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    module._run_pipeline(t, cfg)

        assert calls == [failed, good], calls
        assert not os.path.exists(os.path.join(
            t.TRANSCRIPT_DIR, 'failed [Whisper en].txt'))
        assert io.open(os.path.join(
            t.TRANSCRIPT_DIR, 'good [Whisper en].txt'), encoding='utf-8').read() == (
                'The later source succeeded.')


def test_a_local_file_is_its_own_highest_and_lowest():
    """A file has one stream, not a list of tiers, so only a number constrains
    it - and a number at or above what it already is would re-encode it bigger
    for nothing.
    """

    def two_forty(_path):
        return 240

    def unknown(_path):
        return None

    log = io.StringIO()
    with redirect_stdout(log):
        for answer in ('120', '120p'):
            assert module._local_quality('clip.mp4', answer, two_forty, 'p') == 120, answer
        for answer in ('240', '240p', '480p', 'highest', 'lowest', 'medium', '', None):
            assert module._local_quality('clip.mp4', answer, two_forty, 'p') is None, answer
        # A container that records no bitrate rules nothing out, so the ask stands
        assert module._local_quality('clip.mp4', '64', unknown, 'k') == 64
    # Clamping is said out loud; a keyword was never a constraint to report on
    assert log.getvalue().count('leaves it as it is') == 3, log.getvalue()


def test_a_local_source_is_re_encoded_but_never_replaced():
    """A deliverable is cut from the file the user pointed at; one that would
    land on that file is skipped rather than written over it.
    """
    if not _ffmpeg_available():
        _skip('no ffmpeg')
    t = YouTubeTranscriber()
    with tempfile.TemporaryDirectory() as tmp:
        source = _make_clip(os.path.join(tmp, 'clip.mp4'), 'video')
        assert t.source_height(source) == 120

        with redirect_stdout(io.StringIO()):
            scaled = t.convert_media(source, 'mp4', 'both', os.path.join(tmp, 'out'),
                                     'clip', height=60)
        assert scaled and t.source_height(scaled) == 60, scaled

        # Writing back over the source is what a deliverable we downloaded may
        # do, and a file we were only ever pointed at may not
        log = io.StringIO()
        with redirect_stdout(log):
            assert t.convert_media(source, 'mp4', 'both', tmp, 'clip',
                                   replace_source=False) is None
        assert 'the source file itself' in log.getvalue(), log.getvalue()


def test_a_conversion_that_wrote_nothing_never_costs_the_source():
    """ffmpeg can exit 0 having written an empty file, and the caller deletes
    the pre-conversion file on this function's word."""

    t = YouTubeTranscriber()
    real_run = subprocess.run

    def empty_success(command, **kwargs):
        if command[0] == 'ffmpeg' and '-y' in command:
            io.open(command[-1], 'w', encoding='utf-8').close()
            return subprocess.CompletedProcess(command, 0, '', '')
        return real_run(command, **kwargs)

    with tempfile.TemporaryDirectory() as tmp:
        source = os.path.join(tmp, 'clip.webm')
        io.open(source, 'w', encoding='utf-8').write('pretend this is audio')
        subprocess.run = empty_success
        try:
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                converted = t.convert_media(source, 'mp3', 'audio', tmp, 'clip')
        finally:
            subprocess.run = real_run
        assert converted is None
        # The source is what the caller falls back to, so it has to survive,
        # and the empty output must not be left lying around as a deliverable
        assert os.listdir(tmp) == ['clip.webm'], os.listdir(tmp)


def test_a_transcript_is_worth_a_profile_and_a_repeat_keeps_only_what_was_asked():
    """A run whose only output is YouTube's transcript is still a run worth
    keeping, and a repeat carries forward only the questions its round asked -
    in the session, and not in the environment, where they outlived it."""

    t = YouTubeTranscriber()
    asked = []
    t.get_yes_no_input = lambda prompt, **kw: bool(asked.append(prompt))
    cfg = module.SessionConfig(used_fields={}, yt_transcript_languages=['en'])
    session = module.Session()
    with redirect_stdout(io.StringIO()):
        assert module._finish_session(t, cfg, module._Remembered(session), session) is False
    assert any('create a profile' in prompt for prompt in asked), asked
    assert not session.repeat

    # Saying yes parks the answers and hands the decision back, rather than
    # starting the next round from inside this one: a hundred repeats used to
    # be a hundred live main() frames, each holding its session
    finish = ast.parse(inspect.getsource(module._finish_session))
    assert not [n for n in ast.walk(finish) if isinstance(n, ast.Call)
                and getattr(n.func, 'id', None) == 'main']
    t.get_yes_no_input = lambda prompt, **kw: True
    t.create_profile = lambda fields: None
    environment = dict(os.environ)

    def finish(**round_):
        session = module.Session()
        with redirect_stdout(io.StringIO()):
            repeat = module._finish_session(t, module.SessionConfig(**round_),
                                            module._Remembered(session), session)
        return repeat, session

    repeat, session = finish(used_fields={}, url='https://youtu.be/x',
                             model_choice='',  # Enter took base
                             model_name='base', transcribe_audio=True,
                             yt_transcript_languages=['en'])
    assert repeat is True and session.repeat and session.profile is None
    assert session.remembered.get('MODEL_CHOICE') == 'base'

    # Only questions the round was asked are answered for the next. A
    # refine-only round asks nothing about media, and its "n" made a YouTube
    # URL in the next round download and transcribe nothing
    _, session = finish(used_fields={'TRANSCRIBE_AUDIO': 'n', 'AI_REFINEMENT': 'y',
                                     'KEEP_TRANSCRIPT': 'y'},
                        sources=[(None, True, ['talk.txt'])],
                        ai_mode=module.AIEnhancementMode.LOCAL)
    for key in ('DOWNLOAD_VIDEO', 'TRANSCRIBE_AUDIO', 'AI_REFINEMENT',
                'DOWNLOAD_YT_TRANSCRIPT', 'MODEL_CHOICE'):
        assert key not in session.remembered, key
    assert session.remembered.get('KEEP_TRANSCRIPT') == 'y'

    # A local file is asked nothing about YouTube's transcripts, and a name
    # given to one video's file is not given to the next one's
    _, session = finish(url='clip.mp4', is_local_file=True, used_fields={'DOWNLOAD_VIDEO': 'y'},
                        ask_placement=True, video_only_rename='lecture', audio_path='/music')
    assert session.remembered.get('DOWNLOAD_VIDEO') == 'y'
    assert 'DOWNLOAD_YT_TRANSCRIPT' not in session.remembered
    assert 'VIDEO_ONLY_RENAME' not in session.remembered
    assert session.remembered.get('AUDIO_PATH') == '/music'

    # A round that answered everything: each answer kept is one _Remembered
    # reads back as a setting, or the next round silently asks it again
    qualities = ('video_resolution', 'video_audio_resolution', 'video_only_resolution',
                 'audio_resolution', 'transcribe_audio_quality', 'video_format',
                 'video_only_format', 'audio_format')
    _, session = finish(
        used_fields={key: 'y' for key in t.DEFAULT_FIELDS}, url='https://youtu.be/x',
        transcribe_audio=True, model_name='base', target_languages=['en'],
        yt_transcript_raw='en', ask_placement=True,
        **{attr: 'x' for attr in qualities},
        **{f'{stem}_path': '/x' for stem, _prefix, _label, _dir in module._PLACEMENTS})
    assert len(session.remembered) > 20, session.remembered
    assert set(session.remembered) <= set(module.SETTINGS), (
        set(session.remembered) - set(module.SETTINGS))
    # ...and none of it went where it outlived the session
    assert dict(os.environ) == environment


def test_a_prompt_can_live_outside_the_prompt_folder():
    """A path names a prompt file anywhere, and is tagged by its name."""

    t = YouTubeTranscriber()
    with tempfile.TemporaryDirectory() as tmp:
        outside = os.path.join(tmp, 'house-style.txt')
        io.open(outside, 'w', encoding='utf-8').write('mind the house style')
        with redirect_stdout(io.StringIO()):
            loaded = module._load_prompts(t, f'{outside}, prompt0-translator.txt')
            missing = module._load_prompts(t, 'nowhere-at-all.txt')

    assert [label for _text, label in loaded] == [outside, 'prompt0-translator.txt']
    assert loaded[0][0] == 'mind the house style'
    # A path is tagged by the file's own name, not by the whole path
    assert t.prompt_suffix(outside) == ' - house-style'
    # One that resolves to nothing is dropped, not carried as an empty prompt
    assert missing == []


def test_a_transcript_request_resolves_to_the_tracks_that_exist():
    """What the field's answers mean, without asking anything."""

    t = YouTubeTranscriber()

    def settle(raw):
        cfg = module.SessionConfig(url='https://youtu.be/x', info=_caption_info(),
                                   used_fields={})
        log = io.StringIO()
        with redirect_stdout(log):
            module._settle_yt_transcripts(t, cfg, raw)
        return cfg, log.getvalue()

    assert settle('n')[0].yt_transcript_languages is None
    assert settle('')[0].yt_transcript_languages is None
    assert settle('y')[0].yt_transcript_languages == ['en']
    cfg, _log = settle('all')
    assert cfg.yt_transcript_languages == ['en', 'en-orig', 'de'] and cfg.yt_transcript_all
    # Whitespace and case are noise; a machine translation asked for by name is
    # given, because naming it is asking for it
    assert settle(' EN , DE ')[0].yt_transcript_languages == ['en', 'de']
    # A language the video does not have is reported, not silently dropped
    cfg, log = settle('en,xx')
    assert cfg.yt_transcript_languages == ['en'] and 'xx' in log
    # The exact key wins over a regional one listed ahead of it
    regional = _caption_info(subtitles={
        'en-GB': [{'ext': 'vtt', 'url': 'https://x/gb', 'name': 'English (UK)'}],
        'en': [{'ext': 'vtt', 'url': 'https://x/en', 'name': 'English'}]})
    cfg = module.SessionConfig(url='https://youtu.be/x', info=regional, used_fields={})
    with redirect_stdout(io.StringIO()):
        module._settle_yt_transcripts(t, cfg, 'en')
    assert cfg.yt_transcript_languages == ['en'], cfg.yt_transcript_languages
    # A video with no captions at all says so rather than opening a menu
    empty = module.SessionConfig(url='https://youtu.be/x', info={}, used_fields={})
    log = io.StringIO()
    with redirect_stdout(log):
        module._settle_yt_transcripts(t, empty, 'all')
    assert empty.yt_transcript_languages is None
    assert 'publishes no transcript' in log.getvalue()


def test_a_field_whose_parent_is_off_is_neither_read_nor_asked():
    """Dependent fields go quiet with their parent.

    Every question here would be answered from a profile, so the run is driven
    with input() rigged to record and refuse: a question reaching the user is
    the failure this is looking for, and a stale value read out of a profile
    is the other.
    """

    t = YouTubeTranscriber()
    t.fetch_video_info = lambda url: dict(_caption_info(), title='clip')
    base = {'URL': 'https://www.youtube.com/watch?v=jNQXAC9IVRw', 'DOWNLOAD_VIDEO': 'n',
            'VIDEO_ONLY': 'n', 'DOWNLOAD_AUDIO': 'n', 'REPEAT': 'n'}

    def configure(**over):
        # AI_PROVIDER is configuration, which a profile line puts in the
        # environment: one round's must not answer for the next
        os.environ.pop('AI_PROVIDER', None)
        asked = []
        builtins.input = lambda prompt='': (asked.append(prompt), '')[1]
        try:
            with redirect_stdout(io.StringIO()):
                profile = module._Profile('test.txt', dict(base, **over))
                return module._configure(t, profile), asked
        finally:
            builtins.input = REAL_INPUT

    try:
        # Nothing produced means no backend, no prompt and nothing to keep
        cfg, asked = configure(DOWNLOAD_YT_TRANSCRIPT='n', TRANSCRIBE_AUDIO='n',
                               AI_REFINEMENT='y', AI_PROVIDER='anthropic',
                               PROMPT='prompt0-translator.txt',
                               KEEP_TRANSCRIPT='n')
        assert not asked, asked
        assert cfg.ai_mode is None and not cfg.prompts
        # An API key is never gone looking for on behalf of a disabled backend
        assert cfg.api_key is None and cfg.keep_transcript is True

        # Enhancement off means the prompt and the copy it would make are moot
        cfg, asked = configure(DOWNLOAD_YT_TRANSCRIPT='n', TRANSCRIBE_AUDIO='y',
                               TRANSCRIBE_AUDIO_QUALITY='lowest',
                               MODEL_CHOICE='tiny', TARGET_LANGUAGE='en',
                               USE_EN_MODEL='n', AI_REFINEMENT='n',
                               PROMPT='prompt0-translator.txt', KEEP_TRANSCRIPT='n')
        assert not asked, asked
        assert not cfg.prompts and cfg.keep_transcript is True

        # ...but a run that only downloads transcripts settles the lot, prompt
        # and keep included, which used to hang off TRANSCRIBE_AUDIO
        cfg, asked = configure(DOWNLOAD_YT_TRANSCRIPT='y', TRANSCRIBE_AUDIO='n',
                               AI_REFINEMENT='y', AI_PROVIDER='local',
                               PROMPT='prompt0-translator.txt', KEEP_TRANSCRIPT='n')
        assert not asked, asked
        assert cfg.ai_mode is not None and cfg.keep_transcript is False
        assert [label for _t, label in cfg.prompts] == ['prompt0-translator.txt']
    finally:
        os.environ.pop('AI_PROVIDER', None)


def test_a_profile_on_the_old_field_name_still_runs_unattended():
    """AI_ENHANCEMENT was renamed AI_REFINEMENT; profiles predate the rename.

    A field the script no longer knows is a field it asks about, and a run
    driven from a profile has nobody there to answer.
    """

    t = YouTubeTranscriber()
    t.fetch_video_info = lambda url: dict(_caption_info(), title='clip')
    base = {'URL': 'https://www.youtube.com/watch?v=jNQXAC9IVRw',
            'DOWNLOAD_VIDEO': 'n', 'VIDEO_ONLY': 'n', 'DOWNLOAD_AUDIO': 'n',
            'REPEAT': 'n', 'DOWNLOAD_YT_TRANSCRIPT': 'y', 'TRANSCRIBE_AUDIO': 'n'}

    def configure(**over):
        # Configuration a profile line puts in the environment, cleared between
        os.environ.pop('AI_PROVIDER', None)
        asked = []
        builtins.input = lambda prompt='': (asked.append(prompt), '')[1]
        try:
            with redirect_stdout(io.StringIO()):
                profile = module._Profile('test.txt', dict(base, **over))
                return module._configure(t, profile), asked
        finally:
            builtins.input = REAL_INPUT

    try:
        cfg, asked = configure(AI_ENHANCEMENT='n')
        assert not asked, asked
        assert cfg.ai_mode is None

        # The new name wins over the old one when a profile carries both
        cfg, asked = configure(AI_ENHANCEMENT='n', AI_REFINEMENT='y',
                               AI_PROVIDER='local', KEEP_TRANSCRIPT='n',
                               PROMPT='prompt0-translator.txt')
        assert not asked, asked
        assert cfg.ai_mode is not None
    finally:
        os.environ.pop('AI_PROVIDER', None)


def test_several_target_languages_are_several_transcripts():
    """One audio, one pass per language, one file per language written.

    The files are named for the language the text is in. They were named for
    what was asked for, so French asked of Italian speech - which Whisper
    cannot write - was saved as "[Whisper fr]" with Italian in it.
    """

    t = YouTubeTranscriber()
    codes, unknown = t.normalize_languages(' EN , English , french , klingon ')
    assert codes == ['en', 'fr'] and unknown == ['klingon']
    assert t.normalize_languages('') == ([], [])

    with tempfile.TemporaryDirectory() as tmp:
        t.startfile = lambda *a: None
        t.TRANSCRIPT_DIR = os.path.join(tmp, 'Transcript')
        t.RAW_TRANSCRIPT_DIR = os.path.join(t.TRANSCRIPT_DIR, 'Raw')
        t.AUDIO_DIR = os.path.join(tmp, 'Audio')
        fetched, passes = [], []

        def fake_audio(video_info, stem, is_temp=False, format_selector='',
                       keep_in=None):
            fetched.append(format_selector)
            out = os.path.join(t.AUDIO_DIR, t.TEMP_DIR)
            os.makedirs(out, exist_ok=True)
            path = os.path.join(out, stem + '.mp3')
            io.open(path, 'w').write('x')
            return path, os.path.abspath(path)

        def fake_transcribe(path, model_name, target, source=None):
            passes.append((target, model_name, source))
            # Italian speech: Whisper writes Italian, or translates into English
            language = 'en' if target == 'en' else 'it'
            return f'words in {language}', language

        t.download_audio_stream = fake_audio
        t.transcribe_audio_file = fake_transcribe

        cfg = module.SessionConfig(
            url='https://youtu.be/x', info=_plain_info(), video_title='clip',
            transcribe_audio=True, target_languages=['en', 'fr', 'auto'],
            target_language='en', transcribe_audio_quality='lowest',
            used_fields={})
        log = io.StringIO()
        with redirect_stdout(log):
            module._run_pipeline(t, cfg)

        # French could not be written, so it came back Italian - as the spoken
        # language itself does, and that is one file, not two of one text
        found = sorted(os.listdir(t.TRANSCRIPT_DIR))
        assert found == ['clip [Whisper en].txt', 'clip [Whisper it].txt'], found
        assert io.open(os.path.join(t.TRANSCRIPT_DIR, 'clip [Whisper en].txt'),
                       encoding='utf-8').read() == 'words in en'
        assert 'The auto transcript is the it one already saved' in log.getvalue()
        assert passes == [('en', 'base', None), ('fr', 'base', None),
                          ('auto', 'base', None)], passes
        # One download served both passes
        assert len(fetched) == 1, fetched


def test_one_key_names_its_own_provider():
    """One API_KEY and one MODEL, since one provider runs per session.

    Which provider they belong to comes from the key itself, so a bare 'y'
    no longer means OpenRouter whatever key is on file.
    """
    from OpenAIYouTubeTranscriber import Provider

    saved = {v: os.environ.get(v) for v in
             ('API_KEY', 'MODEL', 'OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'BASE_URL')}
    for var in saved:
        os.environ.pop(var, None)
    try:
        assert Provider.from_api_key('sk-ant-api03-xyz') is Provider.ANTHROPIC
        assert Provider.from_api_key('sk-or-v1-xyz') is Provider.OPENROUTER
        assert Provider.from_api_key('sk-proj-xyz') is Provider.OPENAI
        # A Groq or Together key belongs to nobody here rather than being
        # mistaken for OpenAI's, whose prefix it does not share
        assert Provider.from_api_key('gsk_xyz') is None
        assert Provider.from_api_key('') is None

        # With nothing to go by, 'y' still reaches the most models for one key
        assert Provider.default() is Provider.OPENROUTER
        os.environ['API_KEY'] = 'sk-ant-api03-xyz'
        assert Provider.default() is Provider.ANTHROPIC
        assert Provider.ANTHROPIC.resolve_api_key() == 'sk-ant-api03-xyz'
        # Another vendor's key is not sent to this one, and the key exported for
        # this one is not passed over for it
        assert Provider.OPENAI.resolve_api_key() is None
        os.environ['OPENAI_API_KEY'] = 'sk-proj-exported'
        assert Provider.OPENAI.resolve_api_key() == 'sk-proj-exported'
        del os.environ['OPENAI_API_KEY']
        # ...unless BASE_URL says where it goes, and a key nobody claims is anyone's
        os.environ['BASE_URL'] = 'https://example.com/v1'
        assert Provider.OPENAI.resolve_api_key() == 'sk-ant-api03-xyz'
        del os.environ['BASE_URL']
        os.environ['API_KEY'] = 'gsk_xyz'
        assert Provider.ANTHROPIC.resolve_api_key() == 'gsk_xyz'
        os.environ['API_KEY'] = 'sk-ant-api03-xyz'

        # One MODEL line, but a blank one leaves each provider its own default
        assert Provider.ANTHROPIC.resolve_model() == 'claude-opus-4-8'
        assert Provider.OPENAI.resolve_model() == 'gpt-4o-mini'
        os.environ['MODEL'] = 'gpt-5'
        assert Provider.ANTHROPIC.resolve_model() == 'gpt-5'

        # A key exported the way that vendor's own tools read it needs no entry
        del os.environ['API_KEY']
        os.environ['OPENAI_API_KEY'] = 'sk-from-the-shell'
        assert Provider.OPENAI.resolve_api_key() == 'sk-from-the-shell'
        assert Provider.ANTHROPIC.resolve_api_key() is None

        # 'local' at the backend prompt is the default it names, not the cloud
        # MODEL on file, which failed to load from HuggingFace
        assert os.environ['MODEL'] == 'gpt-5'
        builtins.input = lambda prompt='': 'local'
        try:
            with redirect_stdout(io.StringIO()):
                _mode, _provider, model = YouTubeTranscriber().get_ai_provider_input()
        finally:
            builtins.input = REAL_INPUT
        assert model == module.LocalModel.default().hf_model_id, model
    finally:
        for var, value in saved.items():
            os.environ.pop(var, None)
            if value is not None:
                os.environ[var] = value


def test_the_backend_comes_from_ai_provider_or_the_key():
    """AI_REFINEMENT says whether to enhance; AI_PROVIDER and the key say who.

    Nothing is asked while either of those can answer - a run driven from a
    profile must not stop for a question it already has the answer to.
    """
    from OpenAIYouTubeTranscriber import (AIEnhancementMode, LocalModel,
                                          Provider)

    t = YouTubeTranscriber()
    t.get_ai_provider_input = lambda: ('asked', None, None)
    saved = {v: os.environ.get(v) for v in ('AI_PROVIDER', 'API_KEY', 'MODEL')}
    for var in saved:
        os.environ.pop(var, None)
    try:
        with redirect_stdout(io.StringIO()):
            os.environ['AI_PROVIDER'] = 'anthropic'
            assert module._ai_backend(t) == (AIEnhancementMode.API, Provider.ANTHROPIC, None)

            # local reads its model out of MODEL, the field the cloud models use
            os.environ['AI_PROVIDER'] = 'local'
            assert module._ai_backend(t) == (
                AIEnhancementMode.LOCAL, None, LocalModel.default().hf_model_id)
            os.environ['MODEL'] = 'microsoft/phi-2'
            assert module._ai_backend(t) == (AIEnhancementMode.LOCAL, None, 'microsoft/phi-2')
            # ...and a short name is shorthand for the id behind it
            os.environ['MODEL'] = 'qwen2.5-0.5b'
            assert module._ai_backend(t) == (
                AIEnhancementMode.LOCAL, None, 'Qwen/Qwen2.5-0.5B-Instruct')
            del os.environ['MODEL']

            # Blank: whoever the key belongs to, and only then does it ask
            os.environ['AI_PROVIDER'] = ''
            os.environ['API_KEY'] = 'sk-or-v1-xyz'
            assert module._ai_backend(t) == (AIEnhancementMode.API, Provider.OPENROUTER, None)
            del os.environ['API_KEY']
            assert module._ai_backend(t)[0] == 'asked'

            # A misspelt provider is reported, not silently run as somebody else
            os.environ['AI_PROVIDER'] = 'anthropc'
            log = io.StringIO()
            with redirect_stdout(log):
                assert module._ai_backend(t)[0] == 'asked'
            assert 'anthropc' in log.getvalue()
    finally:
        for var, value in saved.items():
            os.environ.pop(var, None)
            if value is not None:
                os.environ[var] = value


def test_one_failing_source_does_not_take_the_batch_with_it():
    """A URL list is a batch, and a batch outlives one bad entry.

    The failure used to end the process from inside download_format, so a
    private video at position two meant three and four were never attempted.
    """

    t = YouTubeTranscriber()
    attempted = []

    def flaky(transcriber, cfg):
        attempted.append(cfg.url)
        if cfg.url == 'b':
            raise module.DownloadFailed('unavailable')
        if cfg.url == 'c':
            # An unattended run re-asked about one video, a resolution it lacks
            raise EOFError('EOF when reading a line')

    saved, module._run_one = module._run_one, flaky
    try:
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            module._run_pipeline(t, module.SessionConfig(
                sources=[('a', False, None), ('b', False, None), ('c', False, None),
                         ('d', False, None)],
                used_fields={}))
        assert attempted == ['a', 'b', 'c', 'd'], attempted

        # On its own that same failure is the whole run, and main() turns it
        # into the exit code rather than reporting success
        try:
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                module._run_pipeline(t, module.SessionConfig(
                    sources=[('b', False, None)], used_fields={}))
            raise AssertionError('a lone failing source should not be swallowed')
        except module.DownloadFailed:
            pass
    finally:
        module._run_one = saved


def test_an_unavailable_video_can_be_given_up_on():
    """The retry prompt had no way out of itself.

    So a `URL` list parked forever on its one dead entry rather than going on
    to the entries after it, and an unattended run sat on a prompt with nobody
    there to answer it.
    """

    def only_y_exists(url):
        if url.endswith('/y'):
            return {'title': 'the replacement'}
        raise ValueError('Private video')

    t = YouTubeTranscriber()
    t.fetch_video_info = only_y_exists
    cfg = module.SessionConfig(url='https://youtu.be/x', used_fields={})

    script = ['', 'https://youtu.be/y']
    builtins.input = lambda prompt='': script.pop(0)
    try:
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            try:
                module._create_youtube_with_recovery(t, cfg)
                raise AssertionError('a declined replacement should end the pass')
            except module.DownloadFailed:
                pass
        # Enter gave up rather than asking again, so the next answer is untouched
        assert script == ['https://youtu.be/y'], script

        # ...and the same prompt still takes a replacement when one is offered
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            module._create_youtube_with_recovery(t, cfg)
        assert cfg.video_title == 'the replacement'
    finally:
        builtins.input = REAL_INPUT
    assert not script

    # Running out of input is how an unattended run answers, and means the same
    def closed(prompt=''):
        raise EOFError

    builtins.input = closed
    dead = module.SessionConfig(url='https://youtu.be/x', used_fields={})
    try:
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            try:
                module._create_youtube_with_recovery(t, dead)
                raise AssertionError('a closed stdin should not be waited on')
            except module.DownloadFailed:
                pass
        # A source the session opens with is not optional: that prompt still asks
        try:
            t.prompt_for_source('source: ')
            raise AssertionError('the opening prompt has nothing to fall back to')
        except EOFError:
            pass

        # Given up on while a menu was being built, the first of a list is dropped
        # and the next one answers: main() exited on it, and the rest never ran
        batch = module.SessionConfig(url='https://youtu.be/x', used_fields={}, sources=[
            ('https://youtu.be/x', False, None), ('https://youtu.be/y', False, None)])
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            module._ensure_metadata(t, batch)
        assert batch.url == 'https://youtu.be/y' and batch.video_title == 'the replacement'
        assert batch.sources == [('https://youtu.be/y', False, None)], batch.sources
        # With nothing after it, the run still ends as before
        alone = module.SessionConfig(url='https://youtu.be/x', used_fields={},
                                     sources=[('https://youtu.be/x', False, None)])
        try:
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                module._ensure_metadata(t, alone)
            raise AssertionError('the only source is gone')
        except module.DownloadFailed:
            pass
    finally:
        builtins.input = REAL_INPUT


def test_constructing_a_transcriber_writes_nothing():
    """Five directories per construction, in whatever directory the caller
    happened to be in, is a surprising thing for a constructor to do - and this
    file constructs one in most of its tests. main() makes them instead."""
    here = os.getcwd()
    with tempfile.TemporaryDirectory() as tmp:
        os.chdir(tmp)
        try:
            YouTubeTranscriber()
            assert os.listdir(tmp) == [], os.listdir(tmp)
        finally:
            os.chdir(here)


def test_a_deliverable_can_be_renamed_and_sent_somewhere_else():
    """RENAME replaces the title, PATH replaces the folder, and the tags still
    follow - so two resolutions off one answer stay two files, not one."""

    t = YouTubeTranscriber()
    with tempfile.TemporaryDirectory() as tmp:
        elsewhere = os.path.join(tmp, 'elsewhere')

        # A name and a path in the fields are used as they stand, so a profile
        # carrying them still runs unattended
        cfg = module.SessionConfig(used_fields={})
        repeat = module.SessionConfig(used_fields={})
        fields = {'VIDEO_RENAME': 'lecture', 'VIDEO_PATH': elsewhere}
        log = io.StringIO()
        with redirect_stdout(io.StringIO()):
            module._settle_placement(t, cfg, 'video', module._Profile('p.txt', fields))
        # REPEAT=y takes a new video, and the name overwrote the last one's
        with redirect_stdout(log):
            module._settle_placement(t, repeat, 'video', module._Profile(
                'p.txt', fields, module.Session(repeat=True)))
        assert cfg.video_rename == 'lecture'
        assert cfg.video_path == elsewhere
        assert (repeat.video_rename, repeat.video_path) == ('', elsewhere)
        # Said once, as dropped, and not then reported as loaded
        assert 'Ignoring VIDEO_RENAME=lecture' in log.getvalue()
        assert 'Loaded VIDEO_RENAME' not in log.getvalue(), log.getvalue()
        assert os.path.isdir(elsewhere), 'the path is made when it is settled'
        # A profile written from this session replays it, rather than asking
        assert cfg.used_fields['VIDEO_RENAME'] == 'lecture'
        assert cfg.used_fields['VIDEO_PATH'] == elsewhere

        # A field that is not in the profile at all leaves the defaults alone
        # and asks nothing, so an older profile still runs
        cfg = module.SessionConfig(used_fields={})
        with redirect_stdout(io.StringIO()):
            module._settle_placement(t, cfg, 'audio', module._Profile('p.txt', {}))
        assert (cfg.audio_rename, cfg.audio_path) == ('', '')
        assert cfg.used_fields['AUDIO_RENAME'] == 'n'

        # 'n' is the same answer written down
        cfg = module.SessionConfig(used_fields={})
        with redirect_stdout(io.StringIO()):
            module._settle_placement(t, cfg, 'audio', module._Profile(
                'p.txt', {'AUDIO_RENAME': 'n', 'AUDIO_PATH': 'n'}))
        assert (cfg.audio_rename, cfg.audio_path) == ('', '')

        # A relative path is refused rather than quietly written under the
        # working directory, and the prompt says so
        cfg = module.SessionConfig(used_fields={})
        script = ['', '']
        builtins.input = lambda prompt='': script.pop(0)
        log = io.StringIO()
        try:
            with redirect_stdout(log), redirect_stderr(log):
                module._settle_placement(t, cfg, 'audio', module._Profile(
                    'p.txt', {'AUDIO_PATH': 'somewhere/relative'}))
        finally:
            builtins.input = REAL_INPUT
        assert cfg.audio_path == '', cfg.audio_path
        assert 'absolute' in log.getvalue()

        # A typed name cannot smuggle a path through the rename
        assert t.sanitize_filename('../../etc/passwd') == '....etcpasswd'


def test_one_question_gates_the_eight_placement_ones():
    """Two questions for each of four deliverables is eight an ordinary run
    does not want, so one no answers all of them."""

    t = YouTubeTranscriber()
    asked = []

    def answer(prompt, **kw):
        asked.append(prompt)
        return False

    t.get_yes_no_input = answer
    cfg = module.SessionConfig(used_fields={})
    first_round = module._Remembered(module.Session())
    with redirect_stdout(io.StringIO()):
        for stem, _prefix, _label, _dir in module._PLACEMENTS:
            module._settle_placement(t, cfg, stem, first_round)
    assert len(asked) == 1, asked
    assert 'Rename' in asked[0]
    assert cfg.used_fields['TRANSCRIPT_RENAME'] == 'n'
    assert cfg.used_fields['VIDEO_PATH'] == 'n'


def test_a_profile_and_a_repeat_settle_alike():
    """Both ways of setting a session up read one table through one function,
    so the same answers - written in a profile, or remembered from the round a
    repeat follows - settle the same session, and neither asks anything."""

    t = YouTubeTranscriber()
    url = 'https://www.youtube.com/watch?v=jNQXAC9IVRw'
    t.prompt_for_sources = lambda prompt_text=None: [(url, False, None)]
    t.get_yes_no_input = lambda *a, **k: (_ for _ in ()).throw(AssertionError('asked'))
    with tempfile.TemporaryDirectory() as tmp:
        stated = {
            'DOWNLOAD_VIDEO': 'y', 'VIDEO_RESOLUTION': '720p',
            'VIDEO_AUDIO_RESOLUTION': 'highest', 'VIDEO_FORMAT': 'original',
            'VIDEO_RENAME': 'n', 'VIDEO_PATH': tmp, 'VIDEO_ONLY': 'n',
            'DOWNLOAD_AUDIO': 'y', 'AUDIO_RESOLUTION': 'medium', 'AUDIO_FORMAT': 'original',
            'AUDIO_RENAME': 'n', 'AUDIO_PATH': 'n', 'DOWNLOAD_YT_TRANSCRIPT': 'n',
            'TRANSCRIBE_AUDIO': 'y', 'MODEL_CHOICE': 'tiny', 'SOURCE_LANGUAGE': 'en',
            'TARGET_LANGUAGE': 'en', 'USE_EN_MODEL': 'y', 'AI_REFINEMENT': 'n',
            'TRANSCRIPT_RENAME': 'n', 'TRANSCRIPT_PATH': tmp}
        builtins.input = lambda prompt='': (_ for _ in ()).throw(AssertionError(prompt))
        try:
            with redirect_stdout(io.StringIO()):
                from_profile = module._configure(
                    t, module._Profile('p.txt', dict(stated, URL=url)))
                from_last_round = module._configure(
                    t, module._Remembered(module.Session(remembered=stated)))
        finally:
            builtins.input = REAL_INPUT
    assert vars(from_profile) == vars(from_last_round)
    assert (from_profile.video_resolution, from_profile.audio_resolution) == ('720p', 'medium')
    assert (from_profile.video_path, from_profile.transcript_path) == (tmp, tmp)
    assert from_profile.use_en_model and from_profile.model_name == 'tiny'
    assert from_profile.ai_mode is None


def test_the_settings_table_covers_every_field():
    """A field the table leaves out has no meaning for a gap in it, and a
    profile would hand it to the environment as configuration."""

    # URL is settled as the list of sources, and AI_PROVIDER and MODEL are
    # config.txt's too, read from the environment when the backend is chosen
    fields = set(YouTubeTranscriber.DEFAULT_FIELDS) - {'URL', 'AI_PROVIDER', 'MODEL'}
    table = set(module.SETTINGS)
    assert fields <= table, fields - table
    # And nothing a profile cannot hold, but the pre-1.2 name with a meaning of
    # its own and the one question a session asks for all the placements
    assert table <= fields | {'NO_AUDIO_IN_VIDEO', 'PLACEMENT'}, table - fields
    # What a profile keeps as its own, and what it hands on as configuration
    assert fields | {'URL', 'RESOLUTION', 'AI_ENHANCEMENT'} <= module._PROFILE_FIELDS
    assert not {'AI_PROVIDER', 'MODEL', 'API_KEY', 'BASE_URL'} & module._PROFILE_FIELDS


def test_a_stored_yes_or_no_reads_the_same_from_either_source():
    """'skip' declines as 'n' does wherever a yes or no is stored, and a value
    that is neither is asked about rather than taken for a no."""

    t = YouTubeTranscriber()
    asked = []
    t.get_yes_no_input = lambda question, default='y': asked.append(question) or True
    holding = {
        'profile': lambda value: module._Profile('p.txt', {'DOWNLOAD_AUDIO': value}),
        'last round': lambda value: module._Remembered(
            module.Session(remembered={'DOWNLOAD_AUDIO': value}))}
    for kind, source in holding.items():
        for value, settled, asks in (('skip', False, 0), ('S', False, 0),
                                     ('n', False, 0), ('yes', True, 0),
                                     ('maybe', True, 1)):
            asked.clear()
            with redirect_stdout(io.StringIO()):
                got = module._yes_no(t, source(value), 'DOWNLOAD_AUDIO', 'Download audio? ')
            assert (got, len(asked)) == (settled, asks), (kind, value)


def test_nothing_in_the_environment_answers_for_a_profile_or_a_round():
    """A session's state lived in the process environment, where anything of
    the same name answered for it: a shell's VIDEO_ONLY for a profile that left
    it out, a shell's LAST_DOWNLOAD_AUDIO for a first round that never asked,
    and a shell's _REPEAT_INVOCATION made the first round a repeat, which
    skipped config.txt's profile. Only configuration is read from there now."""

    t = YouTubeTranscriber()
    t.prompt_for_sources = lambda prompt_text=None: [('https://youtu.be/x', False, None)]
    t.get_yes_no_input = lambda *a, **k: False
    stray = {'VIDEO_ONLY': 'y', 'VIDEO_ONLY_RESOLUTION': '720p',
             'URL': 'https://youtu.be/stray', 'LAST_DOWNLOAD_AUDIO': 'y',
             '_REPEAT_INVOCATION': '1'}
    saved = {key: os.environ.get(key) for key in list(stray) + ['LOAD_PROFILE']}
    os.environ.update(stray)
    try:
        profile = module._Profile('p.txt', {'DOWNLOAD_VIDEO': 'n', 'DOWNLOAD_AUDIO': 'n',
                                            'DOWNLOAD_YT_TRANSCRIPT': 'n',
                                            'TRANSCRIBE_AUDIO': 'n'})
        with redirect_stdout(io.StringIO()):
            cfg = module._configure(t, profile)
        # Left out of the profile, VIDEO_ONLY means no, and the source is asked
        assert cfg.video_only is False
        assert cfg.url == 'https://youtu.be/x', cfg.url
        # A first round has nothing remembered
        first = module._Remembered(module.Session())
        assert first.lookup(module.SETTINGS['DOWNLOAD_AUDIO'])[1] is None
        # ...and is not a repeat: config.txt's profile is the one loaded
        with tempfile.TemporaryDirectory() as tmp:
            t.PROFILE_DIR = tmp
            io.open(os.path.join(tmp, 'p.txt'), 'w').write('DOWNLOAD_AUDIO=y\n')
            io.open(os.path.join(tmp, t.CONFIG_ENV), 'w').write('LOAD_PROFILE=p.txt\n')
            with redirect_stdout(io.StringIO()):
                chosen = module._select_profile(t, module.Session())
        assert isinstance(chosen, module._Profile) and chosen.origin == 'p.txt'
    finally:
        for key, value in saved.items():
            os.environ.pop(key, None)
            if value is not None:
                os.environ[key] = value


def test_a_profile_hands_on_its_configuration_and_keeps_its_fields():
    """AI_PROVIDER, MODEL and API_KEY are config.txt's too: the backends read
    them from the environment, and a profile's line overrides config.txt's.
    That much of a profile still goes there; its fields stay with it."""

    t = YouTubeTranscriber()
    keys = ('AI_PROVIDER', 'MODEL', 'API_KEY', 'DOWNLOAD_AUDIO', 'URL')
    saved = {key: os.environ.get(key) for key in keys}
    try:
        for key in keys:
            os.environ.pop(key, None)
        os.environ['AI_PROVIDER'] = 'anthropic'  # as config.txt left it
        profile = module._Profile('p.txt', {
            'AI_PROVIDER': 'local', 'MODEL': 'qwen2.5-0.5b', 'API_KEY': 'sk-test',
            'DOWNLOAD_AUDIO': 'y', 'URL': 'https://youtu.be/x'})
        assert profile.fields == {'DOWNLOAD_AUDIO': 'y', 'URL': 'https://youtu.be/x'}
        assert 'DOWNLOAD_AUDIO' not in os.environ and 'URL' not in os.environ
        assert (os.environ['AI_PROVIDER'], os.environ['API_KEY']) == ('local', 'sk-test')
        assert module._ai_backend(t) == (
            module.AIEnhancementMode.LOCAL, None, 'Qwen/Qwen2.5-0.5B-Instruct')
    finally:
        for key, value in saved.items():
            os.environ.pop(key, None)
            if value is not None:
                os.environ[key] = value


def test_a_repeat_that_lost_its_profile_repeats_what_it_fell_back_to():
    """A profile deleted between rounds falls back to choosing again. An
    interactive round chosen then is what the next repeat repeats, rather than
    looking for the vanished profile every round after."""

    t = YouTubeTranscriber()
    t.get_yes_no_input = lambda *a, **k: True
    session = module.Session(repeat=True, profile='gone.txt')
    with tempfile.TemporaryDirectory() as tmp:
        t.PROFILE_DIR = tmp
        log = io.StringIO()
        with redirect_stdout(log):
            chosen = module._select_profile(t, session)
            assert isinstance(chosen, module._Remembered), chosen
            cfg = module.SessionConfig(used_fields={}, url='https://youtu.be/x')
            assert module._finish_session(t, cfg, chosen, session) is True
    assert 'not found for repeat' in log.getvalue()
    assert session.repeat and session.profile is None


def test_a_listed_profile_that_is_not_a_file_falls_back_to_asking():
    """The list is every name in Profile/ that looks like a profile, and a
    folder can. Picked, or deleted while the list was on screen, it was loaded
    from a path that was not there, and the session ended in a TypeError."""

    t = YouTubeTranscriber()
    with tempfile.TemporaryDirectory() as tmp:
        t.PROFILE_DIR = tmp
        os.mkdir(os.path.join(tmp, 'profile-folder.txt'))
        builtins.input = lambda prompt='': '1'
        log = io.StringIO()
        try:
            with redirect_stdout(log):
                chosen = module._select_profile(t, module.Session())
        finally:
            builtins.input = REAL_INPUT
    assert isinstance(chosen, module._Remembered), chosen
    assert 'Profile not found: profile-folder.txt' in log.getvalue(), log.getvalue()


def test_one_name_cannot_name_several_sources():
    """A rename is one name and a URL list is several videos.

    The second landed on the first - one file where two were asked for, and
    for a transcript no message at all, since save_transcript opens 'w'.
    """

    t = YouTubeTranscriber()
    with tempfile.TemporaryDirectory() as tmp:
        t.TRANSCRIPT_DIR = os.path.join(tmp, 'Transcript')
        t.AUDIO_DIR = os.path.join(tmp, 'Audio')
        t.RAW_TRANSCRIPT_DIR = os.path.join(t.TRANSCRIPT_DIR, 'Raw')
        t.startfile = lambda *a: None
        t.transcribe_audio_file = lambda *a: ('words', 'en')
        t.fetch_video_info = lambda url: {
            'title': 'vid' + url[-1],
            'formats': [{'vcodec': 'none', 'acodec': 'opus', 'abr': 60,
                         'format_id': 'a', 'format_note': 'low'}]}

        def fake_audio(info, stem, is_temp=False, format_selector='', keep_in=None):
            out = os.path.join(t.AUDIO_DIR, t.TEMP_DIR) if is_temp else (
                keep_in or t.AUDIO_DIR)
            os.makedirs(out, exist_ok=True)
            path = os.path.join(out, stem + '.mp3')
            io.open(path, 'w', encoding='utf-8').write('x')
            return path, os.path.abspath(path)

        t.download_audio_stream = fake_audio

        opened = []
        t.startfile = opened.append

        def run(sources):
            shutil.rmtree(t.TRANSCRIPT_DIR, ignore_errors=True)
            opened.clear()
            cfg = module.SessionConfig(
                sources=sources, used_fields={}, transcribe_audio=True,
                transcript_rename='meeting', target_languages=['en'],
                model_name='base')
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                module._run_pipeline(t, cfg)
            return sorted(n for _b, _s, names in os.walk(t.TRANSCRIPT_DIR)
                          for n in names)

        # Two videos, one name: the name leads and each title still tells them apart
        assert run([('https://youtu.be/1', False, None),
                    ('https://youtu.be/2', False, None)]) == [
            'meeting - vid1 [Whisper en].txt', 'meeting - vid2 [Whisper en].txt']
        # ...and a batch does not open a window per transcript
        assert opened == [], opened
        # One video: the name is simply the name, and its transcript is opened
        assert run([('https://youtu.be/1', False, None)]) == [
            'meeting [Whisper en].txt']
        assert len(opened) == 1, opened


def test_the_merge_never_takes_the_name_of_the_audio_it_reads():
    """VIDEO_PATH and AUDIO_PATH one folder, both webm at the top tier: the
    merged video and the saved audio came to one name. ffmpeg refused to write
    over its own input, and the failed merge's cleanup deleted the audio."""

    t = YouTubeTranscriber()
    merges = []
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, 'out')
        t.VIDEO_DIR = os.path.join(tmp, 'Video')
        t.fetch_video_info = lambda url: {'title': 'vid', 'formats': [
            {'format_id': 'v', 'vcodec': 'vp9', 'acodec': 'none', 'height': 720,
             'ext': 'webm', 'url': 'v'},
            {'format_id': 'a', 'vcodec': 'none', 'acodec': 'opus', 'abr': 60,
             'ext': 'webm', 'url': 'a', 'format_note': 'low'}]}

        def fake(folder, stem):
            os.makedirs(folder, exist_ok=True)
            path = os.path.join(folder, stem + '.webm')
            io.open(path, 'w', encoding='utf-8').write('x')
            return path

        t.download_format = lambda url, selector, folder, stem, reuse=False: fake(folder, stem)
        t.download_audio_stream = (lambda info, stem, is_temp=False, format_selector='',
                                   keep_in=None: (fake(keep_in, stem),) * 2)
        t.combine_audio_video = lambda video, audio, output: merges.append((audio, output))
        cfg = module.SessionConfig(
            sources=[('https://youtu.be/x', False, None)], used_fields={},
            transcribe_audio=False, download_video=True, video_resolution='highest',
            video_audio_resolution='highest', video_format='webm', video_path=out,
            download_audio=True, audio_resolution='highest', audio_format='original',
            audio_path=out)
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            module._run_pipeline(t, cfg)
    assert len(merges) == 1, merges
    audio, output = merges[0]
    assert audio == os.path.join(out, 'vid.webm'), merges
    assert output == os.path.join(out, 'vid [webm].webm'), merges


def test_a_profile_that_predates_a_field_does_not_stop_to_ask():
    """A field a profile does not carry means no, the way DOWNLOAD_AUDIO and
    VIDEO_ONLY already read one. DOWNLOAD_YT_TRANSCRIPT asked instead, so any
    1.1.0-era profile stopped on a prompt no unattended run could answer."""

    t = YouTubeTranscriber()
    saved = os.environ.pop('DOWNLOAD_YT_TRANSCRIPT', None)
    try:
        cfg = module.SessionConfig(used_fields={}, url='https://youtu.be/x')
        named = os.getenv('DOWNLOAD_YT_TRANSCRIPT')
        assert named is None
        with redirect_stdout(io.StringIO()):
            module._settle_yt_transcripts(t, cfg, 'n' if named is None else named)
        assert cfg.yt_transcript_languages is None
    finally:
        if saved is not None:
            os.environ['DOWNLOAD_YT_TRANSCRIPT'] = saved

    # The audio menu prints its tiers as "106k"; the field has to take that back
    assert Resolution.normalize('106k') == '106'
    assert Resolution.normalize('60K') == '60'
    assert Resolution.normalize('720p') == '720p'
    assert Resolution.normalize('k') == 'k'


def test_a_pre_1_2_profile_still_names_its_own_backend():
    """AI_ENHANCEMENT used to carry the backend as well as the yes - a provider
    key, 'local', or a model name. Reading it as a bare yes/no printed
    "Invalid value" and stopped an unattended run on a prompt."""

    t = YouTubeTranscriber()
    prompts = t.list_available_prompts()
    # The OpenRouter key is not Anthropic's, which reads its own
    base = {'PROMPT': prompts[0] if prompts else '', 'KEEP_TRANSCRIPT': 'y',
            'API_KEY': 'sk-or-v1-test', 'ANTHROPIC_API_KEY': 'sk-ant-test'}
    saved = {k: os.environ.get(k) for k in
             list(base) + ['AI_ENHANCEMENT', 'AI_REFINEMENT', 'AI_PROVIDER', 'MODEL']}
    # Nobody is there to answer an unattended run, and getpass reads the
    # console itself, so an ask hangs the suite rather than failing it
    t.get_yes_no_input = lambda *a, **k: (_ for _ in ()).throw(AssertionError('asked'))
    real_getpass = getpass.getpass
    getpass.getpass = lambda *a, **k: (_ for _ in ()).throw(AssertionError('asked'))
    try:
        # A model name was a local model, and skip a no: both went to whichever
        # cloud provider the key on file belongs to, and that one charges
        for value, mode, backend, local in (
                ('openrouter', 'API', 'openrouter', None),
                ('anthropic', 'API', 'anthropic', None),
                ('y', 'API', 'openrouter', None),      # the plain form still works
                ('n', None, None, None),
                ('skip', None, None, None),
                ('local', 'LOCAL', None, 'Qwen/Qwen2.5-1.5B-Instruct'),
                ('qwen2.5-0.5b', 'LOCAL', None, 'Qwen/Qwen2.5-0.5B-Instruct'),
                ('someone/their-model', 'LOCAL', None, 'someone/their-model')):
            for key in ('AI_PROVIDER', 'MODEL'):
                os.environ.pop(key, None)
            # The keys are configuration, which the profile puts in the environment
            profile = module._Profile('p.txt', dict(base, AI_ENHANCEMENT=value))
            cfg = module.SessionConfig(used_fields={}, transcribe_audio=True)
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                module._settle_refinement(t, cfg, profile)
            assert (cfg.ai_mode.name if cfg.ai_mode else None) == mode, value
            assert (cfg.provider.key if cfg.provider else None) == backend, value
            assert cfg.local_model == local, (value, cfg.local_model)
    finally:
        getpass.getpass = real_getpass
        for key, value in saved.items():
            os.environ.pop(key, None)
            if value is not None:
                os.environ[key] = value


def test_resolution_f_normalizes_to_fetch():
    assert Resolution.normalize(' F ') == Resolution.FETCH.value
    assert Resolution.normalize('fetch') == Resolution.FETCH.value
    assert Resolution.normalize('720P') == '720p'
    assert Resolution.normalize('HIGHEST') == Resolution.HIGHEST.value


def test_a_caption_track_is_fetched_without_extracting_the_video_again():
    """Handed the URL, yt-dlp extracted the whole video again per track: some
    150 extractions for 'all', and the rate limit that comes with them."""
    import yt_dlp

    info = {'id': 'x', 'title': 'clip', 'extractor': 'youtube', 'extractor_key': 'Youtube',
            'webpage_url': 'https://youtu.be/x', 'formats': [
                {'format_id': 'a', 'url': 'https://example.com/a', 'ext': 'webm',
                 'vcodec': 'none', 'acodec': 'opus'}],
            'subtitles': {'en': [{'ext': 'json3', 'url': 'https://example.com/en.json3'}]}}
    payload = json.dumps({'events': [{'segs': [{'utf8': 'the words'}]}]})

    def dl(self, name, sub, **kwargs):
        io.open(name, 'w', encoding='utf-8').write(payload)
        return True

    def extract_info(self, *a, **k):
        raise AssertionError('extracted the video again')

    saved = yt_dlp.YoutubeDL.dl, yt_dlp.YoutubeDL.extract_info
    yt_dlp.YoutubeDL.dl, yt_dlp.YoutubeDL.extract_info = dl, extract_info
    try:
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            text = YouTubeTranscriber().fetch_caption_text(info, 'en')
    finally:
        yt_dlp.YoutubeDL.dl, yt_dlp.YoutubeDL.extract_info = saved
    assert text == 'the words', text


def test_output_the_console_cannot_encode_does_not_end_the_run():
    """Redirected on Windows, stdout is cp1252, and printing a Japanese
    transcript raised before the transcript was saved."""
    code = ("import OpenAIYouTubeTranscriber as m\n"
            "m.YouTubeTranscriber.check_dependencies = "
            "lambda self: print('\\u65e5\\u672c\\u8a9e') or False\n"
            "m.main()\n")
    run = subprocess.run([sys.executable, '-c', code], capture_output=True,
                         cwd=os.path.dirname(os.path.abspath(__file__)),
                         env=dict(os.environ, PYTHONIOENCODING='cp1252'))
    assert run.returncode == 1 and b'UnicodeEncodeError' not in run.stderr, run.stderr[-300:]
    assert b'???' in run.stdout and b'Missing required' in run.stdout, run.stdout


def _refine_setup(tmp):
    """A transcriber refining into tmp/Transcript, every reply the text uppercased."""
    t = YouTubeTranscriber()
    t.startfile = lambda *a: None
    t.enhance_text = lambda text, *a, **k: text.upper()
    t.TRANSCRIPT_DIR = os.path.join(tmp, 'Transcript')
    t.RAW_TRANSCRIPT_DIR = os.path.join(t.TRANSCRIPT_DIR, 'Raw')
    os.makedirs(t.TRANSCRIPT_DIR, exist_ok=True)
    return t


def _tree(root):
    """Every file under root, relative path -> contents."""
    return {os.path.relpath(os.path.join(base, name), root).replace(os.sep, '/'):
            io.open(os.path.join(base, name), encoding='utf-8', errors='replace').read()
            for base, _dirs, names in os.walk(root) for name in names}


def test_a_refinement_renamed_onto_its_own_source_is_not_deleted():
    """Refining 'talk - refinement.txt' with TRANSCRIPT_RENAME=talk names the
    output 'talk - refinement.txt' again. The save wrote over the source, and
    retiring the source then deleted the refinement just saved."""

    for keep in (False, True):
        with tempfile.TemporaryDirectory() as tmp:
            t = _refine_setup(tmp)
            source = os.path.join(t.TRANSCRIPT_DIR, 'talk - refinement.txt')
            io.open(source, 'w', encoding='utf-8').write('the only words')
            cfg = module.SessionConfig(
                used_fields={}, ai_mode=module.AIEnhancementMode.LOCAL,
                refine_sources=[source], prompts=[('TIDY', 'prompt-refinement.txt')],
                transcript_rename='talk', keep_transcript=keep)
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                module._refine_transcripts(t, cfg)
            found = _tree(tmp)
        expected = {'Transcript/talk - refinement.txt': 'THE ONLY WORDS'}
        if keep:
            expected['Transcript/Raw/talk.txt'] = 'the only words'
        assert found == expected, (keep, found)

    # A summary is not a refinement: written over a source that keeps no copy,
    # it would be the end of the words, so it is not written there at all
    with tempfile.TemporaryDirectory() as tmp:
        t = _refine_setup(tmp)
        source = os.path.join(t.TRANSCRIPT_DIR, 'talk - summarizer.txt')
        io.open(source, 'w', encoding='utf-8').write('the only words')
        cfg = module.SessionConfig(
            used_fields={}, ai_mode=module.AIEnhancementMode.LOCAL,
            refine_sources=[source], prompts=[('BRIEF', 'prompt1-summarizer.txt')],
            transcript_rename='talk', keep_transcript=False)
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            module._refine_transcripts(t, cfg)
        assert _tree(tmp) == {'Transcript/talk - summarizer.txt': 'the only words'}

    # The write itself is all or nothing: a failed one leaves the file whole
    with tempfile.TemporaryDirectory() as tmp:
        t = _refine_setup(tmp)
        path = os.path.join(t.TRANSCRIPT_DIR, 'talk.txt')
        io.open(path, 'w', encoding='utf-8').write('the only words')
        os.chmod(path, 0o640)
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            assert not t.save_transcript('unencodable \ud800', 'talk.txt', t.TRANSCRIPT_DIR,
                                         open_after=False)
            assert io.open(path, encoding='utf-8').read() == 'the only words'
            assert t.save_transcript('new words', 'talk.txt', t.TRANSCRIPT_DIR,
                                     open_after=False)
        assert io.open(path, encoding='utf-8').read() == 'new words'
        assert os.listdir(t.TRANSCRIPT_DIR) == ['talk.txt'], os.listdir(t.TRANSCRIPT_DIR)
        if os.name == 'posix':
            assert os.stat(path).st_mode & 0o777 == 0o640


def test_a_refinement_that_failed_to_save_never_retires_its_source():
    """A summary saved and a refinement that failed to: the refinement set its
    flag on the reply rather than the save, the summary's success set the
    other, and KEEP_TRANSCRIPT=n then deleted the only full transcript."""

    summary = ('BRIEF', 'prompt1-summarizer.txt')
    refinement = ('TIDY', 'prompt-refinement.txt')
    for prompts in ([summary, refinement], [refinement, summary]):
        with tempfile.TemporaryDirectory() as tmp:
            t = _refine_setup(tmp)
            t.save_transcript = lambda text, name, folder, real=t.save_transcript, **k: (
                'refinement' not in name and real(text, name, folder, **k))
            source = os.path.join(t.TRANSCRIPT_DIR, 'talk.txt')
            io.open(source, 'w', encoding='utf-8').write('the only words')
            cfg = module.SessionConfig(
                used_fields={}, ai_mode=module.AIEnhancementMode.LOCAL,
                refine_sources=[source], prompts=prompts, keep_transcript=False)
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                module._refine_transcripts(t, cfg)
            found = _tree(tmp)
        assert found == {'Transcript/talk.txt': 'the only words',
                         'Transcript/talk - summarizer.txt': 'THE ONLY WORDS'}, found


def test_the_audio_never_lands_on_the_merged_video():
    """VIDEO_FORMAT=mkv and AUDIO_FORMAT=mkv in one folder: the merged video was
    clip.mkv, and the audio converted after it was written to clip.mkv too."""

    # Local: the same three files, re-encoded from a file on disk
    t = YouTubeTranscriber()
    written = []

    def convert_media(source, target, kind, folder, stem, **kwargs):
        written.append((kind, os.path.join(folder, f'{stem}.{target}')))
        return written[-1][1]

    t.convert_media = convert_media
    t.stream_codec = lambda source, kind: 'h264' if kind == 'video' else 'aac'
    t.source_height = lambda source: 720
    t.source_bitrate = lambda source: 128
    out = os.path.join(tempfile.gettempdir(), 'out')
    cfg = module.SessionConfig(
        url='clip.mp4', is_local_file=True, used_fields={}, download_video=True,
        video_format='mkv', download_audio=True, audio_format='mkv,mp3',
        video_path=out, audio_path=out)
    with redirect_stdout(io.StringIO()):
        module._local_deliverables(t, cfg, 'clip')
    assert written == [('both', os.path.join(out, 'clip.mkv')),
                       ('audio', os.path.join(out, 'clip - Audio.mkv')),
                       ('audio', os.path.join(out, 'clip.mp3'))], written

    # Remote, through the real merge and conversion
    if not _ffmpeg_available():
        _skip('no ffmpeg for the download half')
    with tempfile.TemporaryDirectory() as tmp:
        t = YouTubeTranscriber()
        t.VIDEO_DIR, t.AUDIO_DIR = os.path.join(tmp, 'Video'), os.path.join(tmp, 'Audio')
        seed_video = _make_clip(os.path.join(tmp, 'seed.mp4'), 'video')
        seed_audio = _make_clip(os.path.join(tmp, 'seed.mp3'), 'audio')

        def fake_video(url, selector, output_dir, stem):
            os.makedirs(output_dir, exist_ok=True)
            return shutil.copyfile(seed_video, os.path.join(output_dir, stem + '.mp4'))

        def fake_audio(info, stem, is_temp=False, format_selector='', keep_in=None):
            folder = os.path.join(t.AUDIO_DIR, t.TEMP_DIR) if is_temp else keep_in
            os.makedirs(folder, exist_ok=True)
            path = shutil.copyfile(seed_audio, os.path.join(folder, stem + '.mp3'))
            return path, os.path.abspath(path)

        t.download_format = fake_video
        t.download_audio_stream = fake_audio
        out = os.path.join(tmp, 'out')
        cfg = module.SessionConfig(
            url='https://youtu.be/x', info=_plain_info(), video_title='clip',
            used_fields={}, transcribe_audio=False,
            download_video=True, video_resolution='highest', video_audio_resolution='highest',
            video_format='mkv', video_path=out,
            download_audio=True, audio_resolution='highest', audio_format='mkv', audio_path=out)
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            module._run_pipeline(t, cfg)
        assert sorted(os.listdir(out)) == ['clip - Audio.mkv', 'clip.mkv'], os.listdir(out)
        assert t.stream_codec(os.path.join(out, 'clip.mkv'), 'video') is not None
        assert t.stream_codec(os.path.join(out, 'clip - Audio.mkv'), 'video') is None


def test_two_sources_with_one_title_keep_a_file_each():
    """Two videos titled alike were written to one name, and downloads overwrite:
    a two-video run left one audio file. The same source twice is a repeat,
    and keeps its one name."""

    with tempfile.TemporaryDirectory() as tmp:
        t = YouTubeTranscriber()
        t.AUDIO_DIR = os.path.join(tmp, 'Audio')
        titles = {'https://youtu.be/AAAAAAAAAAA': 'Same title',
                  'https://youtu.be/BBBBBBBBBBB': 'Same title',
                  'https://youtu.be/CCCCCCCCCCC': 'Same title?'}
        t.fetch_video_info = lambda url: dict(
            _plain_info(), id=url[-11:], title=titles[url], webpage_url=url)

        def fake_audio(info, stem, is_temp=False, format_selector='', keep_in=None):
            os.makedirs(keep_in, exist_ok=True)
            path = os.path.join(keep_in, stem + '.webm')
            io.open(path, 'w', encoding='utf-8').write(info['id'])
            return path, os.path.abspath(path)

        t.download_audio_stream = fake_audio
        sources = [(url, False, None) for url in titles] + [
            ('https://youtu.be/AAAAAAAAAAA', False, None)]
        cfg = module.SessionConfig(
            sources=sources, used_fields={}, transcribe_audio=False,
            download_audio=True, audio_resolution='highest', audio_format='original')
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            module._run_pipeline(t, cfg)
        found = _tree(t.AUDIO_DIR)
    # "Same title?" cleans to "Same title" as well, and is a third video
    assert found == {'Same title.webm': 'AAAAAAAAAAA',
                     'Same title [BBBBBBBBBBB].webm': 'BBBBBBBBBBB',
                     'Same title [CCCCCCCCCCC].webm': 'CCCCCCCCCCC'}, found

    # Local files of one name from two folders, and transcripts to refine likewise
    cfg = module.SessionConfig(used_fields={})
    first, second = [module._claim_name(cfg, 'clip', path) for path in ('/a/clip', '/b/clip')]
    assert (first, second) == ('clip', 'clip (2)')
    assert module._claim_name(cfg, 'CLIP', '/c/clip') == 'CLIP (3)', 'case alone is no difference'
    assert module._claim_name(cfg, 'clip', '/a/clip') == 'clip'


def test_scratch_cleanup_deletes_only_what_the_pass_fetched():
    """Merge-only video streams went to the shared Video/Temp, and cleanup
    emptied the whole folder: with VIDEO_PATH pointed at it, the merge it had
    just made went too, along with anything else kept there."""

    with tempfile.TemporaryDirectory() as tmp:
        t = YouTubeTranscriber()
        t.VIDEO_DIR, t.AUDIO_DIR = os.path.join(tmp, 'Video'), os.path.join(tmp, 'Audio')
        shared = os.path.join(t.VIDEO_DIR, t.TEMP_DIR)
        os.makedirs(shared)
        sentinel = os.path.join(shared, 'keep me.txt')
        io.open(sentinel, 'w', encoding='utf-8').write('not yours')
        scratch, failing = [], [False]

        def fake_video(url, selector, output_dir, stem):
            scratch.append(output_dir)
            path = os.path.join(output_dir, stem + '.webm')
            io.open(path, 'w', encoding='utf-8').write('video')
            return path

        def fake_audio(info, stem, is_temp=False, format_selector='', keep_in=None):
            if failing[0]:
                raise module.DownloadFailed('gone')
            folder = os.path.join(t.AUDIO_DIR, t.TEMP_DIR)
            os.makedirs(folder, exist_ok=True)
            path = os.path.join(folder, stem + '.webm')
            io.open(path, 'w', encoding='utf-8').write('audio')
            return path, os.path.abspath(path)

        def combine(video, audio, output):
            io.open(output, 'w', encoding='utf-8').write('merged')
            return output

        t.download_format, t.download_audio_stream = fake_video, fake_audio
        t.combine_audio_video = combine
        for fail in (False, True):
            failing[0] = fail
            scratch.clear()
            cfg = module.SessionConfig(
                sources=[('https://youtu.be/x', False, None)] * 2, info=_plain_info(),
                url='https://youtu.be/x', video_title='clip', used_fields={},
                transcribe_audio=False, download_video=True, video_resolution='highest',
                video_audio_resolution='highest', video_format='mkv', video_path=shared)
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                module._run_pipeline(t, cfg)
            # Its own folder each pass, and gone after it, failed or not
            assert scratch and all(os.path.dirname(s) == shared for s in scratch), scratch
            assert not any(os.path.exists(s) for s in scratch), scratch
            assert io.open(sentinel, encoding='utf-8').read() == 'not yours'
        assert sorted(os.listdir(shared)) == ['clip.mkv', 'keep me.txt'], os.listdir(shared)


def test_whisper_is_told_the_language_spoken_not_the_one_to_write():
    """Whisper's `language` is the language spoken. Handed the target, it
    decoded Italian speech as French; English, the one language it can
    translate into, was never asked of it as a translation."""
    import whisper

    calls = []

    class Model:
        is_multilingual = True

        def transcribe(self, path, language=None, task='transcribe'):
            calls.append((language, task))
            if task == 'translate':
                return {'text': 'words in english', 'language': language}
            heard = language or 'it'
            return {'text': f'parole in {heard}', 'language': heard}

    saved_load = whisper.load_model
    whisper.load_model = lambda name: Model()
    t = YouTubeTranscriber()
    detected = ['it']
    t.spoken_language = lambda model, path: detected[0]
    log = io.StringIO()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            audio = os.path.join(tmp, 'clip.mp3')
            io.open(audio, 'wb').close()

            def run(target, source=None):
                calls.clear()
                t.release_caches()
                with redirect_stdout(log), redirect_stderr(io.StringIO()):
                    return t.transcribe_audio_file(audio, 'base', target, source), calls[:]

            # The language spoken, detected: no hint, and named for what was heard
            assert run('auto') == (('parole in it', 'it'), [(None, 'transcribe')])
            # English is a translation, of the language detected first
            assert run('en') == (('words in english', 'en'), [('it', 'translate')])
            # ...and a transcription of English speech
            detected[0] = 'en'
            assert run('en')[1] == [('en', 'transcribe')]
            # A language Whisper cannot write is not forced on it as a hint:
            # the speech is transcribed as spoken, and named for that
            detected[0] = 'it'
            assert run('fr') == (('parole in it', 'it'), [(None, 'transcribe')])
            assert 'Whisper translates into English only' in log.getvalue()
            # A spoken language named outright is the hint
            assert run('auto', 'de') == (('parole in de', 'de'), [('de', 'transcribe')])
            assert run('en', 'de')[1] == [('de', 'translate')]
            # No detection to be had: Whisper's own, then a translation if needed
            detected[0] = None
            assert run('en') == (('words in english', 'en'),
                                 [(None, 'transcribe'), ('it', 'translate')])
    finally:
        whisper.load_model = saved_load

    # What spoken_language calls is Whisper's own API, whose weights are not here
    assert 'n_mels' in inspect.signature(whisper.log_mel_spectrogram).parameters
    assert hasattr(whisper.model.Whisper, 'detect_language')
    assert hasattr(whisper.model.Whisper, 'is_multilingual')

    # The spoken language is its own answer; the English-only model is offered
    # only where the speech may be English and nothing else is asked for
    cfg = module.SessionConfig(used_fields={})
    for raw, source in (('Japanese', 'ja'), ('auto', None), ('EN', 'en')):
        module._settle_source_language(t, cfg, raw)
        assert cfg.source_language == source, raw
    assert cfg.used_fields['SOURCE_LANGUAGE'] == 'en'
    builtins.input = lambda prompt='': ''
    try:
        with redirect_stdout(io.StringIO()):
            module._settle_source_language(t, cfg, 'klingon')
    finally:
        builtins.input = REAL_INPUT
    assert cfg.source_language is None and cfg.used_fields['SOURCE_LANGUAGE'] == 'auto'
    assert t.normalize_languages('auto, English') == (['auto', 'en'], [])
    for source, targets, offered in ((None, ['auto'], True), ('en', ['en'], True),
                                     ('ja', ['auto'], False), (None, ['en', 'fr'], False)):
        cfg.source_language, cfg.target_languages = source, targets
        assert module._offers_en_model(t, cfg, ModelSize.BASE) == offered, (source, targets)


def test_detection_runs_through_the_installed_whisper():
    """spoken_language and the translate task, through Whisper's own code.

    No weights can be fetched here, so the model is a tiny one with random
    weights: what it detects means nothing, but every call the app makes -
    ffmpeg decoding, the mel spectrogram, detect_language, the task - is the
    installed Whisper's, and a change to any of them fails here.
    """
    if not _ffmpeg_available():
        _skip('no ffmpeg')
    import torch
    import whisper
    from whisper.model import ModelDimensions, Whisper

    def tiny(n_vocab):
        return Whisper(ModelDimensions(
            n_mels=80, n_audio_ctx=1500, n_audio_state=64, n_audio_head=1, n_audio_layer=1,
            n_vocab=n_vocab, n_text_ctx=448, n_text_state=64, n_text_head=1,
            n_text_layer=1)).eval()

    torch.manual_seed(0)
    model, calls = tiny(51865), []
    real_transcribe = model.transcribe

    def transcribe(path, language=None, **kwargs):
        calls.append((language, kwargs.get('task', 'transcribe')))
        # One greedy pass: the weights are random, so a fallback ladder is time wasted
        return real_transcribe(path, language=language, temperature=0.0, **kwargs)

    model.transcribe = transcribe
    t = YouTubeTranscriber()
    saved_load = whisper.load_model
    whisper.load_model = lambda name: model
    try:
        with tempfile.TemporaryDirectory() as tmp:
            audio = os.path.join(tmp, 'tone.wav')
            subprocess.run(['ffmpeg', '-y', '-v', 'error', '-f', 'lavfi', '-i',
                            'sine=frequency=300:duration=2', audio], check=True)
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                heard = t.spoken_language(model, audio)
                assert heard in whisper.tokenizer.LANGUAGES, heard
                # An English-only model is English without asking
                assert t.spoken_language(tiny(51864), audio) == 'en'
                t.transcribe_audio_file(audio, 'tiny', 'auto')
                assert calls == [(None, 'transcribe')], calls
                calls.clear()
                t.release_caches()
                t.transcribe_audio_file(audio, 'tiny', 'en')
            expected = 'transcribe' if heard == 'en' else 'translate'
            assert calls == [(heard, expected)], (heard, calls)
    finally:
        whisper.load_model = saved_load


def test_a_caption_request_stands_for_every_video_of_a_list():
    """DOWNLOAD_YT_TRANSCRIPT=en,fr was narrowed to the tracks the first video
    had: a first video without French asked no video for French, and 'en'
    settled as the first video's en-US missed the next video's en-GB."""

    t = YouTubeTranscriber()
    t.startfile = lambda *a: None
    fetched = []
    t.fetch_caption_text = lambda info, key: fetched.append(key) or f'the {key} words'
    videos = [('https://youtu.be/first', False, None), ('https://youtu.be/second', False, None)]

    def track(key):
        return [{'url': f'https://x/t?lang={key}', 'name': key}]

    for raw, first, second, want in (
            ('en,fr', {'en': track('en')}, {'en': track('en'), 'fr': track('fr')}, ['en', 'fr']),
            ('en', {'en-US': track('en-US')}, {'en-GB': track('en-GB')}, ['en-GB']),
            ('en,en-us', {'en-US': track('en-US')}, {'en-US': track('en-US')}, ['en-US'])):
        fetched.clear()
        cfg = module.SessionConfig(url=videos[0][0], info={'subtitles': first},
                                   used_fields={}, sources=videos)
        with tempfile.TemporaryDirectory() as tmp:
            t.TRANSCRIPT_DIR = os.path.join(tmp, 'Transcript')
            t.RAW_TRANSCRIPT_DIR = os.path.join(t.TRANSCRIPT_DIR, 'Raw')
            with redirect_stdout(io.StringIO()):
                module._settle_yt_transcripts(t, cfg, raw)
                cfg.info = {'subtitles': second}
                module._save_yt_transcripts(t, cfg, 'clip')
        assert fetched == want, (raw, fetched)


def test_a_saved_profile_reads_back_exactly_what_it_saved():
    """Written raw, ' #' started a comment and ${...} expanded on the way back:
    /tmp/Part #2.mp3 came back /tmp/Part, and a prompt path took another
    variable's value into its name."""

    t = YouTubeTranscriber()
    values = {
        'URL': '/tmp/Part #2.mp3,/tmp/other.mp3',
        'TRANSCRIPT_PATH': '/tmp/Course #2',
        'PROMPT': '/tmp/prompt-${COURSE}.txt',
        'VIDEO_RENAME': 'it\'s "quoted"',
        'VIDEO_PATH': r'C:\Users\me\Videos',
        'AUDIO_PATH': r'\\server\share #1\ ',
        # Before python-dotenv 1.2.3, the backslash ate the closing quote
        'VIDEO_ONLY_PATH': 'D:\\Lectures #2\\',
        'AUDIO_RENAME': '  padded  ',
        'DOWNLOAD_AUDIO': 'y',
    }
    keys = tuple(values) + ('COURSE', 'LATER')
    saved = {key: os.environ.get(key) for key in keys}
    try:
        with tempfile.TemporaryDirectory() as tmp:
            t.PROFILE_DIR = tmp
            with redirect_stdout(io.StringIO()):
                t.create_profile(values)
            path = os.path.join(tmp, t.DEFAULT_PROFILE)
            lines = io.open(path, encoding='utf-8').read().splitlines()
            # Plain values stay plain to edit
            assert 'DOWNLOAD_AUDIO=y' in lines and r'VIDEO_PATH=C:\Users\me\Videos' in lines
            os.environ['COURSE'] = 'unrelated'
            environment = dict(os.environ)
            read = module._read_profile(path)
            for key, value in values.items():
                assert read[key] == value, (key, read[key], value)
            # Reading is only reading: what goes where is _Profile's to decide
            assert dict(os.environ) == environment
            # A hand-written, unquoted ${...} still expands, as it always did
            io.open(path, 'a', encoding='utf-8').write('\nLATER=${COURSE}/x\n')
            assert module._read_profile(path)['LATER'] == 'unrelated/x'
    finally:
        for key, value in saved.items():
            os.environ.pop(key, None) if value is None else os.environ.update({key: value})


def test_a_typed_prompt_is_saved_where_a_profile_can_name_it():
    """A typed prompt was saved to the profile as PROMPT=(inline): its words
    were nowhere, and replaying the profile found no such prompt file."""

    t = YouTubeTranscriber()
    with tempfile.TemporaryDirectory() as tmp:
        t.PROMPT_DIR = os.path.join(tmp, 'Prompt')
        cfg = module.SessionConfig(
            used_fields={'PROMPT': '(inline),prompt-refinement.txt'},
            prompts=[('Keep it short.', module.INLINE_PROMPT),
                     ('TIDY', 'prompt-refinement.txt')])
        with redirect_stdout(io.StringIO()):
            module._save_inline_prompts(t, cfg)
            first = cfg.used_fields['PROMPT']
            # Saved again, the file already there is named rather than a copy made
            module._save_inline_prompts(t, cfg)
            loaded = module._load_prompts(t, cfg.used_fields['PROMPT'])
        assert cfg.used_fields['PROMPT'] == first == 'prompt0.txt,prompt-refinement.txt', first
        assert os.listdir(t.PROMPT_DIR) == ['prompt0.txt']
        assert loaded[0] == ('Keep it short.', 'prompt0.txt'), loaded
        # ...and it tags its output as the typed prompt did
        assert t.prompt_suffix('prompt0.txt') == t.prompt_suffix(module.INLINE_PROMPT)


def test_a_new_config_names_the_profile_actually_written():
    """config.txt was written first, naming profile.txt, while a folder that
    already had a profile got profile0.txt: the next run loaded nothing."""
    t = YouTubeTranscriber()
    with tempfile.TemporaryDirectory() as tmp:
        t.PROFILE_DIR = tmp
        io.open(os.path.join(tmp, 'profile-transcriber.txt'), 'w').write('URL=x\n')
        with redirect_stdout(io.StringIO()):
            t.create_profile(dict(t.DEFAULT_FIELDS))
        config = dotenv_values(os.path.join(tmp, t.CONFIG_ENV))
        assert config['LOAD_PROFILE'] == 'profile0.txt', config
        assert os.path.exists(os.path.join(tmp, 'profile0.txt'))


def test_a_text_file_in_another_encoding_does_not_end_the_run():
    """A transcript or prompt saved by another editor raised UnicodeDecodeError
    out of the reader, taking the transcripts after it down too."""

    with tempfile.TemporaryDirectory() as tmp:
        t = _refine_setup(tmp)
        files = {'utf16.txt': 'Grüße aus Köln'.encode('utf-16'),
                 'bom.txt': codecs.BOM_UTF8 + 'with a BOM'.encode('utf-8'),
                 'crlf.txt': b'line one\r\nline two',
                 'cp1252.txt': 'caf\xe9 cr\xe8me'.encode('cp1252')}
        for name, data in files.items():
            io.open(os.path.join(tmp, name), 'wb').write(data)
        log = io.StringIO()
        with redirect_stdout(log), redirect_stderr(log):
            assert t.read_transcript(os.path.join(tmp, 'utf16.txt')) == 'Grüße aus Köln'
            assert t.read_transcript(os.path.join(tmp, 'bom.txt')) == 'with a BOM'
            assert t.read_transcript(os.path.join(tmp, 'crlf.txt')) == 'line one\nline two'
            assert t.read_transcript(os.path.join(tmp, 'cp1252.txt')) == ''
            assert t.load_prompt_file(os.path.join(tmp, 'cp1252.txt')) == ''
        assert 'is not UTF-8 text' in log.getvalue()

        # One unreadable transcript is skipped, and the next is still refined -
        # and retired, its UTF-16 read back the same way to check the Raw/ copy
        bad = os.path.join(t.TRANSCRIPT_DIR, 'a.txt')
        good = os.path.join(t.TRANSCRIPT_DIR, 'b.txt')
        io.open(bad, 'wb').write(files['cp1252.txt'])
        io.open(good, 'wb').write(files['utf16.txt'])
        cfg = module.SessionConfig(used_fields={}, ai_mode=module.AIEnhancementMode.LOCAL,
                                   refine_sources=[bad, good],
                                   prompts=[('TIDY', 'prompt-refinement.txt')])
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            module._refine_transcripts(t, cfg)
        found = _tree(t.TRANSCRIPT_DIR)
        assert found['b - refinement.txt'] == 'GRÜSSE AUS KÖLN', found
        assert found['Raw/b.txt'] == 'Grüße aus Köln' and 'b.txt' not in found, found
        assert os.path.exists(bad)


def test_a_failed_enhancement_hands_back_the_text_it_was_given():
    """Oversized sentences were wrapped with textwrap, which cut long words and
    rejoined them on a space - Thai, with no spaces between words, took one
    at every cut - so a backend that failed on every chunk still changed the
    words, and the result passed for a refinement."""
    import sys
    import types

    t = YouTubeTranscriber()

    def down(chunk):
        raise RuntimeError('backend down')

    for text in ('x' * 10000, 'ภาษาไทย' * 1000, 'a ' * 1800 + '中' * 1500,
                 ' ' + ' '.join(f'word{i}' for i in range(3000)) + '\n',
                 'line one\nline two\n' * 400):
        chunks, seams = t.chunk_spans(text, max_tokens=300)
        assert len(chunks) > 1 and len(seams) == len(chunks) - 1
        # Every chunk inside the budget, by the estimate that set it - a mixed
        # sentence sized by its average character came to 566 of 300
        assert max(t.estimate_tokens(c) for c in chunks) <= 300, text[:20]
        assert ''.join(c + s for c, s in zip(chunks, seams + [''])) == text.strip()
        with redirect_stdout(io.StringIO()):
            merged = t._run_chunked_enhancement(chunks, 'fake', down, seams)
        assert merged == text.strip(), text[:20]
        assert not t.is_refinement(text, merged)
    # A cut between a Thai letter and its vowel sign would open a chunk on the sign
    thai = t.chunk_text('ภาษาไทย' * 1000, max_tokens=300)
    assert not any(unicodedata.category(c[0])[0] == 'M' for c in thai)

    # Through a backend, whose replies all come back empty
    reply = types.SimpleNamespace(choices=[types.SimpleNamespace(
        finish_reason='stop', message=types.SimpleNamespace(content=None))])
    openai = types.SimpleNamespace(OpenAI=lambda **kwargs: types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=types.SimpleNamespace(
            create=lambda **kwargs: reply))))
    saved = sys.modules.get('openai')
    sys.modules['openai'] = openai
    try:
        with redirect_stdout(io.StringIO()):
            text = 'ภาษาไทย' * 3000
            assert t.enhance_with_openai_compatible(
                text, 'tidy', 'key', module.Provider.OPENAI) == text
    finally:
        sys.modules.pop('openai', None) if saved is None else sys.modules.update(openai=saved)


def test_a_local_chunk_is_sized_by_the_models_own_tokenizer():
    """The local backend worked out each chunk's share of the context with the
    model's tokenizer, then cut chunks by the byte estimate. For a tokenizer
    that counts more tokens than the estimate, every chunk overran its share
    and left the reply too little room."""
    import sys
    import types

    t = YouTubeTranscriber()
    chunks = []

    class Tokenizer:
        model_max_length = 1024
        chat_template = 'yes'

        def apply_chat_template(self, messages, **kwargs):
            return messages[-1]['content']

        def encode(self, text, **kwargs):
            return list(text)  # a token a character: four times the estimate

    def pipeline(*args, **kwargs):
        def generate(prompt, **options):
            chunks.append(prompt)
            return [{'generated_text': prompt}]
        return generate

    transformers = types.SimpleNamespace(
        AutoTokenizer=types.SimpleNamespace(from_pretrained=lambda _id: Tokenizer()),
        pipeline=pipeline)
    text = ' '.join(f'sentence number {i} went by.' for i in range(300))
    saved = sys.modules.get('transformers')
    sys.modules['transformers'] = transformers
    try:
        with redirect_stdout(io.StringIO()):
            result = t.enhance_with_local(text, 'tidy', 'any/model')
    finally:
        sys.modules.pop('transformers', None) if saved is None else sys.modules.update(
            transformers=saved)
    prompt_size = len(f'tidy\n\n{t.ENHANCEMENT_OUTPUT_DIRECTIVE}') + 32
    share = min((1024 - prompt_size) // 3, 300)
    assert len(chunks) > 1 and max(len(c) for c in chunks) <= share, (
        share, max(len(c) for c in chunks))
    assert result.split() == text.split()


def test_the_shipped_prompts_travel_with_an_installed_copy():
    """A wheel held the module alone: installed, the app listed no prompts and
    Enter at the prompt menu selected nothing."""
    # setuptools' own reader, as the build reads it (and one that needs no
    # tomllib, which Python 3.10 does not have)
    from setuptools.config.pyprojecttoml import read_configuration

    here = os.path.dirname(os.path.abspath(__file__))
    project = read_configuration(os.path.join(here, 'pyproject.toml'))
    tool = project['tool']['setuptools']
    captured = {'packages': tool['packages'], 'package_dir': tool['package-dir'],
                'package_data': tool['package-data']}
    assert tool['include-package-data'] is False, 'only the files named, never a glob'
    assert project['project']['scripts'] == {
        'openai-youtube-transcriber': 'OpenAIYouTubeTranscriber:main'}
    # Each package is the folder it ships from, and carries the files git holds
    # there by name: a glob would take whatever a checkout's user had saved
    # beside them, and config.txt, which can hold an API key, is never one
    tracked = subprocess.run(['git', 'ls-files', YouTubeTranscriber.DATA_DIR], cwd=here,
                             capture_output=True, text=True).stdout.split('\n')
    for package, folder in ((YouTubeTranscriber.PROMPT_PACKAGE, YouTubeTranscriber.PROMPT_DIR),
                            (YouTubeTranscriber.PROFILE_PACKAGE,
                             YouTubeTranscriber.PROFILE_DIR)):
        assert package in captured['packages'], captured.get('packages')
        source = captured['package_dir'][package]
        assert os.path.samefile(os.path.join(here, source), os.path.join(here, folder))
        names = captured['package_data'][package]
        assert names and all(os.path.isfile(os.path.join(here, source, n)) for n in names)
        assert not any('*' in n or n == YouTubeTranscriber.CONFIG_ENV for n in names), names
        if any(tracked):
            shipped = sorted(os.path.basename(p) for p in tracked
                             if os.path.dirname(p) == source and p.endswith('.txt')
                             and os.path.basename(p) != YouTubeTranscriber.CONFIG_ENV)
            assert sorted(names) == shipped, (names, shipped)

    # Installed, the package is found where site-packages put it, after the
    # working directory's own Prompt/ so an edited copy wins
    package = YouTubeTranscriber.PROMPT_PACKAGE
    with tempfile.TemporaryDirectory() as site:
        os.makedirs(os.path.join(site, package))
        io.open(os.path.join(site, package, 'prompt-refinement.txt'), 'w').write('TIDY')
        sys.path.insert(0, site)
        importlib.invalidate_caches()
        try:
            t = YouTubeTranscriber()
            installed = t.installed_prompt_dir()
            assert installed and os.path.samefile(installed, os.path.join(site, package))
            dirs = t.prompt_dirs()
            assert dirs[-1] == installed, dirs
        finally:
            sys.path.remove(site)
            importlib.invalidate_caches()


def test_a_checkout_run_from_elsewhere_still_finds_its_prompts():
    """`python /path/to/OpenAIYouTubeTranscriber.py` run from another folder
    lists the repo's own Prompt/, found beside the script rather than under
    the folder it was run from."""
    here = os.path.dirname(os.path.abspath(__file__))
    repo_prompts = os.path.join(here, YouTubeTranscriber.PROMPT_DIR)
    cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as elsewhere:
        os.chdir(elsewhere)
        try:
            t = YouTubeTranscriber()
            dirs = t.prompt_dirs()
            prompts = t.list_available_prompts()
        finally:
            os.chdir(cwd)
    assert any(os.path.samefile(d, repo_prompts) for d in dirs), dirs
    assert 'prompt-refinement.txt' in prompts, prompts


def test_an_installed_copy_starts_with_the_sample_profiles():
    """Profiles are listed, loaded and saved in the working directory's
    Profile/, so an installed copy's samples are copied there on first run -
    and a Profile/ that already exists is left exactly as it is."""
    package = YouTubeTranscriber.PROFILE_PACKAGE
    with tempfile.TemporaryDirectory() as site, tempfile.TemporaryDirectory() as work:
        os.makedirs(os.path.join(site, package))
        for name in ('profile-transcriber.txt', 'config.txt', 'notes.md'):
            io.open(os.path.join(site, package, name), 'w').write('URL=x\n')
        t = YouTubeTranscriber()
        t.PROFILE_DIR = os.path.join(work, 'Profile')
        # A checkout has nothing installed to copy, and makes no Profile/
        with redirect_stdout(io.StringIO()):
            t.seed_sample_profiles()
        assert not os.path.exists(t.PROFILE_DIR)
        sys.path.insert(0, site)
        importlib.invalidate_caches()
        try:
            with redirect_stdout(io.StringIO()):
                t.seed_sample_profiles()
            assert os.listdir(t.PROFILE_DIR) == ['profile-transcriber.txt']
            assert t.list_profiles() == ['profile-transcriber.txt']
            # The user's folder is theirs: emptied, it stays empty
            os.remove(os.path.join(t.PROFILE_DIR, 'profile-transcriber.txt'))
            with redirect_stdout(io.StringIO()):
                t.seed_sample_profiles()
            assert os.listdir(t.PROFILE_DIR) == []
        finally:
            sys.path.remove(site)
            importlib.invalidate_caches()


def test_webvtt_is_read_as_cue_blocks():
    """Read line by line, a cue's number and all but the first line of a NOTE
    were saved as speech, and '&amp;' stayed encoded."""
    vtt = '\n'.join([
        'WEBVTT', 'Kind: captions', '',
        'STYLE', '::cue { color: lime }', '',
        '1', '00:00:00.000 --> 00:00:01.000', 'Tom &amp; Jerry', '',
        'NOTE', 'private', 'annotation', '',
        'intro-2', '00:00:01.000 --> 00:00:02.000 align:start',
        '<v Roger>Hello</v> &lt;b&gt; is text', '',
    ])
    assert YouTubeTranscriber.captions_to_text(vtt, '.vtt') == 'Tom & Jerry Hello <b> is text'
    assert YouTubeTranscriber.captions_to_text(vtt.replace('\n', '\r\n'), '.vtt') == (
        'Tom & Jerry Hello <b> is text')


def test_a_home_relative_media_path_is_a_source():
    """~ was expanded to recognise the path, then the unexpanded one checked."""
    t = YouTubeTranscriber()
    saved = {key: os.environ.get(key) for key in ('HOME', 'USERPROFILE')}
    with tempfile.TemporaryDirectory() as home:
        io.open(os.path.join(home, 'clip.mp3'), 'wb').close()
        os.environ.update(HOME=home, USERPROFILE=home)
        try:
            with redirect_stdout(io.StringIO()):
                entries = t.source_entries('~/clip.mp3')
        finally:
            for key, value in saved.items():
                os.environ.pop(key, None) if value is None else os.environ.update({key: value})
    assert entries == [(os.path.join(home, 'clip.mp3'), True, None)], entries


def test_a_source_reached_by_another_path_is_still_never_written_over():
    """convert_media compared paths as text, so a folder reached through a
    symlink - or a name in another case on Windows or macOS - got past the
    check, and ffmpeg -y wrote over the file it was reading."""
    if not _ffmpeg_available():
        _skip('no ffmpeg')
    t = YouTubeTranscriber()
    with tempfile.TemporaryDirectory() as tmp:
        folder = os.path.join(tmp, 'A')
        os.makedirs(folder)
        source = _make_clip(os.path.join(folder, 'clip.mp3'), 'audio')
        before = io.open(source, 'rb').read()
        alias = os.path.join(tmp, 'B')
        try:
            os.symlink(folder, alias, target_is_directory=True)
        except (OSError, NotImplementedError):
            _skip('no symlinks here')
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            made = t.convert_media(source, 'mp3', 'audio', alias, 'clip', bitrate=32,
                                   replace_source=False)
        assert made is None, made
        assert io.open(source, 'rb').read() == before, 'the source was written over'


def test_no_deliverable_or_queued_source_is_written_over():
    """One place settles every name. Before it, a refinement named onto the
    transcript queued after it replaced that source before it was read, two
    streams rounding to one bitrate were downloaded to one file, and the audio
    written over the merged video when their folders were one through a link."""

    # Refinements over a list: the first's output is the second's source
    with tempfile.TemporaryDirectory() as tmp:
        t = _refine_setup(tmp)
        first = os.path.join(t.TRANSCRIPT_DIR, 'talk.txt')
        second = os.path.join(t.TRANSCRIPT_DIR, 'talk - refinement.txt')
        io.open(first, 'w', encoding='utf-8').write('first words')
        io.open(second, 'w', encoding='utf-8').write('an earlier refinement')
        cfg = module.SessionConfig(
            used_fields={}, ai_mode=module.AIEnhancementMode.LOCAL,
            sources=[(None, False, [first, second])],
            prompts=[('TIDY', 'prompt-refinement.txt')])
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            module._run_pipeline(t, cfg)
        found = _tree(t.TRANSCRIPT_DIR)
        assert found['Raw/talk - refinement.txt'] == 'an earlier refinement', found
        assert found['talk - refinement (2).txt'] == 'FIRST WORDS', found
        assert found['talk - refinement - refinement.txt'] == 'AN EARLIER REFINEMENT', found

    # A video's Whisper transcript, onto the transcript queued after it
    with tempfile.TemporaryDirectory() as tmp:
        t = _refine_setup(tmp)
        t.AUDIO_DIR = os.path.join(tmp, 'Audio')
        queued = os.path.join(t.TRANSCRIPT_DIR, 'clip [Whisper en].txt')
        io.open(queued, 'w', encoding='utf-8').write('an older transcript')
        t.fetch_video_info = lambda url: dict(_plain_info(), id='x', title='clip')
        t.transcribe_audio_file = lambda *a: ('new words', 'en')

        def fake_audio(info, stem, is_temp=False, format_selector='', keep_in=None):
            out = os.path.join(t.AUDIO_DIR, t.TEMP_DIR)
            os.makedirs(out, exist_ok=True)
            path = os.path.join(out, stem + '.mp3')
            io.open(path, 'w').write('x')
            return path, os.path.abspath(path)

        t.download_audio_stream = fake_audio
        cfg = module.SessionConfig(
            used_fields={}, sources=[('https://youtu.be/x', False, None),
                                     (None, False, [queued])],
            transcribe_audio=True, target_languages=['en'], transcribe_audio_quality='lowest')
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            module._run_pipeline(t, cfg)  # ai_mode None: the second pass refines nothing
        found = _tree(t.TRANSCRIPT_DIR)
        assert found['clip [Whisper en].txt'] == 'an older transcript', found
        assert found['clip [Whisper en] (2).txt'] == 'new words', found

    # Two streams whose bitrates round alike: 59.8k and 60.2k are both "60k"
    formats = [{'format_id': '249', 'vcodec': 'none', 'acodec': 'opus', 'abr': 59.8,
                'format_note': 'low', 'language_preference': 10},
               {'format_id': '250', 'vcodec': 'none', 'acodec': 'opus', 'abr': 60.2,
                'format_note': 'low', 'language_preference': 10}]
    with tempfile.TemporaryDirectory() as tmp:
        t = YouTubeTranscriber()
        t.AUDIO_DIR = os.path.join(tmp, 'Audio')

        def keep_audio(info, stem, is_temp=False, format_selector='', keep_in=None):
            path = os.path.join(keep_in, stem + '.webm')
            os.makedirs(keep_in, exist_ok=True)
            io.open(path, 'w').write(format_selector)
            return path, os.path.abspath(path)

        t.download_audio_stream = keep_audio
        cfg = module.SessionConfig(
            url='https://youtu.be/x', info={'webpage_url': 'https://youtu.be/x',
                                            'formats': formats},
            video_title='clip', used_fields={}, transcribe_audio=False,
            download_audio=True, audio_resolution='59,lowest', audio_format='original')
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            module._run_pipeline(t, cfg)
        assert len(os.listdir(t.AUDIO_DIR)) == 2, os.listdir(t.AUDIO_DIR)

    # The merged video and the audio, one folder through a symlink
    with tempfile.TemporaryDirectory() as tmp:
        videos = os.path.join(tmp, 'media')
        os.makedirs(videos)
        link = os.path.join(tmp, 'music')
        try:
            os.symlink(videos, link, target_is_directory=True)
        except (OSError, NotImplementedError):
            _skip('no symlinks here')
        t = YouTubeTranscriber()
        written = []
        t.convert_media = lambda source, target, kind, folder, stem, **kw: written.append(
            os.path.join(folder, f'{stem}.{target}'))
        t.stream_codec = lambda source, kind: 'h264' if kind == 'video' else 'aac'
        t.source_height, t.source_bitrate = (lambda source: 720), (lambda source: 128)
        cfg = module.SessionConfig(
            url='clip.mp4', is_local_file=True, used_fields={}, download_video=True,
            video_format='mkv', download_audio=True, audio_format='mkv',
            video_path=videos, audio_path=link)
        with redirect_stdout(io.StringIO()):
            module._local_deliverables(t, cfg, 'clip')
        assert written == [os.path.join(videos, 'clip.mkv'),
                           os.path.join(link, 'clip - Audio.mkv')], written


def test_a_prompt_that_fails_leaves_no_unrefined_copy_beside_the_rest():
    """A prompt whose enhancement failed saved the text as it came under the
    plain name, beside a refinement that worked and with KEEP_TRANSCRIPT=n."""

    prompts = [('TIDY', 'prompt-refinement.txt'), ('BRIEF', 'prompt1-summarizer.txt')]
    for fails, keep, expected in (
            ('BRIEF', False, {'clip - refinement.txt': 'THE WORDS'}),
            ('BRIEF', True, {'clip - refinement.txt': 'THE WORDS', 'Raw/clip.txt': 'the words'}),
            # Every prompt failing still saves the transcript, once
            ('', False, {'clip.txt': 'the words'})):
        with tempfile.TemporaryDirectory() as tmp:
            t = _refine_setup(tmp)
            t.enhance_text = lambda text, mode, prompt, fails=fails, **kw: (
                text if prompt == fails or not fails else text.upper())
            cfg = module.SessionConfig(used_fields={}, ai_mode=module.AIEnhancementMode.LOCAL,
                                       prompts=prompts, keep_transcript=keep)
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                assert module._enhance_and_save(t, cfg, 'the words', 'clip', open_after=False)
            assert _tree(t.TRANSCRIPT_DIR) == expected, (fails, keep, _tree(t.TRANSCRIPT_DIR))


def test_a_summary_never_replaces_a_source_whose_copy_was_not_kept():
    """KEEP_TRANSCRIPT=y, a rename back onto the source, and a Raw/ that could
    not be written: the summary still went over the only full transcript."""

    with tempfile.TemporaryDirectory() as tmp:
        t = _refine_setup(tmp)
        # A file where the Raw folder should be, so nothing can be saved in it
        io.open(t.RAW_TRANSCRIPT_DIR, 'w').write('in the way')
        source = os.path.join(t.TRANSCRIPT_DIR, 'talk - summarizer.txt')
        io.open(source, 'w', encoding='utf-8').write('the only words')
        cfg = module.SessionConfig(
            used_fields={}, ai_mode=module.AIEnhancementMode.LOCAL, refine_sources=[source],
            prompts=[('BRIEF', 'prompt1-summarizer.txt')], transcript_rename='talk',
            keep_transcript=True)
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            module._refine_transcripts(t, cfg)
        assert io.open(source, encoding='utf-8').read() == 'the only words'

    # ...and where the copy did go is where the log says it went
    with tempfile.TemporaryDirectory() as tmp:
        t = _refine_setup(tmp)
        source = os.path.join(t.TRANSCRIPT_DIR, 'talk.txt')
        io.open(source, 'w', encoding='utf-8').write('the words')
        elsewhere = os.path.join(tmp, 'notes')
        cfg = module.SessionConfig(
            used_fields={}, ai_mode=module.AIEnhancementMode.LOCAL, refine_sources=[source],
            prompts=[('TIDY', 'prompt-refinement.txt')], transcript_path=elsewhere)
        log = io.StringIO()
        with redirect_stdout(log), redirect_stderr(io.StringIO()):
            module._refine_transcripts(t, cfg)
        assert not os.path.exists(source)
        assert f"Moved talk.txt to {os.path.join(elsewhere, 'Raw')}" in log.getvalue(), \
            log.getvalue()


def test_ffmpeg_output_is_read_as_utf8_whatever_the_locale():
    """ffmpeg writes UTF-8 and text=True read it in the locale's encoding -
    cp1252 on Windows - so a Japanese filename in its log ended the batch.
    Run here under an ASCII locale, which fails the same way."""
    if not _ffmpeg_available():
        _skip('no ffmpeg')
    with tempfile.TemporaryDirectory() as tmp:
        io.open(os.path.join(tmp, 'あいう.mp3'), 'w').write('not media')
        code = ('import os, sys\n'
                'import OpenAIYouTubeTranscriber as m\n'
                'folder = sys.argv[1]\n'
                'path = os.path.join(folder, os.listdir(folder)[0])\n'
                'print(m.YouTubeTranscriber().get_file_format(path))\n')
        run = subprocess.run(
            [sys.executable, '-c', code, tmp], capture_output=True,
            cwd=os.path.dirname(os.path.abspath(__file__)),
            env=dict(os.environ, LC_ALL='C', LANG='C', PYTHONUTF8='0',
                     PYTHONCOERCECLOCALE='0', PYTHONIOENCODING='utf-8'))
    assert run.returncode == 0 and b'UnicodeDecodeError' not in run.stderr, run.stderr[-400:]
    assert run.stdout.strip() == b'None', run.stdout


def test_a_superscript_digit_at_a_menu_asks_again():
    """'²'.isdigit() is True and int('²') raises: typed at a menu, it ended
    the session with a traceback instead of asking again."""

    t = YouTubeTranscriber()
    script = ['²', '1']
    builtins.input = lambda prompt='': script.pop(0)
    try:
        with redirect_stdout(io.StringIO()):
            assert module._prompt_resolution_selection(t, _plain_info()) == '720p'
            script[:] = ['²', '1']
            assert module._prompt_profile_selection(t, ['profile.txt']) == 'profile.txt'
    finally:
        builtins.input = REAL_INPUT
    assert Resolution.normalize('²k') == '²k'
    assert module._as_height('²') == '²'
    assert not module._is_number('²') and not module._is_number('٣')
    assert module._is_number('720')
    assert t._resolve_prompt_choice('²', ['prompt-refinement.txt']) is None


def test_a_video_with_nothing_to_pick_gives_way_to_the_next():
    """A video with no video streams, met while the settings were still being
    asked, raised DownloadFailed out of the setup: main() exited, and the
    videos after it in the list never ran."""

    t = YouTubeTranscriber()
    infos = {'https://youtu.be/audioonly': dict(_plain_info(), title='a', formats=[
        f for f in _plain_info()['formats'] if f['vcodec'] == 'none']),
        'https://youtu.be/video': dict(_plain_info(), title='v')}
    t.fetch_video_info = lambda url: infos[url]
    cfg = module.SessionConfig(used_fields={}, sources=[(url, False, None) for url in infos])
    module._settle_sources(cfg)
    builtins.input = lambda prompt='': '1'
    try:
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            picked = module._resolve_quality(t, cfg, '', module._prompt_resolution_selection)
    finally:
        builtins.input = REAL_INPUT
    assert picked == '720p' and cfg.url == 'https://youtu.be/video', (picked, cfg.url)
    assert [entry[0] for entry in cfg.sources] == ['https://youtu.be/video']


def test_input_running_out_ends_the_run_without_a_traceback():
    """An unattended run asked something it cannot answer raised EOFError out
    of main(). A REPEAT=y round asking for its next sources has done its work,
    and ends as a success; a first round that got nothing done does not."""
    code = ('import OpenAIYouTubeTranscriber as m\n'
            'm.YouTubeTranscriber.check_dependencies = lambda self: True\n'
            'm.main()\n')
    here = os.path.dirname(os.path.abspath(__file__))
    for repeat, status in ((False, 1), (True, 0)):
        with tempfile.TemporaryDirectory() as tmp:
            if repeat:
                # A round that asks nothing and does nothing, then goes round
                # again: the repeat asks for its sources, and input has run out
                profiles = os.path.join(tmp, YouTubeTranscriber.PROFILE_DIR)
                os.makedirs(profiles)
                clip = os.path.join(tmp, 'clip.mp3')
                io.open(clip, 'w', encoding='utf-8').write('not really audio')
                io.open(os.path.join(profiles, 'p.txt'), 'w', encoding='utf-8').write(
                    f"URL='{clip}'\nDOWNLOAD_VIDEO=n\nVIDEO_ONLY=n\nDOWNLOAD_AUDIO=n\n"
                    "TRANSCRIBE_AUDIO=n\nREPEAT=y\n")
                io.open(os.path.join(profiles, YouTubeTranscriber.CONFIG_ENV), 'w',
                        encoding='utf-8').write('LOAD_PROFILE=p.txt\n')
            env = dict(os.environ, PYTHONPATH=here)
            run = subprocess.run([sys.executable, '-c', code], capture_output=True, cwd=tmp,
                                 stdin=subprocess.DEVNULL, env=env)
        assert run.returncode == status, (repeat, run.returncode, run.stderr[-300:])
        assert b'Traceback' not in run.stderr, run.stderr[-300:]
        assert b'No more input' in run.stdout, run.stdout[-300:]
        assert (b'Repeating session' in run.stdout) == repeat, run.stdout[-300:]


def test_profile_fields_read_as_their_questions_do():
    """'skip' declines a RENAME or PATH as it does everywhere else, ~ is a home
    folder in a PATH as it is in a source, LOAD_PROFILE is read as dotenv reads
    it, and an English-only model is not run on speech declared otherwise."""

    t = YouTubeTranscriber()
    for answer in ('s', 'skip', 'SKIP', 'n'):
        assert module._resolve_rename(t, answer, 'x') == '', answer
        assert module._resolve_path(t, answer, 'x', 'Video') == '', answer
    keys = ('HOME', 'USERPROFILE', 'LOAD_PROFILE')
    saved = {key: os.environ.get(key) for key in keys}
    try:
        with tempfile.TemporaryDirectory() as home:
            os.environ.update(HOME=home, USERPROFILE=home)
            assert module._resolve_path(t, '~/Transcripts', 'x', 'T') == os.path.join(
                home, 'Transcripts')
            assert os.path.isdir(os.path.join(home, 'Transcripts'))

            t.PROFILE_DIR = os.path.join(home, 'Profile')
            os.makedirs(t.PROFILE_DIR)
            io.open(os.path.join(t.PROFILE_DIR, 'profile0.txt'), 'w').write('URL=zero\n')
            for line in ("LOAD_PROFILE='profile0.txt'", 'LOAD_PROFILE=profile0.txt  # lecture'):
                io.open(os.path.join(t.PROFILE_DIR, t.CONFIG_ENV), 'w').write(line + '\n')
                with redirect_stdout(io.StringIO()):
                    answers = module._select_profile(t, module.Session())
                assert (answers.origin, answers.fields) == ('profile0.txt', {'URL': 'zero'}), line
    finally:
        for key, value in saved.items():
            os.environ.pop(key, None) if value is None else os.environ.update({key: value})

    # USE_EN_MODEL=y with Japanese speech: the English-only model is not used
    models = []
    with tempfile.TemporaryDirectory() as tmp:
        t = _refine_setup(tmp)
        audio = os.path.join(tmp, 'clip.mp3')
        io.open(audio, 'w').write('x')
        t.transcribe_audio_file = lambda path, model, target, source=None: (
            models.append(model) or ('words', 'ja'))
        cfg = module.SessionConfig(url=audio, is_local_file=True, used_fields={},
                                   transcribe_audio=True, target_languages=['auto'],
                                   source_language='ja', use_en_model=True)
        t.is_valid_media_file = lambda path: True
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            module._run_one(t, cfg)
    assert models == ['base'], models
    cfg = module.SessionConfig(used_fields={}, source_language='ja', target_languages=['auto'])
    assert not module._offers_en_model(t, cfg, ModelSize.BASE)


def test_a_pick_from_the_caption_listing_stands_for_each_video():
    """Enter at the listing took this video's original, recorded as its key:
    a Japanese video after an English one was given 'en', the machine
    translation of itself, and never its original."""

    t = YouTubeTranscriber()
    t.startfile = lambda *a: None
    fetched = []
    t.fetch_caption_text = lambda info, key: fetched.append(key) or f'the {key} words'
    japanese = {'language': 'ja', 'automatic_captions': {
        'ja-orig': [{'url': 'https://x/t?lang=ja', 'name': 'Japanese (Original)'}],
        'ja': [{'url': 'https://x/t?lang=ja', 'name': 'Japanese'}],
        'en': [{'url': 'https://x/t?lang=ja&tlang=en', 'name': 'English'}]}}
    videos = [('https://youtu.be/first', False, None), ('https://youtu.be/second', False, None)]
    builtins.input = lambda prompt='': ''
    try:
        cfg = module.SessionConfig(url=videos[0][0], info=_caption_info(), used_fields={},
                                   sources=videos)
        with redirect_stdout(io.StringIO()):
            module._settle_yt_transcripts(t, cfg, 'f')
    finally:
        builtins.input = REAL_INPUT
    assert cfg.yt_transcript_languages == ['original'], cfg.yt_transcript_languages
    assert cfg.yt_transcript_raw == 'original'
    with tempfile.TemporaryDirectory() as tmp:
        t.TRANSCRIPT_DIR = os.path.join(tmp, 'Transcript')
        t.RAW_TRANSCRIPT_DIR = os.path.join(t.TRANSCRIPT_DIR, 'Raw')
        cfg.info = japanese
        with redirect_stdout(io.StringIO()):
            module._save_yt_transcripts(t, cfg, 'clip')
    assert fetched == ['ja'], fetched

    # A regional pick answers from another region of the language, never another script
    track = module._track_for
    assert track({'en-GB': 1}, 'en-US') == 'en-GB'
    assert track({'en': 1}, 'en-US') == 'en'
    assert track({'zh-Hant': 1}, 'zh-Hans') is None
    assert track({'zh-Hans': 1, 'zh-Hant': 1}, 'zh-Hant') == 'zh-Hant'


def test_audio_is_copied_only_into_a_container_that_plays_it():
    """A stream copy put YouTube's Opus in an .mp4 and AAC in a .wav: ffmpeg
    writes both, and most players refuse them."""
    if not _ffmpeg_available():
        _skip('no ffmpeg')
    t = YouTubeTranscriber()
    with tempfile.TemporaryDirectory() as tmp:
        opus, aac = os.path.join(tmp, 'a.webm'), os.path.join(tmp, 'b.m4a')
        for path, codec in ((opus, 'libopus'), (aac, 'aac')):
            subprocess.run(['ffmpeg', '-y', '-v', 'error', '-f', 'lavfi', '-i',
                            'sine=frequency=440:duration=0.3', '-c:a', codec, path],
                           capture_output=True, check=True)
        for source, target, want in ((opus, 'mp4', 'aac'), (aac, 'wav', 'pcm_s16le'),
                                     (opus, 'ogg', 'opus'), (aac, 'mkv', 'aac')):
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                made = t.convert_media(source, target, 'audio', tmp, f'out-{target}')
            assert t.stream_codec(made, 'audio') == want, (source, target)


def test_whisper_work_is_neither_repeated_nor_reloaded():
    """TARGET_LANGUAGE=auto,en on English speech ran a second full pass that
    came back identical, a model that failed to load was tried again for every
    target and source, and detection decoded the whole file for 30 seconds."""

    loads, passes = [], []

    class Model:
        def transcribe(self, path, language=None, task='transcribe'):
            passes.append((language, task))
            return {'text': 'english words', 'language': language or 'en'}

    def load_model(name):
        loads.append(name)
        if name == 'large-v3':
            raise RuntimeError('out of memory')
        return Model()

    saved_load = whisper.load_model
    whisper.load_model = load_model
    try:
        with tempfile.TemporaryDirectory() as tmp:
            audio = os.path.join(tmp, 'clip.mp3')
            io.open(audio, 'wb').close()
            for targets in (('auto', 'en'), ('en', 'auto')):
                t = YouTubeTranscriber()
                t.spoken_language = lambda model, path: 'en'
                loads.clear()
                passes.clear()
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    for target in targets:
                        t.transcribe_audio_file(audio, 'large-v3', target)
                assert len(passes) == 1, (targets, passes)
                assert loads == ['large-v3', 'base'], (targets, loads)
    finally:
        whisper.load_model = saved_load

    if _ffmpeg_available():
        with tempfile.TemporaryDirectory() as tmp:
            long_audio = os.path.join(tmp, 'long.wav')
            subprocess.run(['ffmpeg', '-y', '-v', 'error', '-f', 'lavfi', '-i',
                            'sine=frequency=440:duration=45', long_audio], check=True)
            opening = YouTubeTranscriber.load_opening(long_audio)
            assert len(opening) == 30 * whisper.audio.SAMPLE_RATE, len(opening)


def test_the_local_model_is_given_the_dtype_its_transformers_understands():
    """transformers called it torch_dtype until 4.56; given dtype, an older one
    passed it on to generate(), which refused it for every chunk."""
    import sys
    import types

    t = YouTubeTranscriber()

    class Tokenizer:
        model_max_length, chat_template = 4096, None

        def encode(self, text, **kwargs):
            return range(len(text.encode('utf-8')) // 4)

    for name in ('torch_dtype', 'dtype'):
        seen = {}
        namespace = {}
        exec(f'def pipeline(task, model=None, tokenizer=None, {name}=None, device_map=None):\n'
             f'    seen.update(dtype_given={name!r})\n'
             f'    return lambda prompt, **o: [{{"generated_text": prompt}}]\n',
             {'seen': seen}, namespace)
        transformers = types.SimpleNamespace(
            AutoTokenizer=types.SimpleNamespace(from_pretrained=lambda _id: Tokenizer()),
            pipeline=namespace['pipeline'])
        saved = sys.modules.get('transformers')
        sys.modules['transformers'] = transformers
        try:
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                t.enhance_with_local('A few words to tidy.', 'tidy', 'any/model')
        finally:
            sys.modules.pop('transformers', None) if saved is None else sys.modules.update(
                transformers=saved)
        assert seen.get('dtype_given') == name, (name, seen)


def test_a_download_reuses_the_metadata_already_fetched():
    """Every download extracted the video again - page, player and API - though
    the run already had its metadata, and could choose other formats than the
    ones the file names were made from. Through the real yt-dlp, on a stream
    served from disk."""
    if not _ffmpeg_available():
        _skip('no ffmpeg')
    import yt_dlp

    with tempfile.TemporaryDirectory() as tmp:
        stream = os.path.join(tmp, 'stream.webm')
        subprocess.run(['ffmpeg', '-y', '-v', 'error', '-f', 'lavfi', '-i',
                        'sine=frequency=440:duration=0.3', '-c:a', 'libopus', stream],
                       capture_output=True, check=True)
        info = {'id': 'abcdefghijk', 'title': 'clip', 'webpage_url': 'https://youtu.be/abcdefghijk',
                'extractor': 'youtube', 'extractor_key': 'Youtube',
                'formats': [{'format_id': '251', 'url': 'file://' + stream, 'ext': 'webm',
                             'vcodec': 'none', 'acodec': 'opus', 'abr': 106.0,
                             'protocol': 'file'}]}
        t = YouTubeTranscriber()
        t.YDL_OPTS = dict(t.YDL_OPTS, enable_file_urls=True)
        real = yt_dlp.YoutubeDL.extract_info
        yt_dlp.YoutubeDL.extract_info = lambda ydl, url, download=True, **kw: (
            info if not download else (_ for _ in ()).throw(AssertionError('extracted again')))
        try:
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                assert t.fetch_video_info('https://youtu.be/abcdefghijk') is info
                path = t.download_format(info['webpage_url'], 'bestaudio/best',
                                         os.path.join(tmp, 'out'), 'clip')
        finally:
            yt_dlp.YoutubeDL.extract_info = real
        assert os.path.basename(path) == 'clip.webm'
        assert t.stream_codec(path, 'audio') == 'opus'
        t.release_caches()
        assert not t._video_info


if __name__ == '__main__':
    # Without pytest: every test runs, and each failure is reported with its
    # traceback, where the first one used to stop the run and hide the rest.
    # pytest (see conftest.py) also restores what a failed test left patched.
    import traceback

    failed = []
    for name, fn in sorted(globals().items()):
        if name.startswith('test_'):
            try:
                fn()
            except _Skipped as reason:
                print(f'skip {name} ({reason})')
            except Exception:
                failed.append(name)
                print(f'FAIL {name}')
                traceback.print_exc()
            else:
                print(f'ok  {name}')
    if failed:
        print(f'{len(failed)} failed: {", ".join(failed)}')
        sys.exit(1)
    print('all passed')

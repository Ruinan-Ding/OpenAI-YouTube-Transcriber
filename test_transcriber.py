# Self-check for the parsing/chunking logic. Run with: python test_transcriber.py

from OpenAIYouTubeTranscriber import ModelSize, Resolution, YouTubeTranscriber


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
                'https://www.youtube.com/@SomeChannel',
                'https://www.youtube.com/watch?list=PLxxxx',
                'https://www.youtube.com/',
                'https://vimeo.com/123456789',
                'https://notyoutube.com/watch?v=jNQXAC9IVRw'):
        assert not u(url), url


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


def test_video_format_selectors():
    f = YouTubeTranscriber.video_format
    assert f(Resolution.HIGHEST.value) == 'bestvideo'
    assert f(Resolution.LOWEST.value) == 'worstvideo'
    # A resolution reaches this both as '720p' (prompt/profile) and bare '720'
    assert f('720p') == 'bestvideo[height=720]'
    assert f('720') == 'bestvideo[height=720]'


def test_model_choice_is_case_insensitive():
    # _configure_from_profile validates model_choice.lower() but passes the raw
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

    punctuated = t('This is a sentence. ' * 2000, max_tokens=800)
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

    # An overlap wider than the budget must not shred text into single characters
    degenerate = t('hello world this is a test of the emergency system',
                   max_tokens=40, overlap_tokens=50)
    assert 'hello' in degenerate[0]

    assert t('Short.', max_tokens=800) == ['Short.']


def test_merge_chunks_dedupes_overlap():
    m = YouTubeTranscriber.merge_chunks
    assert m([]) == ''
    assert m(['only']) == 'only'
    tail = 'the quick brown fox jumps over the lazy dog'
    assert m(['start ' + tail, tail + ' end']).count('lazy dog') == 1


def test_resolution_f_normalizes_to_fetch():
    assert Resolution.normalize(' F ') == Resolution.FETCH.value
    assert Resolution.normalize('fetch') == Resolution.FETCH.value
    assert Resolution.normalize('720P') == '720p'
    assert Resolution.normalize('HIGHEST') == Resolution.HIGHEST.value


if __name__ == '__main__':
    for name, fn in sorted(globals().items()):
        if name.startswith('test_'):
            fn()
            print(f'ok  {name}')
    print('all passed')

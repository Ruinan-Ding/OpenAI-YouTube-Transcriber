# Checks for subtitle_prototype.py. Run with pytest, or: python test_subtitle_prototype.py

import json
import os
import subprocess
import sys
import tempfile

import subtitle_prototype as sp
from subtitle_prototype import Cue, Word


class _Skipped(Exception):
    """A test that cannot run here: no ffmpeg."""


def _skip(reason):
    if 'pytest' in sys.modules:
        import pytest
        pytest.skip(reason)
    raise _Skipped(reason)


def _ffmpeg_available():
    try:
        subprocess.run(['ffmpeg', '-hide_banner', '-version'], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, OSError):
        return False


def _assert_readable(cues):
    """Every cue fits the reading limits and leaves the next one room."""
    for cue in cues:
        lines = cue.text.split('\n')
        assert len(lines) <= sp.MAX_LINES and all(len(line) <= sp.MAX_LINE for line in lines), cue
        assert cue.end > cue.start, cue
    for one, two in zip(cues, cues[1:]):
        assert one.end <= two.start - sp.CUE_GAP + 1e-9, (one, two)


def test_youtubes_recognised_words_are_cut_into_cues():
    """json3 from YouTube's recognition: each word timed by its offset, the
    '\\n' events dropped, and an event's first word, which carries no space,
    kept apart from the word before it."""
    payload = json.dumps({'events': [
        {'tStartMs': 0, 'dDurationMs': 60000, 'id': 1},
        {'tStartMs': 1000, 'dDurationMs': 6000, 'wWinId': 1, 'segs': [
            {'utf8': 'we'}, {'utf8': ' are', 'tOffsetMs': 300},
            {'utf8': ' here', 'tOffsetMs': 600}]},
        {'tStartMs': 2490, 'wWinId': 1, 'aAppend': 1, 'segs': [{'utf8': '\n'}]},
        {'tStartMs': 2500, 'dDurationMs': 6000, 'wWinId': 1, 'segs': [
            {'utf8': 'today.'}, {'utf8': ' Then', 'tOffsetMs': 3000}]},
    ]})
    cues = sp.json3_cues(payload)
    assert [cue.text for cue in cues] == ['we are here today.', 'Then'], cues
    assert cues[0].start == 1.0 and cues[1].start == 5.5, cues
    _assert_readable(cues)


def test_a_written_youtube_track_keeps_its_own_timing_and_lines():
    payload = json.dumps({'events': [
        {'tStartMs': 1200, 'dDurationMs': 2160,
         'segs': [{'utf8': 'All right, so here we are, in front of the\nelephants'}]},
        {'tStartMs': 5318, 'dDurationMs': 2656, 'segs': [{'utf8': 'the  cool thing'}]},
    ]})
    cues = sp.json3_cues(payload)
    assert cues == [Cue(1.2, 3.36, 'All right, so here we are, in front of the\nelephants'),
                    Cue(5.318, 7.974, 'the cool thing')], cues


def test_vtt_cues_keep_their_timing_and_skip_what_is_not_speech():
    payload = '\n'.join([
        'WEBVTT', 'Kind: captions', '', 'NOTE a comment', '', '1',
        '00:00:01.200 --> 00:00:03.360 align:start', 'Tom &amp; <c>Jerry</c>', '',
        '01:02.500 --> 01:04.000', 'second', ''])
    assert sp.vtt_cues(payload) == [Cue(1.2, 3.36, 'Tom & Jerry'), Cue(62.5, 64.0, 'second')]


def test_cues_stay_within_the_reading_limits():
    """A long run of speech with no pauses is cut by length and by time."""
    words = [Word(i * 0.3, i * 0.3 + 0.25, f' word{i}') for i in range(200)]
    cues = sp.build_cues(words)
    _assert_readable(cues)
    assert ' '.join(cue.text.replace('\n', ' ') for cue in cues).split() == \
        [f'word{i}' for i in range(200)]
    assert all(cue.end - cue.start <= sp.MAX_CUE_SECONDS + sp.LINGER for cue in cues), cues


def test_a_cue_ends_at_a_pause_and_at_a_sentence():
    words = [Word(0.0, 0.3, 'This'), Word(0.3, 0.6, ' is'), Word(0.6, 0.9, ' a'),
             Word(0.9, 1.3, ' complete'), Word(1.3, 1.8, ' sentence.'),
             Word(1.9, 2.2, ' Next'), Word(2.2, 2.5, ' one'),
             Word(4.0, 4.3, ' after'), Word(4.3, 4.6, ' silence')]
    cues = sp.build_cues(words)
    assert [cue.text for cue in cues] == ['This is a complete sentence.', 'Next one',
                                          'after silence'], cues
    assert cues[2].start == 4.0
    _assert_readable(cues)


def test_a_full_cue_is_cut_back_to_its_last_clause():
    words = [Word(i * 0.2, i * 0.2 + 0.2, text) for i, text in enumerate(
        ('Twenty', ' one', ' words', ' arrive', ' here', ' with', ' a', ' comma,', ' and',
         ' then', ' the', ' cue', ' carries', ' on', ' past', ' its', ' room', ' to', ' fill'))]
    cues = sp.build_cues(words)
    assert cues[0].text.replace('\n', ' ').endswith('comma,'), cues
    _assert_readable(cues)


def _spoken(text):
    """text as words a quarter of a second each, with no pause between them."""
    return [Word(i * 0.25, i * 0.25 + 0.25, (' ' if i else '') + word)
            for i, word in enumerate(text.split())]


def test_a_full_cue_is_cut_at_an_earlier_sentence_or_clause_not_mid_phrase():
    """Both from a Spanish fable, where a cue had to be half full to be cut."""
    cases = {
        'la liebre empezó a pensar. Vio un claro en el bosque y se acostó bajo la sombra '
        'de un árbol a descansar.':
            ['la liebre empezó a pensar.',
             'Vio un claro en el bosque y se acostó bajo la sombra de un árbol a descansar.'],
        'Hola Gabriel, es tu papá, mira, hoy te voy a contar el cuento de la liebre y la '
        'tortuga.':
            ['Hola Gabriel, es tu papá, mira,',
             'hoy te voy a contar el cuento de la liebre y la tortuga.'],
    }
    for text, expected in cases.items():
        cues = sp.build_cues(_spoken(text))
        assert [cue.text.replace('\n', ' ') for cue in cues] == expected, cues
        _assert_readable(cues)


def test_a_titles_full_stop_ends_no_cue():
    cues = sp.build_cues(_spoken('but the turtle accepted. Mr. Búho was in charge of '
                                 'organizing the race and giving the start.'))
    assert [cue.text.replace('\n', ' ') for cue in cues] == [
        'but the turtle accepted.',
        'Mr. Búho was in charge of organizing the race and giving the start.'], cues


def test_whisper_words_give_back_the_silence_they_swallowed():
    """Whisper put "The" at the segment's start with no length and ran "cool"
    over a second and a half of silence after it."""
    words = sp.tighten([Word(3.88, 3.88, ' The'), Word(3.88, 5.38, ' cool'),
                        Word(5.38, 5.60, ' thing'), Word(10.48, 12.50, ' hunts.')])
    the, cool, thing, hunts = words
    assert cool.end == 5.38 and cool.start > 4.5, cool
    assert the.end == cool.start and the.start < the.end, the
    assert (thing.start, thing.end) == (5.38, 5.60)
    # Stretched after speech, a word is cut from its start: the pause follows it
    assert hunts.start == 10.48 and hunts.end < 11.5, hunts


def test_a_segment_is_shared_out_by_its_words_lengths():
    words = sp.segment_words(10.0, 13.0, ' aa bbbb')
    assert [(w.start, w.end, w.text) for w in words] == [
        (10.0, 11.0, ' aa'), (11.0, 13.0, ' bbbb')], words


def test_lines_are_broken_near_the_middle_and_after_punctuation():
    assert sp.split_lines('short enough') == 'short enough'
    two = sp.split_lines('the cool thing about these guys is that they have really long trunks')
    left, right = two.split('\n')
    assert len(left) <= sp.MAX_LINE and len(right) <= sp.MAX_LINE, two
    # After the comma, though a break after "is" would be exactly in the middle
    assert sp.split_lines('So the thing about these guys, is that they have really long trunks') \
        == 'So the thing about these guys,\nis that they have really long trunks'
    cjk = sp.split_lines('今日は' * 16)
    assert cjk.count('\n') == 1 and ' ' not in cjk


def test_polish_corrects_the_text_and_leaves_the_timing_alone():
    cues = [Cue(1.0, 3.0, 'alright so here we are\none of the elephants'),
            Cue(4.6, 9.0, 'um the cool thing about these guys'),
            Cue(9.5, 11.0, 'is they have really long hunts')]
    seen = []

    def model(prompt, text):
        seen.append((prompt, text))
        return ('1|All right, so here we are, in front of the elephants.\n'
                '2|The cool thing about these guys\n'
                '3|is they have really long trunks.')

    polished, outcomes = sp.polish_cues(cues, model)
    assert [(cue.start, cue.end) for cue in polished] == [(cue.start, cue.end) for cue in cues]
    assert polished[1].text == 'The cool thing about these guys'
    assert polished[2].text == 'is they have really long trunks.'
    assert outcomes == {'polished': 3}, outcomes
    prompt, sent = seen[0]
    assert sent.splitlines()[0] == '1|alright so here we are one of the elephants', sent
    assert 'never move a word' in prompt


def test_polish_keeps_a_cue_the_reply_moved_dropped_or_gave_twice():
    """Words pulled from the next cue would show before they are said; a cue
    left out or numbered twice cannot be matched to its time."""
    cues = [Cue(0, 1, 'we went to the'), Cue(1, 2, 'market and bought some'),
            Cue(2, 3, 'apples today'), Cue(3, 4, 'then we left')]

    def model(prompt, text):
        return ('1|We went to the market and bought some apples\n'
                '2|today.\n'
                '4|Then we left.\n'
                '4|Then, we left.')

    polished, outcomes = sp.polish_cues(cues, model)
    assert polished == cues, polished
    assert outcomes == {'rejected': 2, 'missing': 2}, outcomes


def test_a_failed_polish_keeps_every_cue():
    cues = [Cue(0, 1, 'one'), Cue(1, 2, 'two')]

    def model(prompt, text):
        raise RuntimeError('rate limited')

    polished, outcomes = sp.polish_cues(cues, model)
    assert polished == cues and outcomes == {'missing': 2}, (polished, outcomes)


def test_polish_goes_in_numbered_batches():
    cues = [Cue(i, i + 1, f'cue {i}') for i in range(5)]
    batches = []

    def model(prompt, text):
        batches.append([line.split('|')[0] for line in text.splitlines()])
        return text

    sp.polish_cues(cues, model, batch=2)
    assert batches == [['1', '2'], ['3', '4'], ['5']], batches


def test_srt_numbering_and_times():
    srt = sp.to_srt([Cue(1.2, 3.36, 'one\ntwo'), Cue(3725.5, 3726.0001, 'three')])
    assert srt == ('1\n00:00:01,200 --> 00:00:03,360\none\ntwo\n\n'
                   '2\n01:02:05,500 --> 01:02:06,000\nthree\n\n'), srt


def test_subtitles_are_muxed_soft_and_burned_in():
    """Through the real ffmpeg: a track per container, and a burn-in from a
    folder whose name the subtitles filter could not have read as it is."""
    if not _ffmpeg_available():
        _skip('no ffmpeg')
    with tempfile.TemporaryDirectory() as tmp:
        folder = os.path.join(tmp, "it's a [test], folder")
        os.makedirs(folder)
        clip = os.path.join(folder, 'clip.mp4')
        subprocess.run(['ffmpeg', '-y', '-v', 'error',
                        '-f', 'lavfi', '-i', 'testsrc=duration=2:size=160x120:rate=10',
                        '-f', 'lavfi', '-i', 'sine=frequency=440:duration=2',
                        '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest',
                        clip], capture_output=True, check=True)
        srt = os.path.join(folder, 'clip.srt')
        with open(srt, 'w', encoding='utf-8') as handle:
            handle.write(sp.to_srt([Cue(0.2, 1.5, 'Hello there')]))

        def streams(path):
            probe = subprocess.run(
                ['ffprobe', '-v', 'error', '-show_entries',
                 'stream=codec_type,codec_name:stream_tags=language', '-of', 'json', path],
                capture_output=True, check=True, text=True)
            return [(s['codec_type'], s['codec_name'], s.get('tags', {}).get('language'))
                    for s in json.loads(probe.stdout)['streams']]

        soft = sp.mux_soft(clip, srt, os.path.join(folder, 'soft.mp4'), 'en')
        assert ('subtitle', 'mov_text', 'eng') in streams(soft), streams(soft)
        # An unknown language is 'und', which Matroska leaves out as its default
        mkv = sp.mux_soft(clip, srt, os.path.join(folder, 'soft.mkv'), 'xx')
        assert ('subtitle', 'subrip', None) in streams(mkv), streams(mkv)
        # A container with no text subtitles becomes Matroska
        avi = sp.mux_soft(clip, srt, os.path.join(folder, 'soft.avi'), 'en')
        assert avi.endswith('soft.mkv'), avi

        hard = sp.burn_in(clip, srt, os.path.join(folder, 'hard.mp4'))
        kinds = streams(hard)
        assert [kind for kind, _codec, _lang in kinds] == ['video', 'audio'], kinds
        assert os.path.getsize(hard) > 0


if __name__ == '__main__':
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

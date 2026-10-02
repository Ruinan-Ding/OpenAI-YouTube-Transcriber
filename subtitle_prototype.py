"""Subtitle prototype: timed cues from Whisper or YouTube, polished per cue, muxed.

A trial of the subtitle feature planned in docs/SUBTITLES_PLAN.md, kept apart
from OpenAIYouTubeTranscriber.py until the approach has held up on real videos.
It borrows the main script's AI backends and ffmpeg settings, and nothing in
the main script calls it.

    python subtitle_prototype.py "lecture.mp4" --polish api --mux soft
    python subtitle_prototype.py https://youtu.be/jNQXAC9IVRw --timing youtube --mux both

Writes <name>.srt, <name>.polished.srt when polishing, and then
"<name> - Soft Subs.<ext>" and/or "<name> - Hard Subs.mp4", into --out.
"""

from __future__ import annotations

import argparse
import difflib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import whisper
import yt_dlp
from dotenv import load_dotenv

from OpenAIYouTubeTranscriber import (FFMPEG_RUN, AIEnhancementMode,
                                      LocalModel, Provider, YouTubeTranscriber)

# Reading limits, as broadcast and streaming style guides set them
MAX_LINE = 42
MAX_LINES = 2
MAX_CUE_SECONDS = 7.0
MIN_CUE_SECONDS = 1.0
# A silence this long between words ends the cue: the next one starts with the speech
PAUSE_BREAK = 0.6
# Left between one cue and the next, so a player never shows both at once
CUE_GAP = 0.05
# How long a cue stays up after its last word, where the next leaves room
LINGER = 0.5
# YouTube times when each word starts, not when it ends; a word held longer
# than this is taken to have ended, and the silence after it to be a pause
LONGEST_WORD = 1.5

SENTENCE_END = '.!?…。！？'
CLAUSE_END = SENTENCE_END + ',;:、，；：'
# Titles whose full stop ends nothing: "Mr. Búho" is one name, not two sentences
ABBREVIATIONS = {'mr.', 'mrs.', 'ms.', 'dr.', 'st.', 'jr.', 'prof.', 'vs.',
                 'sr.', 'sra.', 'srta.', 'dra.'}

# Each cue's text container: MP4 and its kin take only mov_text, WebM only WebVTT
SUBTITLE_CODECS = {'.mp4': 'mov_text', '.m4v': 'mov_text', '.mov': 'mov_text',
                   '.mkv': 'srt', '.webm': 'webvtt'}
# Containers name a language in three letters (ISO 639-2, the bibliographic
# codes Matroska reads); Whisper and YouTube give two, which MP4 drops. Every
# language Whisper knows, and the other two-letter codes YouTube uses most;
# see _language_tag for the rest.
LANGUAGE_TAGS = dict(pair.split(':') for pair in """
    af:afr am:amh ar:ara as:asm az:aze ba:bak be:bel bg:bul bn:ben bo:tib br:bre
    bs:bos ca:cat cs:cze cy:wel da:dan de:ger el:gre en:eng es:spa et:est eu:baq
    fa:per fi:fin fo:fao fr:fre gl:glg gu:guj ha:hau he:heb hi:hin hr:hrv ht:hat
    hu:hun hy:arm id:ind is:ice it:ita ja:jpn jw:jav ka:geo kk:kaz km:khm kn:kan
    ko:kor la:lat lb:ltz ln:lin lo:lao lt:lit lv:lav mg:mlg mi:mao mk:mac ml:mal
    mn:mon mr:mar ms:may mt:mlt my:bur ne:nep nl:dut nn:nno no:nor oc:oci pa:pan
    pl:pol ps:pus pt:por ro:rum ru:rus sa:san sd:snd si:sin sk:slo sl:slv sn:sna
    so:som sq:alb sr:srp su:sun sv:swe sw:swa ta:tam te:tel tg:tgk th:tha tk:tuk
    tl:tgl tr:tur tt:tat uk:ukr ur:urd uz:uzb vi:vie yi:yid yo:yor zh:chi yue:chi
    co:cos eo:epo fy:fry ga:gle gd:gla ig:ibo in:ind iw:heb ji:yid jv:jav ku:kur
    ky:kir ny:nya or:ori rw:kin sm:smo st:sot ug:uig xh:xho zu:zul""".split())

POLISH_PROMPT = """\
You are correcting subtitles made by speech recognition. Each line of the input \
is one subtitle: its number, a "|", and its text.

Correct spelling, grammar, capitalisation and punctuation, and words the speech \
recognition misheard where the context makes the right word clear. Remove filler \
such as "um" and "uh". Keep the speaker's own wording otherwise.

The subtitles are timed to the video, so each line's words must stay on that \
line: never move a word to the line before or after it, and never merge or split \
lines, even where a sentence carries on to the next line. Keep every number. Do \
not summarise, explain or translate.

Reply with every line in the same "number|text" form, and nothing else."""


@dataclass
class Word:
    """One timed word, spelled as its source gives it: a word that follows a
    space carries it, and a Chinese or Japanese one has none."""
    start: float
    end: float
    text: str


@dataclass
class Cue:
    """One subtitle: up to MAX_LINES lines, joined by newlines."""
    start: float
    end: float
    text: str


class BatchTooLong(Exception):
    """A polish batch the backend would have cut into chunks. It cuts at
    sentence ends, which fall inside a cue's line, and a cue lost "So we"
    that way and still passed every check."""


# Timing sources

def whisper_cues(path: str, model_name: str = 'base', language: str | None = None,
                 translate: bool = False) -> tuple[list[Cue], str | None]:
    """Cues from a Whisper pass, and the language they are in.

    A transcription is timed word by word. A translation is timed by segment:
    its English words were never spoken, and Whisper itself warns that word
    timestamps on translations may not be reliable.
    """
    model = whisper.load_model(model_name)
    options = {'task': 'translate'} if translate else {}
    print(f"Transcribing {os.path.basename(path)} with Whisper {model_name}"
          f"{' (translating into English)' if translate else ''}...")
    result = model.transcribe(path, language=language, word_timestamps=not translate,
                              **options)
    segments = result.get('segments') or []
    words: list[Word] = []
    if translate:
        for segment in segments:
            words += segment_words(segment['start'], segment['end'], segment['text'])
        return build_cues(words), 'en'
    for segment in segments:
        words += tighten([Word(word['start'], word['end'], word['word'])
                          for word in segment.get('words') or []],
                         floor=words[-1].end if words else 0.0)
    return build_cues(words), result.get('language')


def tighten(words: list[Word], floor: float = 0.0) -> list[Word]:
    """One segment's Whisper word times, with the silences they swallowed
    given back.

    Whisper stretches a word over the silence beside it. After a pause, the
    segment's first words are put at its start with no length and the first
    real word runs from there - "The" at 3.88s, "cool" from 3.88 to 5.38 -
    so the cue came up a second and a half before the speech. A word longer
    than its letters account for is cut to that: from its end where nothing
    but zero-length words came before it, and otherwise from its start, so the
    silence after it reads as the pause it was.

    Nothing moves back past `floor`, where the words before this segment
    end: three words moved back from 0.15 s came out at -0.28 s, which an
    .srt cannot hold.
    """
    words = [Word(word.start, word.end, word.text) for word in words]
    for index, word in enumerate(words):
        longest = 0.25 + 0.08 * len(word.text.strip())
        if word.end - word.start <= longest:
            continue
        if all(before.end - before.start < 0.02 for before in words[:index]):
            word.start = word.end - longest
            # The words snapped to the segment's start go just ahead of it
            for step, before in enumerate(reversed(words[:index])):
                before.end = max(floor, word.start - 0.15 * step)
                before.start = max(floor, before.end - 0.15)
        else:
            word.end = word.start + longest
    return words


def segment_words(start: float, end: float, text: str) -> list[Word]:
    """A segment's words, its span shared out by their length.

    The segment's own start and end are Whisper's; the times between them are
    estimates, which is why a segment is only cut where it will not fit a cue.
    """
    pieces = [piece for piece in re.findall(r'\s*\S+', text) if piece.strip()]
    total = sum(len(piece.strip()) for piece in pieces) or 1
    words, at = [], start
    for piece in pieces:
        length = (end - start) * len(piece.strip()) / total
        words.append(Word(at, at + length, piece))
        at += length
    return words


def json3_cues(payload: str) -> list[Cue]:
    """Cues from a YouTube json3 caption track.

    YouTube's own speech recognition times every word (tOffsetMs), and those
    words are cut into cues as Whisper's are. A track somebody wrote is a cue
    per event, and that timing is kept as they set it.
    """
    events = [event for event in json.loads(payload).get('events') or []
              if event.get('segs')]
    if any('tOffsetMs' in seg for event in events for seg in event['segs']):
        return build_cues(json3_words(events))
    cues = []
    for event in events:
        text = _tidy(''.join(seg.get('utf8', '') for seg in event['segs']))
        if text:
            # Summed in milliseconds: 1.2 + 2.16 is 3.3600000000000003
            start = event.get('tStartMs', 0)
            cues.append(Cue(start / 1000, (start + event.get('dDurationMs', 0)) / 1000, text))
    # Each event is a window left open over the next; mov_text shows one at a time
    return settle(cues, hold=False)


def json3_words(events: list[dict[str, Any]]) -> list[Word]:
    """The words of YouTube's recognised captions, each with its own start.

    An event is a window that stays open while the next fills, so its duration
    says nothing about its last word: a word ends where the next one starts,
    the window closes, or LONGEST_WORD runs out, whichever is first.

    An event's first word carries no space - "to" then "love." came out
    "tolove." - so it is given the one the words before it need: a space,
    or none after Chinese or Japanese.
    """
    timed = []
    for event in events:
        begin = event.get('tStartMs', 0)
        close = begin + event.get('dDurationMs', 0)
        for seg in event['segs']:
            text = seg.get('utf8', '')
            # The '\n' events only move the rolling window up a line
            if text.strip():
                timed.append((begin + seg.get('tOffsetMs', 0), close, text))
    timed.sort(key=lambda item: item[0])
    words: list[Word] = []
    for index, (start, close, text) in enumerate(timed):
        following = timed[index + 1][0] if index + 1 < len(timed) else close
        end = min(following, close, start + LONGEST_WORD * 1000)
        if words and not text[:1].isspace():
            text = YouTubeTranscriber.rejoin(words[-1].text) + text
        words.append(Word(start / 1000, max(start, end) / 1000, text))
    return words


def vtt_cues(payload: str) -> list[Cue]:
    """Cues from a WebVTT track, timing as given; for a track with no json3."""
    cues = []
    for block in re.split(r'\n[ \t]*\n', payload.replace('\r\n', '\n').replace('\r', '\n')):
        rows = block.strip('\n').split('\n')
        timing = next((i for i, row in enumerate(rows) if '-->' in row), None)
        if timing is None or re.match(r'(NOTE|STYLE|REGION)(\s|$)', rows[0]):
            continue
        start, _, end = rows[timing].partition('-->')
        text = _tidy('\n'.join(html.unescape(re.sub(r'<[^>]*>', '', row))
                               for row in rows[timing + 1:]))
        if text:
            cues.append(Cue(_vtt_seconds(start), _vtt_seconds(end.split()[0]), text))
    return settle(cues, hold=False)


def _vtt_seconds(stamp: str) -> float:
    parts = stamp.strip().replace(',', '.').split(':')
    return float(sum(float(part) * 60 ** power for power, part in enumerate(reversed(parts))))


def _tidy(text: str) -> str:
    """Each line's spacing made single, and empty lines dropped."""
    return '\n'.join(' '.join(line.split()) for line in text.split('\n') if line.strip())


# Cutting words into cues

def build_cues(words: list[Word]) -> list[Cue]:
    """Timed words cut into readable cues.

    A cue ends at a pause, at MAX_CUE_SECONDS, or where its text would not
    fit MAX_LINES lines of MAX_LINE; a full cue is cut back to its last
    sentence end, or its last clause end a third in (_clause_cut). A sentence
    that ends with the cue at least a third full closes it too, so cues
    start where sentences do.
    """
    cues: list[Cue] = []
    current: list[Word] = []
    capacity = MAX_LINE * MAX_LINES

    def emit(words_in_cue: list[Word]) -> None:
        text = _text(words_in_cue)
        if text:
            cues.append(Cue(words_in_cue[0].start, words_in_cue[-1].end, split_lines(text)))

    for word in words:
        if not word.text.strip():
            continue
        if current:
            paused = word.start - current[-1].end >= PAUSE_BREAK
            too_long = (not fits(_text(current + [word]))
                        or word.end - current[0].start > MAX_CUE_SECONDS)
            sentence_done = (_ends(current[-1].text, SENTENCE_END)
                             and len(_text(current)) >= capacity / 3)
            if paused or sentence_done:
                emit(current)
                current = []
            elif too_long:
                cut = _clause_cut(current)
                emit(current[:cut])
                current = current[cut:]
                # What is left fitted with the words cut off, but not always with
                # this one too: "Yes." cut off left a 49-character line
                if current and (not fits(_text(current + [word]))
                                or word.end - current[0].start > MAX_CUE_SECONDS):
                    emit(current)
                    current = []
        current.append(word)
    if current:
        emit(current)
    return settle(cues)


def _text(words: list[Word]) -> str:
    return ' '.join(''.join(word.text for word in words).split())


def _ends(text: str, marks: str) -> bool:
    """Whether text ends on one of marks, a title's full stop aside."""
    last = (text.split() or [''])[-1]
    return last[-1:] in marks and last.lower() not in ABBREVIATIONS


def _clause_cut(words: list[Word]) -> int:
    """Where to end a cue that is full: after its last sentence end, or else
    after its last clause end at least a third in, or else after all of it.

    Asking either for half the cue cut "...bajo la sombra de un" / "árbol a
    descansar." past an earlier sentence end, and left "tortuga." alone in
    a cue of its own after "...de la liebre y la".
    """
    for marks, share in ((SENTENCE_END, 0.0), (CLAUSE_END, 1 / 3)):
        for index in range(len(words) - 1, 0, -1):
            if (_ends(words[index - 1].text, marks)
                    and len(_text(words[:index])) >= len(_text(words)) * share):
                return index
    return len(words)


def _width(text: str) -> int:
    """How wide text shows: a full-width character (Chinese, Japanese, Korean)
    takes two columns. Counted as one, a line held 42 of them, two and a half
    times what a CJK subtitle line holds."""
    return sum(2 if unicodedata.east_asian_width(char) in 'WF' else 1 for char in text)


def fits(text: str) -> bool:
    """Whether text fits a cue's MAX_LINES (two) lines of MAX_LINE columns.

    Not its width against twice MAX_LINE: a line breaks only at a space, and
    84 characters with none at the 42nd made a line of 44.
    """
    text = ' '.join(text.split())
    if _width(text) <= MAX_LINE:
        return True
    if ' ' not in text:
        return _width(text) <= MAX_LINE * MAX_LINES
    return any(_width(text[:index]) <= MAX_LINE and _width(text[index + 1:]) <= MAX_LINE
               for index, char in enumerate(text) if char == ' ')


def split_lines(text: str) -> str:
    """One cue's text on as few lines as fit MAX_LINE, broken near the middle.

    A break after punctuation is taken over one a few characters nearer the
    middle. Text with no spaces (Chinese, Japanese) is cut at the middle.
    """
    text = ' '.join(text.split())
    if _width(text) <= MAX_LINE:
        return text
    spaces = [index for index, char in enumerate(text) if char == ' ']
    if not spaces:
        middle = next(index for index in range(len(text))
                      if _width(text[:index + 1]) * 2 >= _width(text))
        return text[:middle + 1] + '\n' + text[middle + 1:]

    def cost(index: int) -> float:
        left, right = _width(text[:index]), _width(text[index + 1:])
        overflow = max(left, right) > MAX_LINE
        punctuated = _ends(text[:index], CLAUSE_END)
        return abs(left - right) - (8 if punctuated else 0) + (1000 if overflow else 0)

    best = min(spaces, key=cost)
    return text[:best] + '\n' + text[best + 1:]


def settle(cues: list[Cue], hold: bool = True) -> list[Cue]:
    """Each cue held LINGER past its last word and for at least
    MIN_CUE_SECONDS, where the next leaves room, and none overlapping the next.

    `hold=False` only ends each cue before the next: timing someone wrote is
    kept as written otherwise.
    """
    for index, cue in enumerate(cues):
        limit = cues[index + 1].start - CUE_GAP if index + 1 < len(cues) else None
        end = max(cue.end + LINGER, cue.start + MIN_CUE_SECONDS) if hold else cue.end
        if limit is not None:
            end = min(end, limit)
        cue.end = max(end, cue.start + 0.01)
    return cues


# Polish: the text corrected, the timing left alone

def polish_cues(cues: list[Cue], ask: Callable[[str, str], str],
                batch: int = 40) -> tuple[list[Cue], Counter[str]]:
    """Each cue's text corrected by a model, its timing untouched.

    `ask(prompt, text)` is the model, which raises when it fails. Cues go in
    numbered batches, enough for it to read whole sentences, and in smaller
    ones from the first the backend would have cut (BatchTooLong). A cue the
    reply leaves out, moves words into or out of, or rewrites into words it
    was not, keeps its own text; returns the cues and how many of each
    outcome there were, a batch that failed counting as 'failed'.
    """
    result = list(cues)
    outcomes: Counter[str] = Counter()
    first = 0
    while first < len(cues):
        group = {first + offset + 1: _one_line(cue.text)
                 for offset, cue in enumerate(cues[first:first + batch])}
        numbered = '\n'.join(f'{number}|{text}' for number, text in group.items())
        first += len(group)
        try:
            reply = ask(POLISH_PROMPT, numbered)
        except BatchTooLong:
            if batch > 1:
                first -= len(group)
                batch //= 2
                continue
            print(f"  Polish failed for cue {first}: too long for one request.")
            outcomes['failed'] += 1
            continue
        except Exception as e:  # a backend's own failure, whatever its library raises
            print(f"  Polish failed for cues {first - len(group) + 1}-{first}: {e}")
            outcomes['failed'] += len(group)
            continue
        answers = parse_numbered(reply)
        moved = moved_cues(group, answers)
        for number, text in group.items():
            cue, new = cues[number - 1], answers.get(number)
            if new is None:
                outcomes['missing'] += 1
            elif new == text:
                outcomes['unchanged'] += 1
            elif number in moved or not acceptable(text, new) or not fits(new):
                outcomes['rejected'] += 1
            else:
                result[number - 1] = Cue(cue.start, cue.end, split_lines(new))
                outcomes['polished'] += 1
    return result, outcomes


def moved_cues(originals: dict[int, str], answers: dict[int, str]) -> set[int]:
    """The cues a reply moved words into or out of.

    The batch's words, before and after, are matched as one run, each word
    knowing its cue. A word matched from one cue into another was moved
    across a cue boundary, and would show before or after it was said: both
    cues are refused. Matched one cue at a time, a cue that took the next
    one's words could still pass for a fix.
    """
    before = [(word, number) for number, text in originals.items() for word in _words(text)]
    after = [(word, number) for number, text in sorted(answers.items())
             if number in originals for word in _words(text)]
    matcher = difflib.SequenceMatcher(a=[word for word, _ in before],
                                      b=[word for word, _ in after], autojunk=False)
    moved: set[int] = set()
    for block in matcher.get_matching_blocks():
        for step in range(block.size):
            source, target = before[block.a + step][1], after[block.b + step][1]
            if source != target:
                moved.update((source, target))
    return moved


def parse_numbered(reply: str) -> dict[int, str]:
    """A reply's "number|text" lines by number. A number given twice is
    dropped: which of the two is the cue's cannot be told."""
    found: dict[int, str] = {}
    twice: set[int] = set()
    for line in reply.splitlines():
        match = re.match(r'\s*(\d+)\s*\|\s?(.*)$', line)
        if not match:
            continue
        number = int(match[1])
        if number in found:
            twice.add(number)
        found[number] = ' '.join(match[2].split())
    return {number: text for number, text in found.items() if number not in twice and text}


def acceptable(original: str, polished: str) -> bool:
    """Whether a polished cue is still the cue that was said.

    Compared word by word without case, accents or apostrophes, as the main
    script checks a refinement. Dropping filler and fixing a misheard word
    lose a word or two; a rewritten cue loses more than a third of its words.
    A fix can add more than it loses - "one of" heard for "in front of" - so
    up to half the cue's length may be new.
    """
    before, after = _words(original), _words(polished)
    if not after:
        return False
    matcher = difflib.SequenceMatcher(a=before, b=after, autojunk=False)
    kept = sum(block.size for block in matcher.get_matching_blocks())
    return (len(before) - kept <= max(2, -(-len(before) // 3))
            and len(after) - kept <= max(2, -(-len(before) // 2)))


def _words(text: str) -> list[str]:
    text = unicodedata.normalize('NFKD', text.lower().replace("'", '').replace('’', ''))
    text = ''.join(char for char in text if not unicodedata.combining(char))
    return re.findall(r'[\u3040-\u30ff\u3400-\u9fff]|[^\W_]+', text)


def _one_line(text: str) -> str:
    return ' '.join(text.split())


def ai_asker(backend: str, local_model: str | None = None) -> Callable[[str, str], str]:
    """The main script's AI backend as `ask(prompt, text)`, set up as it sets
    it up: config.txt's AI_PROVIDER, API_KEY, MODEL and BASE_URL, or the key
    the vendor's own tools read."""
    transcriber = YouTubeTranscriber()
    config = os.path.join(transcriber.PROFILE_DIR, transcriber.CONFIG_ENV)
    if os.path.exists(config):
        load_dotenv(config, override=True)
    if backend == 'local':
        model = local_model or LocalModel.default().hf_model_id
        return _one_request(transcriber, lambda prompt, text: transcriber.enhance_text(
            text, AIEnhancementMode.LOCAL, prompt, local_model=model, keeps='words'))
    provider = Provider.from_string(os.getenv('AI_PROVIDER')) or Provider.default()
    api_key = provider.resolve_api_key()
    if not api_key:
        raise SystemExit(f"No API key for {provider.key}: set API_KEY in {config}, "
                         f"or {provider.vendor_key_env}.")
    return _one_request(transcriber, lambda prompt, text: transcriber.enhance_text(
        text, AIEnhancementMode.API, prompt, api_key=api_key, provider=provider))


def _one_request(transcriber: YouTubeTranscriber,
                 enhance: Callable[[str, str], str]) -> Callable[[str, str], str]:
    """`enhance` made to send a batch in one request, and to raise when it fails.

    The main script's backends cut text into chunks and hand back the input
    for any chunk that fails, so a bad key or a cut-off reply read as forty
    cues with nothing to fix. They all send their chunks through
    _run_chunked_enhancement, which this replaces for the call.
    ponytail: overrides a private method; at the port, give the backends a
    single-request mode instead.
    """
    def ask(prompt: str, text: str) -> str:
        sent: list[str] = []

        def one(chunks: list[str], label: str, call_chunk: Callable[[str], str],
                seams: list[str] | None = None) -> str:
            if len(chunks) > 1:
                raise BatchTooLong(f"{label} would send it in {len(chunks)} chunks")
            reply = call_chunk(chunks[0])
            if not reply:
                raise RuntimeError(f"{label} sent nothing usable back (see above)")
            sent.append(reply)
            return reply

        transcriber._run_chunked_enhancement = one  # type: ignore[method-assign,assignment]
        try:
            reply = enhance(prompt, text)
        finally:
            del transcriber._run_chunked_enhancement
        if not sent:
            raise RuntimeError("the AI backend did not run (see above)")
        return reply
    return ask


# Writing and muxing

def to_srt(cues: list[Cue]) -> str:
    return ''.join(f'{number}\n{_srt_time(cue.start)} --> {_srt_time(cue.end)}\n{cue.text}\n\n'
                   for number, cue in enumerate(cues, start=1))


def _srt_time(seconds: float) -> str:
    hours, rest = divmod(round(seconds * 1000), 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    whole, millis = divmod(rest, 1000)
    return f'{hours:02}:{minutes:02}:{whole:02},{millis:03}'


def mux_soft(video: str, srt: str, output: str, language: str | None) -> str | None:
    """The video with the cues as a track a player can switch off.

    Every stream is copied, the video's own subtitles, fonts and chapters
    among them, so this takes seconds and loses nothing. The new track is
    the default only where the video had no subtitles of its own. A
    container that holds no text subtitles is reported and left alone.
    """
    codec = SUBTITLE_CODECS.get(os.path.splitext(output)[1].lower())
    if codec is None:
        print(f"{os.path.basename(output)}: this container holds no subtitle track; "
              f"use the .srt beside it.")
        return None
    # The new track comes after the video's own, and is numbered after them
    new = _subtitle_streams(video)
    base = ['ffmpeg', '-y', '-v', 'error', '-i', video, '-i', srt, '-map', '0']
    tail = ['-map', '1:0', '-c', 'copy', f'-c:s:{new}', codec,
            f'-metadata:s:s:{new}', f'language={_language_tag(language)}',
            f'-disposition:s:{new}', '0' if new else 'default', output]
    # A data stream (a timecode) the container cannot take is the one thing
    # worth leaving out to get the track in
    attempts = [base + tail, base + ['-map', '-0:d?'] + tail]
    return _run_ffmpeg(attempts, output, 'add the subtitle track')


def _subtitle_streams(video: str) -> int:
    try:
        probe = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 's',
                                '-show_entries', 'stream=index', '-of', 'csv=p=0', video],
                               capture_output=True, text=True, check=True, **FFMPEG_RUN)
    except (subprocess.CalledProcessError, OSError):
        return 0
    return len(probe.stdout.split())


def _language_tag(language: str | None) -> str:
    """A container's three-letter code for a Whisper or YouTube language:
    'en' and 'en-US' are 'eng'. A three-letter code is one already ('fil',
    'haw'); anything else is 'und', undetermined."""
    base = (language or '').split('-')[0].lower()
    return LANGUAGE_TAGS.get(base) or (base if len(base) == 3 and base.isalpha() else 'und')


def burn_in(video: str, srt: str, output: str,
            style: str = 'FontSize=22,Outline=2') -> str | None:
    """The video with the cues drawn into the picture: a full re-encode.

    The subtitles filter reads its file name inside the filter's own syntax,
    where a drive's colon, a backslash or a quote has to be escaped. ffmpeg
    runs beside a copy of the cues with a plain name instead.
    """
    with tempfile.TemporaryDirectory() as folder:
        shutil.copyfile(srt, os.path.join(folder, 'subs.srt'))
        # 8-bit 4:2:0: a 10-bit source burned to High 10 H.264, which
        # Windows' own player cannot play
        base = ['ffmpeg', '-y', '-v', 'error', '-i', os.path.abspath(video),
                '-map', '0:v:0', '-map', '0:a?',
                '-vf', f"subtitles=subs.srt:force_style='{style}'",
                '-c:v', 'libx264', '-crf', '18', '-preset', 'medium', '-pix_fmt', 'yuv420p']
        target = os.path.abspath(output)
        # The audio copied where MP4 plays it (not Opus), re-encoded where not
        audio = YouTubeTranscriber.stream_codec(video, 'audio')
        attempts = [base + ['-c:a', 'aac', target]]
        if audio is None or YouTubeTranscriber.audio_plays_in(audio, 'mp4'):
            attempts.insert(0, base + ['-c:a', 'copy', target])
        return _run_ffmpeg(attempts, output, 'burn in the subtitles', cwd=folder)


def _run_ffmpeg(attempts: list[list[str]], output: str, what: str,
                cwd: str | None = None) -> str | None:
    last = ''
    for command in attempts:
        try:
            subprocess.run(command, capture_output=True, check=True, cwd=cwd, **FFMPEG_RUN)
        except subprocess.CalledProcessError as e:
            last = e.stderr or ''
            continue
        except OSError as e:
            last = str(e)
            break
        if os.path.exists(output) and os.path.getsize(output):
            return output
        last = 'ffmpeg reported success but wrote nothing'
    print(f"Could not {what}: {last[-300:]}", file=sys.stderr)
    if os.path.exists(output):
        os.remove(output)
    return None


# Fetching a YouTube video and its captions

def fetch_youtube(url: str, folder: str, captions: bool,
                  language: str | None) -> tuple[str, list[Cue] | None, str | None]:
    """Download a video, and its caption cues when asked: a track somebody
    wrote in the language asked for (or the video's own) if there is one,
    else YouTube's recognition of the language spoken."""
    options = dict(YouTubeTranscriber.YDL_OPTS, quiet=True, no_warnings=True, noprogress=True,
                   format='bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b',
                   merge_output_format='mp4', windowsfilenames=True,
                   outtmpl={'default': os.path.join(folder, '%(title).80s.%(ext)s')})
    print(f"Downloading {url}...")
    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=True)
        video = ydl.prepare_filename(info)
    if not os.path.exists(video):
        video = os.path.splitext(video)[0] + '.mp4'
    if not captions:
        return video, None, None

    wanted = (language or info.get('language') or '').split('-')[0]
    # live_chat is a stream's chat replay, filed with the subtitles
    written = [key for key in info.get('subtitles') or {} if key != 'live_chat']
    # The original recognition, not YouTube's machine translations of it
    recognised = [key for key, tracks in (info.get('automatic_captions') or {}).items()
                  if tracks and 'tlang=' not in (tracks[0].get('url') or '')]

    def in_wanted(keys: list[str]) -> str | None:
        return next((key for key in keys if wanted and key.split('-')[0] == wanted), None)

    key = (in_wanted(written) or in_wanted(recognised)
           or next(iter(recognised), None) or next(iter(written), None))
    if key is None:
        print("This video has no captions to time subtitles from.")
        return video, None, None
    with tempfile.TemporaryDirectory() as scratch:
        options = dict(YouTubeTranscriber.YDL_OPTS, quiet=True, no_warnings=True,
                       skip_download=True, writesubtitles=True, writeautomaticsub=True,
                       subtitleslangs=[key], subtitlesformat='json3/vtt',
                       outtmpl={'default': os.path.join(scratch, 'captions.%(ext)s')})
        with yt_dlp.YoutubeDL(options) as ydl:
            ydl.process_ie_result(ydl.sanitize_info(info), download=True)
        files = sorted(os.listdir(scratch))
        if not files:
            return video, None, None
        with open(os.path.join(scratch, files[0]), encoding='utf-8') as handle:
            payload = handle.read()
    kind = 'written' if key in written else 'recognised'
    print(f"Timing from YouTube's {kind} captions ({key}, {os.path.splitext(files[0])[1]}).")
    cues = json3_cues(payload) if files[0].endswith('.json3') else vtt_cues(payload)
    return video, cues, key.split('-')[0]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('source', help='a media file, or a YouTube URL')
    parser.add_argument('--timing', choices=('whisper', 'youtube'), default='whisper',
                        help="where the times come from (youtube: the video's captions)")
    parser.add_argument('--model', default='base', help='Whisper model (default: base)')
    parser.add_argument('--language', help="the spoken language, e.g. 'en'; detected if not given")
    parser.add_argument('--translate', action='store_true',
                        help="Whisper's English translation, timed by segment")
    parser.add_argument('--polish', choices=('off', 'api', 'local'), default='off',
                        help="correct each cue's text with the main script's AI backend")
    parser.add_argument('--local-model', help='Hugging Face model for --polish local')
    parser.add_argument('--mux', choices=('none', 'soft', 'hard', 'both'), default='soft')
    parser.add_argument('--out', default=os.path.join(YouTubeTranscriber.VIDEO_DIR, 'Subtitled'),
                        help='where to write (default: %(default)s)')
    args = parser.parse_args(argv)

    os.makedirs(args.out, exist_ok=True)
    is_url = re.match(r'https?://', args.source) is not None
    cues: list[Cue] | None = None
    language = args.language
    if is_url:
        video, cues, caption_language = fetch_youtube(
            args.source, args.out, args.timing == 'youtube', args.language)
        language = caption_language or language
    else:
        video = args.source
        if args.timing == 'youtube':
            parser.error("--timing youtube needs a YouTube URL")
    if args.timing == 'whisper':
        cues, language = whisper_cues(video, args.model, args.language, args.translate)
    if not cues:
        print("No timed text found: no subtitles to write.")
        return 1

    stem = os.path.join(args.out, os.path.splitext(os.path.basename(video))[0])
    srt = stem + '.srt'
    with open(srt, 'w', encoding='utf-8') as handle:
        handle.write(to_srt(cues))
    print(f"{len(cues)} cues written to {srt}")

    if args.polish != 'off':
        cues, outcomes = polish_cues(cues, ai_asker(args.polish, args.local_model))
        srt = stem + '.polished.srt'
        with open(srt, 'w', encoding='utf-8') as handle:
            handle.write(to_srt(cues))
        summary = ', '.join(f'{count} {outcome}' for outcome, count in sorted(outcomes.items()))
        print(f"Polished cues written to {srt} ({summary})")

    if args.mux in ('soft', 'both'):
        done = mux_soft(video, srt, f'{stem} - Soft Subs{os.path.splitext(video)[1]}', language)
        if done:
            print(f"Soft subtitles: {done}")
    if args.mux in ('hard', 'both'):
        done = burn_in(video, srt, f'{stem} - Hard Subs.mp4')
        if done:
            print(f"Hard subtitles: {done}")
    return 0


if __name__ == '__main__':
    sys.exit(main())

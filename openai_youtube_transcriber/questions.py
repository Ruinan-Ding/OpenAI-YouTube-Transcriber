"""The menus and typed answers a session's settings are asked with."""

import os

from .common import DownloadFailed, Resolution, YesNo, _is_number, error


def _menu_default(options, default):
    """Which listed option Enter lands on, for the prompt to name: the best
    available, or the cheapest where the field asks for it. Shared, so the two
    menus cannot drift apart.
    """
    return options[-1 if default == Resolution.LOWEST.value else 0]


def _valid_entries(transcriber, text, resolve_one):
    """Walk a list answer entry by entry, keeping what resolves.

    A prompt takes the same comma- or space-separated lists the matching
    profile field does, and means the same thing by them: each entry is a
    deliverable of its own. An entry that does not resolve prints its own
    reason and is dropped, so only an answer with nothing usable left in it
    asks again.
    """
    values = []
    for piece in transcriber.split_entries(text):
        value = resolve_one(piece)
        if value and value not in values:
            values.append(value)
    return values


def _prompt_resolution_selection(transcriber, info, default=Resolution.HIGHEST.value):
    """List a video's available resolutions and let the user pick one.

    Ends the pass if the video has no video streams; the rest of a batch of
    sources still runs.
    """
    available_resolutions = transcriber.available_resolutions(info)

    if not available_resolutions:
        error("Error: no video streams found.")
        raise DownloadFailed("no video streams")

    fallback = _menu_default(available_resolutions, default)
    print("Available resolutions:")
    for i, res in enumerate(available_resolutions):
        print(f"{i+1}. {res}")

    def pick(entry):
        """One listed resolution, by number or by name."""
        if _is_number(entry) and 1 <= int(entry) <= len(available_resolutions):
            return available_resolutions[int(entry) - 1]
        if entry in available_resolutions:
            return entry
        if _is_number(entry) and entry + "p" in available_resolutions:
            return entry + "p"
        print("Invalid input. Please enter a valid number or resolution.")
        return None

    while True:
        user_input = input(
            f"Enter desired resolution (number or resolution, or several separated "
            f"by commas or spaces, default {fallback}): ").strip().lower()
        if not user_input:
            # The keyword, not the height it lands on here: recorded as 240p, a
            # profile made from this session fetched 240p of the next video
            return default
        chosen = _valid_entries(transcriber, user_input, pick)
        if chosen:
            return ",".join(chosen)


def _prompt_audio_selection(transcriber, info, default=Resolution.HIGHEST.value):
    """List a video's available audio tiers and let the user pick one.

    `default` is what Enter takes: transcription wants the cheapest stream,
    every other download wants the best.
    """
    available = transcriber.available_audio_qualities(info)
    if not available:
        print("No audio streams found. Using the best available.")
        return Resolution.HIGHEST.value
    fallback = _menu_default(available, default)

    print("Available audio resolutions:")
    for i, tier in enumerate(available):
        # The tier's own headline bitrate is not what gets downloaded, so show
        # the bitrate of the stream this choice actually selects
        bitrate = transcriber.selected_bitrate(tier, info)
        print(f"{i+1}. {tier}" + (f" ({bitrate}k)" if bitrate else ""))

    def pick(entry):
        """One listed tier, by number or name, or a bitrate in kbps."""
        if _is_number(entry) and 1 <= int(entry) <= len(available):
            return available[int(entry) - 1]
        if entry in available:
            return entry
        # The menu prints bitrates as "60k", so take that back as readily as 60
        if entry.endswith('k') and _is_number(entry[:-1]):
            entry = entry[:-1]
        # A number past the end of the list is a bitrate, not a menu choice
        if _is_number(entry):
            return entry
        print("Invalid input. Please enter a valid number or audio resolution.")
        return None

    while True:
        user_input = input(
            f"Enter desired audio resolution (number, name, or a bitrate in kbps, or "
            f"several separated by commas or spaces; default {fallback}): "
        ).strip().lower()
        if not user_input:
            return default
        chosen = _valid_entries(transcriber, user_input, pick)
        if chosen:
            return ",".join(chosen)


def _prompt_audio_resolution_input(transcriber, label):
    """Prompt for a desired audio resolution (tier name, kbps, or fetch keyword).

    An empty answer returns "", which the caller resolves by showing the list
    of what the video actually offers.
    """
    def one(entry):
        quality = Resolution.normalize(entry)
        # A tier name is checked against the video's own list later, which
        # re-prompts if the video does not offer it
        if quality in Resolution.values() or quality.isalnum():
            return quality
        print("Invalid input. Enter a tier name, a bitrate, highest, lowest, or fetch.")
        return None

    while True:
        answer = input(
            f"Enter the desired {label} (e.g., low, medium, 64, highest, lowest, or "
            f"several separated by commas or spaces), "
            f"or press Enter or type fetch to choose from a list: "
        ).strip()
        if not answer:
            return ""
        chosen = _valid_entries(transcriber, answer, one)
        if chosen:
            return ",".join(chosen)


def _prompt_resolution_input(transcriber, label):
    """Prompt for a desired resolution (name, number, or fetch keyword).

    An empty answer returns "", which the caller resolves by showing the list
    of what the video actually offers.
    """
    def one(entry):
        resolution = Resolution.normalize(entry)
        if resolution in Resolution.values():
            return resolution
        if resolution.endswith("p") and _is_number(resolution[:-1]) and int(resolution[:-1]) > 0:
            return resolution
        if _is_number(resolution):
            if int(resolution) > 0:
                return resolution + "p"
            print("Invalid resolution. Please enter a non-zero number.")
        else:
            print("Invalid resolution. Please enter a valid resolution "
                  "(e.g., 720p, 720, highest, lowest).")
        return None

    while True:
        answer = input(
            f"Enter the desired {label} (e.g., 720p, 720, highest, lowest, or several "
            f"separated by commas or spaces), "
            f"or press Enter or type fetch to choose from a list: "
        ).strip()
        if not answer:
            return ""
        chosen = _valid_entries(transcriber, answer, one)
        if chosen:
            return ",".join(chosen)


def _prompt_format(transcriber, label, default, kind):
    """Ask for an output format, listing everything this ffmpeg can write."""
    choices = transcriber.ffmpeg_formats(kind)
    print(f"\nAvailable {label} formats ({len(choices)} from ffmpeg):")
    if choices:
        width = max(len(name) for name in choices) + 2
        per_row = max(1, 78 // width)
        for start in range(0, len(choices), per_row):
            print("  " + "".join(n.ljust(width) for n in choices[start:start + per_row]))
    print(f"  {transcriber.FORMAT_ORIGINAL} - keep what YouTube served, no re-encode")
    if kind == 'container':
        print("  (a muxer named after its standard writes its own extension: "
              "matroska gives .mkv)")

    while True:
        answer = input(
            f"Enter the {label} format, or several separated by commas or spaces for "
            f"one file each, or press Enter for {default} "
            f"(re-encodes if it is not already {default}): ").strip().lower()
        if not answer:
            return default
        chosen = _format_entries(transcriber, answer, default, kind)
        if chosen:
            return ",".join(chosen)
        print("Pick a name from the list above.")


def _writes_a_file(transcriber, name, kind):
    """Whether a container name names something with a file extension.

    ffmpeg's muxer list includes sinks like "null" that write no file, and the
    name chosen here becomes the extension of a deliverable.
    """
    return kind != 'container' or transcriber.format_extension(name) is not None


def _format_entries(transcriber, raw, default, kind):
    """The formats a list answer asks for that this ffmpeg can actually write.

    Several formats, separated by commas or spaces, are several files: the
    deliverable is written in each of them. One this ffmpeg cannot write is
    named and dropped; the caller decides what an empty result means.
    """
    def one(piece):
        # ".mp3" is how a person writes a format, and no name ffmpeg reports
        # starts with a dot, so there is nothing for this to shadow
        piece = piece.lstrip(".")
        if piece == transcriber.FORMAT_DEFAULT:
            piece = default
        if piece in (transcriber.FORMAT_ORIGINAL, default):
            return piece
        if piece not in transcriber.ffmpeg_formats(kind):
            print(f"ffmpeg cannot write '{piece}'.")
            return None
        if not _writes_a_file(transcriber, piece, kind):
            print(f"ffmpeg's '{piece}' does not write a media file.")
            return None
        return piece

    return _valid_entries(transcriber, (raw or "").lower(), one)


def _resolve_format(transcriber, raw, label, default, kind):
    """Settle one format field. Blank asks; DEFAULT and Enter mean `default`.

    Only an answer with nothing usable left in it asks again.
    """
    values = _format_entries(transcriber, raw, default, kind)
    if values:
        return ",".join(values)
    return _prompt_format(transcriber, label, default, kind)


def _writable_dir(transcriber, path):
    """True if `path` is a directory this run can write into, saying so if not."""
    if not transcriber.ensure_directory_exists(path):
        return False
    if not os.access(path, os.W_OK):
        error(f"Error: cannot write to {path}.")
        return False
    return True


def _prompt_rename(label):
    """Ask what to call a deliverable. Enter keeps the source's own title."""
    return input(f"Rename {label}? Enter a name, or press Enter to keep the "
                 f"title: ").strip()


def _resolve_rename(transcriber, raw, label):
    """The stem to write a deliverable under, or "" for the source's own title.

    A name in the field is used as it stands, so a profile carrying one still
    runs unattended; `y` and a blank answer ask for a name; `n` leaves the
    title alone, as Enter at that question does. SETTINGS says what a field
    that is not there means. The quality and format tags are still appended,
    so the several files one answer can produce stay distinct.
    """
    answer = raw.strip()
    # 's' and 'skip' decline as 'n' does, as they do everywhere else; taken as
    # a name, TRANSCRIPT_RENAME=skip called every transcript "skip"
    if answer.lower() in YesNo.all_no_and_skip():
        return ""
    if answer and answer.lower() not in YesNo.YES.value:
        return transcriber.sanitize_filename(answer)
    typed = _prompt_rename(label)
    return transcriber.sanitize_filename(typed) if typed else ""


def _prompt_path(transcriber, label, default_dir):
    """Ask where to write a deliverable. Enter keeps the project's own folder."""
    while True:
        answer = os.path.expanduser(
            input(f"Where should {label} be written? Enter an absolute path, "
                  f"or press Enter for {default_dir}: ").strip().strip('"'))
        if not answer:
            return ""
        if not os.path.isabs(answer):
            print("That is not an absolute path. Enter one, or press Enter to "
                  "keep the default.")
        elif _writable_dir(transcriber, answer):
            return answer


def _resolve_path(transcriber, raw, label, default_dir):
    """The directory to write a deliverable into, or "" for the project's own.

    A path in the field is used as it stands, so a profile carrying one still
    runs unattended; `y` and a blank answer ask for one; `n` keeps the default
    folder. Absolute is os.path.isabs, so a drive letter counts as readily as a
    leading slash. A path that cannot be written is refused here rather than
    after the download that would have filled it.
    """
    answer = raw.strip().strip('"')
    if answer.lower() in YesNo.all_no_and_skip():
        return ""
    if answer and answer.lower() not in YesNo.YES.value:
        # ~/Transcripts is absolute once expanded, as a source path already is
        answer = os.path.expanduser(answer)
        if os.path.isabs(answer) and _writable_dir(transcriber, answer):
            return answer
        error(f"Error: '{answer}' is not an absolute path this run can write to.")
        return _prompt_path(transcriber, label, default_dir)
    return _prompt_path(transcriber, label, default_dir)

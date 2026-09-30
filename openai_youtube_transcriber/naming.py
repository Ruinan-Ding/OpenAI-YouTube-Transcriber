"""What each file of a batch is called, so that no two land on one name."""

import itertools
import os


def _claim_name(cfg, base, identity, video_id=None):
    """The name one source's files are written under, its own across the batch.

    Two videos can share a title, two titles can clean to one name, and two
    local files in different folders share a basename: downloads overwrite, so
    the second source's files replaced the first's. The video's ID tells a
    video apart, and a number anything else. The same source named twice keeps
    the one name - that is a repeat, not a collision.
    """
    candidates = itertools.chain(
        [base], [f"{base} [{video_id}]"] if video_id else [],
        (f"{base} ({n})" for n in itertools.count(2)))
    for candidate in candidates:
        # Casefolded: Windows and macOS file systems do not tell "A" from "a"
        if cfg.claimed_names.setdefault(candidate.casefold(), identity) == identity:
            return candidate
    return base  # unreachable: the numbered names never run out


def _source_identity(cfg):
    """What one source is, however it was written: a video by its ID, a file by
    where it really is."""
    if cfg.is_local_file:
        return _path_identity(cfg.url)
    return (cfg.info or {}).get('id') or cfg.url


def _path_identity(path):
    """A file source's identity: where it really is, as the file system compares."""
    return os.path.normcase(os.path.realpath(os.path.expanduser(path)))


def _file_key(path):
    """Where a path puts its file, to tell two paths to one file apart.

    The folder is resolved through symlinks, and the name compared without
    regard to case, which Windows and macOS do not tell apart. Treating two
    names that differ only in case as one file costs a suffix at worst.
    """
    folder, name = os.path.split(os.path.abspath(os.path.expanduser(path)))
    return os.path.normcase(os.path.realpath(folder)), name.casefold()


# The deliverable a batch source holds its own path as, until it is read
_SOURCE = "source"


def _reserve_sources(cfg):
    """Hold every file source of the batch, so no pass writes over one still to come.

    A refinement named onto the next queued transcript, or a Whisper transcript
    onto a queued one of the same name, replaced it before it was read.
    """
    cfg.taken = {}
    for url, is_local, refine in cfg.sources or []:
        for path in refine or ([url] if is_local else []):
            cfg.taken[_file_key(path)] = (_path_identity(path), _SOURCE)


def _take_path(cfg, path, what, discriminator=None):
    """The path one deliverable is written to: `path`, unless the batch has
    given it to another.

    The one place every deliverable's name is settled, so that none is written
    over another: the merged video and the audio in one folder and container,
    two outputs whose folders are one through a symlink, a refinement and the
    transcript queued after it. The same deliverable of the same source keeps
    its path - a source named twice is a repeat - and a source's own outputs
    may land on the source itself. Otherwise `discriminator` is tried, then a
    number.
    """
    owner = (cfg.identity, what)
    stem, ext = os.path.splitext(path)
    variants = itertools.chain(
        [path], [f"{stem}{discriminator}{ext}"] if discriminator else [],
        (f"{stem} ({n}){ext}" for n in itertools.count(2)))
    for candidate in variants:
        key = _file_key(candidate)
        holder = cfg.taken.get(key)
        if holder in (None, owner, (cfg.identity, _SOURCE)):
            cfg.taken[key] = owner
            return candidate
    return path  # unreachable: the numbered names never run out

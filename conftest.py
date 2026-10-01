"""pytest setup for test_transcriber.py.

The tests stand in for the network, ffmpeg's failures and the console by
swapping module attributes, input() and environment variables, and put them
back in a finally. A test that fails before its finally ran, or forgets one,
used to leave its stand-in for every test after it. Here everything they touch
is restored after each test, whatever happened in it.

The tests still run without pytest: `python test_transcriber.py`.
"""

import builtins
import getpass
import os
import subprocess
import sys
import types

import pytest
import setuptools
import whisper
import yt_dlp

import OpenAIYouTubeTranscriber

# What the tests patch: whole modules, and the classes whose methods they swap
PATCHED = (OpenAIYouTubeTranscriber, OpenAIYouTubeTranscriber.YouTubeTranscriber,
           whisper, yt_dlp, yt_dlp.YoutubeDL, subprocess, getpass, setuptools)
# Modules the tests replace in sys.modules with stand-ins for the AI backends
STAND_INS = ('openai', 'anthropic', 'transformers')


def _restore(owner, before):
    after = vars(owner)
    for name, value in list(after.items()):
        # A submodule imported during the test is an attribute of its package
        # from then on, and removing it would break the next import of it
        if name not in before and not isinstance(value, types.ModuleType):
            delattr(owner, name)
    for name, value in before.items():
        if after.get(name) is not value:
            setattr(owner, name, value)


@pytest.fixture(autouse=True)
def restore_global_state():
    """Snapshot what the tests patch, and put it all back afterwards."""
    attributes = [(owner, dict(vars(owner))) for owner in PATCHED]
    # The console: the script reads the builtin, so that is what is answered
    real_input = builtins.input
    environment = dict(os.environ)
    modules = {name: sys.modules.get(name) for name in STAND_INS}
    path, cwd = list(sys.path), os.getcwd()
    try:
        yield
    finally:
        builtins.input = real_input
        os.chdir(cwd)
        sys.path[:] = path
        for name, module in modules.items():
            # Only a stand-in is undone: a real module imported meanwhile stays
            if isinstance(sys.modules.get(name, module), types.ModuleType):
                continue
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module
        os.environ.clear()
        os.environ.update(environment)
        for owner, before in attributes:
            _restore(owner, before)

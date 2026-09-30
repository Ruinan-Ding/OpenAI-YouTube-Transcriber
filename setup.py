from setuptools import setup

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

# What the project ships, named one by one rather than globbed: Prompt/ and
# Profile/ are also where a checkout's user saves their own prompts and
# profiles, and a wheel built there must carry none of them. config.txt,
# which can hold an API key, is never among them.
PROMPTS = "openai_youtube_transcriber_prompts"
PROFILES = "openai_youtube_transcriber_profiles"
SHIPPED_PROMPTS = ["prompt-refinement.txt", "prompt0-translator.txt",
                   "prompt1-summarizer.txt", "prompt2-explainer.txt"]
SAMPLE_PROFILES = ["profile-transcriber.txt", "profile0-translator.txt",
                   "profile1-video_downloader.txt", "profile2-audio_downloader.txt"]

setup(
    name="openai-youtube-transcriber",
    version="1.2.0",
    author="Ruinan Ding",
    description="Extract and transcribe YouTube audio using OpenAI Whisper",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/Ruinan-Ding/OpenAI-YouTube-Transcriber",
    project_urls={
        "Changelog": "https://github.com/Ruinan-Ding/OpenAI-YouTube-Transcriber"
                     "/blob/main/CHANGELOG.md",
        "Issues": "https://github.com/Ruinan-Ding/OpenAI-YouTube-Transcriber/issues",
    },
    keywords=["youtube", "whisper", "transcription", "subtitles", "yt-dlp", "ffmpeg"],
    license="BSD-3-Clause",
    # One top-level module: OpenAIYouTubeTranscriber/ beside it is the data
    # directory, not a package, so find_packages() found nothing to install
    py_modules=["OpenAIYouTubeTranscriber"],
    # ...but the prompts and sample profiles it ships have to travel with it: a
    # wheel held the module alone, and an installed copy offered no prompt at
    # all. Each goes in as a package of data, which the module finds through
    # the import system; the samples are copied into the working directory's
    # Profile/ on first run, where the user's own profiles live.
    packages=[PROMPTS, PROFILES],
    package_dir={PROMPTS: "OpenAIYouTubeTranscriber/Prompt",
                 PROFILES: "OpenAIYouTubeTranscriber/Profile"},
    package_data={PROMPTS: SHIPPED_PROMPTS, PROFILES: SAMPLE_PROFILES},
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Operating System :: OS Independent",
        "Intended Audience :: End Users/Desktop",
        "Topic :: Multimedia :: Sound/Audio",
        "Topic :: Office/Business",
        "Environment :: Console",
        "Topic :: Multimedia :: Video :: Conversion",
    ],
    # 3.10+ is required by the match/case in _run_pipeline
    python_requires=">=3.10",
    install_requires=[
        "langdetect",
        "yt-dlp",
        # 1.2.3 reads back a quoted value ending in a backslash; see requirements.txt
        "python-dotenv>=1.2.3",
        "openai-whisper @ git+https://github.com/openai/whisper.git",
    ],
    entry_points={
        "console_scripts": [
            "openai-youtube-transcriber=OpenAIYouTubeTranscriber:main",
        ],
    },
)

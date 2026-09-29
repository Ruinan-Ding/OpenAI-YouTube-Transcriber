from setuptools import setup

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

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
    # ...but the prompts it ships have to travel with it: a wheel held the
    # module alone, and an installed copy offered no prompt at all. They go in
    # as a package of their own, which the module finds through the import
    # system. Profiles and config.txt are the user's, and stay in the working
    # directory - config.txt can hold an API key.
    packages=["openai_youtube_transcriber_prompts"],
    package_dir={"openai_youtube_transcriber_prompts": "OpenAIYouTubeTranscriber/Prompt"},
    package_data={"openai_youtube_transcriber_prompts": ["*.txt"]},
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
        "python-dotenv",
        "openai-whisper @ git+https://github.com/openai/whisper.git",
    ],
    entry_points={
        "console_scripts": [
            "openai-youtube-transcriber=OpenAIYouTubeTranscriber:main",
        ],
    },
)

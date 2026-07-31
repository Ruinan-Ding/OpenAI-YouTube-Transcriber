from setuptools import find_packages, setup

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="openai-youtube-transcriber",
    version="1.1.0",
    author="Ruinan Ding",
    description="Extract and transcribe YouTube audio using OpenAI Whisper",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/Ruinan-Ding/OpenAI-YouTube-Transcriber",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "License :: OSI Approved :: BSD License",
        "Operating System :: OS Independent",
        "Intended Audience :: End Users/Desktop",
        "Topic :: Multimedia :: Sound/Audio",
        "Topic :: Office/Business",
    ],
    # 3.10+ is required by the match/case in _run_pipeline
    python_requires=">=3.10",
    install_requires=[
        "requests",
        "py_mini_racer",
        "langdetect",
        "pytubefix",
        "python-dotenv",
        "moviepy",
        "tenacity",
        "openai-whisper @ git+https://github.com/openai/whisper.git",
    ],
    entry_points={
        "console_scripts": [
            "openai-youtube-transcriber=__main__:main",
        ],
    },
)

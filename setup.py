from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="openai-youtube-transcriber",
    version="1.0.0",
    author="Ruinan Ding",
    description="Extract and transcribe YouTube audio using OpenAI Whisper",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/Ruinan-Ding/OpenAI-YouTube-Transcriber",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "License :: OSI Approved :: BSD License",
        "Operating System :: OS Independent",
        "Intended Audience :: End Users/Desktop",
        "Topic :: Multimedia :: Sound/Audio",
        "Topic :: Office/Business",
    ],
    python_requires=">=3.6",
    install_requires=[
        "requests",
        "py_mini_racer",
        "langdetect",
        "pytubefix",
        "python-dotenv",
        "moviepy",
        "tenacity",
        "git+https://github.com/openai/whisper.git",
    ],
    entry_points={
        "console_scripts": [
                "youtube-transcriber=yt_transcriber_entry:main",
        ],
    },
)
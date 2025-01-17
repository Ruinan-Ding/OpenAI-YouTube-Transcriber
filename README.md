# README AND INSTRUCTIONS ARE CURRENTLY OUTDATED

# OpenAI Whisper YouTube Downloader Translator Transcriber Multi-Tool

A powerful and intuitive automation multi-tool, primarily designed to extract audio from YouTube videos, transcribe it into text, detect the language, and save the transcription as a `.txt` file. This core feature is complemented by many other functionalities, making it an essential tool for streamlining your workflow with cutting-edge technology.

## Table of Contents

- [Project Overview](#openai-whisper-youtube-downloader-translator-transcriber-multi-tool)
  - [Description](#description)
  - [Key Features](#key-features)
  - [Prerequisites](#prerequisites)
  - [Required Libraries](#required-libraries)
  - [Installation](#installation)
  - [Usage](#usage)
  - [Workflow](#workflow)
  - [Known Issues](#known-issues)
  - [Tips](#tips)
  - [Contributing](#contributing)
    - [Pull Requests](#pull-requests)
    - [Issues](#issues)

## Description

This script automates the transcription of YouTube videos into text format, eliminating the need for manual transcription. With an intuitive interface, users simply input a YouTube video URL, and the script processes the audio, transcribes it, detects the language, and saves the result in a `.txt` file. Perfect for quick, accurate transcriptions for research, content creation, or accessibility purposes.

## Key Features

- **User-Friendly Interface**: Easy to use—simply input the YouTube video URL to start the transcription process.
- **Efficient Audio Extraction**: Uses the `pytubefix` library to reliably download the audio stream from YouTube videos.
- **High-Quality Transcription**: Powered by the `whisper` library, offering accurate, state-of-the-art speech-to-text capabilities.
- **Convenient Output**: Automatically saves the transcription in a `.txt` file for easy access and sharing.

## Prerequisites

1. **Python 3.6+**  
   - [Install on Windows](https://phoenixnap.com/kb/how-to-install-python-3-windows)  
   - [Install on Mac](https://docs.python-guide.org/starting/install3/osx/)  
   - [Install on Ubuntu](https://phoenixnap.com/kb/how-to-install-python-3-ubuntu)  

2. **pip** (Python Package Installer)  
   - [Install pip on Windows](https://phoenixnap.com/kb/install-pip-windows)  
   - [Install pip on Mac](https://phoenixnap.com/kb/install-pip-mac)  
   - [Install pip on Ubuntu](https://phoenixnap.com/kb/how-to-install-pip-on-ubuntu)

## Required Libraries

- **pytubefix**: A robust Python library for downloading YouTube videos and extracting audio. `pytubefix` resolves occasional issues in `pytube`, where certain regex expressions in `cipher.py` may occasionally fail.
- **whisper**: OpenAI’s advanced speech-to-text model, known for its high accuracy and reliability in transcription.
- **langdetect**: A powerful language detection library based on Google's language-detection algorithm.

## Installation

1. Clone or download the repository.
2. Install the required libraries via pip:

   ```bash
   pip install pytubefix
   pip install git+https://github.com/openai/whisper.git
   pip install langdetect
   ```

3. Install FFmpeg (necessary for audio processing):

   - **Windows**:
     If Scoop is not installed, run PowerShell as administrator and execute:
     ```bash
     Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
     Invoke-RestMethod -Uri https://get.scoop.sh | Invoke-Expression
     scoop install ffmpeg
     ```
   
   - **Mac**:
     ```bash
     brew install ffmpeg
     ```
   
   - **Ubuntu**:
     ```bash
     sudo apt update && sudo apt install ffmpeg
     ```

## Usage

1. Run the script by executing `WhisperYouTubeMultiTool.py`:

   ```bash
   python WhisperYouTubeMultiTool.py
   ```

2. Input the YouTube video URL when prompted:

   ```bash
   Enter the YouTube video URL: https://www.youtube.com/watch?v=XXXXXXXXXXX
   ```

   Example:
   ```bash
   Enter the YouTube video URL: https://www.youtube.com/watch?v=jNQXAC9IVRw
   ```

3. The script will:
   - Download the audio,
   - Transcribe the audio to text,
   - Detect the language,
   - Save the transcription in a file named `Transcript_{language}.txt`.

4. Access the transcription file in the same directory as the script.

## Workflow

1. The user provides the YouTube video URL.
2. `pytubefix` downloads the audio and saves it as an `.mp3` file.
3. `whisper` transcribes the audio into text.
4. `langdetect` identifies the transcription language.
5. The transcription is saved as `Transcript_{language}.txt`, ready for review.

## Known Issues

- **Punctuation Errors**: Occasionally, punctuation may be missing or incorrect in some parts of the transcription. Manual editing or using tools like ChatGPT can help resolve these.
- **Transcription Accuracy**: On rare occasions, the script might misinterpret words or produce spelling errors. These issues can be easily corrected using a text editor or ChatGPT.

## Tips

- If punctuation issues arise, use [ChatGPT](https://chatgpt.com/) to fix grammar and punctuation:

```bash
Correct the punctuation and grammar errors in the provided text while keeping the content and structure the same.

# Steps
1. Carefully review the input text for any grammatical or punctuation mistakes.
2. Correct the identified errors without changing the underlying meaning or structure.
3. Ensure the revised text is grammatically correct and properly punctuated.

# Output Format
- Return the corrected text as plain text without modifications other than grammatical and punctuation corrections.

# Examples
- Input: "this is the sentence which needs fixin"
  Output: "This is the sentence which needs fixing."

- Input: "hello world i am a language model"
  Output: "Hello world, I am a language model."

# Notes
- Maintain verbatim repetition of the original ideas and text, only adjusting for grammatical accuracy.


Here is the text below:

<insert generated text>
```
As of GPT-4o, long YouTube transcripts might be summarized. If this happens, you may have to break the transcript piecemeal.

- If words are misinterpreted, prompt ChatGPT to correct them:

```bash
Edit the given auto-generated transcript to correct any misspellings and grammar errors but do not summarize or leave anything out.

# Steps
1. Read the entire transcript carefully to understand the context and content.
2. Identify any spelling mistakes and correct them.
3. Review the transcript for grammatical errors, including punctuation, subject-verb agreement, and verb tense consistency, and correct them.
4. Ensure the paragraph breaks are logical and support reading comprehension, without altering the original intent or content.

# Output Format
- The corrected transcript should be provided as plain text.

# Notes
- Do not add, summarize, or omit any information from the original transcript.
- Maintain the original meaning and context in all corrections.
- Focus on accuracy in spelling and grammatical structure without rewriting or rephrasing sentences unnecessarily.

Here is the text below:

<insert generated text>
```
As of GPT-4o, long YouTube transcripts might be summarized. If this happens, you may have to break the transcript piecemeal.

- **Using YouTube's Transcript**: If the video has an auto-generated transcript on YouTube, you can copy it and prompt ChatGPT to improve it. [Learn more about obtaining YouTube transcripts](https://www.descript.com/blog/article/transcript-of-youtube-videos). Use this prompt to ensure that the transcript remains verbatim while improving its quality:

```bash
You are tasked with converting a raw transcript from a YouTube video into a verbatim transcript in proper English. Your goal is to provide a transcript that is easy to read, follows the video word-for-word, and preserves the context, excluding any timestamps.

# Steps
1. **Read the Raw Transcript:** Understand the context and overall flow of the conversation without making assumptions about unknown parts.
2. **Edit for Verbatim Accuracy:** Ensure the text is exactly as spoken in the video, capturing all words including fillers and non-verbal expressions, but improving readability without changing meaning.
3. **Preserve the Original Structure:** Maintain any natural pauses or changes in speaker, annotating changes in speakers clearly but subtlely.
4. **Remove Timestamps:** Ensure no timestamps or irrelevant metadata are included in the final output.
5. **Maintain Contextual Integrity:** While improving clarity, do not alter or summarize the content of the transcript.

# Output Format
- The final output should be a clean, verbatim transcript.
- Each speaker’s expressions should be clearly attributed and separated for clarity.
- The transcript should be free of any timestamps or non-dialogue elements.

# Examples

## Example 1
- **Raw Input:** "uh so today we're um going to explore the, like, you know, the Amazon rainforest."
- **Verbatim Transcript:** "Uh, so today, we're um, going to explore, like, uh, you know, the Amazon rainforest."

## Example 2
- **Raw Input:** "and uh, yeah, that's pretty much it."
- **Verbatim Transcript:** "And uh, yeah, that's pretty much it."

# Notes
- Prioritize accuracy and readability while ensuring the transcript remains a direct reflection of the spoken words.
- The output should be suitable for following along with the video content directly.


Here is the text below:

<insert generated text>
```
As of GPT-4o, long YouTube transcripts might be summarized. If this happens, you may have to break the transcript piecemeal.

- **Refining the Transcript**: If you'd like to improve the transcript, you can prompt ChatGPT with the following:

```bash
Given a transcript, convert it into a structured written document by including accurate section titles and correcting any grammatical errors, while preserving the original meaning and content without omitting any words or sentences.

# Steps

1. **Read the Entire Transcript**:
   - Carefully review the transcript to understand its flow and main topics discussed.
   
2. **Correct Grammatical Errors**:
   - Identify and correct any grammatical errors without altering the intended meaning of the transcript.
   
3. **Identify Logical Segments**:
   - Based on the flow of conversation or monologue, identify logical segments that could form distinct sections.

4. **Add Appropriate Section Titles**:
   - Create descriptive and appropriate titles for each section, capturing the essence of the content within that segment.

5. **Ensure No Content is Omitted**:
   - Verify that no content from the original transcript is left out; maintain the verbatim content as much as possible, except where grammatical corrections are necessary.

# Output Format

- A written document with:
  - Edited text with grammatical corrections.
  - Section titles added above relevant content segments.
  - Continuous and clear flow between sections.


Here is the text below:

<insert generated text>
```
As of GPT-4o, long YouTube transcripts might be summarized. If this happens, you may have to break the transcript piecemeal.

- **Summarizing the Transcript**: You can also ask ChatGPT to summarize the transcript into key takeaways:

```bash
Summarize the provided text by extracting the most important points and core messages into concise key takeaways.

# Steps
1. Carefully read through the provided text to fully understand its content and context.
2. Identify the main ideas and supporting details.
3. Extract these elements and condense them into clear and concise bullet points or numbered lists of key takeaways.

# Output Format
- Provide a list of key takeaways, with each point clearly articulated.
- Use bullet points or numbered lists for clarity and separation between different takeaways.

# Notes
- Ensure that the key takeaways preserve the original meaning and intent of the text.
- Avoid adding personal opinions or external information.
- Consider including any potential implications or conclusions directly supported by the text.


Here is the text below:

<insert generated text>
```

- **Translating the Transcript**: You can ask ChatGPT to translate the transcript into another language. For example:

```bash
Translate a YouTube video transcript into verbatim text in the specified target language, ensuring a word-for-word translation that retains all context while excluding timestamps.

# Steps
1. Review the provided transcript to understand its content and context fully.
2. Translate each line of the transcript into the target language specified by [language], ensuring accuracy and fidelity to the source.
3. Avoid including any timestamps or summarizing any content.
4. Ensure the translation retains all context and details as per the original transcript.

# Output Format
Produce a verbatim transcript in the specified target language, maintaining the original order of text as presented in the source document. Do not include any formatting or timestamps, strictly focusing on text translation only.

# Example
**Source:** Hello, and welcome to my channel. Today, we're going to talk about astrophysics.

**Output in French:** Bonjour, et bienvenue sur ma chaîne. Aujourd'hui, nous allons parler d'astrophysique.

# Notes
- The translation should be clear and as direct as possible, to be used as a one-to-one guide while watching the video.
- Pay attention to maintaining the tone and nuances of the original language to ensure effective communication.


Here is the text below:

<insert generated text>
```
As of GPT-4o, long YouTube transcripts might be summarized. If this happens, you may have to break the transcript piecemeal.

## Contributing

We welcome contributions to this project! To get involved, participate in [Discussions](https://github.com/Ruinan-Ding/OpenAI-Whisper-YouTube-Downloader-Translator-Transcriber-Multi-Tool/discussions), submit a pull request, or report any issues. We're open to suggestions for new features or improvements.

### Pull Requests

1. Fork the repository and create a branch from the `main` branch.
2. Make your changes or additions.
3. Commit your changes and push them to your branch.
4. Open a pull request to the `main` branch, describing your changes clearly.

### Issues

1. Before opening a new issue, check if a similar one already exists in the [Issues](https://github.com/Ruinan-Ding/OpenAI-Whisper-YouTube-Downloader-Translator-Transcriber-Multi-Tool/issues) section.
2. If not, create a new issue with a detailed description of the problem or proposed enhancement.

---

Feel free to contribute, share, and help improve this project!
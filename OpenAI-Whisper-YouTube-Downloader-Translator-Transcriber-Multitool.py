#This Python script downloads the audio or video from a YouTube link, uses OpenAI's Whisper to detect the language, and transcribes it into a .txt file.
#Author: Ruinan Ding

#Ruinan Ding

#Description
#To run this script, open this script with Python or use the following command in a command line terminal where this file is:
#python OpenAI-Whisper-YouTube-Downloader-Translator-Transcriber-Multitool.py
#Input the YouTube video URL when prompted, and it will download the audio or video streams from the URL along with the transcription of the audio.


# import required modules
import os
import whisper
from langdetect import detect
from pytubefix import YouTube
from dotenv import load_dotenv

# Function to open a file
def startfile(fn):
    os.system('open %s' % fn)

# Function to create and open a txt file
def create_and_open_txt(text, filename):
    # Create and write the text to a txt file
    with open(filename, "w") as file:
        file.write(text)
    startfile(filename)

# Check if .env file exists
if os.path.exists(".env"):
    load_env = input("Load parameters from .env file? (Y/n): ").lower() != 'n'
    if load_env:  # Load only if the user selects yes
        load_dotenv()

# Get parameters from environment variables or user input
url = os.getenv("YOUTUBE_URL")
if not (load_env and url):  # Prompt if not loading from .env OR if YOUTUBE_URL is not set
    url = input("Enter the YouTube video URL: ")

# Create a YouTube object from the URL
yt = YouTube(url)

# Extract the filename base from the video title  <--- Moved outside the if block
video_title = yt.title
filename_base = "".join(c for c in video_title if c.isalnum() or c in "._- ")

download_video_str = os.getenv("DOWNLOAD_VIDEO")
if load_env and download_video_str:  # Check load_env first
    download_video = download_video_str.lower() == 'y'
else:
    download_video = input("Download video stream? (y/N): ").lower() == 'y'

include_audio_str = os.getenv("INCLUDE_AUDIO")
if load_env and include_audio_str:
    include_audio = include_audio_str.lower() == 'y'
else:
    if download_video:
        include_audio = input("Include audio stream with video stream? (Y/n): ").lower() != 'n'
    else:
        include_audio = input("Include audio stream? (y/N): ").lower() == 'y'  # Prompt for audio even if not downloading video

    if include_audio:
        # Get the highest resolution video with audio
        print("Downloading the video stream of the highest resolution with audio...")
        stream = yt.streams.filter().get_highest_resolution()
        output_path = "VideoWithAudio"
        filename = filename_base + ".mp4"
    else:
        # Get the video stream without audio
        print("Downloading the video stream...")
        stream = yt.streams.filter(only_video=True).first()
        output_path = "Video"
        filename = filename_base + ".mp4"

    # Download the selected stream
    stream.download(output_path=output_path, filename=filename)
    print(f"Video downloaded to {output_path}/{filename}")

# Get the audio stream in .mp3 format
print("Downloading the audio stream...")
audio_stream = yt.streams.filter().get_audio_only()

# Set output_path and filename for the audio file
output_path = "Audio"
filename = filename_base + ".mp3"

# Download the audio stream
audio_stream.download(output_path=output_path, filename=filename)
print(f"Audio downloaded to {output_path}/{filename}")


model_choice = os.getenv("MODEL_CHOICE")
if not (load_env and model_choice):  # Prompt if not loading from .env OR if MODEL_CHOICE is not set in .env
    model_choice = input("Select Whisper model:\n"
                         "1. Tiny\n"
                         "2. Base\n"
                         "3. Small\n"
                         "4. Medium\n"
                         "5. Large-v1\n"
                         "6. Large-v2\n"
                         "7. Large-v3\n"
                         "Enter your choice (1-7 or model name, default Base): ").lower()

# Set model based on user input (default to "base") using match statement
match model_choice:
    case '1' | 'tiny':
        model_name = "tiny"
    case '2' | 'base':
        model_name = "base"
    case '3' | 'small':
        model_name = "small"
    case '4' | 'medium':
        model_name = "medium"
    case '5' | 'large-v1':
        model_name = "large-v1"
    case '6' | 'large-v2':
        model_name = "large-v2"
    case '7' | 'large-v3':
        model_name = "large-v3"
    case _:  # Default case
        model_name = "base"

transcribe_audio_str = os.getenv("TRANSCRIBE_AUDIO")
if load_env and transcribe_audio_str:
    transcribe_audio = transcribe_audio_str.lower() == 'y'
else:
    transcribe_audio = input("Transcribe the audio? (Y/n): ").lower() != 'n'

if transcribe_audio:
    target_language = os.getenv("TARGET_LANGUAGE")
    if load_env and target_language:
        # Use target_language from .env
        pass  # Add your logic here to use the target_language from .env
    else:
        target_language = input("Enter the target language for transcription (e.g., 'es' or 'spanish', default 'en'. "
                                "See supported languages at https://github.com/openai/whisper#supported-languages): ").lower()
        if not target_language:
            target_language = 'en'  # Default to English

    use_en_model_str = os.getenv("USE_EN_MODEL")
    if load_env and use_en_model_str:
        use_en_model = use_en_model_str.lower() == 'y'
    elif model_name in ("tiny", "base", "small", "medium") and target_language == 'en':
        use_en_model = input("Use English-specific model? (Recommended only if the video is originally in English) (y/N): ").lower() == 'y'
    else:
        use_en_model = False  # Default to False if not in .env and not English

    if use_en_model:
        model_name += ".en"

    # Load the selected model
    model = whisper.load_model(model_name)

    result = model.transcribe("Audio/" + filename_base + ".mp3", language=target_language)
    transcribed_text = result["text"]
    print(transcribed_text)

    # Detect the language
    language = detect(transcribed_text)
    print(f"Detected language: {language}")

    # Create and open a txt file with the text
    if language == 'en':
        create_and_open_txt(transcribed_text, f"{filename_base}.txt")
    else:
        create_and_open_txt(transcribed_text, f"{filename_base} [{language}].txt")
else:
    print("Skipping transcription.")
    transcribed_text = ""  # Assign an empty string

# Ask the user if they want to delete the audio file (default yes)
delete_audio_str = os.getenv("DELETE_AUDIO")
if load_env and delete_audio_str:
    delete_audio = delete_audio_str.lower() == 'y'  # Use value from .env
else:
    delete_audio = input("Delete the audio file? (Y/n): ").lower() != 'n'

if delete_audio:
    # Delete the audio file
    os.remove(f"{output_path}/{filename}")
    print("Audio file deleted.")
else:
    print("Audio file kept.")
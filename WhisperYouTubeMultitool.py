# This Python script downloads the audio or video from a YouTube link,
# uses OpenAI's Whisper to detect the language, and transcribes it into a .txt file.
# Author: Ruinan Ding

# Description
# To run this script, open this script with Python or use the following command in a command line terminal where this file is:
# python WhisperYouTubeMultitool.py
# Input the YouTube video URL when prompted, and it will download the audio or video streams
# from the URL along with the transcription of the audio.

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

# Initialize load_env to False
load_env = False

# Check if .env file exists
if os.path.exists("config.env"):
    load_dotenv(dotenv_path="config.env")  # Load config.env first
    auto_load_env_str = os.getenv("AUTO_LOAD_ENV")  # Check for AUTO_LOAD_ENV in config.env
    if auto_load_env_str and auto_load_env_str.lower() == 'y':
        load_env = True
    elif auto_load_env_str and auto_load_env_str.lower() == 'n':
        print("Using default/interactive mode.")
        load_env = False
    else:
        load_env = input("Load parameters from .env file? (Y/n): ").lower() != 'n'
else:
    print("config.env file not found. Using default/interactive mode.")

# --- Get ALL parameters from user first if not loading from .env ---
if not load_env:
    url = input("Enter the YouTube video URL: ")
    download_video = input("Download video stream? (y/N): ").lower() == 'y'

    include_audio = False

    if download_video:
        include_audio = input("Include audio stream with video stream? (Y/n): ").lower() != 'n'
    else:
        # ... (No need to ask about including audio here)
        pass  # You can remove this 'pass' if there's no other code in the else block
    
    transcribe_audio_str = os.getenv("TRANSCRIBE_AUDIO")
    if load_env and transcribe_audio_str:
        transcribe_audio = transcribe_audio_str.lower() == 'y'
    else:
        transcribe_audio = input("Transcribe the audio? (Y/n): ").lower() != 'n'

    if transcribe_audio:  # Only ask model and language options if transcribing
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

        target_language = input("Enter the target language for transcription (e.g., 'es' or 'spanish', default 'en'. "
                                "See supported languages at https://github.com/openai/whisper#supported-languages): ").lower()
        if not target_language:
            target_language = 'en'  # Default to English if no input
        if model_name in ("tiny", "base", "small", "medium") and target_language == 'en':  # Corrected condition
            use_en_model = input("Use English-specific model? (Recommended only if the video is originally in English) (y/N): ").lower() == 'y'
        else:
            use_en_model = False
    else:  # If not transcribing, skip model and language options
        model_name = "base"  # Set a default model name
        target_language = 'en'  # Default to English
        use_en_model = False

    # --- Download audio only if not transcribing ---
    download_audio = False
    if not transcribe_audio:
        download_audio = input("Download audio only? (y/N): ").lower() == 'y'

    if transcribe_audio:  # Only ask to delete audio if transcribing
        delete_audio = input("Delete the audio file? (Y/n): ").lower() != 'n'
    else:
        delete_audio = False  # Don't delete audio if not transcribing
        
# --- If loading from .env, get parameters from environment variables or prompt for missing ones ---
else:
    url = os.getenv("YOUTUBE_URL")
    if not url:
        url = input("Enter the YouTube video URL: ")

    download_video_str = os.getenv("DOWNLOAD_VIDEO")
    if download_video_str:
        download_video = download_video_str.lower() == 'y'
    else:
        download_video = input("Download video stream? (y/N): ").lower() == 'y'

    include_audio_str = os.getenv("INCLUDE_AUDIO")
    if include_audio_str:
        include_audio = include_audio_str.lower() == 'y'
    else:
        if download_video:
            include_audio = input("Include audio stream with video stream? (Y/n): ").lower() != 'n'
        else:
            include_audio = False  # Or prompt the user if you prefer

    transcribe_audio_str = os.getenv("TRANSCRIBE_AUDIO")
    if transcribe_audio_str:
        transcribe_audio = transcribe_audio_str.lower() == 'y'
    else:
        transcribe_audio = input("Transcribe the audio? (Y/n): ").lower() != 'n'

    if transcribe_audio:
        model_choice = os.getenv("MODEL_CHOICE")
        if not model_choice:
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

        target_language = os.getenv("TARGET_LANGUAGE")
        if target_language:
            # Use target_language from .env
            pass  # Add your logic here to use the target_language from .env
        else:
            target_language = input("Enter the target language for transcription (e.g., 'es' or 'spanish', default 'en'. "
                                    "See supported languages at https://github.com/openai/whisper#supported-languages): ").lower()
            if not target_language:
                target_language = 'en'  # Default to English

        use_en_model_str = os.getenv("USE_EN_MODEL")
        if use_en_model_str:
            use_en_model = use_en_model_str.lower() == 'y'
        elif model_name in ("tiny", "base", "small", "medium") and target_language == 'en':
            use_en_model = input("Use English-specific model? (Recommended only if the video is originally in English) (y/N): ").lower() == 'y'
        else:
            use_en_model = False  # Default to False if not in .env and not English
    else:
        model_name = "base"  # Set a default model name
        target_language = 'en'  # Default to English
        use_en_model = False

    download_audio_str = os.getenv("DOWNLOAD_AUDIO")
    if download_audio_str:
        download_audio = download_audio_str.lower() == 'y'
    else:
        if not transcribe_audio:
            download_audio = input("Download audio only? (y/N): ").lower() == 'y'
        else:
            download_audio = False

    if transcribe_audio or download_audio:
        delete_audio_str = os.getenv("DELETE_AUDIO")
        if delete_audio_str:
            delete_audio = delete_audio_str.lower() == 'y'
        else:
            delete_audio = input("Delete the audio file? (Y/n): ").lower() != 'n'
    else:
        delete_audio = False

# --- Now, proceed with the rest of the script using the gathered parameters ---

# Create a YouTube object from the URL
yt = YouTube(url)

# Extract the filename base from the video title
video_title = yt.title
filename_base = "".join(c for c in video_title if c.isalnum() or c in "._- ")

if download_video:
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

if transcribe_audio or download_audio:  # Download audio if needed for video or audio-only
    print("Downloading the audio stream...")
    audio_stream = yt.streams.filter().get_audio_only()

    # Set output_path and filename for the audio file
    output_path = "Audio"
    filename = filename_base + ".mp3"

    # Download the audio stream
    audio_stream.download(output_path=output_path, filename=filename)
    print(f"Audio downloaded to {output_path}/{filename}")

if transcribe_audio:
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

if delete_audio:
    output_path = "Audio"  # Set output_path here, before os.remove()
    filename = filename_base + ".mp3"
    # Delete the audio file
    os.remove(f"{output_path}/{filename}")
    print("Audio file deleted.")
elif transcribe_audio or download_audio:
    print("Audio file kept.")
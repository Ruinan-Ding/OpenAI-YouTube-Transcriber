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
from pytubefix.exceptions import RegexMatchError  # Import RegexMatchError
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

# Function to get a yes/no input with validation and default option
def get_yes_no_input(prompt_text, default="y"):
    """
    Gets a yes/no input with validation and default option.

    Args:
        prompt_text: The text to prompt the user with.
        default: The default value to return if the user provides no input.
            Should be 'y' or 'n'.

    Returns:
        True if the user inputs a "yes" value, False if the user inputs a "no" value.
    """
    while True:
        user_input = input(prompt_text).lower()
        if user_input in ('y', 'yes', 'true', 't', '1'):
            return True
        elif user_input in ('n', 'no', 'false', 'f', '0'):
            return False
        elif user_input == "":
            return default == 'y'  # Return True if default is 'y', False otherwise
        else:
            print("Invalid input. Please enter 'y', 'yes', 'true', 't', '1', 'n', 'no', 'false', 'f', or '0'.")

# Function to get a model choice input with validation
def get_model_choice_input():
    while True:
        model_choice = input("Select Whisper model:\n"
                             "1. Tiny\n"
                             "2. Base\n"
                             "3. Small\n"
                             "4. Medium\n"
                             "5. Large-v1\n"
                             "6. Large-v2\n"
                             "7. Large-v3\n"
                             "Enter your choice (1-7 or model name, default Base): ").lower()
        if model_choice in ('1', '2', '3', '4', '5', '6', '7', 'tiny', 'base', 'small', 'medium', 'large-v1', 'large-v2', 'large-v3', ''):
            return model_choice
        else:
            print("Invalid input. Please enter a valid model choice or number (1-7).")

def get_target_language_input():
    """
    Prompts the user for the target language and validates the input against Whisper's supported languages.
    Defaults to 'en' (English) if no input is provided.
    """
    while True:
        target_language = input("Enter the target language for transcription (e.g., 'es' or 'spanish', default 'en'. "
                                "See supported languages at https://github.com/openai/whisper#supported-languages): ").lower()
        if not target_language:
            return 'en'  # Default to English if no input is provided
        # Check if the language code or full name is valid
        if target_language in whisper.tokenizer.LANGUAGES or target_language in whisper.tokenizer.LANGUAGES.values():
            return target_language
        else:
            print("Invalid language code or name. Please refer to the supported languages list and try again.")

# Initialize load_env to False
load_env = False

# Check if .env file exists
if os.path.exists("config.env"):
    load_dotenv(dotenv_path="config.env")  # Load config.env first
    auto_load_env_str = os.getenv("AUTO_LOAD_ENV")  # Check for AUTO_LOAD_ENV in config.env
    if auto_load_env_str and auto_load_env_str.lower() in ('y', 'yes', 'true', 't', '1'):
        load_env = True
    elif auto_load_env_str and auto_load_env_str.lower() in ('n', 'no', 'false', 'f', '0'):
        print("Using default/interactive mode.")
        load_env = False
    else:
        print(f"Invalid value for AUTO_LOAD_ENV in .env: {auto_load_env_str}")  # Print invalid value message
        load_env = get_yes_no_input("Load parameters from .env file? (Y/n): ")  # Use the validation function
else:
    print("config.env file not found. Using default/interactive mode.")

# --- Get ALL parameters from user first if not loading from .env ---

if not load_env:
    while True:  # Loop until a valid URL is provided
        url = input("Enter the YouTube video URL: ")
        try:
            # Attempt to create a YouTube object
            yt = YouTube(url)
            break  # Exit loop if the URL is valid
        except RegexMatchError:
            print("Incorrect value for YOUTUBE_URL. Please enter a valid YouTube video URL.")
    download_video = get_yes_no_input("Download video stream? (y/N): ", default='n')  # Use the validation function

    include_audio = False

    if download_video:
        include_audio = get_yes_no_input("Include audio stream with video stream? (Y/n): ")  # Use the validation function
    else:
        # ... (No need to ask about including audio here)
        pass  # You can remove this 'pass' if there's no other code in the else block
    
    transcribe_audio_str = os.getenv("TRANSCRIBE_AUDIO")
    if load_env and transcribe_audio_str:
        transcribe_audio = transcribe_audio_str.lower() in ('y', 'yes', 'true', 't', '1')
    else:
        transcribe_audio = get_yes_no_input("Transcribe the audio? (Y/n): ")

    if transcribe_audio:
        model_choice = get_model_choice_input()  # Use the validation function

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
            case _:  # Default case (empty input)
                model_name = "base"

        target_language = get_target_language_input()  # Use the validation function

        if model_name in ("tiny", "base", "small", "medium") and target_language == 'en':  # Corrected condition
            use_en_model = get_yes_no_input("Use English-specific model? (Recommended only if the video is originally in English) (y/N): ", default='n')
        else:
            use_en_model = False
    else:  # If not transcribing, skip model and language options
        model_name = "base"  # Set a default model name
        use_en_model = False

    # --- Download audio only if not transcribing ---
    download_audio = False
    if not transcribe_audio:
        download_audio = get_yes_no_input("Download audio only? (y/N): ", default='n')

    if transcribe_audio:  # Only ask to delete audio if transcribing
        delete_audio = get_yes_no_input("Delete the audio file? (Y/n): ")
    else:
        delete_audio = False  # Don't delete audio if not transcribing
        
# --- If loading from .env, get parameters from environment variables or prompt for missing ones ---
else:
    while True:  # Loop until a valid URL is provided
        url = os.getenv("YOUTUBE_URL")
        if not url:
            url = input("Enter the YouTube video URL: ")
        try:
            # Attempt to create a YouTube object
            yt = YouTube(url)
            break  # Exit loop if the URL is valid
        except RegexMatchError:
            print("Incorrect value for YOUTUBE_URL. Please enter a valid YouTube video URL.")

    download_video_str = os.getenv("DOWNLOAD_VIDEO")
    if download_video_str:
        if download_video_str.lower() in ('y', 'yes', 'true', 't', '1'):
            download_video = True
        elif download_video_str.lower() in ('n', 'no', 'false', 'f', '0'):
            download_video = False
        else:
            print(f"Invalid value for DOWNLOAD_VIDEO in .env: {download_video_str}")
            download_video = get_yes_no_input("Download video stream? (y/N): ", default='n')
    else:
        download_video = get_yes_no_input("Download video stream? (y/N): ", default='n')

    include_audio_str = os.getenv("INCLUDE_AUDIO")
    if include_audio_str:
        if include_audio_str.lower() in ('y', 'yes', 'true', 't', '1'):
            include_audio = True
        elif include_audio_str.lower() in ('n', 'no', 'false', 'f', '0'):
            include_audio = False
        elif download_video:
            print(f"Invalid value for INCLUDE_AUDIO in .env: {include_audio_str}")
            if download_video:
                include_audio = get_yes_no_input("Include audio stream with video stream? (Y/n): ")
            else:
                include_audio = False
    else:
        if download_video:
            include_audio = get_yes_no_input("Include audio stream with video stream? (Y/n): ")
        else:
            include_audio = False

    transcribe_audio_str = os.getenv("TRANSCRIBE_AUDIO")
    if transcribe_audio_str:
        if transcribe_audio_str.lower() in ('y', 'yes', 'true', 't', '1'):
            transcribe_audio = True
        elif transcribe_audio_str.lower() in ('n', 'no', 'false', 'f', '0'):
            transcribe_audio = False
        else:
            print(f"Invalid value for TRANSCRIBE_AUDIO in .env: {transcribe_audio_str}")
            transcribe_audio = get_yes_no_input("Transcribe the audio? (Y/n): ")
    else:
        transcribe_audio = get_yes_no_input("Transcribe the audio? (Y/n): ")

    model_choice = os.getenv("MODEL_CHOICE")
    if model_choice and transcribe_audio:
        # Validate model_choice from .env
        if model_choice.lower() not in ('1', '2', '3', '4', '5', '6', '7', 'tiny', 'base', 'small', 'medium', 'large-v1', 'large-v2', 'large-v3'):
            print(f"Invalid value for MODEL_CHOICE in .env: {model_choice}")
            model_choice = get_model_choice_input()  # Prompt for valid input
    elif transcribe_audio:
        model_choice = get_model_choice_input()  # Use the validation function

    if transcribe_audio:
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
            case _:  # Default case (empty input)
                model_name = "base"

        target_language = os.getenv("TARGET_LANGUAGE")
        if target_language and transcribe_audio:
            # Use target_language from .env
            if target_language.lower() not in whisper.tokenizer.LANGUAGES:
                print(f"Invalid value for TARGET_LANGUAGE in .env: {target_language}")
                target_language = get_target_language_input()
        elif transcribe_audio:
            target_language = get_target_language_input()  # Use the validation function

        use_en_model_str = os.getenv("USE_EN_MODEL")
        if use_en_model_str and transcribe_audio:
            if use_en_model_str.lower() in ('y', 'yes', 'true', 't', '1'):
                use_en_model = True
            elif use_en_model_str.lower() in ('n', 'no', 'false', 'f', '0'):
                use_en_model = False
            elif transcribe_audio:
                print(f"Invalid value for USE_EN_MODEL in .env: {use_en_model_str}")
                if model_name in ("tiny", "base", "small", "medium") and target_language == 'en':
                    use_en_model = get_yes_no_input("Use English-specific model? (Recommended only if the video is originally in English) (y/N): ", default='n')
                else:
                    use_en_model = False

    download_audio = False
    download_audio_str = os.getenv("DOWNLOAD_AUDIO")
    if download_audio_str:
        if download_audio_str.lower() in ('y', 'yes', 'true', 't', '1'):
            download_audio = True
        elif download_audio_str.lower() in ('n', 'no', 'false', 'f', '0'):
            download_audio = False
        elif not transcribe_audio:
            print(f"Invalid value for DOWNLOAD_AUDIO in .env: {download_audio_str}")
            download_audio = get_yes_no_input("Download audio only? (y/N): ", default='n')

    if transcribe_audio or download_audio:
        delete_audio_str = os.getenv("DELETE_AUDIO")
        if delete_audio_str:
            if delete_audio_str.lower() in ('y', 'yes', 'true', 't', '1'):
                delete_audio = True
            elif delete_audio_str.lower() in ('n', 'no', 'false', 'f', '0'):
                delete_audio = False
            else:
                print(f"Invalid value for DELETE_AUDIO in .env: {delete_audio_str}")
                delete_audio = get_yes_no_input("Delete the audio file? (Y/n): ")
        else:
            delete_audio = get_yes_no_input("Delete the audio file? (Y/n): ")
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
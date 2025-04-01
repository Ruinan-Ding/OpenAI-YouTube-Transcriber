# This Python script downloads the audio or video from a YouTube link,
# uses OpenAI's Whisper to detect the language, and transcribes it into a .txt file.
# Author: Ruinan Ding

# Description
# To run this script, open this script with Python or use the following command in a command line terminal where this file is:
# python WhisperYouTubeMultiTool.py
# Input the YouTube video URL when prompted, and it will download the audio or video streams
# from the URL along with the transcription of the audio.

# ===== IMPORTS =====
import sys
import os
import re
from urllib.parse import urlparse
import requests
import urllib.request
from py_mini_racer import MiniRacer
import whisper
from langdetect import detect
from pytubefix import YouTube
from pytubefix.exceptions import RegexMatchError
from dotenv import load_dotenv
import moviepy
import subprocess
import json
from enum import Enum

# ===== CONSTANTS =====
# Directory names
AUDIO_DIR = "Audio"
TEMP_DIR = "Temp"
VIDEO_DIR = "Video"
TRANSCRIPT_DIR = "Transcript"
VIDEO_WITHOUT_AUDIO_DIR = "VideoWithoutAudio"

# File extensions
MP3_EXT = ".mp3"
MP4_EXT = ".mp4"
TXT_EXT = ".txt"
ENV_EXT = ".txt"

# Profile settings
PROFILE_PREFIX = "profile"
CONFIG_ENV = f"config{ENV_EXT}"
PROFILE_NAME_TEMPLATE = f"{PROFILE_PREFIX}{{}}{ENV_EXT}"
DEFAULT_PROFILE = f"{PROFILE_PREFIX}{ENV_EXT}"
URL_PLACEHOLDER = "<Insert_YouTube_link_or_local_path_to_audio_or_video>"
DEFAULT_LANGUAGE = 'en'

# Define the profile directory
profile_dir = os.path.join(os.path.dirname(__file__), "Profile")

# ===== ENUMS =====
class YesNo(Enum):
    YES = ('y', 'yes', 'true', 't', '1')
    NO = ('n', 'no', 'false', 'f', '0')
    SKIP = ('skip', 's')
    
    @classmethod
    def all_no_and_skip(cls):
        return cls.NO.value + cls.SKIP.value

class Resolution(Enum):
    HIGHEST = 'highest'
    LOWEST = 'lowest'
    FETCH = 'fetch'
    F = 'f'
    
    @classmethod
    def values(cls):
        return [item.value for item in cls]

class ModelSize(Enum):
    TINY = 'tiny'
    BASE = 'base'
    SMALL = 'small'
    MEDIUM = 'medium'
    LARGE_V1 = 'large-v1'
    LARGE_V2 = 'large-v2'
    LARGE_V3 = 'large-v3'
    
    @classmethod
    def standard_models(cls):
        return [cls.TINY, cls.BASE, cls.SMALL, cls.MEDIUM]
    
    @classmethod
    def large_models(cls):
        return [cls.LARGE_V1, cls.LARGE_V2, cls.LARGE_V3]
    
    @classmethod
    def all_model_values(cls):
        return [model.value for model in cls]
    
    @classmethod
    def get_model_by_number(cls, number):
        mapping = {
            '1': cls.TINY,
            '2': cls.BASE, 
            '3': cls.SMALL,
            '4': cls.MEDIUM,
            '5': cls.LARGE_V1,
            '6': cls.LARGE_V2,
            '7': cls.LARGE_V3
        }
        return mapping.get(number, cls.BASE)
    
    @classmethod
    def get_model_by_name(cls, name):
        for model in cls:
            if model.value == name:
                return model
        return cls.BASE  # Default to BASE if not found

class ModelChoice(Enum):
    OPTIONS = ('1', '2', '3', '4', '5', '6', '7') + tuple(ModelSize.all_model_values()) + ('',)

# ===== FILE OPERATION FUNCTIONS =====
def startfile(fn):
    """Open a file with the default application."""
    if os.name == 'nt':  # Windows
        os.startfile(fn)
    elif os.name == 'posix':  # macOS or Linux
        opener = 'open' if sys.platform == 'darwin' else 'xdg-open'
        subprocess.run([opener, fn])

def create_and_open_txt(text, filename):
    """Create a text file with the given content and open it."""
    # Create a directory for the transcript if it doesn't exist
    output_dir = os.path.join(os.path.dirname(__file__), TRANSCRIPT_DIR)
    os.makedirs(output_dir, exist_ok=True)

    # Create the full path for the transcript file
    file_path = os.path.join(output_dir, filename)

    # Create and write the text to a txt file
    with open(file_path, "w") as file:
        file.write(text)
    startfile(file_path)

def get_file_format(file_path):
    """Returns the format of the input file using ffprobe."""
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=format_name', 
             '-of', 'default=noprint_wrappers=1:nokey=1', file_path],
            capture_output=True, text=True, check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return None

# ===== URL AND FILE VALIDATION FUNCTIONS =====
def is_web_url(input_str):
    """Check if input is a valid web URL format without network calls."""
    try:
        result = urlparse(input_str)
        return all([result.scheme in ['http', 'https'], result.netloc])
    except:
        return False

def is_youtube_url(url):
    """Check if URL is YouTube using pytubefix's internal regex."""
    try:
        YouTube(url, "WEB")
        return True
    except RegexMatchError:
        return False

def is_valid_media_file(path):
    """Check if path is an existing local media file."""
    return os.path.exists(path) and get_file_format(path) is not None

# ===== USER INPUT HANDLING FUNCTIONS =====
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
        if user_input in YesNo.YES.value:
            return True
        elif user_input in YesNo.NO.value:
            return False
        elif user_input == "":
            return default == 'y'  # Return True if default is 'y', False otherwise
        else:
            print(f"Invalid input. Please enter one of {YesNo.YES.value + YesNo.NO.value}.")

def get_model_choice_input():
    """Get and validate user's choice of Whisper model."""
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
        if model_choice in ModelChoice.OPTIONS.value:
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
            return DEFAULT_LANGUAGE  # Default to English if no input is provided
        # Check if the language code or full name is valid
        if target_language in whisper.tokenizer.LANGUAGES or target_language in whisper.tokenizer.LANGUAGES.values():
            return target_language
        else:
            print("Invalid language code or name. Please refer to the supported languages list and try again.")

# ===== PROFILE MANAGEMENT FUNCTIONS =====
def create_profile(used_fields):
    """Creates a new profile file and config.txt (if it doesn't exist)."""
    os.makedirs(profile_dir, exist_ok=True)
    
    # Check and create config.txt if it doesn't exist
    config_path = os.path.join(profile_dir, CONFIG_ENV)
    if not os.path.exists(config_path):
        with open(config_path, "w") as config_file:
            config_file.write("# Configuration file for YouTube Transcriber\n")
            config_file.write(f"LOAD_PROFILE={DEFAULT_PROFILE}")  # Removed trailing newline
        print(f"Created {CONFIG_ENV}: {os.path.abspath(config_path)}")
    else:
        print(f"{CONFIG_ENV} already exists: {os.path.abspath(config_path)}. No changes were made to it.")

    # Find all existing profiles and determine next available name
    existing_profiles = [f for f in os.listdir(profile_dir) 
                        if re.match(f"^{PROFILE_PREFIX}\\d*{ENV_EXT}$", f, re.IGNORECASE)]
    existing_numbers = [int(re.search(r"\d+", f).group()) 
                       for f in existing_profiles if re.search(r"\d+", f)]
    
    # Determine profile name
    if not existing_profiles:
        profile_name = DEFAULT_PROFILE
    else:
        next_number = 0
        while next_number in existing_numbers:
            next_number += 1
        profile_name = PROFILE_NAME_TEMPLATE.format(next_number)

    profile_path = os.path.join(profile_dir, profile_name)

    # Write fields with helpful comments
    with open(profile_path, "w") as profile_file:
        profile_file.write("#Change values after the equals sign (=)\n\n")
        
        # Keep track of fields we've written
        written_fields = set()
        
        if "URL" in used_fields:
            profile_file.write(f"URL={used_fields['URL']}\n")
            written_fields.add("URL")
            
        if "DOWNLOAD_VIDEO" in used_fields:
            profile_file.write(f"DOWNLOAD_VIDEO={used_fields['DOWNLOAD_VIDEO']}\n")
            written_fields.add("DOWNLOAD_VIDEO")
        
        # Add any remaining fields that don't have specific comments
        remaining_fields = sorted(set(used_fields.keys()) - written_fields)
        for i, key in enumerate(remaining_fields):
            # Add newline only if it's not the last field
            if i < len(remaining_fields) - 1:
                profile_file.write(f"{key}={used_fields[key]}\n")
            else:
                # No newline for last field
                profile_file.write(f"{key}={used_fields[key]}")

    print(f"Created profile: {os.path.abspath(profile_path)}")

# ===== RUNTIME SETTINGS =====
used_fields = {
    "URL": URL_PLACEHOLDER,
    "DOWNLOAD_VIDEO": "",
    "NO_AUDIO_IN_VIDEO": "",
    "RESOLUTION": "",
    "DOWNLOAD_AUDIO": "",
    "TRANSCRIBE_AUDIO": "",
    "MODEL_CHOICE": "",
    "TARGET_LANGUAGE": "",
    "USE_EN_MODEL": ""
}

# Initialize load_profile to False
load_profile = False
loaded_profile = False
interactive_mode = False

# Check if config.env exists
config_env_path = os.path.join(profile_dir, CONFIG_ENV)
if not os.path.exists(config_env_path):
    print(f"config.env not found in the {profile_dir} directory. Switching to default/interactive mode.")
    load_profile = False
    interactive_mode = True
else:
    print(f"config.env detected in the {profile_dir} directory.")
    load_dotenv(dotenv_path=config_env_path)
    load_profile_str = os.getenv("LOAD_PROFILE")
    print(f"LOAD_PROFILE: {load_profile_str} (from config.env)")

    if load_profile_str is None:
        load_profile = True

    elif load_profile_str and load_profile_str.lower() in YesNo.YES.value + ('',):
        load_profile = True
    elif load_profile_str and load_profile_str.lower() in YesNo.all_no_and_skip():
        print("Using default/interactive mode.")
        load_profile = False
        interactive_mode = True
    else:
        # Check if LOAD_PROFILE specifies a profile name
        if load_profile_str and not load_profile_str.endswith(ENV_EXT):
            load_profile_str += ENV_EXT
        profile_path = os.path.join(profile_dir, load_profile_str)  # Directly use the provided name

        profile_pattern = f"^{PROFILE_PREFIX}\\d*{ENV_EXT}$"
        if re.match(profile_pattern, load_profile_str, re.IGNORECASE):
            if os.path.exists(profile_path):
                load_profile = True
                loaded_profile = True
                profile_name = os.path.basename(profile_path)
                print(f"Loading profile: {profile_name}")
            else:
                print(f"Profile not found: {load_profile_str}. "
                      f"Make sure the profile file exists in the 'Profile' directory "
                      f"relative to the script.")
        else:
            print(f"Invalid profile name format: {load_profile_str}. "
                  f"Profile names must match the format '{PROFILE_PREFIX}<number>{ENV_EXT}' "
                  f"and be located in the 'Profile' directory relative to the script.")

    if interactive_mode is False and loaded_profile is False:
        # List available profiles (only if not found or invalid format)
        profiles = [f for f in os.listdir(profile_dir) if re.match(f"^{PROFILE_PREFIX}\\d*{ENV_EXT}$", f, re.IGNORECASE)]
        if profiles:
            print("Available profiles:")
            for i, profile in enumerate(profiles):
                print(f"{i+1}. {profile}")

            while True:
                profile_input = input(f"Select a profile (number or name, default 1. {profiles[0]}, "
                                      f"or 'no' / 'n' / 'false' / 'f' / '0' / 'skip' / 's' to skip): ").lower()
                if profile_input == '' or profile_input == '1':
                    profile_name = profiles[0]
                    load_profile = True
                    break
                elif profile_input.isdigit() and 1 <= int(profile_input) <= len(profiles):
                    profile_name = profiles[int(profile_input) - 1]
                    load_profile = True
                    break
                elif profile_input in profiles:
                    profile_name = profile_input
                    load_profile = True
                    break
                elif profile_input + ENV_EXT in profiles:
                    profile_name = profile_input + ENV_EXT
                    load_profile = True
                    break
                elif profile_input in YesNo.all_no_and_skip():
                    load_profile = False
                    break
                else:
                    print("Invalid profile selection.")
        else:
            print("No profiles found. Switching to default/interactive mode.")
            load_profile = False

    if load_profile:
        # Ensure profile_name is set – default to "profile.env" if not already assigned
        if 'profile_name' not in globals():
            profile_name = DEFAULT_PROFILE
        # Load the selected profile
        profile_path = os.path.join(profile_dir, profile_name)
        load_dotenv(dotenv_path=profile_path)
        print(f"Loaded profile: {profile_name}")

# --- Get ALL parameters from user first if not loading from .env ---

if not load_profile:
    is_local_file = False  # Initialize the flag here
    while True:
        url = input("Enter the YouTube video URL or local file path: ").strip()
        
        # --- Validation Steps ---
        if is_web_url(url):
            if is_youtube_url(url):
                is_local_file = False
                break  # Exit loop after successful YouTube validation
            else:
                print("Error: Only YouTube URLs supported for web inputs")
                continue
        elif is_valid_media_file(url):
            is_local_file = True
            break
        else:
            print("Invalid input. Please enter valid YouTube URL or local file path")
            continue

    download_video = False
    no_audio_in_video = False
    resolution = None  # Initialize resolution variable

    if not is_local_file:
        download_video = get_yes_no_input("Download video? (y/N): ", default='n')  # Use the validation function
        used_fields["DOWNLOAD_VIDEO"] = "y" if download_video else "n"

        if download_video:
            no_audio_in_video = False
            no_audio_in_video = get_yes_no_input("... without the audio in the video? (y/N): ", "n")  # Use the validation function
            used_fields["NO_AUDIO_IN_VIDEO"] = "y" if no_audio_in_video else "n"

        if download_video:
            while True:
                resolution = input("... enter desired resolution (e.g., 720p, 720, highest, lowest, default get the highest resolutions), or enter fetch or f to get a list of available resolutions: ")
                if not resolution:
                    resolution = Resolution.HIGHEST.value  # Default to highest if input is empty
                    break
                
                resolution = resolution.lower()  # Convert to lowercase after checking for empty input
                
                if resolution in Resolution.values():
                    if resolution == Resolution.F.value:
                        resolution = Resolution.FETCH.value
                    used_fields["RESOLUTION"] = resolution
                    break
                elif resolution.endswith("p"):
                    used_fields["RESOLUTION"] = resolution
                    break
                elif resolution.isdigit():
                    if int(resolution) > 0:  # Check if it's a non-zero number
                        resolution += "p"  # Add "p" if it's a number
                        used_fields["RESOLUTION"] = resolution
                        break
                    else:
                        print("Invalid resolution. Please enter a non-zero number.")
                elif resolution.endswith("p") and resolution[:-1].isdigit():
                    if int(resolution[:-1]) > 0:  # Check if it's a non-zero number ending with "p"
                        used_fields["RESOLUTION"] = resolution
                        break
                    else:
                        print("Invalid resolution. Please enter a non-zero number.")
                else:
                    print("Invalid resolution. Please enter a valid resolution (e.g., 720p, 720, highest, lowest).")
            if resolution not in (Resolution.FETCH.value, Resolution.F.value):
                print(f"Using resolution: {resolution}")  # Indicate selected resolution
            else:
                if resolution == Resolution.F.value:
                    resolution = Resolution.FETCH.value
                print("Loading available resolution...")

        # If the requested resolution is not found, prompt the user
        if resolution == Resolution.FETCH.value:
            try:
                yt = YouTube(url, "WEB")
            except RegexMatchError:
                print("Error: Invalid YouTube URL.")
                exit()
            if resolution != Resolution.FETCH.value:
                print("Requested resolution not found, left null, or invalid.")
            available_streams = yt.streams.filter(only_video=True)  # Define available_streams here

            # Order streams by resolution numerically
            available_streams = sorted(available_streams, key=lambda stream: int(stream.resolution[:-1]) if stream.resolution else 0, reverse=True)

            # Use a set to get unique resolutions and then order them
            available_resolutions = set([stream.resolution for stream in available_streams if stream.resolution])
            available_resolutions = sorted(available_resolutions, key=lambda res: int(res[:-1]) if res else 0, reverse=True)

            if not available_resolutions:
                print("No video streams found. Exiting...")
                exit()

            print("Available resolutions:")
            for i, res in enumerate(available_resolutions):
                print(f"{i+1}. {res}")

            while True:
                user_input = input("Enter desired resolution (number or resolution, default highest): ").lower()
                if not user_input:
                    selected_res = available_resolutions[0]  # Default to highest
                    break
                elif user_input.isdigit() and 1 <= int(user_input) <= len(available_resolutions):
                    selected_res = available_resolutions[int(user_input) - 1]
                    break
                elif user_input in available_resolutions or (user_input.isdigit() and user_input + "p" in available_resolutions):
                    selected_res = user_input if user_input in available_resolutions else user_input + "p"
                    break
                else:
                    print("Invalid input. Please enter a valid number or resolution.")

    if not is_local_file:
        # --- Download audio only if not transcribing ---
        download_audio = get_yes_no_input("Download audio? (y/N): ", default='n')
        used_fields["DOWNLOAD_AUDIO"] = "y" if download_audio else "n"

    transcribe_audio = get_yes_no_input("Transcribe the audio? (Y/n): ")
    used_fields["TRANSCRIBE_AUDIO"] = "y" if transcribe_audio else "n"

    if transcribe_audio:
        model_choice = get_model_choice_input()  # Use the validation function

        # Set model based on user input (default to "base") using match statement
        if model_choice in ('1', '2', '3', '4', '5', '6', '7'):
            # Number choice
            model_enum = ModelSize.get_model_by_number(model_choice)
            model_name = model_enum.value
        else:
            # Name choice or empty (default)
            if model_choice == '':
                model_enum = ModelSize.BASE
            else:
                model_enum = ModelSize.get_model_by_name(model_choice)
            model_name = model_enum.value

        used_fields["MODEL_CHOICE"] = model_name

        target_language = get_target_language_input()  # Use the validation function
        used_fields["TARGET_LANGUAGE"] = target_language

        if model_enum in ModelSize.standard_models() and target_language == DEFAULT_LANGUAGE:  # Corrected condition
            use_en_model = get_yes_no_input("Use English-specific model? (Recommended only if the video is originally in English) (y/N): ", default='n')
            used_fields["USE_EN_MODEL"] = "y" if use_en_model else "n"
        else:
            use_en_model = False
    else:  # If not transcribing, skip model and language options
        model_name = ModelSize.BASE.value  # Set a default model name
        use_en_model = False
        
# --- If loading from .env, get parameters from environment variables or prompt for missing ones ---

else:
    is_local_file = False
    url = os.getenv("URL")
    if url and url != URL_PLACEHOLDER:
        if is_web_url(url):
            if is_youtube_url(url):
                try:
                    # Create YouTube object
                    yt = YouTube(url, "WEB")
                    print(f"Loaded YOUTUBE_URL: {url} (from {profile_name})")
                except RegexMatchError:
                    # Use ffprobe to determine if it's a valid audio/video file
                    file_format = get_file_format(url)
                    if file_format:
                        is_local_file = True
                        print(f"Loaded local file: {url} (from {profile_name})")
                    else:
                        print("Incorrect value for YOUTUBE_URL in config.env. "
                              "Please enter a valid YouTube video URL or local file path: ")
                        url = input()
            else:
                print("Error: Only YouTube URLs supported for web inputs")
        elif is_valid_media_file(url):
            is_local_file = True
            print(f"Loaded local file: {url} (from {profile_name})")
        else:
            if url != URL_PLACEHOLDER:
                print("Invalid input. Please enter valid YouTube URL or local file path")
            while True:
                url = input("Enter the YouTube video URL or local file path: ").strip()
                if is_web_url(url):
                    if is_youtube_url(url):
                        try:
                            # Check if the URL is a valid YouTube URL
                            yt = YouTube(url, "WEB")
                            break
                        except RegexMatchError:
                            # Use ffprobe to determine if it's a valid audio/video file
                            file_format = get_file_format(url)
                            if file_format:
                                is_local_file = True
                                print(f"Loaded local file: {url}")
                                break
                            else:
                                print("Incorrect value for YOUTUBE_URL. "
                                      "Please enter a valid YouTube video URL or local file path.")
                elif is_valid_media_file(url):
                    is_local_file = True
                    break
                else:
                    print("Invalid input. Please enter valid YouTube URL or local file path")
                    continue
    else:
        while True:
                url = input("Enter the YouTube video URL or local file path: ").strip()
                if is_web_url(url):
                    if is_youtube_url(url):
                        try:
                            # Check if the URL is a valid YouTube URL
                            yt = YouTube(url, "WEB")
                            break
                        except RegexMatchError:
                            # Use ffprobe to determine if it's a valid audio/video file
                            file_format = get_file_format(url)
                            if file_format:
                                is_local_file = True
                                print(f"Loaded local file: {url}")
                                break
                            else:
                                print("Incorrect value for YOUTUBE_URL. "
                                      "Please enter a valid YouTube video URL or local file path.")
                elif is_valid_media_file(url):
                    is_local_file = True
                    break
                else:
                    print("Invalid input. Please enter valid YouTube URL or local file path")
                    continue

    download_video = False
    no_audio_in_video = False

    if not is_local_file:
        download_video_str = os.getenv("DOWNLOAD_VIDEO")
        if download_video_str:
            if download_video_str.lower() in YesNo.YES.value:
                download_video = True
                print(f"Loaded DOWNLOAD_VIDEO: {download_video_str} (from {profile_name})")
            elif download_video_str.lower() in YesNo.NO.value:
                download_video = False
                print(f"Loaded DOWNLOAD_VIDEO: {download_video_str} (from {profile_name})")
            else:
                print(f"Invalid value for DOWNLOAD_VIDEO in .env: {download_video_str}")
                download_video = get_yes_no_input("Download video stream? (y/N): ", default='n')
        else:
            download_video = get_yes_no_input("Download video stream? (y/N): ", default='n')

        if download_video:
            no_audio_in_video_str = os.getenv("NO_AUDIO_IN_VIDEO")
            if no_audio_in_video_str:
                if no_audio_in_video_str.lower() in YesNo.YES.value:
                    no_audio_in_video = True
                    print(f"Loaded NO_AUDIO_IN_VIDEO: {no_audio_in_video_str} (from {profile_name})")
                elif no_audio_in_video_str.lower() in YesNo.NO.value:
                    no_audio_in_video = False
                    print(f"Loaded NO_AUDIO_IN_VIDEO: {no_audio_in_video_str} (from {profile_name})")
                elif download_video:
                    print(f"Invalid value for NO_AUDIO_IN_VIDEO in .env: {no_audio_in_video_str}")
                    if download_video:
                        no_audio_in_video = get_yes_no_input("Include audio stream with video stream? (Y/n): ")
                    else:
                        no_audio_in_video = False
                
            resolution = os.getenv("RESOLUTION")
            if resolution:
                resolution = resolution.lower()  # Convert to lowercase for easier comparison
                if resolution not in Resolution.values():
                    if resolution.isdigit():
                        if int(resolution) > 0:
                            resolution += "p"  # Add "p" if it's a number
                            print(f"Loaded RESOLUTION: {resolution} (from {profile_name})")
                        else:
                            print(f"Invalid value for RESOLUTION in .env: {resolution}")
                            resolution = None  # Set to None to trigger the prompt
                    elif not (resolution.endswith("p") and resolution[:-1].isdigit()):
                        print(f"Invalid value for RESOLUTION in .env: {resolution}")
                        resolution = Resolution.FETCH.value  # Set to None to trigger the prompt
                elif resolution in Resolution.values():
                    print(f"Loaded RESOLUTION: {resolution} (from {profile_name})")
                elif resolution in (Resolution.FETCH.value, Resolution.F.value):
                    print(f"Loaded RESOLUTION: {resolution} (from {profile_name})")
                    print(f"Loading available resolution...")
                    if resolution == Resolution.F.value:
                        resolution = Resolution.FETCH.value
                else:
                    print(f"Loaded RESOLUTION: null (from {profile_name})")
                    print(f"Loading available resolution...")
                    resolution = Resolution.FETCH.value  # Set to "fetch" to trigger the prompt

    if download_video and not is_local_file and resolution == Resolution.FETCH.value:
        try:
            yt = YouTube(url, "WEB")
        except RegexMatchError:
            print("Error: Invalid YouTube URL.")
            exit()
        if resolution == Resolution.HIGHEST.value:
            streams = yt.streams.filter(only_video=True)
            streams = sorted(streams, key=lambda stream: int(stream.resolution[:-1]) if stream.resolution else 0, reverse=True)

            if streams:
                stream = streams[0]  # Highest resolution is first in descending order
            else:
                stream = None

        elif resolution == Resolution.LOWEST.value:
            streams = yt.streams.filter(only_video=True)
            streams = sorted(streams, key=lambda stream: int(stream.resolution[:-1]) if stream.resolution else 0, reverse=True)

            if streams:
                stream = streams[-1]  # Lowest resolution is last in descending order
            else:
                stream = None

        elif resolution == Resolution.FETCH.value:
            stream = None
            resolution = Resolution.FETCH.value  # Set to "fetch" to trigger the prompt

        else:  # Specific resolution provided
            streams = yt.streams.filter(only_video=True, resolution=resolution)
            streams = sorted(streams, key=lambda stream: int(stream.resolution[:-1]) if stream.resolution else 0, reverse=True)

            if streams:
                stream = streams[0]  # If specific resolution exists, take the first
            else:
                stream = None

        # If the requested resolution is not found, prompt the user
        if stream is None and resolution == Resolution.FETCH.value:
            if resolution != Resolution.FETCH.value:
                print("Requested resolution not found, left null, or invalid.")
            available_streams = yt.streams.filter(only_video=True)  # Define available_streams here

            # Order streams by resolution numerically
            available_streams = sorted(available_streams, key=lambda stream: int(stream.resolution[:-1]) if stream.resolution else 0, reverse=True)

            # Use a set to get unique resolutions and then order them
            available_resolutions = set([stream.resolution for stream in available_streams if stream.resolution])
            available_resolutions = sorted(available_resolutions, key=lambda res: int(res[:-1]) if res else 0, reverse=True)

            if not available_resolutions:
                print("No video streams found. Exiting...")
                exit()

            print("Available resolutions:")
            for i, res in enumerate(available_resolutions):
                print(f"{i+1}. {res}")

            while True:
                user_input = input("Enter desired resolution (number or resolution, default highest): ").lower()
                if not user_input:
                    selected_res = available_resolutions[0]  # Default to highest
                    break
                elif user_input.isdigit() and 1 <= int(user_input) <= len(available_resolutions):
                    selected_res = available_resolutions[int(user_input) - 1]
                    break
                elif user_input in available_resolutions or (user_input.isdigit() and user_input + "p" in available_resolutions):
                    selected_res = user_input if user_input in available_resolutions else user_input + "p"
                    break
                else:
                    print("Invalid input. Please enter a valid number or resolution.")
    
    if not is_local_file:
        download_audio_str = os.getenv("DOWNLOAD_AUDIO")
        if download_audio_str:
            if download_audio_str.lower() in YesNo.YES.value:
                download_audio = True
                print(f"Loaded DOWNLOAD_AUDIO: {download_audio_str} (from {profile_name})")
            elif download_audio_str.lower() in YesNo.NO.value:
                download_audio = False
                print(f"Loaded DOWNLOAD_AUDIO: {download_audio_str} (from {profile_name})")
            else:
                print(f"Invalid value for DOWNLOAD_AUDIO in .env: {download_audio_str}")
                download_audio = get_yes_no_input("Download audio only? (y/N): ", default='n')

    transcribe_audio_str = os.getenv("TRANSCRIBE_AUDIO")
    if transcribe_audio_str:
        if transcribe_audio_str.lower() in YesNo.YES.value:
            transcribe_audio = True
            print(f"Loaded TRANSCRIBE_AUDIO: {transcribe_audio_str} (from {profile_name})")
        elif transcribe_audio_str.lower() in YesNo.NO.value:
            transcribe_audio = False
            print(f"Loaded TRANSCRIBE_AUDIO: {transcribe_audio_str} (from {profile_name})")
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
        else:
            print(f"Loaded MODEL_CHOICE: {model_choice} (from {profile_name})")  # Indicate successful load from config.env
    elif transcribe_audio:
        model_choice = get_model_choice_input()  # Use the validation function

    if transcribe_audio:
        # Set model based on user input (default to "base") using match statement
        if model_choice in ('1', '2', '3', '4', '5', '6', '7'):
            # Number choice
            model_enum = ModelSize.get_model_by_number(model_choice)
            model_name = model_enum.value
        else:
            # Name choice or empty (default)
            if model_choice == '':
                model_enum = ModelSize.BASE
            else:
                model_enum = ModelSize.get_model_by_name(model_choice)
            model_name = model_enum.value

        target_language = os.getenv("TARGET_LANGUAGE")
        if target_language:
            # Use target_language from .env
            if target_language.lower() not in whisper.tokenizer.LANGUAGES:
                print(f"Invalid value for TARGET_LANGUAGE in .env: {target_language}")
                target_language = get_target_language_input()
            else:
                print(f"Loaded TARGET_LANGUAGE: {target_language} (from {profile_name})")  # Indicate successful load from config.env
        else:
            target_language = get_target_language_input()
            if not target_language:
                target_language = DEFAULT_LANGUAGE  # Default to English

        use_en_model_str = os.getenv("USE_EN_MODEL")
        if use_en_model_str and transcribe_audio:
            if use_en_model_str.lower() in YesNo.YES.value:
                use_en_model = True
                print(f"Loaded USE_EN_MODEL: {use_en_model_str} (from {profile_name})")
            elif use_en_model_str.lower() in YesNo.NO.value:
                use_en_model = False
                print(f"Loaded USE_EN_MODEL: {use_en_model_str} (from {profile_name})")
            elif transcribe_audio:
                print(f"Invalid value for USE_EN_MODEL in .env: {use_en_model_str}")
                if model_enum in ModelSize.standard_models() and target_language == DEFAULT_LANGUAGE:
                    use_en_model = get_yes_no_input("Use English-specific model? (Recommended only if the video is originally in English) (y/N): ", default='n')
                else:
                    use_en_model = False

# --- Now, proceed with the rest of the script using the gathered parameters ---

print("\nProcessing...")  # Indicate step

# Create a YouTube object from the URL ONLY if it's NOT a local file
if not is_local_file:
    try:
        # Create YouTube object
        yt = YouTube(url, "WEB")
    except RegexMatchError:
        # Instead of checking extensions, use ffprobe to determine if it's a valid audio/video file
        file_format = get_file_format(url)
        if file_format:
            is_local_file = True
        else:
            print("Incorrect value. Please enter a valid YouTube video URL or local file path.")

    # Extract the filename base from the video title
    video_title = yt.title
else:  # If it's a local file, extract the filename base from the URL
    video_title = os.path.splitext(os.path.basename(url))[0]  # Get filename without extension

filename_base = "".join(c for c in video_title if c.isalnum() or c in "._- ")
print(f"Processing: {video_title}")  # Indicate step

if download_video and not is_local_file:
    match resolution:
        case Resolution.HIGHEST.value:
            streams = yt.streams.filter(only_video=True)
            streams = sorted(streams, key=lambda stream: int(stream.resolution[:-1]) if stream.resolution else 0, reverse=True)
            stream = streams[0] if streams else None

        case Resolution.LOWEST.value:
            streams = yt.streams.filter(only_video=True)
            streams = sorted(streams, key=lambda stream: int(stream.resolution[:-1]) if stream.resolution else 0, reverse=True)
            stream = streams[-1] if streams else None

        case Resolution.FETCH.value:
            stream = yt.streams.filter(only_video=True, resolution=selected_res)

        case _:
            streams = yt.streams.filter(only_video=True, resolution=resolution)
            streams = sorted(streams, key=lambda stream: int(stream.resolution[:-1]) if stream.resolution else 0, reverse=True)
            stream = streams[0] if streams else None

    # If the requested resolution is not found, prompt the user
    if stream is None:
        print("Requested resolution not found, left null, or invalid.")
        available_streams = yt.streams.filter(only_video=True)  # Define available_streams here

        # Order streams by resolution numerically
        available_streams = sorted(available_streams, key=lambda stream: int(stream.resolution[:-1]) if stream.resolution else 0, reverse=True)

        # Use a set to get unique resolutions and then order them
        available_resolutions = set([stream.resolution for stream in available_streams if stream.resolution])
        available_resolutions = sorted(available_resolutions, key=lambda res: int(res[:-1]) if res else 0, reverse=True)

        if not available_resolutions:
            print("No video streams found. Exiting...")
            exit()

        print("Available resolutions:")
        for i, res in enumerate(available_resolutions):
            print(f"{i+1}. {res}")

        while True:
            user_input = input("Enter desired resolution (number or resolution, default highest): ").lower()
            if not user_input:
                selected_res = available_resolutions[0]  # Default to highest
                break
            elif user_input.isdigit() and 1 <= int(user_input) <= len(available_resolutions):
                selected_res = available_resolutions[int(user_input) - 1]
                break
            elif user_input in available_resolutions or (user_input.isdigit() and user_input + "p" in available_resolutions):
                selected_res = user_input if user_input in available_resolutions else user_input + "p"
                break
            else:
                print("Invalid input. Please enter a valid number or resolution.")

        stream = yt.streams.filter(only_video=True, resolution=selected_res).first()

        if stream is None:
            print(f"Error: No suitable stream found for resolution {selected_res}. Exiting...")
            exit()

    # Set output path based on audio preference
    if no_audio_in_video:
        filename = filename_base + MP4_EXT
        output_path = VIDEO_WITHOUT_AUDIO_DIR

        # Download the selected stream
        print(f"Downloading video stream ({stream.resolution} {'with audio' if not no_audio_in_video else 'without audio'})...")  # Modified print statement
        stream.download(output_path=output_path, filename=filename)
        file_path = os.path.abspath(output_path + "/" + filename)
        print(f"Video downloaded to {file_path}")
    else:
        video_temp_dir = os.path.join(VIDEO_DIR, TEMP_DIR)
        os.makedirs(video_temp_dir, exist_ok=True)

        video_filename = filename_base + MP4_EXT
        audio_filename = filename_base + MP3_EXT

        if resolution == Resolution.FETCH.value:
            stream = yt.streams.filter(only_video=True, resolution=selected_res).first()

        # Download the selected video stream
        stream.download(output_path=video_temp_dir, filename=video_filename)
        video_path = os.path.join(video_temp_dir, video_filename)
        print(f"Video downloaded to {video_path}")

else:
    print("Skipping video download...")  # Indicate that video download is skipped
    
if download_audio:  # Download audio if needed for video or audio-only
    print("Downloading the audio stream (highest quality)...")

    audio_streams = yt.streams.filter(only_audio=True)  # Get audio stream query

    # Order audio streams by bitrate numerically, but keep it as a stream query
    audio_streams = sorted(audio_streams, key=lambda stream: int(stream.abr[:-4]) if stream.abr else 0, reverse=True)

    audio_stream = audio_streams[0]  # Select the first stream from the sorted list


    # Set output_path and filename for the audio file
    #output_path = "Audio" if download_audio else os.path.join("Audio", "Temp")
    audio_path = AUDIO_DIR
    filename = filename_base + MP3_EXT

    # Download the audio stream
    audio_stream.download(output_path=audio_path, filename=filename)
    file_path = os.path.abspath(os.path.join(audio_path, filename))
    print(f"Audio downloaded to {file_path}")

if download_video and not no_audio_in_video:
    audio_path = os.path.join(AUDIO_DIR, audio_filename)
    if not download_audio:
        # Download the audio stream
        print("Downloading the audio stream (highest quality)...")
        audio_temp_dir = os.path.join(AUDIO_DIR, TEMP_DIR)
        os.makedirs(audio_temp_dir, exist_ok=True)
        audio_streams = yt.streams.filter(only_audio=True)  # Get audio stream query
        # Order audio streams by bitrate numerically, but keep it as a stream query
        audio_streams = sorted(audio_streams, key=lambda stream: int(stream.abr[:-4]) if stream.abr else 0, reverse=True)
        audio_stream = audio_streams[0]  # Select the first stream from the sorted list
        audio_stream.download(output_path=audio_temp_dir, filename=audio_filename)
        audio_path = os.path.abspath(os.path.join(audio_temp_dir, audio_filename))
        print(f"Audio downloaded to {audio_path}")
        audio_path = os.path.join(audio_temp_dir, audio_filename)

    # Mux with ffmpeg
    output_path_combined = os.path.join(VIDEO_DIR, video_filename)  # Use original filename
    command = f'ffmpeg -i "{video_path}" -i "{audio_path}" -c:v copy -c:a aac "{output_path_combined}"'
    os.system(command)

    if not no_audio_in_video:
        # Delete temporary files and directories
        os.remove(video_path)
        os.rmdir(video_temp_dir)

    print(f"Combined video saved to {output_path_combined}")

if transcribe_audio:
    if is_local_file:  # Check if it's a local file
        if is_valid_media_file(url):  # Check if it's a valid media file
            audio_file = url  # Use the URL directly as the audio file
        else:  # If it's not an MP3 file, assume it's an MP4
            video = VideoFileClip(url)  # Create a VideoFileClip object from the URL
            audio_file = f"{filename_base}.mp3"  # Create a filename for the extracted audio
            video.audio.write_audiofile(audio_file)  # Extract the audio from the video
    else:  # If it's not a local file, it's a YouTube video
        audio_filename = filename_base + MP3_EXT
        audio_file = os.path.join(AUDIO_DIR, audio_filename)  # Use the downloaded audio file
        if not download_audio and ((not download_audio) or (download_video and no_audio_in_video)):
            # Download the audio stream
            print("Downloading the audio stream (highest quality)...")
            audio_temp_dir = os.path.join(AUDIO_DIR, TEMP_DIR)
            audio_filename = filename_base + MP3_EXT
            os.makedirs(audio_temp_dir, exist_ok=True)
            audio_streams = yt.streams.filter(only_audio=True)  # Get audio stream query
            # Order audio streams by bitrate numerically, but keep it as a stream query
            audio_streams = sorted(audio_streams, key=lambda stream: int(stream.abr[:-4]) if stream.abr else 0, reverse=True)
            audio_stream = audio_streams[0]  # Select the first stream from the sorted list
            audio_stream.download(output_path=audio_temp_dir, filename=audio_filename)
            audio_file = os.path.abspath(os.path.join(audio_temp_dir, audio_filename))
            print(f"Audio downloaded to {audio_file}")
            audio_file = os.path.join(audio_temp_dir, audio_filename)

    # Load the selected model
    model = whisper.load_model(model_name)

    target_language_full = whisper.tokenizer.LANGUAGES.get(target_language, target_language)
    target_language_full = target_language_full.capitalize()

    if is_local_file:  # Use the user-provided path for local files
        file_path = url
    else:  # Use the default "Audio/" path for YouTube downloads
        file_path = audio_file

    absolute_path = os.path.abspath(file_path)
    print(f"Transcribing audio from {absolute_path} into {target_language_full}...")
    result = model.transcribe(file_path, language=target_language)  # Use file_path here
    transcribed_text = result["text"]
    print("\nTranscription:\n" + transcribed_text + "\n")

    # Detect the language
    language = detect(transcribed_text)
    language_full = whisper.tokenizer.LANGUAGES.get(language, language)  # Get full name or use code if not found
    language_full = language_full.capitalize()  # Capitalize the first letter
    if language_full == target_language_full:
        print(f"Verified {language_full}")
    else:
        print("Transcription/translation mismatch")

    # Create and open a txt file with the text
    if language == DEFAULT_LANGUAGE:
        create_and_open_txt(transcribed_text, f"{filename_base}{TXT_EXT}")
        file_path = os.path.abspath(f"{TRANSCRIPT_DIR}/{filename_base}{TXT_EXT}")
        print(f"Saved transcript to {file_path}")  # Indicate location
    else:
        create_and_open_txt(transcribed_text, f"{filename_base} [{language}]{TXT_EXT}")
        file_path = os.path.abspath(f"{TRANSCRIPT_DIR}/{filename_base} [{language}]{TXT_EXT}")
        print(f"Saved transcript to {file_path}")  # Indicate location
else:
    print("Skipping transcription.")
    transcribed_text = ""  # Assign an empty string

if not download_audio and (transcribe_audio or download_video) and not no_audio_in_video:
    output_path = os.path.join(AUDIO_DIR, TEMP_DIR)  # Set output_path here, before os.remove()
    filename = filename_base + MP3_EXT
    os.remove(os.path.join(output_path, filename))  # Remove the audio file
    os.rmdir(output_path)
    print(f"Deleted audio residual in {file_path}")

print("Tasks complete.")

if not load_profile:
    create_profile_prompt = get_yes_no_input("Do you want to create a profile from this session? (y/N): ", default='n')
    if create_profile_prompt:
        create_profile(used_fields)
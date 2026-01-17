# Downloads audio/video from YouTube and transcribes it using OpenAI's Whisper
# Author: Ruinan Ding

# Run with: python OpenAIYouTubeTranscriber.py

#########################################
## IMPORTS
#########################################

# Standard library imports
import sys
import os
import re
import subprocess
import shutil
from enum import Enum
from urllib.parse import urlparse

# Third-party imports
import whisper
import moviepy
from langdetect import detect, LangDetectException
from pytubefix import YouTube
from pytubefix.exceptions import RegexMatchError, VideoUnavailable, VideoPrivate, VideoRegionBlocked
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type

#########################################
## ENUMS
#########################################

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

#########################################
## TRANSCRIBER CLASS
#########################################

class YouTubeTranscriber:
    """Handles YouTube downloads and Whisper transcription."""
    
    # Data directories
    DATA_DIR = "OpenAIYouTubeTranscriber"
    AUDIO_DIR = os.path.join(DATA_DIR, "Audio")
    TEMP_DIR = "Temp"
    VIDEO_DIR = os.path.join(DATA_DIR, "Video")
    TRANSCRIPT_DIR = os.path.join(DATA_DIR, "Transcript")
    VIDEO_WITHOUT_AUDIO_DIR = os.path.join(DATA_DIR, "VideoWithoutAudio")
    profile_dir = os.path.join(DATA_DIR, "Profile")
    MP3_EXT = ".mp3"
    MP4_EXT = ".mp4"
    TXT_EXT = ".txt"
    PROFILE_PREFIX = "profile"
    ENV_EXT = ".txt"
    CONFIG_ENV = f"config{ENV_EXT}"
    PROFILE_NAME_TEMPLATE = f"{PROFILE_PREFIX}{{}}{ENV_EXT}"
    DEFAULT_PROFILE = f"{PROFILE_PREFIX}{ENV_EXT}"
    URL_PLACEHOLDER = "<Insert_YouTube_link_or_local_path_to_audio_or_video>"
    DEFAULT_LANGUAGE = 'en'
    
    # Default field values for profile creation
    DEFAULT_FIELDS = {
        "URL": URL_PLACEHOLDER,
        "DOWNLOAD_VIDEO": "",
        "NO_AUDIO_IN_VIDEO": "",
        "RESOLUTION": "",
        "DOWNLOAD_AUDIO": "",
        "TRANSCRIBE_AUDIO": "",
        "MODEL_CHOICE": "",
        "TARGET_LANGUAGE": "",
        "USE_EN_MODEL": "",
        "REPEAT": ""
    }
    
    def __init__(self):
        """Set up defaults."""
        # Operation params
        self.url = None
        self.is_local_file = False
        self.yt_object = None
        self.video_title = None
        self.filename_base = None
        
        # Download settings
        self.download_video = False
        self.no_audio_in_video = False
        self.resolution = None
        self.selected_res = None
        self.download_audio = False
        
        # Transcription options
        self.transcribe_audio = True
        self.model_name = ModelSize.BASE.value
        self.model_enum = ModelSize.BASE
        self.target_language = self.DEFAULT_LANGUAGE
        self.use_en_model = False
        
        # Profile stuff
        self.profile_dir = os.path.join(self.DATA_DIR, "Profile")
        self.load_profile = False
        self.loaded_profile = False
        self.interactive_mode = False
        self.profile_name = None
        
        self.used_fields = self.DEFAULT_FIELDS.copy()
        self._create_required_dirs()
        
    def _create_required_dirs(self):
        """Make directories we need."""
        required_dirs = [
            self.AUDIO_DIR, 
            self.VIDEO_DIR, 
            self.TRANSCRIPT_DIR, 
            self.VIDEO_WITHOUT_AUDIO_DIR
        ]
        for directory in required_dirs:
            os.makedirs(directory, exist_ok=True)

    def ensure_directory_exists(self, directory_path):
        """Create directory if it doesn't exist. Returns True on success."""
        try:
            os.makedirs(directory_path, exist_ok=True)
            return True
        except (PermissionError, OSError) as e:
            print(f"Error creating directory {directory_path}: {str(e)}")
            return False

    def is_web_url(self, input_str):
        """Check if string is a valid http/https URL (no network calls)."""
        try:
            result = urlparse(input_str)
            return all([result.scheme in ['http', 'https'], result.netloc])
        except ValueError:
            return False

    def is_youtube_video_id(self, text):
        """Check if text is a valid 11-character YouTube video ID (letters, numbers, dash, underscore only)."""
        if len(text) != 11:
            return False
        import re
        return bool(re.match(r'^[a-zA-Z0-9_-]{11}$', text))
    
    def construct_youtube_url(self, video_id):
        """Build full YouTube URL from video ID. Query params get stripped by pytubefix automatically."""
        return f"https://www.youtube.com/watch?v={video_id}"

    def is_youtube_url(self, url):
        """Validate YouTube URL using pytubefix. Extracts video ID from any format (standard, short, embed URLs)."""
        try:
            YouTube(url, "WEB")
            return True
        except (RegexMatchError, VideoUnavailable, VideoPrivate, VideoRegionBlocked):
            return False
        except (ValueError, OSError) as e:
            print(f"Warning: Error checking YouTube URL: {str(e)}")
            return False

    def is_valid_media_file(self, path):
        """Check if path is a supported audio/video file."""
        if not os.path.exists(path):
            return False
            
        format_name = self.get_file_format(path)
        if format_name is not None:
            return True
            
        valid_extensions = ['.mp3', '.mp4', '.wav', '.avi', '.mov', '.mkv', '.flac', '.ogg', '.m4a', '.webm']
        file_ext = os.path.splitext(path)[1].lower()
        return file_ext in valid_extensions

    def get_file_format(self, file_path):
        """Get media format using ffprobe."""
        try:
            cmd = [
                'ffprobe', '-v', 'error', 
                '-show_entries', 'format=format_name',
                '-of', 'default=noprint_wrappers=1:nokey=1', 
                file_path
            ]
            result = subprocess.run(
                cmd, capture_output=True, text=True, check=True
            )
            return result.stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print(f"Error with ffprobe: {str(e)}")
            return None

    def get_yes_no_input(self, prompt_text, default="y"):
        """Prompt user for yes/no input with validation."""
        while True:
            user_input = input(prompt_text).lower()
            if user_input in YesNo.YES.value:
                return True
            elif user_input in YesNo.NO.value:
                return False
            elif user_input == "":
                return default == 'y'
            else:
                print(f"Invalid input. Please enter one of {YesNo.YES.value + YesNo.NO.value}.")

    def get_model_choice_input(self):
        """Prompt for Whisper model selection (1-7 or name)."""
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

    def get_target_language_input(self):
        """Prompt for target language (validates against Whisper's supported list)."""
        while True:
            prompt = (
                "Enter the target language for transcription (e.g., 'es' or 'spanish', "
                f"default '{self.DEFAULT_LANGUAGE}'). See supported languages at "
                "https://github.com/openai/whisper#supported-languages): "
            )
            target_language = input(prompt).lower()
            
            if not target_language:
                return self.DEFAULT_LANGUAGE
            
            in_codes = target_language in whisper.tokenizer.LANGUAGES
            in_names = target_language in whisper.tokenizer.LANGUAGES.values()
            
            if in_codes or in_names:
                return target_language
            else:
                print("Invalid language code or name. Please refer to the supported "
                      "languages list and try again.")

    def startfile(self, fn):
        """Open file with system default app (cross-platform)."""
        if os.name == 'nt':  # Windows
            os.startfile(fn)
        elif os.name == 'posix':  # macOS or Linux
            opener = 'open' if sys.platform == 'darwin' else 'xdg-open'
            subprocess.run([opener, fn], check=True)

    def sanitize_filename(self, text):
        """Strip invalid characters from filename."""
        return "".join(c for c in text if c.isalnum() or c in "._- ")

    def create_and_open_txt(self, text, filename):
        output_dir = os.path.join(os.path.dirname(__file__), self.TRANSCRIPT_DIR)
        
        if not self.ensure_directory_exists(output_dir):
            print(f"Error: Cannot create transcript directory {output_dir}")
            return False
            
        file_path = os.path.join(output_dir, filename)
        
        if not self.verify_file_writable(file_path):
            print(f"Error: Cannot write to transcript file {file_path}")
            return False
            
        required_space = max(len(text) * 2, 1024 * 1024)
        free_space = self.get_free_disk_space(output_dir)
        if free_space is not None and free_space < required_space:
            print(f"Error: Not enough disk space to save transcript. Need {required_space/1024/1024:.1f}MB, have {free_space/1024/1024:.1f}MB free.")
            return False

        try:
            with open(file_path, "w", encoding='utf-8') as file:
                file.write(text)
            self.startfile(file_path)
            return True
        except (PermissionError, OSError) as e:
            print(f"Error writing transcript file: {str(e)}")
            return False

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2), 
           retry=retry_if_exception_type(Exception))
    def create_youtube_object(self, url):
        """Create YouTube object (retries up to 3 times on failures)."""
        try:
            return YouTube(url, "WEB")
        except (RegexMatchError, VideoUnavailable, VideoPrivate, VideoRegionBlocked, ValueError, OSError) as e:
            print(f"Error creating YouTube object: {str(e)}")
            raise

    def get_sorted_video_streams(self, yt):
        """Get available video streams sorted by resolution (highest first)."""
        try:
            streams = yt.streams.filter(only_video=True)
            return sorted(
                streams, 
                key=lambda stream: int(stream.resolution[:-1]) if stream.resolution else 0,  # [:-1] strips 'p' from '1080p' 
                reverse=True
            )
        except (AttributeError, ValueError, OSError) as e:
            print(f"Error retrieving video streams: {str(e)}")
            return []

    def get_sorted_audio_streams(self, yt):
        """Get available audio streams sorted by bitrate (highest first)."""
        try:
            audio_streams = yt.streams.filter(only_audio=True)
            return sorted(
                audio_streams, 
                key=lambda stream: int(stream.abr[:-4]) if stream.abr else 0,  # [:-4] strips 'kbps' from '128kbps' 
                reverse=True
            )
        except (AttributeError, ValueError) as e:
            print(f"Error retrieving audio streams: {str(e)}")
            return []

    def get_unique_sorted_resolutions(self, streams):
        """Extract unique resolutions from streams and sort by quality (highest first)."""
        resolutions = set([stream.resolution for stream in streams if stream.resolution])
        
        return sorted(
            resolutions, 
            key=lambda res: int(res[:-1]) if res else 0,  # Strip 'p' suffix for numeric sorting 
            reverse=True
        )

    def download_audio_stream(self, yt, filename_base, is_temp=False):
        """Download highest quality audio stream (optionally to temp directory)."""
        print("Downloading the audio stream (highest quality)...")
        
        audio_streams = self.get_sorted_audio_streams(yt)
        
        if not audio_streams:
            raise ValueError("No audio streams available for this video")
            
        audio_stream = audio_streams[0]
        
        audio_filename = filename_base + self.MP3_EXT
        
        if is_temp:
            output_dir = os.path.join(self.AUDIO_DIR, self.TEMP_DIR)
            os.makedirs(output_dir, exist_ok=True)
        else:
            output_dir = self.AUDIO_DIR
            os.makedirs(output_dir, exist_ok=True)
        
        relative_path = os.path.join(output_dir, audio_filename)
        
        @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
        def download_with_retry():
            audio_stream.download(output_path=output_dir, filename=audio_filename)
            if not os.path.exists(relative_path):
                raise FileNotFoundError(f"Failed to download audio stream to {relative_path}")
            return True
        
        download_with_retry()
        
        absolute_path = os.path.abspath(relative_path)
        print(f"Audio downloaded to {absolute_path}")
        
        return relative_path, absolute_path

    def combine_audio_video(self, video_path, audio_path, output_path, cleanup_temp=True, temp_video_dir=None):
        """Merge separate video and audio files using ffmpeg."""
        output_dir = os.path.dirname(output_path)
        if not self.ensure_directory_exists(output_dir):
            print(f"Error: Cannot create video output directory {output_dir}")
            return None
            
        if not self.verify_file_writable(output_path):
            print(f"Error: Cannot write to output video file {output_path}")
            return None
            
        try:
            video_size = os.path.getsize(video_path)
            audio_size = os.path.getsize(audio_path)
            required_space = (video_size + audio_size) * 1.5
            
            free_space = self.get_free_disk_space(output_dir)
            if free_space is not None and free_space < required_space:
                print(f"Error: Not enough disk space to combine video. Need {required_space/1024/1024:.1f}MB, have {free_space/1024/1024:.1f}MB free.")
                return None
        except (OSError, IOError) as e:
            print(f"Warning: Could not verify file sizes: {str(e)}")
        
        if not os.path.exists(video_path):
            print(f"Error: Video file not found: {video_path}")
            return None
            
        if not os.path.exists(audio_path):
            print(f"Error: Audio file not found: {audio_path}")
            return None
        
        command = f'ffmpeg -y -i "{video_path}" -i "{audio_path}" -c:v copy -c:a aac "{output_path}"'
        
        try:
            subprocess.run(command, shell=True, capture_output=True, text=True, check=True)
        except subprocess.CalledProcessError as e:
            print(f"Error combining audio and video: {e.stderr}")
            return None
        except OSError:
            print("Error running ffmpeg")
            return None
        
        if not os.path.exists(output_path):
            print("Error: Failed to create combined video file")
            return None
        
        if cleanup_temp:
            try:
                if os.path.exists(video_path):
                    os.remove(video_path)
                if temp_video_dir and os.path.exists(temp_video_dir):
                    os.rmdir(temp_video_dir)
            except (PermissionError, OSError) as e:
                print(f"Warning: Could not clean up temporary files: {str(e)}")
        
        print(f"Combined video saved to {output_path}")
        return output_path

    def transcribe_audio_file(self, file_path, model_name, target_language):
        """Transcribe audio file using Whisper and detect the language."""
        if not os.path.exists(file_path):
            error_msg = f"Error: Audio file not found: {file_path}"
            print(error_msg)
            return error_msg, "en"
        
        try:
            print(f"Loading Whisper model: {model_name}")
            model = whisper.load_model(model_name)
        except (OSError, ValueError) as load_error:
            print(f"Error loading Whisper model: {str(load_error)}")
            fallback_model = "base"
            print("Falling back to base model")
            try:
                model = whisper.load_model(fallback_model)
            except (OSError, ValueError) as fallback_error:
                error_msg = f"Error loading fallback model: {str(fallback_error)}"
                print(error_msg)
                return "Error: Unable to load Whisper model", "en"
        
        target_language_full = whisper.tokenizer.LANGUAGES.get(target_language, target_language)
        target_language_full = target_language_full.capitalize()
        
        absolute_path = os.path.abspath(file_path)
        print(f"Transcribing audio from {absolute_path} into {target_language_full}...")
        
        try:
            result = model.transcribe(file_path, language=target_language)
            transcribed_text = result["text"]
            
            if not transcribed_text.strip():
                print("Warning: Transcription produced empty text. The audio might be silent or not contain speech.")
                return "No speech detected in audio.", target_language
                
        except (RuntimeError, ValueError) as e:
            error_msg = f"Error during transcription: {str(e)}"
            print(error_msg)
            return error_msg, "en"
        
        print("\nTranscription:\n" + transcribed_text + "\n")
        
        try:
            detected_language = detect(transcribed_text)
            detected_language_full = whisper.tokenizer.LANGUAGES.get(detected_language, detected_language)
            detected_language_full = detected_language_full.capitalize()
            
            if detected_language_full == target_language_full:
                print(f"Verified {detected_language_full}")
            else:
                print("Transcription/translation mismatch")
        except LangDetectException as e:
            print(f"Error detecting language: {str(e)}")
            detected_language = "unknown"
        
        return transcribed_text, detected_language

    def check_dependencies(self):
        """Verify required system dependencies (ffmpeg) are installed."""
        # ffmpeg needed for format detection (ffprobe) and combining video/audio streams
        ffmpeg_available = shutil.which("ffmpeg") is not None
        if not ffmpeg_available:
            print("ERROR: ffmpeg is not found in the system PATH.")
            print("Please install ffmpeg and make sure it's in your PATH:")
            print("- Windows: https://ffmpeg.org/download.html")
            print("- macOS: brew install ffmpeg")
            print("- Linux: apt-get install ffmpeg")
            return False
        
        return True

    def create_profile(self, profile_fields):
        """Save current session settings as a reusable profile file."""
        if not os.path.exists(self.profile_dir):
            print(f"Creating profile directory: {self.profile_dir}")
            os.makedirs(self.profile_dir, exist_ok=True)
        
        config_path = os.path.join(self.profile_dir, self.CONFIG_ENV)
        if not os.path.exists(config_path):
            with open(config_path, "w", encoding='utf-8') as config_file:
                config_file.write("# Configuration file for YouTube Transcriber\n")
                config_file.write(f"LOAD_PROFILE={self.DEFAULT_PROFILE}")
            print(f"Created {self.CONFIG_ENV}: {os.path.abspath(config_path)}")
        else:
            print(f"{self.CONFIG_ENV} already exists: {os.path.abspath(config_path)}. "
                  "No changes were made to it.")

        # Accepts: profile.txt, profile<number>.txt, profile-<desc>.txt, profile<number>-<desc>.txt
        profile_pattern = rf"^{re.escape(self.PROFILE_PREFIX)}(?:\d+)?(?:-.*)?{re.escape(self.ENV_EXT)}$"
        existing_profiles = [
            f for f in os.listdir(self.profile_dir)
            if re.match(profile_pattern, f)
        ]
        num_pattern = rf"^{re.escape(self.PROFILE_PREFIX)}(?P<num>\d+)(?:-.*)?{re.escape(self.ENV_EXT)}$"
        existing_numbers = []
        for f in existing_profiles:
            m = re.match(num_pattern, f)
            if m:
                try:
                    existing_numbers.append(int(m.group('num')))
                except (ValueError, TypeError):
                    continue
        
        if not existing_profiles:
            profile_name = self.DEFAULT_PROFILE
        else:
            next_number = 0
            while next_number in existing_numbers:
                next_number += 1
            profile_name = self.PROFILE_NAME_TEMPLATE.format(next_number)

        profile_path = os.path.join(self.profile_dir, profile_name)

        with open(profile_path, "w", encoding='utf-8') as profile_file:
            profile_file.write("# Edit values after the = sign\n\n")
            
            field_order = [
                "URL",
                "DOWNLOAD_VIDEO",
                "NO_AUDIO_IN_VIDEO",
                "RESOLUTION",
                "DOWNLOAD_AUDIO",
                "TRANSCRIBE_AUDIO",
                "MODEL_CHOICE",
                "TARGET_LANGUAGE",
                "USE_EN_MODEL",
                "REPEAT"
            ]
            
            for i, field in enumerate(field_order):
                if field in profile_fields:
                    newline = "" if i == len(field_order) - 1 else "\n"
                    profile_file.write(f"{field}={profile_fields[field]}{newline}")

        print(f"Created profile: {os.path.abspath(profile_path)}")

    def verify_file_writable(self, file_path):
        """Check if file path is writable (creates parent dirs if needed)."""
        try:
            if os.path.exists(file_path):
                return os.access(file_path, os.W_OK)
            
            parent_dir = os.path.dirname(file_path)
            if not parent_dir:
                parent_dir = '.'
            
            if not os.path.exists(parent_dir):
                try:
                    os.makedirs(parent_dir, exist_ok=True)
                except (PermissionError, OSError):
                    return False
            
            return os.access(parent_dir, os.W_OK)
        except (OSError, IOError):
            return False

    def get_free_disk_space(self, directory):
        """Get available disk space in bytes for the given directory."""
        try:
            if os.path.exists(directory):
                target_dir = directory
            else:
                target_dir = os.path.dirname(directory)
                if not target_dir:
                    target_dir = '.'
            
            if not os.path.exists(target_dir):
                target_dir = '.'
                
            return shutil.disk_usage(target_dir).free
        except (OSError, IOError, ValueError) as e:
            print(f"Error checking disk space: {str(e)}")
            return None

#########################################
## MAIN EXECUTION
#########################################

def main():
    """Main entry point - handles user interaction and orchestrates transcription workflow."""
    transcriber = YouTubeTranscriber()
    
    used_fields = transcriber.DEFAULT_FIELDS.copy()
    
    if not transcriber.check_dependencies():
        print("Missing required dependencies. Please install them and try again.")
        sys.exit(1)
        
    required_dirs = [
        transcriber.AUDIO_DIR, 
        transcriber.VIDEO_DIR, 
        transcriber.TRANSCRIPT_DIR,
        transcriber.VIDEO_WITHOUT_AUDIO_DIR
    ]
    for directory in required_dirs:
        if not transcriber.ensure_directory_exists(directory):
            print(f"Error: Cannot create required directory {directory}")
            print("Please check permissions and try again.")
            sys.exit(1)

    load_profile = False
    loaded_profile = False
    interactive_mode = False

    # Check if this is a recursive call from user choosing "repeat" option
    repeat_invocation = os.environ.get("_REPEAT_INVOCATION", "") == "1"
    repeat_profile_name = os.environ.get("_REPEAT_PROFILE_NAME")
    repeat_without_profile = repeat_invocation and not repeat_profile_name

    if repeat_invocation and repeat_profile_name:
        profile_name = repeat_profile_name
        profile_path = os.path.join(transcriber.profile_dir, profile_name)
        if os.path.exists(profile_path):
            load_profile = True
            loaded_profile = True
            interactive_mode = False
            load_dotenv(dotenv_path=profile_path, override=True)
            print(f"Loaded profile (repeat): {profile_name}")
        else:
            print(f"Profile not found for repeat: {profile_name}. Falling back to selection.")
    elif repeat_without_profile:
        load_profile = False
        interactive_mode = True

    if not repeat_without_profile:
        config_env_path = os.path.join(transcriber.profile_dir, transcriber.CONFIG_ENV)
        if not os.path.exists(config_env_path):
            print(
                f"config.txt not found in the {transcriber.profile_dir} directory."
            )
            if os.path.exists(transcriber.profile_dir):
                # Accepts: profile.txt, profile<number>.txt, profile-<desc>.txt, profile<number>-<desc>.txt
                profile_pattern = rf"^{re.escape(transcriber.PROFILE_PREFIX)}(?:\d+)?(?:-.*)?{re.escape(transcriber.ENV_EXT)}$"
                profiles = sorted([f for f in os.listdir(transcriber.profile_dir) if re.match(profile_pattern, f)])
                if profiles:
                    print("Found existing profiles. Checking if you want to use one of them...")
                    print("Available profiles:")
                    for i, profile in enumerate(profiles):
                        print(f"{i+1}. {profile}")

                    while True:
                        profile_input = input(
                            f"Select a profile (number or name, default 1. {profiles[0]}, "
                            f"or 'no' / 'n' / 'false' / 'f' / '0' / 'skip' / 's' to skip): "
                        )
                        lower_input = profile_input.lower()
                        if profile_input == '' or lower_input == '1':
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
                        elif profile_input + transcriber.ENV_EXT in profiles:
                            profile_name = profile_input + transcriber.ENV_EXT
                            load_profile = True
                            break
                        elif lower_input in YesNo.all_no_and_skip():
                            print("Switching to default/interactive mode.")
                            load_profile = False
                            break
                        else:
                            print("Invalid profile selection.")

                    if load_profile:
                        # Load the selected profile
                        profile_path = os.path.join(transcriber.profile_dir, profile_name)
                        load_dotenv(dotenv_path=profile_path, override=True)
                        print(f"Loaded profile: {profile_name}")
                else:
                    print("No profiles found. Switching to default/interactive mode.")
                    load_profile = False
                    interactive_mode = True
            else:
                print("Switching to default/interactive mode.")
                load_profile = False
                interactive_mode = True
        else:
            print(f"config.txt detected in the {transcriber.profile_dir} directory.")
            load_dotenv(dotenv_path=config_env_path, override=True)
            # Manually read LOAD_PROFILE from config.txt to ensure accurate value
            load_profile_str = None
            with open(config_env_path, 'r', encoding='utf-8') as cf:
                for line in cf:
                    if line.strip().startswith("LOAD_PROFILE"):
                        _, val = line.split("=", 1)
                        load_profile_str = val.strip()
                        os.environ["LOAD_PROFILE"] = load_profile_str
                        break

            print(f"LOAD_PROFILE: {load_profile_str} (from config.txt)")
            # Determine if LOAD_PROFILE is specifying a profile name or a boolean
            lower_lp = load_profile_str.lower() if load_profile_str else ''
            # Explicit profile names (not simple yes/no) take precedence
            if load_profile_str and lower_lp not in YesNo.YES.value + YesNo.NO.value + YesNo.SKIP.value + ('',):
                # Treat as profile name
                if not load_profile_str.endswith(transcriber.ENV_EXT):
                    load_profile_str += transcriber.ENV_EXT
                profile_path = os.path.join(transcriber.profile_dir, load_profile_str)
                if os.path.exists(profile_path):
                    load_profile = True
                    loaded_profile = True
                    profile_name = os.path.basename(profile_path)
                    print(f"Loading profile: {profile_name}")
                else:
                    print(f"Profile not found: {load_profile_str}. Using interactive mode.")
                    load_profile = False
                    interactive_mode = True
            else:
                # Interpret as boolean or skip
                if lower_lp in YesNo.YES.value + ('',):
                    load_profile = True
                elif lower_lp in YesNo.NO.value + YesNo.SKIP.value:
                    print("Using default/interactive mode.")
                    load_profile = False
                    interactive_mode = True
                else:
                    # Fallback to interactive
                    load_profile = False
                    interactive_mode = True

            if interactive_mode is False and loaded_profile is False:
                # List available profiles (only if not found or invalid format)
                # Match profile files: profile.txt, profile<number>.txt, profile-<desc>.txt, profile<number>-<desc>.txt
                profile_pattern = rf"^{re.escape(transcriber.PROFILE_PREFIX)}(?:\d+)?(?:-.*)?{re.escape(transcriber.ENV_EXT)}$"
                profiles = sorted([f for f in os.listdir(transcriber.profile_dir) if re.match(profile_pattern, f)])
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
                        elif profile_input + transcriber.ENV_EXT in profiles:
                            profile_name = profile_input + transcriber.ENV_EXT
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
                # Load the selected profile read earlier
                profile_path = os.path.join(transcriber.profile_dir, profile_name)
                load_dotenv(dotenv_path=profile_path, override=True)
                print(f"Loaded profile: {profile_name}")

    # --- Get ALL parameters from user first if not loading from .env ---

    if not load_profile:
        is_local_file = False
        while True:
            url = input("Enter the YouTube video URL, video ID, or local file path: ").strip()
            
            # --- Validation Steps ---
            if transcriber.is_youtube_video_id(url):
                url = transcriber.construct_youtube_url(url)
                print(f"Detected video ID, using: {url}")
                is_local_file = False
                break
            elif transcriber.is_web_url(url):
                if transcriber.is_youtube_url(url):
                    is_local_file = False
                    break
                else:
                    print("Error: Only YouTube URLs supported for web inputs")
                    continue
            elif transcriber.is_valid_media_file(url):
                is_local_file = True
                break
            else:
                print("Invalid input. Please enter valid YouTube URL, video ID, or local file path")
                continue

        download_video = False
        no_audio_in_video = False
        resolution = None
        download_audio = False

        if not is_local_file:
            last_download = os.environ.get("LAST_DOWNLOAD_VIDEO")
            if last_download is not None:
                download_video = last_download.lower() in YesNo.YES.value
                print(f"Using previous DOWNLOAD_VIDEO: {last_download} (from last session)")
            else:
                download_video = transcriber.get_yes_no_input("Download video? (y/N): ", default='n')
            used_fields["DOWNLOAD_VIDEO"] = "y" if download_video else "n"

            if download_video:
                no_audio_in_video = False
                no_audio_prompt = "... without the audio in the video? (y/N): "
                last_no_audio = os.environ.get("LAST_NO_AUDIO_IN_VIDEO")
                if last_no_audio is not None:
                    no_audio_in_video = last_no_audio.lower() in YesNo.YES.value
                    print(f"Using previous NO_AUDIO_IN_VIDEO: {last_no_audio} (from last session)")
                else:
                    no_audio_in_video = transcriber.get_yes_no_input(no_audio_prompt, "n")
                used_fields["NO_AUDIO_IN_VIDEO"] = "y" if no_audio_in_video else "n"

            if download_video:
                last_res = os.environ.get("LAST_RESOLUTION")
                if last_res is not None:
                    resolution = last_res
                    print(f"Using previous RESOLUTION: {resolution} (from last session)")
                else:
                    while True:
                        resolution_prompt = (
                            "... enter desired resolution (e.g., 720p, 720, highest, lowest, "
                            "default get the highest resolutions), or enter fetch or f to get "
                            "a list of available resolutions: "
                        )
                        resolution = input(resolution_prompt)
                        
                        if not resolution:
                            # Default to highest if input is empty
                            resolution = Resolution.HIGHEST.value
                            break
                        
                        # Convert to lowercase after checking for empty input
                        resolution = resolution.lower()
                        
                        if resolution in Resolution.values():
                            if resolution == Resolution.F.value:
                                resolution = Resolution.FETCH.value
                            used_fields["RESOLUTION"] = resolution
                            break
                        elif resolution.endswith("p"):
                            used_fields["RESOLUTION"] = resolution
                            break
                        elif resolution.isdigit():
                            if int(resolution) > 0:
                                resolution += "p"
                                used_fields["RESOLUTION"] = resolution
                                break
                            else:
                                print("Invalid resolution. Please enter a non-zero number.")
                        elif resolution.endswith("p") and resolution[:-1].isdigit():
                            if int(resolution[:-1]) > 0:
                                used_fields["RESOLUTION"] = resolution
                                break
                            else:
                                print("Invalid resolution. Please enter a non-zero number.")
                        else:
                            print("Invalid resolution. Please enter a valid resolution "
                                  "(e.g., 720p, 720, highest, lowest).")
                
                if resolution not in (Resolution.FETCH.value, Resolution.F.value):
                    print(f"Using resolution: {resolution}")
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
                available_streams = transcriber.get_sorted_video_streams(yt)

                # Get unique resolutions sorted by quality
                available_resolutions = transcriber.get_unique_sorted_resolutions(available_streams)

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
            last_da = os.environ.get("LAST_DOWNLOAD_AUDIO")
            if last_da is not None:
                download_audio = last_da.lower() in YesNo.YES.value
                print(f"Using previous DOWNLOAD_AUDIO: {last_da} (from last session)")
            else:
                download_audio = transcriber.get_yes_no_input("Download audio? (y/N): ", default='n')
            used_fields["DOWNLOAD_AUDIO"] = "y" if download_audio else "n"

        last_transcribe = os.environ.get("LAST_TRANSCRIBE_AUDIO")
        if last_transcribe is not None:
            transcribe_audio = last_transcribe.lower() in YesNo.YES.value
            print(f"Using previous TRANSCRIBE_AUDIO: {last_transcribe} (from last session)")
        else:
            transcribe_audio = transcriber.get_yes_no_input("Transcribe the audio? (Y/n): ")
        used_fields["TRANSCRIBE_AUDIO"] = "y" if transcribe_audio else "n"

        if transcribe_audio:
            last_model = os.environ.get("LAST_MODEL_CHOICE")
            if last_model is not None:
                model_choice = last_model
                print(f"Using previous MODEL_CHOICE: {model_choice} (from last session)")
            else:
                model_choice = transcriber.get_model_choice_input()

            # Set model based on user input (default to "base") using match statement
            if model_choice in ('1', '2', '3', '4', '5', '6', '7'):
                model_enum = ModelSize.get_model_by_number(model_choice)
                model_name = model_enum.value
            else:
                if model_choice == '':
                    model_enum = ModelSize.BASE
                else:
                    model_enum = ModelSize.get_model_by_name(model_choice)
                model_name = model_enum.value

            used_fields["MODEL_CHOICE"] = model_name

            last_target = os.environ.get("LAST_TARGET_LANGUAGE")
            if last_target is not None:
                target_language = last_target
                print(f"Using previous TARGET_LANGUAGE: {target_language} (from last session)")
            else:
                target_language = transcriber.get_target_language_input()
            used_fields["TARGET_LANGUAGE"] = target_language

            if model_enum in ModelSize.standard_models() and target_language == transcriber.DEFAULT_LANGUAGE:  # Corrected condition
                last_use_en = os.environ.get("LAST_USE_EN_MODEL")
                if last_use_en is not None:
                    use_en_model = last_use_en.lower() in YesNo.YES.value
                    print(f"Using previous USE_EN_MODEL: {last_use_en} (from last session)")
                else:
                    use_en_model = transcriber.get_yes_no_input("Use English-specific model? (Recommended only if the video is originally in English) (y/N): ", default='n')
                used_fields["USE_EN_MODEL"] = "y" if use_en_model else "n"
            else:
                use_en_model = False
        else:
            model_name = ModelSize.BASE.value
            use_en_model = False
            
    # --- If loading from .env, get parameters from environment variables or prompt for missing ones ---

    else:
        is_local_file = False
        repeat_invocation = os.environ.get("_REPEAT_INVOCATION", "") == "1"
        url_env = os.getenv("URL")
        if repeat_invocation:
            url = transcriber.URL_PLACEHOLDER
        else:
            url = url_env
        if url and url != transcriber.URL_PLACEHOLDER:
            if transcriber.is_youtube_video_id(url):
                url = transcriber.construct_youtube_url(url)
                print(f"Detected video ID from profile, using: {url}")
                try:
                    yt = YouTube(url, "WEB")
                    print(f"Loaded YOUTUBE_URL: {url} (from {profile_name})")
                except RegexMatchError:
                    print("Error creating YouTube object. Please enter a valid URL or video ID.")
                    url = input()
            elif transcriber.is_web_url(url):
                if transcriber.is_youtube_url(url):
                    try:
                        yt = YouTube(url, "WEB")
                        print(f"Loaded YOUTUBE_URL: {url} (from {profile_name})")
                    except RegexMatchError:
                        # Use ffprobe to determine if it's a valid audio/video file
                        file_format = transcriber.get_file_format(url)
                        if file_format:
                            is_local_file = True
                            print(f"Loaded local file: {url} (from {profile_name})")
                        else:
                            print("Incorrect value for YOUTUBE_URL in config.env. "
                                  "Please enter a valid YouTube video URL, video ID, or local file path: ")
                            url = input()
                else:
                    print("Error: Only YouTube URLs supported for web inputs")
            elif transcriber.is_valid_media_file(url):
                is_local_file = True
                print(f"Loaded local file: {url} (from {profile_name})")
            else:
                if url != transcriber.URL_PLACEHOLDER:
                    print("Invalid input. Please enter valid YouTube URL, video ID, or local file path")
                while True:
                    url = input("Enter the YouTube video URL, video ID,, video ID, or local file path: ").strip()
                    if transcriber.is_youtube_video_id(url):
                        url = transcriber.construct_youtube_url(url)
                        print(f"Detected video ID, using: {url}")
                        break
                    elif transcriber.is_web_url(url):
                        if transcriber.is_youtube_url(url):
                            try:
                                yt = YouTube(url, "WEB")
                                break
                            except RegexMatchError:
                                # Use ffprobe to determine if it's a valid audio/video file
                                file_format = transcriber.get_file_format(url)
                                if file_format:
                                    is_local_file = True
                                    print(f"Loaded local file: {url}")
                                    break
                                else:
                                    print("Incorrect value for YOUTUBE_URL. "
                                          "Please enter a valid YouTube video URL, video ID, or local file path.")
                    elif transcriber.is_valid_media_file(url):
                        is_local_file = True
                        break
                    else:
                        print("Invalid input. Please enter valid YouTube URL, video ID, or local file path")
                        continue

        download_video = False
        no_audio_in_video = False
        download_audio = False

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
                    download_video = transcriber.get_yes_no_input("Download video stream? (y/N): ", default='n')
            else:
                download_video = transcriber.get_yes_no_input("Download video stream? (y/N): ", default='n')

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
                            no_audio_in_video = transcriber.get_yes_no_input("Include audio stream with video stream? (Y/n): ")
                        else:
                            no_audio_in_video = False
                    
                resolution = os.getenv("RESOLUTION")
                if resolution:
                    resolution = resolution.lower()  # Convert to lowercase for easier comparison
                    if resolution not in Resolution.values():
                        if resolution.isdigit():
                            if int(resolution) > 0:
                                resolution += "p"
                                print(f"Loaded RESOLUTION: {resolution} (from {profile_name})")
                            else:
                                print(f"Invalid value for RESOLUTION in .env: {resolution}")
                                resolution = None
                        elif not (resolution.endswith("p") and resolution[:-1].isdigit()):
                            print(f"Invalid value for RESOLUTION in .env: {resolution}")
                            resolution = Resolution.FETCH.value
                    elif resolution in Resolution.values():
                        print(f"Loaded RESOLUTION: {resolution} (from {profile_name})")
                    elif resolution in (Resolution.FETCH.value, Resolution.F.value):
                        print(f"Loaded RESOLUTION: {resolution} (from {profile_name})")
                        print("Loading available resolution...")
                        if resolution == Resolution.F.value:
                            resolution = Resolution.FETCH.value
                    else:
                        print("Loading available resolution...")
                        resolution = Resolution.FETCH.value

        if download_video and not is_local_file and resolution == Resolution.FETCH.value:
            try:
                yt = YouTube(url, "WEB")
            except RegexMatchError:
                print("Error: Invalid YouTube URL.")
                exit()
            if resolution == Resolution.HIGHEST.value:
                streams = transcriber.get_sorted_video_streams(yt)
                stream = streams[0] if streams else None

            elif resolution == Resolution.LOWEST.value:
                streams = transcriber.get_sorted_video_streams(yt)
                stream = streams[-1] if streams else None

            elif resolution == Resolution.FETCH.value:
                stream = None
                resolution = Resolution.FETCH.value

            else:  # Specific resolution provided
                streams = yt.streams.filter(only_video=True, resolution=resolution)
                streams = sorted(streams, key=lambda stream: int(stream.resolution[:-1]) if stream.resolution else 0, reverse=True)

                if streams:
                    stream = streams[0]
                else:
                    stream = None

            # If the requested resolution is not found, prompt the user
            if stream is None and resolution == Resolution.FETCH.value:
                if resolution != Resolution.FETCH.value:
                    print("Requested resolution not found, left null, or invalid.")
                available_streams = transcriber.get_sorted_video_streams(yt)

                # Get unique resolutions sorted by quality
                available_resolutions = transcriber.get_unique_sorted_resolutions(available_streams)

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
                    download_audio = transcriber.get_yes_no_input("Download audio only? (y/N): ", default='n')

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
                transcribe_audio = transcriber.get_yes_no_input("Transcribe the audio? (Y/n): ")
        else:
            transcribe_audio = transcriber.get_yes_no_input("Transcribe the audio? (Y/n): ")

        model_choice = os.getenv("MODEL_CHOICE")
        if model_choice and transcribe_audio:
            # Validate model_choice from .env
            if model_choice.lower() not in ('1', '2', '3', '4', '5', '6', '7', 'tiny', 'base', 'small', 'medium', 'large-v1', 'large-v2', 'large-v3'):
                print(f"Invalid value for MODEL_CHOICE in .env: {model_choice}")
                model_choice = transcriber.get_model_choice_input()  # Prompt for valid input
            else:
                print(f"Loaded MODEL_CHOICE: {model_choice} (from {profile_name})")
        elif transcribe_audio:
            model_choice = transcriber.get_model_choice_input()

        if transcribe_audio:
            # Set model based on user input (default to "base") using match statement
            if model_choice in ('1', '2', '3', '4', '5', '6', '7'):
                model_enum = ModelSize.get_model_by_number(model_choice)
                model_name = model_enum.value
            else:
                if model_choice == '':
                    model_enum = ModelSize.BASE
                else:
                    model_enum = ModelSize.get_model_by_name(model_choice)
                model_name = model_enum.value

            if url == transcriber.URL_PLACEHOLDER:
                while True:
                    url = input("Enter the YouTube video URL, video ID, or local file path: ").strip()
                    if transcriber.is_youtube_video_id(url):
                        url = transcriber.construct_youtube_url(url)
                        print(f"Detected video ID, using: {url}")
                        try:
                            yt = YouTube(url, "WEB")
                            break
                        except RegexMatchError:
                            print("Invalid video ID. Please try again.")
                            continue
                    elif transcriber.is_web_url(url):
                        if transcriber.is_youtube_url(url):
                            try:
                                yt = YouTube(url, "WEB")
                                break
                            except RegexMatchError:
                                print("Invalid YouTube URL. Please try again.")
                                continue
                        else:
                            print("Error: Only YouTube URLs supported for web inputs")
                            continue
                    elif transcriber.is_valid_media_file(url):
                        is_local_file = True
                        break
                    else:
                        print("Invalid input. Please enter valid YouTube URL, video ID, or local file path")
                        continue

            target_language = os.getenv("TARGET_LANGUAGE")
            if target_language:
                # Use target_language from .env
                if target_language.lower() not in whisper.tokenizer.LANGUAGES:
                    print(f"Invalid value for TARGET_LANGUAGE in .env: {target_language}")
                    target_language = transcriber.get_target_language_input()
                else:
                    print(f"Loaded TARGET_LANGUAGE: {target_language} (from {profile_name})")
            else:
                target_language = transcriber.get_target_language_input()
                if not target_language:
                    target_language = transcriber.DEFAULT_LANGUAGE  # Default to English

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
                    if model_enum in ModelSize.standard_models() and target_language == transcriber.DEFAULT_LANGUAGE:
                        use_en_model = transcriber.get_yes_no_input("Use English-specific model? (Recommended only if the video is originally in English) (y/N): ", default='n')
                    else:
                        use_en_model = False

    # --- Now, proceed with the rest of the script using the gathered parameters ---
    # Create a YouTube object from the URL only if it's not a local file
    if not is_local_file:
        if url == transcriber.URL_PLACEHOLDER:
            while True:
                url = input("Enter the YouTube video URL, video ID, or local file path: ").strip()
                if transcriber.is_youtube_video_id(url):
                    url = transcriber.construct_youtube_url(url)
                    print(f"Detected video ID, using: {url}")
                    is_local_file = False
                    break
                elif transcriber.is_web_url(url):
                    if transcriber.is_youtube_url(url):
                        is_local_file = False
                        break
                    else:
                        print("Error: Only YouTube URLs supported for web inputs")
                        continue
                elif transcriber.is_valid_media_file(url):
                    is_local_file = True
                    break
                else:
                    print("Invalid input. Please enter valid YouTube URL, video ID, or local file path")
                    continue
        
        while True:
            try:
                yt = transcriber.create_youtube_object(url)
                try:
                    video_title = yt.title
                    yt.check_availability()
                except (AttributeError, OSError, VideoUnavailable, VideoPrivate, VideoRegionBlocked) as e:
                    print(f"\nError with URL '{url}': {str(e)}")
                    print("The video is unavailable or inaccessible.")
                    
                    while True:
                        url = input("\nEnter a different YouTube video URL, video ID, or local file path: ").strip()
                        if transcriber.is_youtube_video_id(url):
                            url = transcriber.construct_youtube_url(url)
                            print(f"Detected video ID, using: {url}")
                            break
                        elif transcriber.is_web_url(url):
                            if transcriber.is_youtube_url(url):
                                break
                            else:
                                print("Error: Only YouTube URLs supported for web inputs")
                                continue
                        elif transcriber.is_valid_media_file(url):
                            is_local_file = True
                            break
                        else:
                            print("Invalid input. Please enter valid YouTube URL, video ID, or local file path")
                            continue
                    
                    if is_local_file:
                        break
                    continue
                break
            except (RegexMatchError, VideoUnavailable, VideoPrivate, VideoRegionBlocked, OSError, ValueError) as e:
                print(f"\nError with URL '{url}': {str(e)}")
                print("The URL appears to be invalid or the video is unavailable.")
                
                while True:
                    url = input("\nEnter a different YouTube video URL, video ID, or local file path: ").strip()
                    if transcriber.is_youtube_video_id(url):
                        url = transcriber.construct_youtube_url(url)
                        print(f"Detected video ID, using: {url}")
                        break
                    elif transcriber.is_web_url(url):
                        if transcriber.is_youtube_url(url):
                            break
                        else:
                            print("Error: Only YouTube URLs supported for web inputs")
                            continue
                    elif transcriber.is_valid_media_file(url):
                        is_local_file = True
                        break
                    else:
                        print("Invalid input. Please enter valid YouTube URL, video ID, or local file path")
                        continue
                
                if is_local_file:
                    break
    else:
        video_title = os.path.splitext(os.path.basename(url))[0]

    filename_base = transcriber.sanitize_filename(video_title)
    try:
        display_source = os.path.abspath(url) if is_local_file else url
    except NameError:
        display_source = video_title

    print(f"\nProcessing: {display_source}...")

    if download_video and not is_local_file:
        match resolution:
            case Resolution.HIGHEST.value:
                streams = transcriber.get_sorted_video_streams(yt)
                stream = streams[0] if streams else None

            case Resolution.LOWEST.value:
                streams = transcriber.get_sorted_video_streams(yt)
                stream = streams[-1] if streams else None

            case Resolution.FETCH.value:
                stream = yt.streams.filter(only_video=True, resolution=selected_res).first()

            case _:
                streams = yt.streams.filter(only_video=True, resolution=resolution)
                streams = sorted(streams, key=lambda stream: int(stream.resolution[:-1]) if stream.resolution else 0, reverse=True)
                stream = streams[0] if streams else None

        # If the requested resolution is not found, prompt the user
        if stream is None:
            print("Requested resolution not found, left null, or invalid.")
            available_streams = transcriber.get_sorted_video_streams(yt)

            # Get unique resolutions sorted by quality
            available_resolutions = transcriber.get_unique_sorted_resolutions(available_streams)

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

        if no_audio_in_video:
            filename = filename_base + transcriber.MP4_EXT
            output_path = transcriber.VIDEO_WITHOUT_AUDIO_DIR

            print(f"Downloading video stream ({stream.resolution} {'with audio' if not no_audio_in_video else 'without audio'})...")
            stream.download(output_path=output_path, filename=filename)
            file_path = os.path.abspath(output_path + "/" + filename)
            print(f"Video downloaded to {file_path}")
        else:
            video_temp_dir = os.path.join(transcriber.VIDEO_DIR, transcriber.TEMP_DIR)
            os.makedirs(video_temp_dir, exist_ok=True)

            video_filename = filename_base + transcriber.MP4_EXT
            audio_filename = filename_base + transcriber.MP3_EXT

            if resolution == Resolution.FETCH.value:
                stream = yt.streams.filter(only_video=True, resolution=selected_res).first()

            # Download the selected video stream
            stream.download(output_path=video_temp_dir, filename=video_filename)
            video_path = os.path.join(video_temp_dir, video_filename)
            print(f"Video downloaded to {video_path}")

    else:
        print("Skipping video download...")
        
    if download_audio:
        audio_path, file_path = transcriber.download_audio_stream(yt, filename_base, is_temp=False)

    if download_video and not no_audio_in_video:
        if not download_audio:
            audio_path, _ = transcriber.download_audio_stream(yt, filename_base, is_temp=True)
        else:
            audio_path = os.path.join(transcriber.AUDIO_DIR, audio_filename)

        output_path_combined = os.path.join(transcriber.VIDEO_DIR, video_filename)
        transcriber.combine_audio_video(video_path, audio_path, output_path_combined, 
                cleanup_temp=not no_audio_in_video, temp_video_dir=video_temp_dir)
        

    if transcribe_audio:
        if is_local_file:
            if transcriber.is_valid_media_file(url):
                audio_file = url
            else:
                try:
                    video = moviepy.editor.VideoFileClip(url)
                    audio_file = f"{filename_base}.mp3"
                    try:
                        video.audio.write_audiofile(audio_file)
                    finally:
                        video.close()
                except (IOError, OSError, ValueError, moviepy.editor.VideoFileClip.Error) as e:
                    print(f"Error processing video file: {str(e)}")
                    sys.exit(1)
        else:  # If it's not a local file, it's a YouTube video
            audio_filename = filename_base + transcriber.MP3_EXT
            # Use the downloaded audio file
            audio_file = os.path.join(transcriber.AUDIO_DIR, audio_filename)
            if not download_audio and ((not download_audio) or 
                                       (download_video and no_audio_in_video)):
                # Download the audio stream
                audio_file, _ = transcriber.download_audio_stream(yt, filename_base, is_temp=True)

        if is_local_file:
            file_path = url
        else:
            file_path = audio_file
            
        transcribed_text, language = transcriber.transcribe_audio_file(
            file_path, model_name, target_language
        )

        # Create and open a txt file with the text
        if language == transcriber.DEFAULT_LANGUAGE:
            transcriber.create_and_open_txt(transcribed_text, f"{filename_base}{transcriber.TXT_EXT}")
            transcript_path = f"{transcriber.TRANSCRIPT_DIR}/{filename_base}{transcriber.TXT_EXT}"
            file_path = os.path.abspath(transcript_path)
            print(f"Saved transcript to {file_path}")
        else:
            transcript_name = f"{filename_base} [{language}]{transcriber.TXT_EXT}"
            transcriber.create_and_open_txt(transcribed_text, transcript_name)
            transcript_path = f"{transcriber.TRANSCRIPT_DIR}/{transcript_name}"
            file_path = os.path.abspath(transcript_path)
            print(f"Saved transcript to {file_path}")
    else:
        print("Skipping transcription.")
        transcribed_text = ""

    temp_audio_path = os.path.join(transcriber.AUDIO_DIR, transcriber.TEMP_DIR)
    temp_audio_file = os.path.join(temp_audio_path, filename_base + transcriber.MP3_EXT)
    if not is_local_file and not download_audio and (transcribe_audio or download_video) and not no_audio_in_video and os.path.exists(temp_audio_file):
        os.remove(temp_audio_file)
        if os.path.exists(temp_audio_path) and not os.listdir(temp_audio_path):
            os.rmdir(temp_audio_path)
        print(f"Deleted audio residual in {temp_audio_file}")

    print("Tasks complete.")

    did_something_useful = (download_audio or download_video or transcribe_audio)
    is_repeat = os.environ.get("_REPEAT_INVOCATION", "") == "1"
    repeat = False
    repeat_value = ""
    try:
        if load_profile:
            repeat_setting = os.getenv("REPEAT", "") or ""
            if repeat_setting.lower() in YesNo.YES.value:
                repeat = True
                repeat_value = "y"
            elif repeat_setting.lower() in YesNo.NO.value:
                repeat = False
                repeat_value = "n"
            else:
                # blank or invalid -> ask user
                # Track how many times we've asked in this repeat chain
                repeat_ask_count = int(os.environ.get("_REPEAT_ASK_COUNT", "0"))
                # On first ask (count 0), default to 'n'; on subsequent asks, default to 'y'
                default_repeat = 'y' if repeat_ask_count > 0 else 'n'
                prompt_text = "Run again? (Y/n): " if default_repeat == 'y' else "Run again? Hit Enter to repeat (y/N): "
                repeat = transcriber.get_yes_no_input(prompt_text, default=default_repeat)
                repeat_value = "y" if repeat else "n"
                # Increment counter for next ask
                os.environ["_REPEAT_ASK_COUNT"] = str(repeat_ask_count + 1)
        else:
            # Interactive mode - also use the same repeat counter logic
            repeat_ask_count = int(os.environ.get("_REPEAT_ASK_COUNT", "0"))
            default_repeat = 'y' if repeat_ask_count > 0 else 'n'
            prompt_text = "Run again? (Y/n): " if default_repeat == 'y' else "Run again? Hit Enter to repeat (y/N): "
            repeat = transcriber.get_yes_no_input(prompt_text, default=default_repeat)
            repeat_value = "y" if repeat else "n"
            # Increment counter for next ask
            os.environ["_REPEAT_ASK_COUNT"] = str(repeat_ask_count + 1)
    except Exception:
        repeat = False
        repeat_value = ""

    used_fields["REPEAT"] = repeat_value

    if not load_profile and did_something_useful and not is_repeat:
        create_profile_prompt = transcriber.get_yes_no_input("Do you want to create a profile from this session? (y/N): ", default='n')
        if create_profile_prompt:
            transcriber.create_profile(used_fields)

    try:
        if repeat:
            if not load_profile:
                try:
                    os.environ["LAST_DOWNLOAD_VIDEO"] = "y" if download_video else "n"
                except Exception:
                    pass
                try:
                    os.environ["LAST_NO_AUDIO_IN_VIDEO"] = "y" if no_audio_in_video else "n"
                except Exception:
                    pass
                try:
                    os.environ["LAST_RESOLUTION"] = resolution or ""
                except Exception:
                    pass
                try:
                    os.environ["LAST_DOWNLOAD_AUDIO"] = "y" if download_audio else "n"
                except Exception:
                    pass
                try:
                    os.environ["LAST_TRANSCRIBE_AUDIO"] = "y" if transcribe_audio else "n"
                except Exception:
                    pass
                try:
                    os.environ["LAST_MODEL_CHOICE"] = model_choice if 'model_choice' in locals() else ""
                except Exception:
                    pass
                try:
                    os.environ["LAST_TARGET_LANGUAGE"] = target_language if 'target_language' in locals() else ""
                except Exception:
                    pass
                try:
                    os.environ["LAST_USE_EN_MODEL"] = "y" if use_en_model else "n"
                except Exception:
                    pass
            os.environ["_REPEAT_INVOCATION"] = "1"
            try:
                os.environ["URL"] = transcriber.URL_PLACEHOLDER
            except Exception:
                pass
            if load_profile and 'profile_name' in locals():
                try:
                    os.environ["_REPEAT_PROFILE_NAME"] = profile_name
                except Exception:
                    pass
            print("Repeating session as requested...")
            main()
        else:
            for k in ("_REPEAT_INVOCATION", "_REPEAT_PROFILE_NAME", "_REPEAT_ASK_COUNT", "LAST_DOWNLOAD_VIDEO", "LAST_NO_AUDIO_IN_VIDEO", "LAST_RESOLUTION", "LAST_DOWNLOAD_AUDIO", "LAST_TRANSCRIBE_AUDIO", "LAST_MODEL_CHOICE", "LAST_TARGET_LANGUAGE", "LAST_USE_EN_MODEL"):
                if k in os.environ:
                    try:
                        del os.environ[k]
                    except Exception:
                        pass
    except Exception:
        for k in ("_REPEAT_INVOCATION", "_REPEAT_PROFILE_NAME", "_REPEAT_ASK_COUNT", "LAST_DOWNLOAD_VIDEO", "LAST_NO_AUDIO_IN_VIDEO", "LAST_RESOLUTION", "LAST_DOWNLOAD_AUDIO", "LAST_TRANSCRIBE_AUDIO", "LAST_MODEL_CHOICE", "LAST_TARGET_LANGUAGE", "LAST_USE_EN_MODEL"):
            if k in os.environ:
                try:
                    del os.environ[k]
                except Exception:
                    pass
    

def get_required_packages(requirements_path):
    """
    Reads requirements.txt and returns a list of package specs (ignoring comments/blank lines).
    """
    packages = []
    try:
        with open(requirements_path, 'r', encoding='utf-8') as req_file:
            for line in req_file:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                packages.append(line)
    except Exception as e:
        print(f"Error reading requirements.txt: {e}")
    return packages

if __name__ == "__main__":
    main()
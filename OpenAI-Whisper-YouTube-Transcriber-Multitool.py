#This Python script downloads the audio or video from a YouTube link, uses OpenAI's Whisper to detect the language, and transcribes it into a .txt file.
#Author: Ruinan Ding

#Ruinan Ding

#Description
#To run this script, open this script with Python or use the following command in a command line terminal where this file is:
#python OpenAI-Whisper-YouTube-Transcriber-Multitool.py
#Input the YouTube video URL when prompted, and it will download the audio or video streams from the URL along with the transcription of the audio.


#import required modules
import os
import whisper
from langdetect import detect
from pytubefix import YouTube


#Function to open a file
def startfile(fn):
    os.system('open %s' % fn)


#Function to create and open a txt file
def create_and_open_txt(text, filename):
    #Create and write the text to a txt file
    with open(filename, "w") as file:
        file.write(text)
    startfile(filename)


#Ask user for the YouTube video URL
url = input("Enter the YouTube video URL: ")

#Create a YouTube object from the URL
yt = YouTube(url)

# Ask user if they want to download the video stream (default no)
download_video = input("Download video stream? (y/N): ").lower() == 'y'

video_title = yt.title
filename_base = "".join(c for c in video_title if c.isalnum() or c in "._- ") 

if download_video:
    # Ask if they want audio with the video (default yes)
    include_audio = input("Include audio stream with video stream? (Y/n): ").lower() != 'n'

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
# Download the audio stream
output_path = "Audio"
filename = filename_base + ".mp3"  # Use the video title for audio filename
audio_stream.download(output_path=output_path, filename=filename)
print(f"Audio downloaded to {output_path}/{filename}")


# Ask the user if they want to transcribe the audio (default yes)
transcribe_audio = input("Transcribe the audio? (Y/n): ").lower() != 'n'

if transcribe_audio:
    # Prompt for model selection
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

    # Ask if they want the .en model (only if model is tiny, base, small, or medium)
    if model_name in ("tiny", "base", "small", "medium"):
        use_en_model = input("Use English-specific model? (y/N): ").lower() == 'y'
        if use_en_model:
            model_name += ".en"

    # Load the selected model
    model = whisper.load_model(model_name)

    result = model.transcribe("Audio/" + filename_base + ".mp3")
    transcribed_text = result["text"]
    print(transcribed_text)

    # Detect the language
    language = detect(transcribed_text)
    print(f"Detected language: {language}")

    # Create and open a txt file with the text
    create_and_open_txt(transcribed_text, f"Transcript_{language}.txt")
else:
    print("Skipping transcription.")
    transcribed_text = ""  # Assign an empty string

# Ask the user if they want to delete the audio file (default yes)
delete_audio = input("Delete the audio file? (Y/n): ").lower() != 'n'

if delete_audio:
    # Delete the audio file
    os.remove(f"{output_path}/{filename}")
    print("Audio file deleted.")
else:
    print("Audio file kept.")
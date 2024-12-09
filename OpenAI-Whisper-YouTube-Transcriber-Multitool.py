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
    # Load model and transcribe the audio
    print("Transcribing the audio...")

    #Uncomment any of the following line and comment out the selected model to use a different model. The larger the better quality but slower processing time. May require stronger PC for larger models.
    #model = whisper.load_model("tiny")
    model = whisper.load_model("base")
    #model = whisper.load_model("small")
    #model = whisper.load_model("medium")
    #model = whisper.load_model("large-v1")
    #model = whisper.load_model("large-v2")
    #model = whisper.load_model("large-v3")

    #These are the English models. Uncomment the following lines and comment out the selected model to use the English models. They preform better for English audio but may not work as well for other languages.
    #model = whisper.load_model("tiny.en")
    #model = whisper.load_model("base.en")
    #model = whisper.load_model("small.en")
    #model = whisper.load_model("medium.en")

    result = model.transcribe("Audio/" + filename_base + ".mp3")
    transcribed_text = result["text"]
    print(transcribed_text)

    # Ask the user if they want to delete the audio file (default yes)
    delete_audio = input("Delete the audio file? (Y/n): ").lower() != 'n'

    if delete_audio:
        # Delete the audio file
        os.remove(f"{output_path}/{filename}")
        print("Audio file deleted.")
    else:
        print("Audio file kept.")
else:
    print("Skipping transcription.")

#Detect the language
language = detect(transcribed_text)
print(f"Detected language: {language}")

#Create and open a txt file with the text
create_and_open_txt(transcribed_text, f"Transcript_{language}.txt")
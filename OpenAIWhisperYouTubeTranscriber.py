#This Python script downloads the audio or video from a YouTube link, uses OpenAI's Whisper to detect the language, and transcribes it into a .txt file.
#Author: Ruinan Ding

#Ruinan Ding

#Description
#To run this script, open this script with Python or use the following command in a command line terminal where this file is:
#python OpenAIWhisperYouTubeTranscriber.py
#Input the YouTube video URL when prompted, and it will download the audio or video streams from the URL along with the transcription of the audio.


#import required modules
import os
import whisper
from langdetect import detect
from pytube import YouTube


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

#Uncomment the following block to download the video stream of the highest resolution with audio
'''
#Get the video stream in .mp4 format
print("Downloading the video stream of the highest resolution with audio...")
video_audio_stream = yt.streams.filter().get_highest_resolution()
#Download the video stream
output_path = "VideoWithAudio"
filename = "VideoWithAudio.mp4"
video_audio_stream.download(output_path = output_path, filename = filename)
print(f"Video with audio downloaded to {output_path}/{filename}")
'''

#Uncomment the following block to download the video stream
'''
#Get the video stream in .mp4 format
print("Downloading the video stream...")
video_stream = yt.streams.filter(only_video = True).first()
#Download the video stream
output_path = "Video"
filename = "Video.mp4"
video_stream.download(output_path = output_path, filename = filename)
print(f"Video downloaded to {output_path}/{filename}")
'''

#Get the audio stream in .mp3 format
print("Downloading the audio stream...")
audio_stream = yt.streams.filter().get_audio_only()
#Download the audio stream
output_path = "Audio"
filename = "Audio.mp3"
audio_stream.download(output_path = output_path, filename = filename)
print(f"Audio downloaded to {output_path}/{filename}")


#Load model and transcribe the audio
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

result = model.transcribe("Audio/Audio.mp3")
transcribed_text = result["text"]
print(transcribed_text)

#Delete the audio file. Comment out the following line to keep the audio file
os.remove(f"{output_path}/{filename}")

#Detect the language
language = detect(transcribed_text)
print(f"Detected language: {language}")

#Create and open a txt file with the text
create_and_open_txt(transcribed_text, f"Transcript_{language}.txt")
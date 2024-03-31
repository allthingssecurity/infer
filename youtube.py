from pytube import YouTube
from moviepy.editor import *
import os

def download_video_as_mp3(url, output_path, max_length=180):
    # Downloading the video from YouTube
    yt = YouTube(url)
    stream = yt.streams.filter(only_audio=True).first()
    downloaded_file = stream.download()

    # Loading the downloaded file with moviepy
    video = AudioFileClip(downloaded_file)
    
    # Trimming the audio file to the first 3 minutes if it's longer than that
    if video.duration > max_length:
        video = video.subclip(0, max_length)
    
    # Exporting the trimmed audio as MP3
    video.write_audiofile(output_path, codec='mp3')
    
    # Closing the video file to release it
    video.close()
    
    # Removing the original download to clean up
    try:
        os.remove(downloaded_file)
    except PermissionError as e:
        print(f"Error deleting file {downloaded_file}: {e}")

# Example usage
youtube_url = 'https://www.youtube.com/watch?v=T8qg2CYanh4'  # Replace with your YouTube video's URL
output_mp3_path = 'output_audio.mp3'
download_video_as_mp3(youtube_url, output_mp3_path)





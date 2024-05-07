from pytube import YouTube
from moviepy.editor import *
import os
import uuid
from pytube.exceptions import PytubeError
import yt_dlp
from moviepy.editor import AudioFileClip
import os
import uuid



def is_video_downloadable(url):
    try:
        yt = YouTube(url)
        yt.streams.first()  # Attempt to access the first stream as a basic check
        return True, "Video is likely downloadable."
    except PytubeError as e:
        return False, f"Video might not be downloadable due to restrictions: {e}"

def get_video_duration(url):
    try:
        yt = YouTube(url)
        return yt.length  # Duration in seconds
    except PytubeError as e:
        raise ValueError(f"Failed to fetch video metadata: {e}")



import yt_dlp
from moviepy.editor import AudioFileClip
import os
import uuid

def download_video_as_mp3(url, output_path, max_length=180,max_duration=600):
    # Generate a unique filename without an extension
    duration=get_video_duration(url)
    if duration > max_duration:
        raise ValueError(f"Video duration is {duration} seconds, which exceeds the maximum allowed length of {max_duration} seconds.")

    unique_filename = f"{uuid.uuid4()}"

    # Setup yt-dlp options with modified output template
    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'outtmpl': f"{unique_filename}.%(ext)s",  # This will create files like <uuid>.mp3 directly
        'noplaylist': True,
        'quiet': False
    }

    # Downloading and processing the video using yt-dlp
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        # Since the file is already in MP3, just check if we need to trim it
        video = AudioFileClip(f"{unique_filename}.mp3")
        if video.duration > max_length:
            video = video.subclip(0, max_length)
            video.write_audiofile(output_path, codec='mp3', bitrate="320k")
        else:
            # If no trimming is needed, simply rename the file
            os.rename(f"{unique_filename}.mp3", output_path)
        video.close()
        return True
    except Exception as e:
        print(f"Error downloading or processing video: {e}")
        return False
    finally:
        # Cleanup: ensure no temporary files remain
        temp_file = f"{unique_filename}.mp3"
        if os.path.exists(temp_file):
            os.remove(temp_file)

# Example usage
youtube_url = 'https://youtu.be/-rhPlLYCcg8?si=4g8wI7noXEfGoqb3'
output_mp3_path = 'output_audio.mp3'
download_video_as_mp3(youtube_url, output_mp3_path)






def download_video_as_mp3_ytl(url, output_path, max_length=180,max_duration=600):
    # Generate a unique filename for the temporary download
    duration=get_video_duration(url)
    if duration > max_duration:
        raise ValueError(f"Video duration is {duration} seconds, which exceeds the maximum allowed length of {max_duration} seconds.")

    unique_filename = f"{uuid.uuid4()}.mp4"

    # Setup yt-dlp options
    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'outtmpl': unique_filename,
        'noplaylist': True,
        'quiet': False
    }

    # Downloading the video using yt-dlp
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        # Loading the downloaded file with moviepy to check duration and possibly trim
        video = AudioFileClip(unique_filename)
        if video.duration > max_length:
            video = video.subclip(0, max_length)
            video.write_audiofile(output_path, codec='mp3', bitrate="320k")
        else:
            # If no trimming is needed, rename the file to the desired output path
            os.rename(unique_filename, output_path)
        video.close()
        return True
    except Exception as e:
        print(f"Error downloading or processing video: {e}")
        return False
    finally:
        # Cleanup: remove temporary files if they exist
        if os.path.exists(unique_filename):
            os.remove(unique_filename)





def download_video_as_mp3(url, output_path, max_length=180,max_duration=600):
    # Generate a unique filename for this particular download
    
    downloadable, message = is_video_downloadable(url)
    if not downloadable:
        raise ValueError(message)
        
    duration=get_video_duration(url)
    if duration > max_duration:
        raise ValueError(f"Video duration is {duration} seconds, which exceeds the maximum allowed length of {max_duration} seconds.")

    
    unique_filename = str(uuid.uuid4())
    
    # Downloading the video from YouTube
    yt = YouTube(url)
    # Attempt to select the highest quality audio stream
    stream = sorted(yt.streams.filter(only_audio=True), key=lambda s: s.abr, reverse=True)[0]
    downloaded_file = stream.download(filename_prefix=unique_filename)
    
    # Loading the downloaded file with moviepy
    video = AudioFileClip(downloaded_file)
    
    # Trimming the audio file to the first 3 minutes if it's longer than that
    if video.duration > max_length:
        video = video.subclip(0, max_length)
    
    # Exporting the trimmed audio as MP3 with a high bitrate
    video.write_audiofile(output_path, codec='mp3', bitrate="320k")
    
    # Closing the video file to release it
    video.close()
    
    # Removing the original download to clean up
    try:
        os.remove(downloaded_file)
        # Temporarily commented out the print statement for clarity
        # print("for now not removing to check functionality")
    except PermissionError as e:
        print(f"Error deleting file {downloaded_file}: {e}")


def download_video_as_mp3_bak(url, output_path, max_length=180):
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
        print("for now not removing to check functionality")
    except PermissionError as e:
        print(f"Error deleting file {downloaded_file}: {e}")

# Example usage
#youtube_url = 'https://www.youtube.com/clip/UgkxTE5l8eU-AVsYBSjTXb_-oH_we2f1dp_k'  # Replace with your YouTube video's URL
#output_mp3_path = 'output_audio.mp3'
#download_video_as_mp3(youtube_url, output_mp3_path)




from pytube import YouTube
from moviepy.editor import *
import os
import uuid
from pytube.exceptions import PytubeError
import yt_dlp
from moviepy.editor import AudioFileClip
import os
import uuid
import http.client
import json
import time
import uuid
import os
import requests
from pydub import AudioSegment



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



import os
import http.client
import json
import requests
import time
import uuid
from pydub import AudioSegment
import subprocess

def fallback_download_with_ytdlp(url, output_file, max_length_seconds=180):
    output_directory, original_filename = os.path.split(output_file)
    temp_file_path = os.path.join(output_directory, "temp_" + original_filename)
    final_file_path = os.path.join(output_directory, original_filename)
    
    if not os.path.exists(output_directory):
        os.makedirs(output_directory)

    # Prepare yt-dlp command
    cmd = [
        'yt-dlp',
        '-x', '--audio-format', 'mp3', # Extract audio and convert to mp3
        '-o', temp_file_path,          # Output file path
        '--username', 'oauth2',        # Using oauth2
        '--password', '',              # Empty password (for fallback compatibility)
        url                            # YouTube URL
    ]

    try:
        # Execute the yt-dlp command
        subprocess.run(cmd, check=True)
        print(f"yt-dlp download successful. File saved as {temp_file_path}")

        # Load the downloaded file and trim it if necessary
        audio = AudioSegment.from_mp3(temp_file_path)
        if len(audio) > max_length_seconds * 1000:  # pydub works in milliseconds
            audio = audio[:max_length_seconds * 1000]
            print(f"Audio trimmed to {max_length_seconds} seconds")

        audio.export(final_file_path, format="mp3")
        os.remove(temp_file_path)  # Remove the temporary file after processing
        print(f"File successfully saved and trimmed as {final_file_path}")

        return final_file_path
    except subprocess.CalledProcessError as e:
        print(f"yt-dlp fallback failed: {str(e)}")
        raise Exception("yt-dlp fallback failed")

def download_youtube_mp3(url, api_key, output_file, max_length_seconds=180):
    conn = http.client.HTTPSConnection("youtube-to-mp315.p.rapidapi.com")

    headers = {
        'x-rapidapi-key': api_key,
        'x-rapidapi-host': "youtube-to-mp315.p.rapidapi.com",
        'Content-Type': "application/json"
    }

    try:
        # Start conversion process
        payload = "{}"
        conn.request("POST", f"/download?url={url}&format=mp3", payload, headers)
        res = conn.getresponse()
        data = json.loads(res.read().decode("utf-8"))

        if 'id' not in data:
            raise Exception("Failed to start conversion process")

        conversion_id = data['id']
        print(f"Conversion started with ID: {conversion_id}")

        # Check status until available
        while True:
            conn.request("GET", f"/status/{conversion_id}", headers=headers)
            res = conn.getresponse()
            status_data = json.loads(res.read().decode("utf-8"))

            if status_data['status'] == 'AVAILABLE':
                print("Conversion completed. Downloading file...")
                break
            elif status_data['status'] == 'CONVERSION_ERROR':
                raise Exception("Conversion failed")

            print("Converting... Please wait.")
            time.sleep(5)  # Wait for 5 seconds before checking again

        # Prepare for download
        download_url = status_data['downloadUrl']
        title = status_data.get('title', 'Unknown Title')

        # Create a sanitized filename with UUID
        output_directory, original_filename = os.path.split(output_file)

        if not os.path.exists(output_directory):
            os.makedirs(output_directory)

        temp_file_path = os.path.join(output_directory, "temp_" + original_filename)
        final_file_path = os.path.join(output_directory, original_filename)

        # Download the file
        response = requests.get(download_url, stream=True)
        response.raise_for_status()

        with open(temp_file_path, 'wb') as file:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    file.write(chunk)

        audio = AudioSegment.from_mp3(temp_file_path)
        if len(audio) > max_length_seconds * 1000:  # pydub works in milliseconds
            audio = audio[:max_length_seconds * 1000]
            print(f"Audio trimmed to {max_length_seconds} seconds")

        audio.export(final_file_path, format="mp3")
        os.remove(temp_file_path)

        print(f"File downloaded successfully: {final_file_path}")
        return final_file_path
    except Exception as e:
        print(f"Failed to download via API: {str(e)}")
        print("Falling back to yt-dlp...")
        return fallback_download_with_ytdlp(url, output_file, max_length_seconds)

# Example usage
# download_youtube_mp3("https://youtube.com/video", "your_api_key", "output_path.mp3")



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
        'quiet': False,
        'keepvideo': True
    }

    # Downloading and processing the video using yt-dlp
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        # Since the file is already in MP3, just check if we need to trim it
        video = AudioFileClip(f"{unique_filename}.webm")
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
        temp_file = f"{unique_filename}.webm"
        if os.path.exists(temp_file):
            os.remove(temp_file)

# Example usage






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





def download_video_as_mp3_old(url, output_path, max_length=180,max_duration=600):
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




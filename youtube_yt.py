import yt_dlp
from moviepy.editor import AudioFileClip
import os
import uuid

def download_video_as_mp3(url, output_path, max_length=180):
    # Generate a unique filename for the temporary download
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

# Example usage
youtube_url = 'https://www.youtube.com/watch?v=-rhPlLYCcg8'
output_mp3_path = 'output_audio.mp3'
download_video_as_mp3(youtube_url, output_mp3_path)

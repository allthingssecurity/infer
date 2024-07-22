import yt_dlp
from moviepy.editor import AudioFileClip
import os
import uuid

def download_youtube_audio(url, output_path, max_length=180, max_duration=600, bitrate="192k"):
    def get_video_info(url):
        ydl_opts = {'quiet': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return info

    try:
        # Get video info
        info = get_video_info(url)
        
        # Check if video is downloadable
        if info is None:
            raise ValueError("Unable to fetch video information. The video might be unavailable or restricted.")
        
        # Get video duration
        duration = info.get('duration')
        if duration is None:
            raise ValueError("Unable to determine video duration")
        
        # Check if video exceeds maximum duration
        if duration > max_duration:
            raise ValueError(f"Video duration is {duration} seconds, which exceeds the maximum allowed length of {max_duration} seconds.")
        
        # Generate a unique filename
        unique_filename = f"{uuid.uuid4()}"
        temp_audio_file = f"{unique_filename}.%(ext)s"
        
        # Setup yt-dlp options
        ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': bitrate,
            }],
            'outtmpl': temp_audio_file,
            'noplaylist': True,
            'quiet': False
        }
        
        # Download the audio
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        
        # Get the name of the downloaded file
        downloaded_file = f"{unique_filename}.mp3"
        
        # Load the audio file and trim if necessary
        audio = AudioFileClip(downloaded_file)
        if audio.duration > max_length:
            audio = audio.subclip(0, max_length)
            audio.write_audiofile(output_path, codec='mp3', bitrate=bitrate)
        else:
            os.rename(downloaded_file, output_path)
        
        audio.close()
        print(f"Successfully downloaded and processed: {output_path}")
        return True

    except Exception as e:
        print(f"Error downloading or processing video: {e}")
        return False

    finally:
        # Cleanup: remove temporary files if they exist
        temp_files = [f"{unique_filename}.mp3", f"{unique_filename}.webm", f"{unique_filename}.m4a"]
        for temp_file in temp_files:
            if os.path.exists(temp_file):
                os.remove(temp_file)

# Example usage
youtube_url = 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'
output_mp3_path = 'output_audio.mp3'
success = download_youtube_audio(youtube_url, output_mp3_path, max_length=180, max_duration=600, bitrate="320k")
if success:
    print("Download completed successfully")
 else:
    print("Download failed")
import os
import uuid
import yt_dlp
import requests
import imageio_ffmpeg
from urllib.parse import urlparse
from utils import get_temp_dir

def download_media(url, is_audio=False, progress_callback=None):
    """
    Downloads media from a URL using yt-dlp.
    If is_audio is True, it extracts the best audio.
    Returns the path to the downloaded file.
    """
    temp_dir = get_temp_dir()
    file_id = str(uuid.uuid4())
    
    def yt_dlp_hook(d):
        if d['status'] == 'downloading' and progress_callback:
            percent = d.get('_percent_str', 'N/A')
            speed = d.get('_speed_str', 'N/A')
            size = d.get('_total_bytes_str') or d.get('_total_bytes_estimate_str', 'N/A')
            text = f"Downloading... {percent.strip()} of {size.strip()} at {speed.strip()}"
            progress_callback(text)
    
    # yt-dlp options
    ydl_opts = {
        'outtmpl': os.path.join(temp_dir, f'{file_id}.%(ext)s'),
        'quiet': True,
        'no_warnings': True,
        'ffmpeg_location': imageio_ffmpeg.get_ffmpeg_exe(),
        'progress_hooks': [yt_dlp_hook] if progress_callback else [],
        'js_runtimes': {'nodejs': {}, 'node': {}},
        'extractor_args': {'youtube': {'player_client': ['android_vr', 'web']}},
    }
    
    # Use cookies file if available (helps bypass YouTube bot detection on cloud servers)
    cookies_path = '/etc/secrets/cookies.txt'
    if os.path.exists(cookies_path):
        import shutil
        writable_cookies_path = os.path.join(temp_dir, 'cookies.txt')
        try:
            shutil.copyfile(cookies_path, writable_cookies_path)
            ydl_opts['cookiefile'] = writable_cookies_path
            print(f"✅ Found cookies file, copied to {writable_cookies_path} and applying to yt-dlp...")
        except Exception as e:
            print(f"⚠️ Error copying cookies file: {e}")
            ydl_opts['cookiefile'] = cookies_path # fallback
    else:
        print(f"⚠️ No cookies file found at {cookies_path}. YouTube might block downloads.")
    
    # Telegram bot file size limit is 50MB on public API, but up to 2GB on Local API Server
    MAX_SIZE_BYTES = 1950 * 1024 * 1024  # 1950MB to be safe

    if is_audio:
        ydl_opts.update({
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        })
    else:
        ydl_opts.update({
            'format': 'bestvideo[height<=720]+bestaudio/best[height<=720]/best',
            'merge_output_format': 'mp4',
        })
        
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # We don't need to specify max_filesize since yt-dlp will download the whole thing 
            # and we check size before returning
            
            info_dict = ydl.extract_info(url, download=True)
            downloaded_file = None
            for f in os.listdir(temp_dir):
                if f.startswith(file_id) and not f.endswith('.part') and not f.endswith('.ytdl'):
                    downloaded_file = os.path.join(temp_dir, f)
                    break
            
            # Check file size before returning
            if downloaded_file and os.path.exists(downloaded_file):
                file_size = os.path.getsize(downloaded_file)
                if file_size > MAX_SIZE_BYTES:
                    os.remove(downloaded_file)
                    print(f"File too large: {file_size / 1024 / 1024 / 1024:.2f}GB, limit is 1.95GB")
                    return 'TOO_LARGE'
            
            return downloaded_file
    except Exception as e:
        error_str = str(e)
        print(f"Error downloading with yt-dlp: {e}")
        if 'Sign in to confirm' in error_str or 'bot' in error_str.lower():
            return 'BOT_DETECTED'
        return f"ERROR: {error_str}"

def download_direct_file(url):
    """
    Downloads a file directly using requests. (useful for direct image links)
    """
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()
        
        parsed_url = urlparse(url)
        filename = os.path.basename(parsed_url.path)
        if not filename:
            filename = f"{uuid.uuid4()}.file"
            
        temp_dir = get_temp_dir()
        filepath = os.path.join(temp_dir, f"{uuid.uuid4()}_{filename}")
        
        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
                
        return filepath
    except Exception as e:
        print(f"Error downloading direct file: {e}")
        return None

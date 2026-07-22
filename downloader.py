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
    
    # yt-dlp options with user device spoofing and player client rotation
    ydl_opts = {
        'outtmpl': os.path.join(temp_dir, f'{file_id}.%(ext)s'),
        'quiet': True,
        'no_warnings': True,
        'ffmpeg_location': imageio_ffmpeg.get_ffmpeg_exe(),
        'progress_hooks': [yt_dlp_hook] if progress_callback else [],
        'js_runtimes': {'nodejs': {}, 'node': {}},
        'geo_bypass': True,
        'geo_bypass_country': 'US',
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Telegram/10.14',
            'Accept-Language': 'en-US,en;q=0.9,km-KH;q=0.8',
        },
        'extractor_args': {
            'youtube': {
                'player_client': ['ios', 'android', 'mweb', 'tv', 'web_creator']
            }
        },
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
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'merge_output_format': 'mp4',
        })

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # First extract info without downloading to see if it's too large
            info = ydl.extract_info(url, download=False)
            
            # Check filesize if available
            filesize = info.get('filesize') or info.get('filesize_approx')
            if filesize and filesize > MAX_SIZE_BYTES:
                print(f"File too large: {filesize / 1024 / 1024 / 1024:.2f}GB")
                return 'TOO_LARGE'
                
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
        
        # Fallback to pytubefix if YouTube blocked the cloud IP
        if 'Sign in to confirm' in error_str or 'bot' in error_str.lower() or 'Requested format is not available' in error_str or 'HTTP Error 400' in error_str or 'HTTP Error 403' in error_str:
            print("YouTube blocked yt-dlp. Attempting fallback with pytubefix...")
            try:
                from pytubefix import YouTube
                # Fallback sequentially through clients
                yt = None
                for client in ['ANDROID', 'TV', 'MWEB']:
                    try:
                        yt = YouTube(url, client=client)
                        # trigger network request to see if it works
                        test_title = yt.title
                        break
                    except Exception:
                        continue
                        
                if yt is None:
                    yt = YouTube(url) # try default
                
                temp_dir = get_temp_dir()
                if is_audio:
                    ys = yt.streams.get_audio_only()
                    out_file = ys.download(output_path=temp_dir)
                    # Convert to mp3 using pydub
                    from pydub import AudioSegment
                    audio = AudioSegment.from_file(out_file)
                    base, ext = os.path.splitext(out_file)
                    new_file = base + '.mp3'
                    audio.export(new_file, format="mp3")
                    os.remove(out_file)
                    return new_file
                else:
                    ys = yt.streams.get_highest_resolution()
                    out_file = ys.download(output_path=temp_dir)
                    return out_file
            except Exception as pytube_e:
                print(f"pytubefix fallback failed: {pytube_e}")
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

import os
import uuid
import ffmpeg
import imageio_ffmpeg
from PIL import Image
from utils import get_temp_dir, cleanup_file

import re

def _run_ffmpeg_with_progress(stream, output_path, progress_callback):
    try:
        process = stream.run_async(
            cmd=imageio_ffmpeg.get_ffmpeg_exe(),
            pipe_stderr=True,
            pipe_stdout=False,
            quiet=True
        )
        
        size_pattern = re.compile(r"size=\s*(\d+[a-zA-Z]+)")
        speed_pattern = re.compile(r"speed=\s*([\d.]+x)")
        
        while True:
            line = process.stderr.readline()
            if not line:
                break
            
            line_str = line.decode('utf-8', errors='ignore')
            
            if progress_callback:
                size_match = size_pattern.search(line_str)
                speed_match = speed_pattern.search(line_str)
                
                if size_match and speed_match:
                    size = size_match.group(1)
                    speed = speed_match.group(1)
                    progress_callback(f"Converting... Size: {size}, Speed: {speed}")
                    
        process.wait()
        if process.returncode != 0:
            print(f"FFmpeg error with code {process.returncode}")
            return None
            
        return output_path
    except Exception as e:
        print(f"Error during ffmpeg execution: {e}")
        return None

def convert_video_to_audio(input_path, output_format='mp3', progress_callback=None):
    """
    Converts a video or audio file to a specified audio format.
    """
    temp_dir = get_temp_dir()
    output_filename = f"{uuid.uuid4()}.{output_format}"
    output_path = os.path.join(temp_dir, output_filename)
    
    stream = (
        ffmpeg
        .input(input_path)
        .output(output_path, acodec='libmp3lame' if output_format == 'mp3' else 'copy', qscale=2)
        .overwrite_output()
    )
    
    return _run_ffmpeg_with_progress(stream, output_path, progress_callback)

def convert_video_format(input_path, output_format='mp4', progress_callback=None):
    """
    Converts a video file to a different video format.
    """
    temp_dir = get_temp_dir()
    output_filename = f"{uuid.uuid4()}.{output_format}"
    output_path = os.path.join(temp_dir, output_filename)
    
    stream = (
        ffmpeg
        .input(input_path)
        .output(output_path)
        .overwrite_output()
    )
    
    return _run_ffmpeg_with_progress(stream, output_path, progress_callback)

def convert_image_format(input_path, output_format='png'):
    """
    Converts an image file to a different format using Pillow.
    """
    temp_dir = get_temp_dir()
    output_filename = f"{uuid.uuid4()}.{output_format}"
    output_path = os.path.join(temp_dir, output_filename)
    
    try:
        with Image.open(input_path) as img:
            rgb_im = img.convert('RGB')
            rgb_im.save(output_path, format=output_format.upper())
        return output_path
    except Exception as e:
        print(f"Error converting image format: {e}")
        return None

def convert_document_format(input_path, output_format='pdf'):
    """
    Converts a document (PDF, DOCX, TXT) to another document format (PDF, DOCX, TXT).
    """
    temp_dir = get_temp_dir()
    output_filename = f"{uuid.uuid4()}.{output_format}"
    output_path = os.path.join(temp_dir, output_filename)
    
    ext = os.path.splitext(input_path)[1].lower()
    extracted_text = ""
    
    try:
        if ext == '.pdf':
            import fitz
            doc = fitz.open(input_path)
            for page in doc:
                extracted_text += page.get_text() + "\n"
        elif ext in ['.docx', '.doc']:
            import docx
            doc = docx.Document(input_path)
            extracted_text = "\n".join([p.text for p in doc.paragraphs])
        else:
            with open(input_path, 'r', encoding='utf-8', errors='ignore') as f:
                extracted_text = f.read()
                
        if not extracted_text.strip():
            extracted_text = "No text content found in original file."

        if output_format == 'txt':
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(extracted_text)
            return output_path
            
        elif output_format == 'docx':
            import docx
            doc = docx.Document()
            for line in extracted_text.split('\n'):
                doc.add_paragraph(line)
            doc.save(output_path)
            return output_path
            
        elif output_format == 'pdf':
            import fitz
            doc = fitz.open()
            page = doc.new_page()
            margin = 50
            rect = fitz.Rect(margin, margin, page.rect.width - margin, page.rect.height - margin)
            page.insert_textbox(rect, extracted_text, fontsize=11)
            doc.save(output_path)
            return output_path
            
    except Exception as e:
        print(f"Error converting document: {e}")
        return None

def translate_and_dub_media(input_path, target_lang='km', is_video=True, progress_callback=None):
    """
    1. Transcribes speech in video/audio to text.
    2. Translates text into target_lang (Khmer, English, Chinese, French, Spanish, Japanese, etc.).
    3. Generates new vocal dubbing audio using gTTS.
    4. Merges/replaces video audio track with the translated voice dubbing.
    """
    temp_dir = get_temp_dir()
    
    from plugins.document_parser import transcribe_audio_video
    if progress_callback: progress_callback("⏳ Transcribing speech from media...")
    transcript = transcribe_audio_video(input_path)
    
    if not transcript or "Error" in transcript or "Unsupported" in transcript or len(transcript.strip()) < 3:
        return "ERROR: Could not recognize speech in media."
        
    lang_names = {'km': 'Khmer', 'en': 'English', 'zh': 'Chinese (Mandarin)', 'fr': 'French', 'es': 'Spanish', 'ja': 'Japanese', 'ko': 'Korean', 'de': 'German'}
    target_lang_name = lang_names.get(target_lang[:2], 'Khmer')
    
    if progress_callback: progress_callback(f"🌐 Translating speech to {target_lang_name}...")
    
    import asyncio
    from plugins.ai_handler import get_ai_response
    prompt = (
        f"You are a professional movie dubbing director and voiceover scriptwriter.\n"
        f"Translate and adapt the following spoken transcript into natural, professional spoken {target_lang_name}.\n"
        f"Guidelines:\n"
        f"1. Make the phrasing sound like a native human speaker giving an engaging, fluent voiceover narration.\n"
        f"2. Remove filler words (um, uh, like) and smooth out choppy or awkward sentence structures.\n"
        f"3. Insert proper punctuation (commas, periods, question marks) so text-to-speech reads with natural human rhythm, pauses, and cadence.\n"
        f"4. Output ONLY the raw spoken translation in {target_lang_name} script (NO English explanations, NO markdown, NO headers, NO quotes):\n\n"
        f"{transcript}"
    )
    
    try:
        try:
            loop = asyncio.get_running_loop()
            translated_text = asyncio.run_coroutine_threadsafe(get_ai_response(0, prompt), loop).result(40)
        except RuntimeError:
            translated_text = asyncio.run(get_ai_response(0, prompt))
    except Exception as e:
        print(f"AI Translation Error: {e}")
        translated_text = transcript
        
    # Clean text strictly for gTTS speech with natural human pause punctuation
    translated_text = re.sub(r'[*#_~`>\[\]\(\)]', ' ', translated_text)
    translated_text = re.sub(r'^(Here is|Translation|Translate|Khmer|English|Note):.*$', '', translated_text, flags=re.MULTILINE | re.IGNORECASE)
    translated_text = " ".join(translated_text.split()).strip()
    
    if not translated_text:
        return "ERROR: Translation resulted in empty speech text."
        
    if progress_callback: progress_callback("🎙 Generating studio-quality voiceover dubbing...")
    from gtts import gTTS
    tts_lang = 'km' if target_lang.startswith('km') else ('zh-CN' if target_lang.startswith('zh') else target_lang[:2])
    
    raw_tts_output = os.path.join(temp_dir, f"{uuid.uuid4()}_raw_tts.mp3")
    studio_tts_output = os.path.join(temp_dir, f"{uuid.uuid4()}_studio_tts.mp3")
    synced_tts_output = os.path.join(temp_dir, f"{uuid.uuid4()}_synced_tts.mp3")
    
    try:
        tts = gTTS(text=translated_text, lang=tts_lang, slow=False)
        tts.save(raw_tts_output)
        
        # Apply professional audio studio filtering (lowpass/highpass EQ + warm volume boost)
        try:
            (
                ffmpeg
                .input(raw_tts_output)
                .filter('highpass', f=80)
                .filter('lowpass', f=12000)
                .filter('volume', 1.2)
                .output(studio_tts_output)
                .overwrite_output()
                .run(capture_stdout=True, capture_stderr=True)
            )
            if os.path.exists(studio_tts_output) and os.path.getsize(studio_tts_output) > 0:
                raw_tts_output = studio_tts_output
        except Exception as filter_e:
            print(f"Audio filter error: {filter_e}")
    except Exception as e:
        print(f"gTTS Error: {e}")
        return f"ERROR: Failed to generate TTS voice: {e}"
        
    final_audio_track = raw_tts_output
    if is_video:
        orig_duration = get_video_duration(input_path)
        tts_duration = get_video_duration(raw_tts_output)
        
        # Keep speed ratio strictly within 0.90x to 1.15x so natural voice pronunciation is preserved
        if orig_duration > 0 and tts_duration > 0:
            speed_ratio = tts_duration / orig_duration
            if 0.85 <= speed_ratio <= 1.20:
                try:
                    (
                        ffmpeg
                        .input(raw_tts_output)
                        .filter('atempo', speed_ratio)
                        .output(synced_tts_output)
                        .overwrite_output()
                        .run(capture_stdout=True, capture_stderr=True)
                    )
                    if os.path.exists(synced_tts_output) and os.path.getsize(synced_tts_output) > 0:
                        final_audio_track = synced_tts_output
                except Exception as e_tempo:
                    print(f"Atempo Sync Error: {e_tempo}")

    if progress_callback: progress_callback("🎬 Merging translated vocal audio with video...")
    output_ext = "mp4" if is_video else "mp3"
    output_path = os.path.join(temp_dir, f"{uuid.uuid4()}_dubbed.{output_ext}")
    
    if is_video:
        try:
            orig_dur = get_video_duration(input_path)
            tts_dur = get_video_duration(final_audio_track)
            target_dur = max(orig_dur, tts_dur) if (orig_dur > 0 or tts_dur > 0) else None
            
            video_input = ffmpeg.input(input_path, stream_loop=-1).video if (orig_dur > 0 and tts_dur > orig_dur) else ffmpeg.input(input_path).video
            audio_input = ffmpeg.input(final_audio_track).audio
            
            out_opts = {'vcodec': 'copy', 'acodec': 'aac'}
            if target_dur and target_dur > 0:
                out_opts['t'] = target_dur
                
            stream = ffmpeg.output(video_input, audio_input, output_path, **out_opts).overwrite_output()
            res = _run_ffmpeg_with_progress(stream, output_path, progress_callback)
        except Exception as e:
            print(f"FFmpeg Merge Error: {e}")
            res = None
    else:
        res = final_audio_track
        
    cleanup_file(raw_tts_output)
    if os.path.exists(synced_tts_output) and final_audio_track != synced_tts_output:
        cleanup_file(synced_tts_output)
        
    return res

def recap_video_audio(input_path, target_lang='km', is_video=True, voiceover=False, progress_callback=None):
    """
    1. Transcribes full speech in media.
    2. Uses Udom AI to generate a concise, structured Recap / Summary of the video/audio.
    3. If voiceover=True, converts the recap into spoken TTS voice and merges it into video/audio.
    """
    temp_dir = get_temp_dir()
    
    from plugins.document_parser import transcribe_audio_video
    if progress_callback: progress_callback("⏳ Transcribing media content for AI Recap...")
    transcript = transcribe_audio_video(input_path)
    
    if not transcript or "Error" in transcript or "Unsupported" in transcript or len(transcript.strip()) < 3:
        return "ERROR: Could not extract speech from media to generate recap.", None
        
    lang_names = {'km': 'Khmer', 'en': 'English', 'zh': 'Chinese (Mandarin)', 'fr': 'French', 'es': 'Spanish', 'ja': 'Japanese'}
    target_lang_name = lang_names.get(target_lang[:2], 'Khmer')
    
    if progress_callback: progress_callback(f"🧠 Generating AI Video Recap in {target_lang_name}...")
    
    import asyncio
    from plugins.ai_handler import get_ai_response
    prompt = (
        f"You are Udom AI. Please create a clear, engaging, and concise Recap & Summary of the following video/audio transcript in {target_lang_name}.\n"
        f"Include:\n"
        f"1. 📌 Key Highlights & Main Points\n"
        f"2. 💡 Summary of Story / Discussion\n"
        f"3. 🎯 Main Takeaways\n\n"
        f"Transcript:\n{transcript}"
    )
    
    try:
        try:
            loop = asyncio.get_running_loop()
            recap_text = asyncio.run_coroutine_threadsafe(get_ai_response(0, prompt), loop).result(45)
        except RuntimeError:
            recap_text = asyncio.run(get_ai_response(0, prompt))
    except Exception as e:
        print(f"AI Recap Error: {e}")
        recap_text = f"Failed to generate recap: {e}"
        
    if not voiceover:
        return recap_text, None
        
    # Generate Voiceover Recap Video/Audio
    if progress_callback: progress_callback("🎙 Generating Voiceover Recap audio...")
    from gtts import gTTS
    tts_lang = 'km' if target_lang.startswith('km') else ('zh-CN' if target_lang.startswith('zh') else target_lang[:2])
    
    tts_speech = re.sub(r'[*#_~`>\[\]\(\)]', ' ', recap_text)
    tts_speech = re.sub(r'^(Here is|Summary|Recap|Khmer|English|Note):.*$', '', tts_speech, flags=re.MULTILINE | re.IGNORECASE)
    tts_speech = " ".join(tts_speech.split()).strip()
    
    raw_tts = os.path.join(temp_dir, f"{uuid.uuid4()}_recap_raw.mp3")
    studio_tts = os.path.join(temp_dir, f"{uuid.uuid4()}_recap_studio.mp3")
    synced_tts = os.path.join(temp_dir, f"{uuid.uuid4()}_recap_synced.mp3")
    
    try:
        tts = gTTS(text=tts_speech, lang=tts_lang, slow=False)
        tts.save(raw_tts)
        
        # Apply professional audio studio filtering
        try:
            (
                ffmpeg
                .input(raw_tts)
                .filter('highpass', f=80)
                .filter('lowpass', f=12000)
                .filter('volume', 1.2)
                .output(studio_tts)
                .overwrite_output()
                .run(capture_stdout=True, capture_stderr=True)
            )
            if os.path.exists(studio_tts) and os.path.getsize(studio_tts) > 0:
                raw_tts = studio_tts
        except Exception as filter_e:
            print(f"Recap Audio filter error: {filter_e}")
    except Exception as e:
        print(f"Recap TTS Error: {e}")
        return recap_text, None
        
    final_audio = raw_tts
    if is_video:
        orig_dur = get_video_duration(input_path)
        tts_dur = get_video_duration(raw_tts)
        if orig_dur > 0 and tts_dur > 0:
            ratio = tts_dur / orig_dur
            if 0.85 <= ratio <= 1.20:
                try:
                    (
                        ffmpeg
                        .input(raw_tts)
                        .filter('atempo', ratio)
                        .output(synced_tts)
                        .overwrite_output()
                        .run(capture_stdout=True, capture_stderr=True)
                    )
                    if os.path.exists(synced_tts) and os.path.getsize(synced_tts) > 0:
                        final_audio = synced_tts
                except Exception as e_tempo:
                    print(f"Recap Tempo Sync Error: {e_tempo}")
                
    output_ext = "mp4" if is_video else "mp3"
    output_path = os.path.join(temp_dir, f"{uuid.uuid4()}_recap_dubbed.{output_ext}")
    
    if is_video:
        try:
            orig_dur = get_video_duration(input_path)
            tts_dur = get_video_duration(final_audio)
            target_dur = max(orig_dur, tts_dur) if (orig_dur > 0 or tts_dur > 0) else None
            
            video_input = ffmpeg.input(input_path, stream_loop=-1).video if (orig_dur > 0 and tts_dur > orig_dur) else ffmpeg.input(input_path).video
            audio_input = ffmpeg.input(final_audio).audio
            
            out_opts = {'vcodec': 'copy', 'acodec': 'aac'}
            if target_dur and target_dur > 0:
                out_opts['t'] = target_dur
                
            stream = ffmpeg.output(video_input, audio_input, output_path, **out_opts).overwrite_output()
            res_media = _run_ffmpeg_with_progress(stream, output_path, progress_callback)
        except Exception as e:
            print(f"FFmpeg Recap Merge Error: {e}")
            res_media = None
    else:
        res_media = final_audio
        
    cleanup_file(raw_tts)
    if os.path.exists(synced_tts) and final_audio != synced_tts:
        cleanup_file(synced_tts)
        
    return recap_text, res_media

def get_video_duration(file_path):
    """Accurately extracts video or audio duration in seconds using imageio_ffmpeg or ffprobe."""
    try:
        import subprocess
        import re
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        cmd = [ffmpeg_exe, "-i", file_path]
        res = subprocess.run(cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True, encoding="utf-8", errors="ignore")
        match = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", res.stderr)
        if match:
            hours, minutes, seconds = match.groups()
            return float(hours) * 3600 + float(minutes) * 60 + float(seconds)
    except Exception as e:
        print(f"Error getting duration with imageio_ffmpeg: {e}")
        
    try:
        probe = ffmpeg.probe(file_path)
        return float(probe['format']['duration'])
    except Exception as e:
        print(f"Error getting video duration: {e}")
        return 0.0

def clip_video_into_parts(input_path, num_clips=3, progress_callback=None):
    """
    Splits a video file into num_clips equal segment files using FFmpeg.
    """
    temp_dir = get_temp_dir()
    duration = get_video_duration(input_path)
    
    if duration <= 0:
        return []
        
    clip_duration = duration / max(1, num_clips)
    output_files = []
    
    for i in range(num_clips):
        start_time = i * clip_duration
        if progress_callback:
            progress_callback(f"✂️ Cutting video clip {i+1} of {num_clips}...")
            
        out_file = os.path.join(temp_dir, f"{uuid.uuid4()}_clip_{i+1}.mp4")
        try:
            stream = (
                ffmpeg
                .input(input_path, ss=start_time, t=clip_duration)
                .output(out_file, vcodec='copy', acodec='copy')
                .overwrite_output()
            )
            ffmpeg.run(stream, capture_stdout=True, capture_stderr=True)
            if os.path.exists(out_file) and os.path.getsize(out_file) > 0:
                output_files.append(out_file)
        except Exception as e:
            print(f"Error creating clip {i+1}: {e}")
            
    return output_files

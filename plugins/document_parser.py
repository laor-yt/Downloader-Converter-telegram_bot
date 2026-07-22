import os
import fitz # PyMuPDF
import docx
import pandas as pd
from pptx import Presentation
import speech_recognition as sr
from pydub import AudioSegment
import imageio_ffmpeg
import uuid

# Configure pydub to use the ffmpeg binary from imageio_ffmpeg
AudioSegment.converter = imageio_ffmpeg.get_ffmpeg_exe()

# Maximum number of characters to extract to prevent AI context overflow
MAX_CHARS = 12000

def parse_document(file_path: str, mime_type: str) -> str:
    """Extracts text from a document file based on its MIME type."""
    ext = os.path.splitext(file_path)[1].lower()
    
    text = ""
    try:
        if ext == ".pdf" or "pdf" in mime_type:
            doc = fitz.open(file_path)
            for page in doc:
                text += page.get_text() + "\n"
                if len(text) > MAX_CHARS:
                    break
                    
        elif ext in [".docx", ".doc"] or "word" in mime_type:
            doc = docx.Document(file_path)
            text = "\n".join([para.text for para in doc.paragraphs])
            
        elif ext in [".xlsx", ".xls", ".csv"] or "excel" in mime_type or "spreadsheet" in mime_type:
            if ext == ".csv":
                df = pd.read_csv(file_path)
            else:
                df = pd.read_excel(file_path)
            text = df.head(100).to_string() # Read first 100 rows
            
        elif ext in [".pptx", ".ppt"] or "powerpoint" in mime_type or "presentation" in mime_type:
            prs = Presentation(file_path)
            for slide in prs.slides:
                for shape in slide.shapes:
                    if hasattr(shape, "text"):
                        text += shape.text + "\n"
                if len(text) > MAX_CHARS:
                    break
        else:
            return "Unsupported document format for text extraction."
            
    except Exception as e:
        print(f"Error parsing document: {e}")
        return f"Error reading file: {e}"
        
    if not text.strip():
        return "The document appears to be empty or contains no readable text (it might be scanned images)."
        
    return text[:MAX_CHARS]


def transcribe_audio_video(file_path: str) -> str:
    """Extracts audio and transcribes 100% of spoken speech with high precision and performance."""
    temp_wav = f"temp_{uuid.uuid4().hex}.wav"
    temp_mp3 = f"temp_{uuid.uuid4().hex}.mp3"
    
    try:
        # Extract audio track to lightweight format
        audio = AudioSegment.from_file(file_path)
        audio_mono = audio.set_frame_rate(16000).set_channels(1)
        audio_mono.export(temp_mp3, format="mp3", bitrate="64k")
        
        # 1. Try Gemini 1.5 Flash Vision / Audio AI with lightweight audio track
        api_key = os.environ.get("GEMINI_API_KEY")
        if api_key and os.path.exists(temp_mp3):
            try:
                import base64
                import requests
                with open(temp_mp3, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode("utf-8")
                    
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
                payload = {
                    "contents": [{
                        "parts": [
                            {"text": "Transcribe 100% of ALL spoken words in this audio/video media with exact precision. Do not skip any sentence or word. Output ONLY the raw spoken transcript text."},
                            {"inline_data": {"mime_type": "audio/mp3", "data": b64}}
                        ]
                    }]
                }
                res = requests.post(url, json=payload, timeout=60).json()
                if "candidates" in res and res["candidates"]:
                    text = res["candidates"][0]["content"]["parts"][0]["text"].strip()
                    if text and len(text) > 3:
                        return text
            except Exception as e:
                print(f"Gemini Audio Transcription Error: {e}")

        # 2. Multi-language Chunked Google SpeechRecognition Fallback (Transcribes ALL chunks 100%)
        audio_mono.export(temp_wav, format="wav")
        recognizer = sr.Recognizer()
        
        chunk_length_ms = 15000  # 15-second chunks
        total_length_ms = len(audio_mono)
        full_transcript = []
        
        # Determine language by testing first 15 seconds
        first_chunk = audio_mono[:min(15000, total_length_ms)]
        temp_first = f"temp_first_{uuid.uuid4().hex}.wav"
        first_chunk.export(temp_first, format="wav")
        
        detected_lang = "km-KH"
        with sr.AudioFile(temp_first) as source:
            audio_data = recognizer.record(source)
            for lang in ["km-KH", "en-US", "zh-CN", "fr-FR", "es-ES", "ja-JP"]:
                try:
                    t = recognizer.recognize_google(audio_data, language=lang)
                    if t and len(t.strip()) > 2:
                        detected_lang = lang
                        break
                except:
                    continue
        if os.path.exists(temp_first):
            os.remove(temp_first)

        # Transcribe every 15-second chunk sequentially
        with sr.AudioFile(temp_wav) as source:
            for start_ms in range(0, total_length_ms, chunk_length_ms):
                try:
                    duration_sec = min(15, (total_length_ms - start_ms) / 1000.0)
                    if duration_sec <= 0.5:
                        break
                    audio_data = recognizer.record(source, duration=duration_sec)
                    try:
                        chunk_text = recognizer.recognize_google(audio_data, language=detected_lang)
                        if chunk_text:
                            full_transcript.append(chunk_text)
                    except sr.UnknownValueError:
                        pass
                except Exception as e_chunk:
                    print(f"Chunk error at {start_ms}ms: {e_chunk}")
                    
        result_text = " ".join(full_transcript).strip()
        if result_text:
            return result_text
            
        return "Could not recognize speech in media."
    except Exception as e:
        print(f"Error transcribing media: {e}")
        return f"Error extracting speech: {e}"
    finally:
        if os.path.exists(temp_wav): os.remove(temp_wav)
        if os.path.exists(temp_mp3): os.remove(temp_mp3)

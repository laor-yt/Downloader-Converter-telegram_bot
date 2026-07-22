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
    """Extracts audio and transcribes full speech using Gemini 1.5 Flash or multi-language SpeechRecognition."""
    # 1. Try Gemini 1.5 Flash (handles 100% multilingual audio & video transcription natively)
    api_key = os.environ.get("GEMINI_API_KEY")
    if api_key:
        try:
            import base64
            import requests
            ext = os.path.splitext(file_path)[1].lower()
            mime = "video/mp4" if ext in ['.mp4', '.mkv', '.mov', '.avi'] else "audio/mp3"
            
            with open(file_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")
                
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
            payload = {
                "contents": [{
                    "parts": [
                        {"text": "Transcribe ALL spoken words in this media file with 100% precision. Output ONLY the raw spoken transcript without any introductory text."},
                        {"inline_data": {"mime_type": mime, "data": b64}}
                    ]
                }]
            }
            res = requests.post(url, json=payload, timeout=60).json()
            if "candidates" in res and res["candidates"]:
                text = res["candidates"][0]["content"]["parts"][0]["text"].strip()
                if text:
                    return text
        except Exception as e:
            print(f"Gemini Transcription Error: {e}")

    # 2. Multi-language chunked Google SpeechRecognition Fallback
    temp_wav = f"temp_{uuid.uuid4().hex}.wav"
    try:
        audio = AudioSegment.from_file(file_path)
        if len(audio) > 180000:
            audio = audio[:180000]
        audio = audio.set_frame_rate(16000).set_channels(1)
        audio.export(temp_wav, format="wav")
        
        recognizer = sr.Recognizer()
        with sr.AudioFile(temp_wav) as source:
            audio_data = recognizer.record(source)
            for lang in ["en-US", "zh-CN", "km-KH", "fr-FR", "es-ES", "ja-JP"]:
                try:
                    text = recognizer.recognize_google(audio_data, language=lang)
                    if text and len(text.strip()) > 2:
                        return text
                except:
                    continue
        return "Could not recognize speech."
    except Exception as e:
        print(f"Error transcribing: {e}")
        return f"Error extracting audio/speech: {e}"
    finally:
        if os.path.exists(temp_wav):
            os.remove(temp_wav)

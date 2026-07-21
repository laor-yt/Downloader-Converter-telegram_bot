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
    """Extracts audio and transcribes it using Google SpeechRecognition."""
    temp_wav = f"temp_{uuid.uuid4().hex}.wav"
    try:
        # Convert audio/video to WAV 16kHz mono (best for SpeechRecognition)
        audio = AudioSegment.from_file(file_path)
        
        # Limit to first 3 minutes (180 seconds) to avoid timeouts
        if len(audio) > 180000:
            audio = audio[:180000]
            
        audio = audio.set_frame_rate(16000).set_channels(1)
        audio.export(temp_wav, format="wav")
        
        recognizer = sr.Recognizer()
        with sr.AudioFile(temp_wav) as source:
            audio_data = recognizer.record(source)
            text = recognizer.recognize_google(audio_data)
            return text
            
    except sr.UnknownValueError:
        return "No speech could be understood in the file."
    except sr.RequestError as e:
        return f"Could not request results from transcription service; {e}"
    except Exception as e:
        print(f"Error transcribing: {e}")
        return f"Error extracting audio/speech: {e}"
    finally:
        if os.path.exists(temp_wav):
            os.remove(temp_wav)

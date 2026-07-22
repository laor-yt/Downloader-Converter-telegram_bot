import os
import uuid
import ffmpeg
import imageio_ffmpeg
from PIL import Image
from utils import get_temp_dir

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

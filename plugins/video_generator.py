"""
plugins/video_generator.py  —  Free AI Video Generator (No Restrictions)
=========================================================================
Supports 3 generation modes, all 100% free:

1. TEXT-TO-VIDEO   : HuggingFace Inference API (Zeroscope, DAMO)
2. IMAGE-TO-VIDEO  : Stable Video Diffusion via HuggingFace Inference API
3. AUDIO-TO-VIDEO  : Transcribe audio → AI image scenes (FLUX) → FFmpeg slideshow

All modes fall back gracefully if the primary API is unavailable.
No API keys required (HF_TOKEN optional for higher rate limits).
"""

import os
import uuid
import time
import asyncio
import subprocess
import urllib.parse
import requests
import imageio_ffmpeg

from utils import get_temp_dir, cleanup_file

# ─── Optional HuggingFace token for higher rate limits (free tier works without) ──
HF_TOKEN = os.environ.get("HF_TOKEN", "")
_HF_HEADERS = {"Authorization": f"Bearer {HF_TOKEN}"} if HF_TOKEN else {}

# ─── Free HuggingFace text-to-video models (tried in order) ────────────────────
T2V_MODELS = [
    "cerspense/zeroscope_v2_576w",         # 576×320, fast, good quality
    "cerspense/zeroscope_v2_XL",           # 1024×576, slower, higher quality
    "damo-vilab/text-to-video-ms-1.7b",    # 256×256 fallback
    "ali-vilab/text-to-video-ms-1.7b",     # alternate mirror
]

# ─── Free HuggingFace image-to-video model ─────────────────────────────────────
I2V_MODELS = [
    "stabilityai/stable-video-diffusion-img2vid-xt",  # 25 frames, 1024×576
    "stabilityai/stable-video-diffusion-img2vid",     # 14 frames fallback
]

FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()


# ══════════════════════════════════════════════════════════════════════════════
# Internal helpers
# ══════════════════════════════════════════════════════════════════════════════

def _hf_api(model_id: str, payload, binary_input=False, timeout=300) -> bytes | None:
    """
    POST to the HuggingFace Inference API with retry on model-loading (503).
    Returns raw response bytes on success, None on failure.
    """
    url = f"https://api-inference.huggingface.co/models/{model_id}"
    headers = dict(_HF_HEADERS)

    for attempt in range(4):
        try:
            if binary_input:
                headers["Content-Type"] = "application/octet-stream"
                resp = requests.post(url, headers=headers, data=payload, timeout=timeout)
            else:
                headers["Content-Type"] = "application/json"
                resp = requests.post(url, headers=headers, json=payload, timeout=timeout)

            if resp.status_code == 200:
                return resp.content

            if resp.status_code == 503:
                wait = min(40 * (attempt + 1), 120)
                print(f"[VideoGen] {model_id} loading, retry in {wait}s…")
                time.sleep(wait)
                continue

            if resp.status_code == 429:
                print(f"[VideoGen] Rate limit on {model_id}, waiting 60s…")
                time.sleep(60)
                continue

            print(f"[VideoGen] {model_id} returned {resp.status_code}: {resp.text[:120]}")
            return None

        except requests.exceptions.Timeout:
            print(f"[VideoGen] Timeout on {model_id} (attempt {attempt+1})")
        except Exception as e:
            print(f"[VideoGen] Error calling {model_id}: {e}")

        time.sleep(10)

    return None


def _validate_and_enhance_video(raw_path: str, temp_dir: str, width=1280, height=720) -> str:
    """Upscale / re-encode raw video to 720p H.264 with FFmpeg."""
    out_path = os.path.join(temp_dir, f"enhanced_{uuid.uuid4().hex}.mp4")
    try:
        subprocess.run([
            FFMPEG_EXE, "-y", "-i", raw_path,
            "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                   f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,setsar=1,fps=24",
            "-c:v", "libx264", "-preset", "medium", "-crf", "22",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            out_path
        ], capture_output=True, timeout=120, check=True)
        if os.path.exists(out_path) and os.path.getsize(out_path) > 5000:
            cleanup_file(raw_path)
            return out_path
    except Exception as e:
        print(f"[VideoGen] Enhance error: {e}")
    return raw_path

async def _fallback_slideshow(prompt: str, temp_dir: str, progress_callback=None) -> str | None:
    if progress_callback: progress_callback("🎬 Generating cinematic scenes...")
    images = []
    for i in range(2):
        try:
            p = f"{prompt}, cinematic scene {i+1}, ultra-realistic, 8k, photorealistic"
            encoded = urllib.parse.quote(p)
            url = f"https://image.pollinations.ai/prompt/{encoded}?model=flux&width=1280&height=720&nologo=true&seed={i * 999}"
            resp = await asyncio.to_thread(requests.get, url, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
            if resp.status_code == 200 and len(resp.content) > 5000:
                p_img = os.path.join(temp_dir, f"fb_scene_{i}_{uuid.uuid4().hex}.jpg")
                with open(p_img, "wb") as f:
                    f.write(resp.content)
                images.append(p_img)
        except Exception:
            pass
            
    if not images: return None
    
    if progress_callback: progress_callback("🎬 Animating scenes...")
    out_path = os.path.join(temp_dir, f"fb_vid_{uuid.uuid4().hex}.mp4")
    try:
        inputs = []
        for img in images:
            inputs.extend(["-loop", "1", "-t", "4", "-i", img])
            
        n = len(images)
        vf = []
        for j in range(n):
            vf.append(f"[{j}:v]scale=8000:-1,zoompan=z='min(zoom+0.0015,1.5)':d=96:s=1280x720[v{j}]")
        
        concat = "".join(f"[v{j}]" for j in range(n))
        vf.append(f"{concat}concat=n={n}:v=1:a=0[outv]")
        
        cmd = [FFMPEG_EXE, "-y", *inputs, "-filter_complex", ";".join(vf), "-map", "[outv]", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-fpsmax", "24", out_path]
        subprocess.run(cmd, capture_output=True, check=True, timeout=120)
        
        if os.path.exists(out_path):
            for img in images: cleanup_file(img)
            return out_path
    except Exception as e:
        print(f"Fallback slideshow error: {e}")
        
    return None

async def _fallback_image_zoom(image_path: str, temp_dir: str, progress_callback=None) -> str | None:
    if progress_callback: progress_callback("🎬 Applying cinematic animation...")
    out_path = os.path.join(temp_dir, f"fb_img_vid_{uuid.uuid4().hex}.mp4")
    try:
        cmd = [
            FFMPEG_EXE, "-y", "-loop", "1", "-t", "5", "-i", image_path,
            "-vf", "scale=8000:-1,zoompan=z='min(zoom+0.0015,1.5)':d=120:s=1280x720",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-fpsmax", "24", out_path
        ]
        subprocess.run(cmd, capture_output=True, check=True, timeout=120)
        if os.path.exists(out_path): return out_path
    except Exception as e:
        print(f"Fallback image zoom error: {e}")
    return None

def _get_duration(file_path: str) -> float:
    """Return duration of audio/video in seconds."""
    try:
        result = subprocess.run(
            [FFMPEG_EXE, "-i", file_path, "-f", "null", "-"],
            capture_output=True, text=True, timeout=15
        )
        import re
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", result.stderr)
        if m:
            h, mn, s = m.groups()
            return int(h) * 3600 + int(mn) * 60 + float(s)
    except Exception:
        pass
    return 10.0


# ══════════════════════════════════════════════════════════════════════════════
# 1. TEXT → VIDEO
# ══════════════════════════════════════════════════════════════════════════════

async def text_to_video(prompt: str, progress_callback=None) -> str | None:
    """
    Generate a video from a text prompt using free HuggingFace models.
    Tries multiple models in order of quality.
    Returns path to MP4 file, or None on failure.
    """
    temp_dir = get_temp_dir()

    enhanced = (
        f"{prompt.strip()}, cinematic, high quality, smooth motion, "
        "4K UHD, professional cinematography, vivid colors, sharp focus, "
        "award-winning footage, no flicker, stable camera"
    )

    for model in T2V_MODELS:
        model_name = model.split("/")[-1]
        if progress_callback:
            progress_callback(f"🎬 Generating video with {model_name}…")

        video_bytes = await asyncio.to_thread(
            _hf_api, model, {"inputs": enhanced}, False, 300
        )

        if video_bytes and len(video_bytes) > 5000:
            raw = os.path.join(temp_dir, f"t2v_raw_{uuid.uuid4().hex}.mp4")
            with open(raw, "wb") as f:
                f.write(video_bytes)

            if progress_callback:
                progress_callback("✨ Enhancing resolution & quality…")
            final = _validate_and_enhance_video(raw, temp_dir)
            return final

        print(f"[VideoGen] {model_name} failed or returned too little data.")

    print("[VideoGen] All HF models failed, running fallback generator...")
    return await _fallback_slideshow(prompt, temp_dir, progress_callback)


# ══════════════════════════════════════════════════════════════════════════════
# 2. IMAGE → VIDEO
# ══════════════════════════════════════════════════════════════════════════════

async def image_to_video(image_path: str, progress_callback=None) -> str | None:
    """
    Animate a static image using Stable Video Diffusion.
    Returns path to MP4 file, or None on failure.
    """
    temp_dir = get_temp_dir()

    # Ensure image is JPEG ≤ 1024×576 (SVD requirement)
    resized_path = os.path.join(temp_dir, f"i2v_input_{uuid.uuid4().hex}.jpg")
    try:
        subprocess.run([
            FFMPEG_EXE, "-y", "-i", image_path,
            "-vf", "scale=1024:576:force_original_aspect_ratio=decrease,"
                   "pad=1024:576:(ow-iw)/2:(oh-ih)/2:white",
            "-q:v", "2", resized_path
        ], capture_output=True, timeout=30, check=True)
    except Exception as e:
        print(f"[VideoGen] Image resize error: {e}")
        resized_path = image_path

    for model in I2V_MODELS:
        model_name = model.split("/")[-1]
        if progress_callback:
            progress_callback(f"🎬 Animating image with {model_name}…")

        try:
            with open(resized_path, "rb") as f:
                img_data = f.read()
        except Exception:
            return None

        video_bytes = await asyncio.to_thread(
            _hf_api, model, img_data, True, 360
        )

        if video_bytes and len(video_bytes) > 5000:
            raw = os.path.join(temp_dir, f"i2v_raw_{uuid.uuid4().hex}.mp4")
            with open(raw, "wb") as f:
                f.write(video_bytes)

            if progress_callback:
                progress_callback("✨ Enhancing video quality…")
            final = _validate_and_enhance_video(raw, temp_dir)
            cleanup_file(resized_path)
            return final

    print("[VideoGen] All HF I2V models failed, running fallback image zoom...")
    final = await _fallback_image_zoom(resized_path, temp_dir, progress_callback)
    cleanup_file(resized_path)
    return final


# ══════════════════════════════════════════════════════════════════════════════
# 3. AUDIO → VIDEO  (Transcribe → AI Images → FFmpeg Slideshow)
# ══════════════════════════════════════════════════════════════════════════════

async def audio_to_video(audio_path: str, progress_callback=None) -> str | None:
    """
    Convert audio to video:
    1. Transcribe audio with Gemini
    2. Generate scene descriptions with AI
    3. Generate cinematic FLUX images for each scene
    4. Stitch images + original audio into slideshow MP4 with FFmpeg
    Returns path to MP4 file, or None on failure.
    """
    temp_dir = get_temp_dir()
    audio_dur = _get_duration(audio_path)

    # ── Step 1: Transcribe ────────────────────────────────────────────────
    if progress_callback:
        progress_callback("🎤 Transcribing audio content…")
    transcript = ""
    try:
        from plugins.document_parser import transcribe_audio_video
        transcript = (transcribe_audio_video(audio_path) or "").strip()[:3000]
    except Exception as e:
        print(f"[VideoGen] Transcription error: {e}")

    # ── Step 2: Generate scene descriptions ──────────────────────────────
    if progress_callback:
        progress_callback("🧠 Generating cinematic scene concepts…")

    scene_count = max(3, min(8, int(audio_dur / 8)))  # 1 scene per ~8 sec
    scenes: list[str] = []

    try:
        from plugins.ai_handler import get_ai_response
        base = transcript if transcript else "abstract music visualization, vibrant art"
        resp = await get_ai_response(
            0,
            f"Create exactly {scene_count} distinct cinematic scene descriptions for an AI image generator. "
            f"Each line = one scene. Be vivid and visual. No numbering, no bullets, no headers.\n\n"
            f"Audio content: {base}"
        )
        scenes = [s.strip() for s in resp.splitlines() if s.strip() and len(s.strip()) > 15][:scene_count]
    except Exception as e:
        print(f"[VideoGen] Scene generation error: {e}")

    if not scenes:
        scenes = [
            "dramatic golden sunset over misty mountains, cinematic, 8K",
            "abstract colorful light waves flowing through dark space",
            "close-up of musical notes floating in neon-lit studio",
            "aerial view of shimmering ocean at night with stars",
        ]

    # ── Step 3: Generate FLUX images ─────────────────────────────────────
    image_files: list[str] = []
    for i, scene in enumerate(scenes):
        if progress_callback:
            progress_callback(f"🎨 Generating scene {i+1}/{len(scenes)}…")
        try:
            prompt_full = (
                f"{scene}, ultra-realistic, professional cinematography, "
                "8K UHD, award-winning photo, cinematic lighting, tack sharp, "
                "vibrant colors, masterpiece quality"
            )
            encoded = urllib.parse.quote(prompt_full)
            img_url = (
                f"https://image.pollinations.ai/prompt/{encoded}"
                f"?model=flux&width=1920&height=1080&nologo=true&enhance=true&seed={i * 137}"
            )
            resp = requests.get(img_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
            if resp.status_code == 200 and len(resp.content) > 5000:
                img_path = os.path.join(temp_dir, f"scene_{i}_{uuid.uuid4().hex}.jpg")
                with open(img_path, "wb") as f:
                    f.write(resp.content)
                image_files.append(img_path)
        except Exception as e:
            print(f"[VideoGen] Scene {i} image error: {e}")
        await asyncio.sleep(0.5)

    if not image_files:
        return None

    # ── Step 4: Build FFmpeg slideshow with audio ─────────────────────────
    if progress_callback:
        progress_callback("🎬 Compositing video with audio…")

    out_path = os.path.join(temp_dir, f"a2v_{uuid.uuid4().hex}.mp4")
    dur_per_img = max(3.0, audio_dur / len(image_files))

    try:
        inputs_args = []
        for img in image_files:
            inputs_args += ["-loop", "1", "-t", f"{dur_per_img:.2f}", "-i", img]

        n = len(image_files)
        vf_parts = []
        for j in range(n):
            vf_parts.append(
                f"[{j}:v]scale=1920:1080:force_original_aspect_ratio=decrease,"
                f"pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black,setsar=1,fps=24,"
                f"format=yuv420p[v{j}]"
            )
        concat_in = "".join(f"[v{j}]" for j in range(n))
        vf_parts.append(f"{concat_in}concat=n={n}:v=1:a=0[video]")
        filter_complex = ";".join(vf_parts)

        cmd = [
            FFMPEG_EXE, "-y",
            *inputs_args,
            "-i", audio_path,
            "-filter_complex", filter_complex,
            "-map", "[video]",
            "-map", f"{n}:a",
            "-c:v", "libx264", "-preset", "medium", "-crf", "22",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            out_path
        ]

        result = subprocess.run(cmd, capture_output=True, timeout=600, check=True)

        if os.path.exists(out_path) and os.path.getsize(out_path) > 5000:
            for img in image_files:
                cleanup_file(img)
            return out_path

    except subprocess.CalledProcessError as e:
        print(f"[VideoGen] FFmpeg slideshow error: {e.stderr.decode()[:500]}")
    except Exception as e:
        print(f"[VideoGen] audio_to_video error: {e}")

    return None


# ══════════════════════════════════════════════════════════════════════════════
# Compress video if > 45 MB (Telegram Bot API limit)
# ══════════════════════════════════════════════════════════════════════════════

def compress_for_telegram(video_path: str, temp_dir: str, max_mb: int = 45) -> str:
    """Re-encode video to fit within Telegram's 50 MB upload limit."""
    size_mb = os.path.getsize(video_path) / (1024 * 1024)
    if size_mb <= max_mb:
        return video_path

    out_path = os.path.join(temp_dir, f"compressed_{uuid.uuid4().hex}.mp4")
    # Target bitrate based on duration
    duration = _get_duration(video_path)
    target_kbps = max(500, int((max_mb * 8 * 1024) / max(1, duration)))

    try:
        subprocess.run([
            FFMPEG_EXE, "-y", "-i", video_path,
            "-c:v", "libx264", "-preset", "fast",
            "-b:v", f"{target_kbps}k",
            "-vf", "scale=1280:-2:flags=lanczos",
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart",
            out_path
        ], capture_output=True, timeout=300, check=True)

        if os.path.exists(out_path) and os.path.getsize(out_path) > 1000:
            cleanup_file(video_path)
            return out_path
    except Exception as e:
        print(f"[VideoGen] Compression error: {e}")

    return video_path

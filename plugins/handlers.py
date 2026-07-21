import os
import uuid
import time
import asyncio
from pyrogram import Client, filters, ContinuePropagation
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup
from pyrogram.errors import MessageNotModified
from downloader import download_media
from converter import convert_video_to_audio, convert_video_format, convert_image_format
from utils import cleanup_file
from plugins.ai_handler import get_ai_response
import requests

url_cache = {}

def is_url(text):
    return "http://" in text or "https://" in text

@Client.on_message(filters.command(["start", "help"]) | filters.regex("^(ℹ️ Help)$"))
async def start_command(client, message):
    welcome_message = (
        "Welcome to the Media Downloader and Converter Bot!\n\n"
        "Send me a link to download video/audio (e.g., YouTube, TikTok).\n"
        "Send me a video or image file to convert it."
    )
    keyboard = ReplyKeyboardMarkup(
        [
            ["📥 Download Media", "🔄 Convert Media"],
            ["ℹ️ Help"]
        ],
        resize_keyboard=True
    )
    
    await message.reply_text(welcome_message, reply_markup=keyboard)

@Client.on_message(filters.regex("^(📥 Download Media|🔄 Convert Media)$"))
async def handle_menu(client, message):
    text = message.text
    if text == "📥 Download Media":
        await message.reply_text("To download media, simply send me a link (e.g., from YouTube, TikTok, Instagram, etc.). I will reply with download options!")
    elif text == "🔄 Convert Media":
        await message.reply_text("To convert media, simply send me the file (video or image). I will reply with format options!")

@Client.on_message(filters.text & ~filters.command(["start", "help"]))
async def handle_text(client, message):
    text = message.text
    if text and is_url(text):
        short_id = str(uuid.uuid4())[:8]
        url_cache[short_id] = text
        
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("Download Video", callback_data=f"dl_vid|{short_id}"),
                InlineKeyboardButton("Download Audio", callback_data=f"dl_aud|{short_id}")
            ]
        ])
        await message.reply_text("Link detected. What would you like to do?", reply_markup=keyboard)
        raise ContinuePropagation
    else:
        # Let other handlers (like AI) process non-url text
        raise ContinuePropagation

@Client.on_message(filters.photo | filters.video | filters.audio | filters.voice | filters.document)
async def handle_media(client, message):
    file_id = None
    file_name = ""
    mime_type = ""
    
    if message.photo:
        file_id = message.photo.file_id
        file_name = "image.jpg"
        mime_type = "image/jpeg"
    elif message.video:
        file_id = message.video.file_id
        file_name = message.video.file_name or "video.mp4"
        mime_type = message.video.mime_type or "video/mp4"
    elif message.audio or message.voice:
        audio = message.audio or message.voice
        file_id = audio.file_id
        file_name = getattr(audio, 'file_name', "audio.mp3")
        mime_type = getattr(audio, 'mime_type', "audio/mpeg")
    elif message.document:
        file_id = message.document.file_id
        file_name = message.document.file_name or "document"
        mime_type = message.document.mime_type or ""

    if file_id:
        short_id = str(uuid.uuid4())[:8]
        url_cache[short_id] = message # Store full message object for downloading
        
        if mime_type.startswith('image/'):
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("💬 Ask AI about Image", callback_data=f"ask_ai|{short_id}")],
                [InlineKeyboardButton("Convert to PNG", callback_data=f"conv_img|{short_id}|png")],
                [InlineKeyboardButton("Convert to JPG", callback_data=f"conv_img|{short_id}|jpg")],
                [InlineKeyboardButton("Convert to WEBP", callback_data=f"conv_img|{short_id}|webp")],
            ])
            await message.reply_text(f"Image received: {file_name}. Choose an action:", reply_markup=keyboard)
        elif mime_type.startswith('video/'):
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("Convert to MP3", callback_data=f"conv_aud|{short_id}")],
                [InlineKeyboardButton("Convert to MP4", callback_data=f"conv_vid|{short_id}|mp4")],
                [InlineKeyboardButton("Convert to MKV", callback_data=f"conv_vid|{short_id}|mkv")],
            ])
            await message.reply_text(f"Video received: {file_name}. Choose an action:", reply_markup=keyboard)
        elif mime_type.startswith('audio/'):
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("Convert to MP3", callback_data=f"conv_aud|{short_id}")]
            ])
            await message.reply_text(f"Audio received: {file_name}. Choose an action:", reply_markup=keyboard)
        else:
            await message.reply_text(f"Received unsupported file type: {mime_type or 'Unknown'}")

async def safe_edit_text(message, text, reply_markup=None):
    try:
        if reply_markup:
            await message.edit_text(text, reply_markup=reply_markup)
        else:
            await message.edit_text(text)
    except MessageNotModified:
        pass
    except Exception as e:
        print(f"Error editing message: {e}")

@Client.on_callback_query()
async def button_callback(client, callback_query):
    data = callback_query.data
    query_msg = callback_query.message
    
    if data.startswith("help_"):
        if data == "help_dl":
            text = "To download media, simply send me a link (e.g., from YouTube, TikTok, Instagram, etc.). I will reply with download options!"
        elif data == "help_conv_aud":
            text = "To convert a video to audio, simply send me the video file or document. I will reply with an option to convert it to MP3!"
        elif data == "help_conv_vid":
            text = "To convert a video format, simply send me the video file or document. I will reply with options to convert it to MP4 or MKV!"
        elif data == "help_conv_img":
            text = "To convert an image format, simply send me the photo or image document. I will reply with options to convert it to PNG, JPG, or WEBP!"
        
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_menu")]])
        await safe_edit_text(query_msg, text, reply_markup=keyboard)
        
    elif data == "back_to_menu":
        welcome_message = (
            "Welcome to the Media Downloader and Converter Bot!\n\n"
            "Send me a link to download video/audio (e.g., YouTube, TikTok).\n"
            "Send me a video or image file to convert it."
        )
        keyboard = ReplyKeyboardMarkup(
            [
                ["📥 Download Media", "🔄 Convert Media"],
                ["ℹ️ Help"]
            ],
            resize_keyboard=True
        )
        try:
            await query_msg.delete()
        except:
            pass
        await client.send_message(query_msg.chat.id, welcome_message, reply_markup=keyboard)
        
    elif data.startswith("ask_ai|"):
        _, short_id = data.split("|")
        original_msg = url_cache.get(short_id)
        
        if not original_msg:
            await query_msg.answer("Session expired. Please send the image again.", show_alert=True)
            return
            
        await safe_edit_text(query_msg, "🤔 Processing image...")
        
        try:
            # Download the image
            file_path = await client.download_media(original_msg)
            
            # Upload to catbox.moe
            with open(file_path, "rb") as f:
                response = requests.post("https://catbox.moe/user/api.php", data={"reqtype": "fileupload"}, files={"fileToUpload": (os.path.basename(file_path), f)})
                
            image_url = response.text.strip()
            
            # Clean up local file
            cleanup_file(file_path)
            
            if not image_url.startswith("http"):
                await safe_edit_text(query_msg, "Failed to upload image for analysis.")
                return
                
            # Prepare prompt
            prompt = original_msg.caption if original_msg.caption else "Describe this image in detail."
            
            # Get AI response
            reply = await get_ai_response(query_msg.chat.id, prompt, image_url=image_url)
            
            await safe_edit_text(query_msg, reply)
        except Exception as e:
            print(f"Error in ask_ai: {e}")
            await safe_edit_text(query_msg, "Failed to process image with AI.")
            
    elif data.startswith("dl_"):
        action, short_id = data.split('|', 1)
        url = url_cache.get(short_id)
        if not url:
            await safe_edit_text(query_msg, "Link expired or invalid. Please send it again.")
            return
            
        is_audio = (action == "dl_aud")
        await safe_edit_text(query_msg, "Downloading... Please wait.")
        
        last_update_time = time.time()
        last_text = ""
        loop = asyncio.get_running_loop()
        
        def progress_callback(text):
            nonlocal last_update_time, last_text
            current_time = time.time()
            if current_time - last_update_time > 2.0 and text != last_text:
                last_update_time = current_time
                last_text = text
                asyncio.run_coroutine_threadsafe(safe_edit_text(query_msg, text), loop)

        try:
            filepath = await asyncio.to_thread(download_media, url, is_audio, progress_callback)
        except Exception as e:
            print(f"Download error: {e}")
            filepath = None
        
        if filepath == 'TOO_LARGE':
            await safe_edit_text(query_msg, "❌ File is too large to send via Telegram (limit is 1.95GB).")
        elif filepath == 'BOT_DETECTED':
            await safe_edit_text(query_msg, "❌ YouTube is blocking downloads from this server. This is a known issue with cloud hosting. Try running the bot locally for YouTube downloads.")
        elif isinstance(filepath, str) and filepath.startswith('ERROR:'):
            await safe_edit_text(query_msg, f"❌ {filepath}")
        elif filepath and os.path.exists(filepath):
            await safe_edit_text(query_msg, "Download complete! Uploading...")
            
            try:
                # Use Pyrogram's built-in progress for uploading
                def pyrogram_upload_progress(current, total):
                    nonlocal last_update_time, last_text
                    current_time = time.time()
                    if current_time - last_update_time > 2.0:
                        last_update_time = current_time
                        percent = current * 100 / total
                        text = f"Uploading... {percent:.1f}% ({current/1024/1024:.1f}MB / {total/1024/1024:.1f}MB)"
                        if text != last_text:
                            last_text = text
                            asyncio.run_coroutine_threadsafe(safe_edit_text(query_msg, text), loop)
                
                if is_audio:
                    await client.send_audio(chat_id=query_msg.chat.id, audio=filepath, progress=pyrogram_upload_progress)
                else:
                    await client.send_video(chat_id=query_msg.chat.id, video=filepath, supports_streaming=True, progress=pyrogram_upload_progress)
                
                await safe_edit_text(query_msg, "Done! ✅")
            except Exception as e:
                error_str = str(e)
                print(f"Upload failed: {error_str}")
                await safe_edit_text(query_msg, f"❌ Upload failed: {error_str}")
            finally:
                cleanup_file(filepath)
        else:
            await safe_edit_text(query_msg, "❌ Failed to download the media. The link may be unsupported or geo-restricted.")
            
    elif data.startswith("conv_"):
        parts = data.split('|')
        action = parts[0]
        short_id = parts[1]
        cached_msg = url_cache.get(short_id)
        
        if not cached_msg:
            await safe_edit_text(query_msg, "Session expired. Please send the file again.")
            return
            
        await safe_edit_text(query_msg, "Downloading file from Telegram... (This is fast now!)")
        try:
            last_update_time = time.time()
            last_text = ""
            loop = asyncio.get_running_loop()
            
            def pyrogram_download_progress(current, total):
                nonlocal last_update_time, last_text
                current_time = time.time()
                if current_time - last_update_time > 2.0:
                    last_update_time = current_time
                    percent = current * 100 / total
                    text = f"Downloading... {percent:.1f}% ({current/1024/1024:.1f}MB / {total/1024/1024:.1f}MB)"
                    if text != last_text:
                        last_text = text
                        asyncio.run_coroutine_threadsafe(safe_edit_text(query_msg, text), loop)
            
            input_path = await cached_msg.download(progress=pyrogram_download_progress)
            
            await safe_edit_text(query_msg, "Converting... Please wait.")
            output_path = None
            
            def progress_callback(text):
                nonlocal last_update_time, last_text
                current_time = time.time()
                if current_time - last_update_time > 2.0 and text != last_text:
                    last_update_time = current_time
                    last_text = text
                    asyncio.run_coroutine_threadsafe(safe_edit_text(query_msg, text), loop)
                        
            if action == "conv_aud":
                output_path = await asyncio.to_thread(convert_video_to_audio, input_path, 'mp3', progress_callback)
                send_method = client.send_audio
                send_kwargs = {'audio': output_path} if output_path else {}
            elif action == "conv_vid":
                target_format = parts[2]
                output_path = await asyncio.to_thread(convert_video_format, input_path, target_format, progress_callback)
                if target_format in ['mp4', 'mkv', 'avi']:
                    send_method = client.send_video
                    send_kwargs = {'video': output_path, 'supports_streaming': True} if output_path else {}
                else:
                    send_method = client.send_document
                    send_kwargs = {'document': output_path} if output_path else {}
            elif action == "conv_img":
                target_format = parts[2]
                output_path = await asyncio.to_thread(convert_image_format, input_path, target_format)
                send_method = client.send_photo
                send_kwargs = {'photo': output_path} if output_path else {}
                
            if output_path and os.path.exists(output_path):
                await safe_edit_text(query_msg, "Conversion complete! Uploading...")
                
                def pyrogram_upload_progress(current, total):
                    nonlocal last_update_time, last_text
                    current_time = time.time()
                    if current_time - last_update_time > 2.0:
                        last_update_time = current_time
                        percent = current * 100 / total
                        text = f"Uploading... {percent:.1f}% ({current/1024/1024:.1f}MB / {total/1024/1024:.1f}MB)"
                        if text != last_text:
                            last_text = text
                            asyncio.run_coroutine_threadsafe(safe_edit_text(query_msg, text), loop)
                            
                await send_method(chat_id=query_msg.chat.id, **send_kwargs, progress=pyrogram_upload_progress)
                cleanup_file(output_path)
                await safe_edit_text(query_msg, "Done! ✅")
            else:
                await safe_edit_text(query_msg, "Failed to convert the file.")
                
            cleanup_file(input_path)
            
        except Exception as e:
            error_str = str(e)
            print(f"Error in callback: {error_str}")
            await safe_edit_text(query_msg, f"❌ An error occurred: {error_str}")

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import ContextTypes
import os
import re
from downloader import download_media
from converter import convert_video_to_audio, convert_video_format, convert_image_format
from utils import cleanup_file

def is_url(text):
    return "http://" in text or "https://" in text

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_message = (
        "Welcome to the Media Downloader and Converter Bot!\n\n"
        "Send me a link to download video/audio (e.g., YouTube, TikTok).\n"
        "Send me a video or image file to convert it."
    )
    keyboard = [
        ["📥 Download Media", "🔄 Convert Media"],
        ["ℹ️ Help"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    if update.message:
        await update.message.reply_text(welcome_message, reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.message.reply_text(welcome_message, reply_markup=reply_markup)

import uuid

url_cache = {}

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    
    if text == "📥 Download Media":
        await update.message.reply_text("To download media, simply send me a link (e.g., from YouTube, TikTok, Instagram, etc.). I will reply with download options!")
        return
    elif text == "🔄 Convert Media":
        await update.message.reply_text("To convert media, simply send me the file (video or image). I will reply with format options!")
        return
    elif text == "ℹ️ Help":
        await update.message.reply_text("This bot allows you to download videos/audio from links and convert media files between formats.\n\nJust send a link or a file to get started.")
        return
        
    if text and is_url(text):
        short_id = str(uuid.uuid4())[:8]
        url_cache[short_id] = text
        
        keyboard = [
            [
                InlineKeyboardButton("Download Video", callback_data=f"dl_vid|{short_id}"),
                InlineKeyboardButton("Download Audio", callback_data=f"dl_aud|{short_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Link detected. What would you like to do?", reply_markup=reply_markup)
        return

    # Handle document/video/photo/audio directly sent
    if update.message.photo:
        file_id = update.message.photo[-1].file_id # Get best quality
        file_name = "image.jpg"
        mime_type = "image/jpeg"
    elif update.message.video:
        file_id = update.message.video.file_id
        file_name = update.message.video.file_name or "video.mp4"
        mime_type = update.message.video.mime_type or "video/mp4"
    elif update.message.audio or update.message.voice:
        audio_obj = update.message.audio or update.message.voice
        file_id = audio_obj.file_id
        file_name = getattr(audio_obj, 'file_name', "audio.mp3")
        mime_type = getattr(audio_obj, 'mime_type', "audio/mpeg")
    elif update.message.document:
        file_id = update.message.document.file_id
        file_name = update.message.document.file_name or "document"
        mime_type = update.message.document.mime_type or ""
    else:
        file_id = None
        mime_type = ""
        file_name = ""

    if file_id:
        short_id = str(uuid.uuid4())[:8]
        url_cache[short_id] = file_id
        
        if mime_type.startswith('image/'):
            keyboard = [
                [InlineKeyboardButton("Convert to PNG", callback_data=f"conv_img|{short_id}|png")],
                [InlineKeyboardButton("Convert to JPG", callback_data=f"conv_img|{short_id}|jpg")],
                [InlineKeyboardButton("Convert to WEBP", callback_data=f"conv_img|{short_id}|webp")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(f"Image received: {file_name}. Choose an action:", reply_markup=reply_markup)
            return
        elif mime_type.startswith('video/'):
            keyboard = [
                [InlineKeyboardButton("Convert to MP3", callback_data=f"conv_aud|{short_id}")],
                [InlineKeyboardButton("Convert to MP4", callback_data=f"conv_vid|{short_id}|mp4")],
                [InlineKeyboardButton("Convert to MKV", callback_data=f"conv_vid|{short_id}|mkv")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(f"Video received: {file_name}. Choose an action:", reply_markup=reply_markup)
            return
        elif mime_type.startswith('audio/'):
            # Only allow converting to some audio types, e.g. mp3
            keyboard = [
                [InlineKeyboardButton("Convert to MP3", callback_data=f"conv_aud|{short_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(f"Audio received: {file_name}. Choose an action:", reply_markup=reply_markup)
            return
        else:
            await update.message.reply_text(f"Received unsupported file type: {mime_type or 'Unknown'}")
            return

    await update.message.reply_text("Please send a valid link or a media file.")

import time
import asyncio

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data.startswith("help_"):
        if data == "help_dl":
            text = "To download media, simply send me a link (e.g., from YouTube, TikTok, Instagram, etc.). I will reply with download options!"
        elif data == "help_conv_aud":
            text = "To convert a video to audio, simply send me the video file or document. I will reply with an option to convert it to MP3!"
        elif data == "help_conv_vid":
            text = "To convert a video format, simply send me the video file or document. I will reply with options to convert it to MP4 or MKV!"
        elif data == "help_conv_img":
            text = "To convert an image format, simply send me the photo or image document. I will reply with options to convert it to PNG, JPG, or WEBP!"
        
        keyboard = [[InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text=text, reply_markup=reply_markup)
        
    elif data == "back_to_menu":
        await start_command(update, context)
        
    elif data.startswith("dl_"):
        action, short_id = data.split('|', 1)
        url = url_cache.get(short_id)
        if not url:
            await query.edit_message_text(text="Link expired or invalid. Please send it again.")
            return
            
        is_audio = (action == "dl_aud")
        await query.edit_message_text(text="Downloading... Please wait.")
        
        last_update_time = time.time()
        last_text = ""
        loop = asyncio.get_running_loop()
        
        def progress_callback(text):
            nonlocal last_update_time, last_text
            current_time = time.time()
            if current_time - last_update_time > 2.0 and text != last_text:
                last_update_time = current_time
                last_text = text
                try:
                    asyncio.run_coroutine_threadsafe(
                        query.edit_message_text(text=text),
                        loop
                    )
                except Exception:
                    pass

        try:
            filepath = await asyncio.to_thread(download_media, url, is_audio, progress_callback)
        except Exception as e:
            print(f"Download error: {e}")
            filepath = None
        
        if filepath == 'TOO_LARGE':
            try:
                await query.edit_message_text(text="❌ File is too large to send via Telegram (limit is 1.95GB).")
            except Exception:
                pass
        elif filepath == 'BOT_DETECTED':
            try:
                await query.edit_message_text(text="❌ YouTube is blocking downloads from this server. This is a known issue with cloud hosting. Try running the bot locally for YouTube downloads.")
            except Exception:
                pass
        elif isinstance(filepath, str) and filepath.startswith('ERROR:'):
            try:
                await query.edit_message_text(text=f"❌ {filepath}")
            except Exception:
                pass
        elif filepath and os.path.exists(filepath):
            try:
                await query.edit_message_text(text="Download complete! Uploading...")
            except Exception:
                pass
            
            try:
                with open(filepath, 'rb') as f:
                    if is_audio:
                        await context.bot.send_audio(chat_id=query.message.chat_id, audio=f)
                    else:
                        await context.bot.send_video(chat_id=query.message.chat_id, video=f, supports_streaming=True)
                try:
                    await query.edit_message_text(text="Done! ✅")
                except Exception:
                    pass
            except Exception as e:
                error_str = str(e)
                print(f"Upload failed: {error_str}")
                try:
                    if "File too large" in error_str or "Entity too large" in error_str:
                        await query.edit_message_text(text="❌ Upload failed: File is larger than Telegram's 50MB bot limit.")
                    else:
                        await query.edit_message_text(text=f"❌ Upload failed: {error_str}")
                except Exception:
                    pass
            finally:
                cleanup_file(filepath)
        else:
            try:
                await query.edit_message_text(text="❌ Failed to download the media. The link may be unsupported or geo-restricted.")
            except Exception:
                pass
            
    elif data.startswith("conv_"):
        parts = data.split('|')
        action = parts[0]
        short_id = parts[1]
        file_id = url_cache.get(short_id)
        
        if not file_id:
            await query.edit_message_text(text="Session expired. Please send the file again.")
            return
            
        await query.edit_message_text(text="Downloading file from Telegram...")
        try:
            tg_file = await context.bot.get_file(file_id)
            input_path = await tg_file.download_to_drive()
            
            await query.edit_message_text(text="Converting... Please wait.")
            output_path = None
            
            last_update_time = time.time()
            last_text = ""
            loop = asyncio.get_running_loop()
            
            def progress_callback(text):
                nonlocal last_update_time, last_text
                current_time = time.time()
                if current_time - last_update_time > 2.0 and text != last_text:
                    last_update_time = current_time
                    last_text = text
                    try:
                        asyncio.run_coroutine_threadsafe(
                            query.edit_message_text(text=text),
                            loop
                        )
                    except Exception:
                        pass
                        
            if action == "conv_aud":
                output_path = await asyncio.to_thread(convert_video_to_audio, input_path, 'mp3', progress_callback)
                send_method = context.bot.send_audio
                send_kwargs = {'audio': open(output_path, 'rb')} if output_path else {}
            elif action == "conv_vid":
                target_format = parts[2]
                output_path = await asyncio.to_thread(convert_video_format, input_path, target_format, progress_callback)
                if target_format in ['mp4', 'mkv', 'avi']:
                    send_method = context.bot.send_video
                    send_kwargs = {'video': open(output_path, 'rb'), 'supports_streaming': True} if output_path else {}
                else:
                    send_method = context.bot.send_document
                    send_kwargs = {'document': open(output_path, 'rb')} if output_path else {}
            elif action == "conv_img":
                target_format = parts[2]
                output_path = await asyncio.to_thread(convert_image_format, input_path, target_format)
                send_method = context.bot.send_photo
                send_kwargs = {'photo': open(output_path, 'rb')} if output_path else {}
                
            if output_path and os.path.exists(output_path):
                await query.edit_message_text(text="Conversion complete! Uploading...")
                await send_method(chat_id=query.message.chat_id, **send_kwargs)
                send_kwargs[list(send_kwargs.keys())[0]].close()
                cleanup_file(output_path)
                await query.edit_message_text(text="Done!")
            else:
                await query.edit_message_text(text="Failed to convert the file.")
                
            cleanup_file(input_path)
            
        except Exception as e:
            error_str = str(e)
            print(f"Error in callback: {error_str}")
            if "File is too big" in error_str:
                await query.edit_message_text(text="❌ Telegram bots are strictly limited to downloading files under **20MB** directly from chat. Please send a smaller file, or use a download link instead!")
            else:
                await query.edit_message_text(text=f"❌ An error occurred: {error_str}")

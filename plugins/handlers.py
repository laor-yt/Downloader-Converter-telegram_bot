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
from plugins.document_parser import parse_document, transcribe_audio_video
import requests

url_cache = {}

def is_url(text):
    return "http://" in text or "https://" in text

@Client.on_message(filters.command(["start"]) | filters.regex("^(ℹ️ Help)$"))
async def start_command(client, message):
    welcome_message = (
        "👋 Welcome to the **Telegram AI Bot (Udom)**!\n\n"
        "⚠️ **Note:** Please wait a minute and ask again if Bot does not reply to you.\n\n"
        "To see all available commands, tap the Menu button or use the buttons below."
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🛠 Commands (Help)", callback_data="show_help")],
        [InlineKeyboardButton("ℹ️ About", callback_data="show_about")]
    ])
    
    from pyrogram.types import ReplyKeyboardRemove
    # Send welcome with inline keyboard, and remove any leftover reply keyboard
    await message.reply_text(welcome_message, reply_markup=keyboard)
    # Also send an invisible remove keyboard message just in case and delete it
    msg = await message.reply_text("Keyboard hidden.", reply_markup=ReplyKeyboardRemove(), disable_notification=True)
    await msg.delete()
    
@Client.on_message(filters.command(["help"]))
async def help_command(client, message):
    help_text = (
        "**Available Commands:**\n\n"
        "📥 `/download <link>` - Download video/audio from YouTube, TikTok, etc.\n"
        "🔄 `/convert` - Reply to or attach a media file to convert it.\n"
        "💬 `/ask <question>` - Ask the AI a question.\n"
        "🎨 `/image <prompt>` - Generate an image with AI.\n"
        "🔍 `/search <query>` - Search the web with AI."
    )
    await message.reply_text(help_text)

@Client.on_callback_query(filters.regex("^(show_help|show_about)$"))
async def handle_start_menu(client, query):
    if query.data == "show_help":
        help_text = (
            "**Available Commands:**\n\n"
            "📥 `/download <link>` - Download video/audio from YouTube, TikTok, etc.\n"
            "🔄 `/convert` - Reply to or attach a media file to convert it.\n"
            "💬 `/ask <question>` - Ask the AI a question.\n"
            "🎨 `/image <prompt>` - Generate an image with AI.\n"
            "🔍 `/search <query>` - Search the web with AI."
        )
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="start_menu")]])
        await query.message.edit_text(help_text, reply_markup=keyboard)
        
    elif query.data == "show_about":
        about_text = (
            "**About This Bot**\n\n"
            "This bot is a versatile tool for downloading, converting, and interacting with AI.\n\n"
            "Developed to provide completely free, unlimited AI features, media conversion, and YouTube downloading directly within Telegram."
        )
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="start_menu")]])
        await query.message.edit_text(about_text, reply_markup=keyboard)

@Client.on_callback_query(filters.regex("^start_menu$"))
async def handle_back_to_start(client, query):
    welcome_message = (
        "👋 Welcome to the **Telegram AI Bot**!\n\n"
        "To see all available commands, tap the Menu button or use the buttons below."
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🛠 Commands (Help)", callback_data="show_help")],
        [InlineKeyboardButton("ℹ️ About", callback_data="show_about")]
    ])
    await query.message.edit_text(welcome_message, reply_markup=keyboard)

@Client.on_message(filters.regex("^(📥 Download Media|🔄 Convert Media)$"))
async def handle_menu(client, message):
    text = message.text
    if text == "📥 Download Media":
        await message.reply_text("To download media, simply send me a link (e.g., from YouTube, TikTok, Instagram, etc.). I will reply with download options!")
    elif text == "🔄 Convert Media":
        await message.reply_text("To convert media, simply send me the file (video or image). I will reply with format options!")

@Client.on_message(filters.command("download"))
async def download_command(client, message):
    if len(message.command) < 2:
        from pyrogram.types import ForceReply
        await message.reply_text("Please paste the link you want to download below:", reply_markup=ForceReply(selective=True))
        return
        
    url = message.text.split(None, 1)[1]
    if not is_url(url):
        await message.reply_text("That doesn't look like a valid URL.")
        return
        
    short_id = str(uuid.uuid4())[:8]
    url_cache[short_id] = url
    
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📥 Download", callback_data=f"url_show_dl|{short_id}"),
            InlineKeyboardButton("🤖 Ask AI", callback_data=f"url_show_ask|{short_id}")
        ]
    ])
    await message.reply_text(f"🔗 **Link Detected:** `{url}`\nWhat would you like to do?", reply_markup=keyboard)

# Automatic URL detector: Automatically shows download buttons whenever a user pastes a link
@Client.on_message(filters.text & filters.private & ~filters.command(["download", "convert", "start", "help", "ask", "image", "search"]), group=0)
async def auto_url_and_menu_handler(client, message):
    text = message.text.strip()
    
    # 1. If text contains a URL, trigger download menu automatically
    words = text.split()
    found_url = None
    for w in words:
        if is_url(w):
            found_url = w
            break
            
    if found_url:
        short_id = str(uuid.uuid4())[:8]
        url_cache[short_id] = found_url
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("📥 Download", callback_data=f"url_show_dl|{short_id}"),
                InlineKeyboardButton("🤖 Ask AI", callback_data=f"url_show_ask|{short_id}")
            ]
        ])
        await message.reply_text(f"🔗 **Link Detected:** `{found_url}`\nWhat would you like to do?", reply_markup=keyboard)
        message.stop_propagation()
        return

    # 2. If user asks for menu or help in natural language
    if text.lower() in ["menu", "help", "start", "options", "commands"]:
        welcome_message = (
            "👋 Welcome to the **Telegram AI Bot**!\n\n"
            "To see all available commands, tap the Menu button or use the buttons below."
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🛠 Commands (Help)", callback_data="show_help")],
            [InlineKeyboardButton("ℹ️ About", callback_data="show_about")]
        ])
        await message.reply_text(welcome_message, reply_markup=keyboard)
        message.stop_propagation()
        return

@Client.on_message(filters.command("convert"))
async def convert_command(client, message):
    from pyrogram.types import ForceReply
    await message.reply_text("Please send the video or image file you want to convert below:", reply_markup=ForceReply(selective=True))

@Client.on_message(filters.photo | filters.video | filters.audio | filters.voice | filters.document)
async def handle_media(client, message):
    target_msg = message

    file_id = None
    file_name = ""
    mime_type = ""
    
    if target_msg.photo:
        file_id = target_msg.photo.file_id
        file_name = "image.jpg"
        mime_type = "image/jpeg"
    elif target_msg.video:
        file_id = target_msg.video.file_id
        file_name = target_msg.video.file_name or "video.mp4"
        mime_type = target_msg.video.mime_type or "video/mp4"
    elif target_msg.audio or target_msg.voice:
        audio = target_msg.audio or target_msg.voice
        file_id = audio.file_id
        file_name = getattr(audio, 'file_name', "audio.mp3")
        mime_type = getattr(audio, 'mime_type', "audio/mpeg")
    elif target_msg.document:
        file_id = target_msg.document.file_id
        file_name = target_msg.document.file_name or "document"
        mime_type = target_msg.document.mime_type or ""

    if file_id:
        short_id = str(uuid.uuid4())[:8]
        url_cache[short_id] = target_msg # Store full message object for downloading
        
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🔄 Convert", callback_data=f"file_show_conv|{short_id}"),
                InlineKeyboardButton("🤖 Ask AI", callback_data=f"file_show_ask|{short_id}")
            ]
        ])
        await message.reply_text(f"📁 **File Received:** `{file_name}`\nWhat would you like to do?", reply_markup=keyboard)

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
        
    elif data.startswith("file_show_main|"):
        _, short_id = data.split("|")
        original_msg = url_cache.get(short_id)
        if not original_msg:
            await callback_query.answer("Session expired. Please send the file again.", show_alert=True)
            return
        file_name = "file"
        if original_msg.photo: file_name = "image.jpg"
        elif original_msg.video: file_name = original_msg.video.file_name or "video.mp4"
        elif original_msg.audio or original_msg.voice: file_name = getattr(original_msg.audio or original_msg.voice, 'file_name', "audio.mp3")
        elif original_msg.document: file_name = original_msg.document.file_name or "document"

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🔄 Convert", callback_data=f"file_show_conv|{short_id}"),
                InlineKeyboardButton("🤖 Ask AI", callback_data=f"file_show_ask|{short_id}")
            ]
        ])
        await safe_edit_text(query_msg, f"📁 **File Received:** `{file_name}`\nWhat would you like to do?", reply_markup=keyboard)

    elif data.startswith("file_show_conv|"):
        _, short_id = data.split("|")
        original_msg = url_cache.get(short_id)
        if not original_msg:
            await callback_query.answer("Session expired. Please send the file again.", show_alert=True)
            return
            
        mime_type = ""
        file_name = ""
        if original_msg.photo:
            mime_type = "image/jpeg"
        elif original_msg.video:
            mime_type = original_msg.video.mime_type or "video/mp4"
        elif original_msg.audio or original_msg.voice:
            mime_type = getattr(original_msg.audio or original_msg.voice, 'mime_type', "audio/mpeg")
        elif original_msg.document:
            mime_type = original_msg.document.mime_type or ""
            file_name = original_msg.document.file_name or ""

        buttons = []
        if mime_type.startswith('image/'):
            buttons = [
                [InlineKeyboardButton("PNG", callback_data=f"conv_img|{short_id}|png"), InlineKeyboardButton("JPG", callback_data=f"conv_img|{short_id}|jpg"), InlineKeyboardButton("WEBP", callback_data=f"conv_img|{short_id}|webp")]
            ]
        elif mime_type.startswith('video/'):
            buttons = [
                [InlineKeyboardButton("🎬 MP4", callback_data=f"conv_vid|{short_id}|mp4"), InlineKeyboardButton("🎬 MKV", callback_data=f"conv_vid|{short_id}|mkv"), InlineKeyboardButton("🎵 MP3", callback_data=f"conv_aud|{short_id}")],
                [InlineKeyboardButton("🎙 Voice Dub & Translate", callback_data=f"file_show_dub|{short_id}")]
            ]
        elif mime_type.startswith('audio/') or original_msg.voice:
            buttons = [
                [InlineKeyboardButton("🎵 MP3", callback_data=f"conv_aud|{short_id}")],
                [InlineKeyboardButton("🎙 Voice Dub & Translate", callback_data=f"file_show_dub|{short_id}")]
            ]
        else:
            # Document conversions (PDF, DOCX, TXT)
            buttons = [
                [InlineKeyboardButton("📄 PDF", callback_data=f"conv_doc|{short_id}|pdf"), InlineKeyboardButton("📝 DOCX", callback_data=f"conv_doc|{short_id}|docx"), InlineKeyboardButton("📄 TXT", callback_data=f"conv_doc|{short_id}|txt")]
            ]

        buttons.append([InlineKeyboardButton("🔙 Back", callback_data=f"file_show_main|{short_id}")])
        keyboard = InlineKeyboardMarkup(buttons)
        await safe_edit_text(query_msg, "🔄 **Choose conversion type:**", reply_markup=keyboard)

    elif data.startswith("file_show_dub|"):
        _, short_id = data.split("|")
        original_msg = url_cache.get(short_id)
        if not original_msg:
            await callback_query.answer("Session expired. Please send the file again.", show_alert=True)
            return
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🇰🇭 Khmer", callback_data=f"dub_lang|{short_id}|km"),
                InlineKeyboardButton("🇬🇧 English", callback_data=f"dub_lang|{short_id}|en"),
                InlineKeyboardButton("🇨🇳 Chinese", callback_data=f"dub_lang|{short_id}|zh")
            ],
            [
                InlineKeyboardButton("🇫🇷 French", callback_data=f"dub_lang|{short_id}|fr"),
                InlineKeyboardButton("🇪🇸 Spanish", callback_data=f"dub_lang|{short_id}|es"),
                InlineKeyboardButton("🇯🇵 Japanese", callback_data=f"dub_lang|{short_id}|ja")
            ],
            [InlineKeyboardButton("🔙 Back", callback_data=f"file_show_conv|{short_id}")]
        ])
        await safe_edit_text(query_msg, "🎙 **Choose target language for Voice Dubbing:**", reply_markup=keyboard)

    elif data.startswith("file_show_ask|"):
        _, short_id = data.split("|")
        original_msg = url_cache.get(short_id)
        if not original_msg:
            await callback_query.answer("Session expired. Please send the file again.", show_alert=True)
            return
        file_name = "file"
        if original_msg.photo: file_name = "image.jpg"
        elif original_msg.video: file_name = original_msg.video.file_name or "video.mp4"
        elif original_msg.audio or original_msg.voice: file_name = getattr(original_msg.audio or original_msg.voice, 'file_name', "audio.mp3")
        elif original_msg.document: file_name = original_msg.document.file_name or "document"

        from pyrogram.types import ForceReply
        await client.send_message(
            query_msg.chat.id,
            f"🤖 **Ask Udom about this file:** `{file_name}` [ID:{short_id}]\n\nPlease reply directly to this message with what you want Udom to do for you:",
            reply_markup=ForceReply(selective=True)
        )

    elif data.startswith("url_show_main|"):
        _, short_id = data.split("|")
        url = url_cache.get(short_id)
        if not url:
            await callback_query.answer("Session expired. Please send the link again.", show_alert=True)
            return
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("📥 Download", callback_data=f"url_show_dl|{short_id}"),
                InlineKeyboardButton("🤖 Ask AI", callback_data=f"url_show_ask|{short_id}")
            ]
        ])
        await safe_edit_text(query_msg, f"🔗 **Link Detected:** `{url}`\nWhat would you like to do?", reply_markup=keyboard)

    elif data.startswith("url_show_dl|"):
        _, short_id = data.split("|")
        url = url_cache.get(short_id)
        if not url:
            await callback_query.answer("Session expired. Please send the link again.", show_alert=True)
            return
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🎬 Download Video", callback_data=f"dl_vid|{short_id}"),
                InlineKeyboardButton("🎵 Download Audio", callback_data=f"dl_aud|{short_id}")
            ],
            [
                InlineKeyboardButton("🔙 Back", callback_data=f"url_show_main|{short_id}")
            ]
        ])
        await safe_edit_text(query_msg, f"📥 **Download Options for:** `{url}`", reply_markup=keyboard)

    elif data.startswith("url_show_ask|"):
        _, short_id = data.split("|")
        url = url_cache.get(short_id)
        if not url:
            await callback_query.answer("Session expired. Please send the link again.", show_alert=True)
            return
        from pyrogram.types import ForceReply
        await client.send_message(
            query_msg.chat.id,
            f"🤖 **Ask Udom about this link:** `{url}`\n\nPlease reply directly to this message with what you want Udom to do for you:",
            reply_markup=ForceReply(selective=True)
        )

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
            
            # Upload to tmpfiles.org
            with open(file_path, "rb") as f:
                response = requests.post("https://tmpfiles.org/api/v1/upload", files={"file": f})
                
            data = response.json()
            image_url = ""
            if "data" in data and "url" in data["data"]:
                image_url = data["data"]["url"].replace("tmpfiles.org/", "tmpfiles.org/dl/")
                
            # Perform OCR to extract text from the image for the AI
            extracted_text = ""
            try:
                with open(file_path, "rb") as f:
                    ocr_res = requests.post(
                        "https://api.ocr.space/parse/image",
                        files={"filename": f},
                        data={"apikey": "helloworld", "language": "eng"}
                    )
                ocr_data = ocr_res.json()
                if not ocr_data.get("IsErroredOnProcessing") and ocr_data.get("ParsedResults"):
                    parsed_text = ocr_data["ParsedResults"][0].get("ParsedText", "").strip()
                    if parsed_text:
                        extracted_text = f"\n\n[Extracted Text from Image:]\n{parsed_text}"
            except Exception as e:
                print(f"OCR Error: {e}")
            
            # Clean up local file
            cleanup_file(file_path)
            
            if not image_url.startswith("http"):
                await safe_edit_text(query_msg, "Failed to upload image for analysis.")
                return
                
            # Prepare prompt
            prompt = original_msg.caption if original_msg.caption else "Analyze this image and its text in detail."
            
            prompt += extracted_text
            
            # Get AI response
            reply = await get_ai_response(query_msg.chat.id, prompt, image_url=image_url)
            
            await safe_edit_text(query_msg, reply)
        except Exception as e:
            print(f"Error in ask_ai: {e}")
            await safe_edit_text(query_msg, "Failed to process image with AI.")
            
    elif data.startswith("ask_doc|"):
        _, short_id = data.split("|")
        original_msg = url_cache.get(short_id)
        
        if not original_msg:
            await query_msg.answer("Session expired. Please send the file again.", show_alert=True)
            return
            
        await safe_edit_text(query_msg, "⏳ Downloading and analyzing file...")
        
        try:
            file_path = await client.download_media(original_msg)
            
            # Determine file type
            is_media = False
            mime_type = ""
            if original_msg.video:
                is_media = True
                mime_type = original_msg.video.mime_type
            elif original_msg.audio or original_msg.voice:
                is_media = True
                mime_type = "audio"
            elif original_msg.document:
                mime_type = str(original_msg.document.mime_type or "")
                file_name = str(original_msg.document.file_name or "").lower()
                if mime_type.startswith("video/") or mime_type.startswith("audio/") or file_name.endswith(('.mp4', '.mkv', '.avi', '.mov', '.mp3', '.wav', '.ogg', '.m4a')):
                    is_media = True
                else:
                    is_media = False
                
            text = ""
            if is_media:
                await safe_edit_text(query_msg, "⏳ Transcribing audio (this may take a minute)...")
                text = transcribe_audio_video(file_path)
            else:
                text = parse_document(file_path, str(mime_type))
                
            cleanup_file(file_path)
            
            if "Error" in text or "Unsupported" in text or not text.strip():
                await safe_edit_text(query_msg, f"❌ Failed to extract content: {text}")
                return
                
            await safe_edit_text(query_msg, "🤔 Asking AI...")
            
            prompt = "Please summarize and analyze the following document/transcript:\n\n" + text
            if original_msg.caption:
                prompt = f"User instruction: {original_msg.caption}\n\nDocument/Transcript:\n{text}"
                
            reply = await get_ai_response(query_msg.chat.id, prompt)
            await safe_edit_text(query_msg, reply)
            
        except Exception as e:
            print(f"Error in ask_doc: {e}")
            await safe_edit_text(query_msg, "❌ Failed to analyze document with AI.")
            
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
            elif action == "conv_doc":
                target_format = parts[2]
                from converter import convert_document_format
                output_path = await asyncio.to_thread(convert_document_format, input_path, target_format)
                send_method = client.send_document
                send_kwargs = {'document': output_path} if output_path else {}
            elif action == "dub_lang":
                target_lang = parts[2]
                is_video = bool(cached_msg.video or (cached_msg.document and str(cached_msg.document.mime_type or "").startswith("video/")))
                from converter import translate_and_dub_media
                output_path = await asyncio.to_thread(translate_and_dub_media, input_path, target_lang, is_video, progress_callback)
                if is_video:
                    send_method = client.send_video
                    send_kwargs = {'video': output_path, 'supports_streaming': True} if output_path and not str(output_path).startswith("ERROR:") else {}
                else:
                    send_method = client.send_audio
                    send_kwargs = {'audio': output_path} if output_path and not str(output_path).startswith("ERROR:") else {}
                
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

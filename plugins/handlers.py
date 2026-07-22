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

# ── Update offset tracker ──────────────────────────────────────────────────────
# Saves the latest processed Telegram update_id so the recovery system knows
# exactly where to resume after a server restart / downtime.
_OFFSET_FILE = os.path.join(os.path.dirname(__file__), "..", "last_update_offset.txt")

def _track_offset(message):
    """Call this at the start of every handler to track the latest offset."""
    try:
        # Pyrogram Message doesn't expose update_id directly, but we can use
        # the message_id as a proxy — recovery uses Bot API update_id separately.
        # Store the latest message date (Unix ts) to filter out already-seen messages.
        ts = int(getattr(message, "date", None) or 0)
        if ts > 0:
            with open(_OFFSET_FILE, "a") as f:
                f.write(f"msg_ts:{ts}\n")
    except Exception:
        pass


def is_url(text):
    return "http://" in text or "https://" in text


@Client.on_message(filters.command(["start"]) | filters.regex("^(ℹ️ Help)$"))
async def start_command(client, message):
    welcome_message = (
        "👋 Welcome to the **Telegram AI Bot (Udom)**!\n\n"
        "🤖 Your all-in-one AI assistant: Download • Convert • Chat • Image Generator • Voice Dubbing • Recap\n\n"
        "⚠️ **Note:** Please wait a moment and retry if the bot does not reply.\n\n"
        "Choose an option below:"
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🛠 Commands (Help)", callback_data="show_help"),
         InlineKeyboardButton("ℹ️ About", callback_data="show_about")],
        [InlineKeyboardButton("📖 How to Use / របៀបប្រើប្រាស់", callback_data="show_howto")]
    ])
    from pyrogram.types import ReplyKeyboardRemove
    await message.reply_text(welcome_message, reply_markup=keyboard)
    msg = await message.reply_text("Keyboard hidden.", reply_markup=ReplyKeyboardRemove(), disable_notification=True)
    await msg.delete()

@Client.on_message(filters.command(["help"]))
async def help_command(client, message):
    help_text = (
        "**⚡ Available Commands:**\n\n"
        "📥 `/download <link>` — Download video/audio from YouTube, TikTok, Facebook, Instagram & 1000+ sites\n"
        "🔄 `/convert` — Send a file → convert format (MP4/MP3/AVI/WebM/JPG/PNG...)\n"
        "💬 `/ask <question>` — Ask the AI anything (also works by just typing)\n"
        "🎨 `/image <prompt>` — Generate professional Full HD AI photo\n"
        "🔍 `/search <query>` — Live web search with AI summary\n"
        "🧠 `/train` — Trigger bot self-learning research session\n"
        "📊 `/brainstats` — View brain knowledge base stats\n"
        "🕒 `/timezone +7` — Set your local timezone\n"
        "📖 `/howto` — How to use this bot (Khmer/English guide)\n\n"
        "_You can also just send any URL, file, photo or voice message directly!_"
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📖 How to Use / របៀបប្រើប្រាស់", callback_data="show_howto")]
    ])
    await message.reply_text(help_text, reply_markup=keyboard)

@Client.on_message(filters.command(["howto"]))
async def howto_command(client, message):
    """Show the How to Use language chooser."""
    chooser = (
        "📖 **How to Use / របៀបប្រើប្រាស់**\n\n"
        "Please choose your language:\nសូមជ្រើសរើសភាសា:"
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🇰🇭 ភាសាខ្មែរ (Khmer)", callback_data="howto_km")],
        [InlineKeyboardButton("🇬🇧 English", callback_data="howto_en")]
    ])
    await message.reply_text(chooser, reply_markup=keyboard)


@Client.on_callback_query(filters.regex("^(show_help|show_about|show_howto)$"))
async def handle_start_menu(client, query):
    if query.data == "show_help":
        help_text = (
            "**⚡ Available Commands:**\n\n"
            "📥 `/download <link>` — Download video/audio from YouTube, TikTok, Facebook, Instagram & 1000+ sites\n"
            "🔄 `/convert` — Send a file → convert format (MP4/MP3/AVI/WebM/JPG/PNG...)\n"
            "💬 `/ask <question>` — Ask the AI anything (also works by just typing)\n"
            "🎨 `/image <prompt>` — Generate professional Full HD AI photo\n"
            "🔍 `/search <query>` — Live web search with AI summary\n"
            "🧠 `/train` — Trigger bot self-learning research session\n"
            "📊 `/brainstats` — View brain knowledge base stats\n"
            "🕒 `/timezone +7` — Set your local timezone\n"
            "📖 `/howto` — How to use this bot (Khmer/English guide)\n\n"
            "_You can also just send any URL, file, photo or voice message directly!_"
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📖 How to Use", callback_data="show_howto")],
            [InlineKeyboardButton("🔙 Back", callback_data="start_menu")]
        ])
        await query.message.edit_text(help_text, reply_markup=keyboard)

    elif query.data == "show_about":
        about_text = (
            "**🤖 About Udom AI Bot**\n\n"
            "An all-in-one free Telegram AI assistant with:\n"
            "• 📥 Media downloader (1000+ sites)\n"
            "• 🔄 Format converter (video/audio/image)\n"
            "• 💬 AI chat (Gemini + GPT powered)\n"
            "• 🎨 Professional AI image generator (FLUX)\n"
            "• 🎙 AI Voice Dubbing & Translation\n"
            "• 📝 AI Video/Audio Recap & Summary\n"
            "• 🧠 Self-learning brain (auto-trains every 6h)\n"
            "• 🔄 Missed message recovery (replies even after downtime)\n\n"
            "_Built with ❤️ — 100% free, no limits._"
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📖 How to Use", callback_data="show_howto")],
            [InlineKeyboardButton("🔙 Back", callback_data="start_menu")]
        ])
        await query.message.edit_text(about_text, reply_markup=keyboard)

    elif query.data == "show_howto":
        howto_chooser = (
            "📖 **How to Use / របៀបប្រើប្រាស់**\n\n"
            "Please choose your language:\nសូមជ្រើសរើសភាសា:"
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🇰🇭 ភាសាខ្មែរ (Khmer)", callback_data="howto_km")],
            [InlineKeyboardButton("🇬🇧 English", callback_data="howto_en")],
            [InlineKeyboardButton("🔙 Back", callback_data="start_menu")]
        ])
        await query.message.edit_text(howto_chooser, reply_markup=keyboard)


@Client.on_callback_query(filters.regex("^(howto_km|howto_en)$"))
async def handle_howto_guide(client, query):
    back_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 ត្រឡប់ / Back", callback_data="show_howto")]
    ])

    if query.data == "howto_km":
        guide = (
            "📖 **របៀបប្រើប្រាស់ Bot Udom AI**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

            "📥 **ទាញយកវីដេអូ / អូឌីយ៉ូ**\n"
            "① ចម្លង link ពី YouTube, TikTok, Facebook, Instagram ជាដើម\n"
            "② ផ្ញើ link ទៅ Bot ផ្ទាល់\n"
            "③ Bot នឹងផ្ញើឯកសារ ឬ ជម្រើស ទាញយក\n"
            "💡 ឬប្រើ: `/download https://youtube.com/...`\n\n"

            "🔄 **បំលែងទ្រង់ទ្រាយ (Convert)**\n"
            "① ផ្ញើឯកសារ (វីដេអូ / រូបភាព / អូឌីយ៉ូ) ទៅ Bot\n"
            "② ចុចប៊ូតុង **🔄 Convert** ដែលលេចឡើង\n"
            "③ ជ្រើសរើសទ្រង់ទ្រាយថ្មី (MP4, MP3, AVI, PNG...)\n\n"

            "🎙 **ដាក់សំឡេងបកប្រែ (AI Voice Dubbing)**\n"
            "① ផ្ញើឯកសារ ឬ link វីដេអូ\n"
            "② ចុចប៊ូតុង **🎙 Voice Dub & Translate**\n"
            "③ ជ្រើសរើសភាសាគោលដៅ (ខ្មែរ / អង់គ្លេស / ចិន...)\n"
            "④ Bot នឹងផ្ញើវីដេអូមកវិញ ដែលមានសំឡេងបកប្រែ\n\n"

            "📝 **សង្ខេបវីដេអូ (AI Recap)**\n"
            "① ផ្ញើឯកសារ ឬ link វីដេអូ\n"
            "② ចុចប៊ូតុង **📝 AI Video Recap**\n"
            "③ ជ្រើសរើសភាសា — Bot នឹងបង្កើតសង្ខេបខ្លី 5-10 ប្រយោគ\n\n"

            "🎨 **បង្កើតរូបភាព AI**\n"
            "① វាយ: `generate image ព្រៃភ្នំ ពេលព្រឹក`\n"
            "② ឬប្រើ: `/image a beautiful Cambodian temple at sunset`\n"
            "③ Bot នឹងបង្កើតរូបភាព Full HD ភ្លាមៗ\n\n"

            "💬 **ចូលសន話ជាមួយ AI**\n"
            "① វាយសំណួរ ឬ ប្រធានបទណាមួយ\n"
            "② Bot នឹងឆ្លើយតប ជាភាសាដែលអ្នកប្រើ\n"
            "③ ផ្ញើរូបភាព ដើម្បីឱ្យ Bot វិភាគ ឬ ពិពណ៌នា\n\n"

            "🔍 **ស្វែងរកលើអ៊ីនធឺណិត**\n"
            "① `/search ប្រទេសកម្ពុជា` — Bot ស្វែងរក ហើយសង្ខេបលទ្ធផលភ្លាមៗ\n\n"

            "📄 **វិភាគឯកសារ (PDF/Word/Excel)**\n"
            "① ផ្ញើឯកសារ PDF, Word, Excel, PowerPoint\n"
            "② Bot នឹងអានមាតិការ ហើយអ្នកអាចសួរសំណួរអំពីឯកសារ\n\n"

            "⚠️ **ចំណាំ:**\n"
            "• ប្រសិន Bot មិនឆ្លើយ → រង់ចាំ 1 នាទី ហើយផ្ញើម្ដងទៀត\n"
            "• Bot នឹងឆ្លើយតបសំណូមពរដែលបាន queue ទុក ពេល server ចាប់ផ្ដើមឡើងវិញ"
        )
        await query.message.edit_text(guide, reply_markup=back_kb)

    elif query.data == "howto_en":
        guide = (
            "📖 **How to Use Udom AI Bot**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

            "📥 **Download Video / Audio**\n"
            "① Copy a link from YouTube, TikTok, Facebook, Instagram, etc.\n"
            "② Send the link directly to the bot\n"
            "③ The bot will send download options or the file directly\n"
            "💡 Or use: `/download https://youtube.com/...`\n\n"

            "🔄 **Convert Media Format**\n"
            "① Send a video, audio, or image file to the bot\n"
            "② Tap the **🔄 Convert** button that appears\n"
            "③ Choose a new format (MP4, MP3, AVI, WebM, PNG, JPG...)\n\n"

            "🎙 **AI Voice Dubbing & Translation**\n"
            "① Send a video file or link\n"
            "② Tap **🎙 Voice Dub & Translate**\n"
            "③ Choose the target language (Khmer / English / Chinese / French...)\n"
            "④ The bot sends back the video with translated dubbed voice\n"
            "   (original background music preserved at 20% volume)\n\n"

            "📝 **AI Video Recap & Summary**\n"
            "① Send a video/audio file or link\n"
            "② Tap **📝 AI Video Recap**\n"
            "③ Choose language — bot generates a short 5-10 sentence spoken summary\n\n"

            "🎨 **Generate AI Images**\n"
            "① Type: `generate image a lion at sunset`\n"
            "② Or use: `/image beautiful Angkor Wat at golden hour`\n"
            "③ Bot generates a professional Full HD photo instantly\n"
            "   (auto-detects: portrait / landscape / food / product / fantasy style)\n\n"

            "💬 **Chat with AI**\n"
            "① Just type any question or message\n"
            "② The bot replies in the same language you used\n"
            "③ Send a photo → bot analyzes and describes it\n"
            "④ Send a voice message → bot transcribes and replies\n\n"

            "🔍 **Live Web Search**\n"
            "① `/search Cambodia tourism 2025` — bot searches + AI summary\n\n"

            "📄 **Document Analysis (PDF/Word/Excel)**\n"
            "① Send any PDF, Word (.docx), Excel (.xlsx) or PowerPoint file\n"
            "② Bot reads the content — then ask any question about it\n\n"

            "✂️ **Video Clipper**\n"
            "① Send a video file\n"
            "② Type a number (1–10) when prompted to split into equal clips\n\n"

            "⚠️ **Tips:**\n"
            "• If the bot doesn't reply → wait 1 min and retry\n"
            "• After a server restart, the bot auto-replies to missed messages\n"
            "• Use `/brainstats` to see how much the bot has learned\n"
            "• Use `/train` to make the bot research & learn new topics now"
        )
        await query.message.edit_text(guide, reply_markup=back_kb)


@Client.on_callback_query(filters.regex("^start_menu$"))
async def handle_back_to_start(client, query):
    welcome_message = (
        "👋 Welcome to the **Telegram AI Bot (Udom)**!\n\n"
        "🤖 Your all-in-one AI assistant: Download • Convert • Chat • Image Generator • Voice Dubbing • Recap\n\n"
        "Choose an option below:"
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🛠 Commands (Help)", callback_data="show_help"),
         InlineKeyboardButton("ℹ️ About", callback_data="show_about")],
        [InlineKeyboardButton("📖 How to Use / របៀបប្រើប្រាស់", callback_data="show_howto")]
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

class RealtimeTimer:
    def __init__(self, message, initial_text="Thinking"):
        self.message = message
        self.current_text = initial_text
        self.start_time = time.time()
        self.stop_event = asyncio.Event()
        self.task = None

    def update_text(self, text):
        self.current_text = text

    async def _timer_loop(self):
        last_sent = ""
        dot_count = 1
        while not self.stop_event.is_set():
            elapsed = int(time.time() - self.start_time)
            mins, secs = divmod(elapsed, 60)
            
            dots = "." * dot_count
            dot_count = (dot_count % 3) + 1  # 1 -> 2 -> 3 -> 1 -> 2 -> 3
            
            clean_text = self.current_text.rstrip(". ").strip()
            formatted = f"⏱ [{mins:02d}:{secs:02d}] {clean_text} {dots}"
            
            if formatted != last_sent:
                last_sent = formatted
                try:
                    await self.message.edit_text(formatted)
                except MessageNotModified:
                    pass
                except Exception:
                    pass
            try:
                await asyncio.sleep(1.0)
            except (asyncio.CancelledError, Exception):
                break

    async def __aenter__(self):
        self.task = asyncio.create_task(self._timer_loop())
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.stop_event.set()
        if self.task:
            self.task.cancel()

message_start_times = {}

async def safe_edit_text(message, text, reply_markup=None):
    msg_id = getattr(message, 'id', None)
    if msg_id:
        if msg_id not in message_start_times:
            message_start_times[msg_id] = time.time()
            
        start_time = message_start_times[msg_id]
        elapsed = int(time.time() - start_time)
        mins, secs = divmod(elapsed, 60)
        
        is_done = "Done!" in text or "complete!" in text or "❌" in text or "Received:" in text or "Detected:" in text
        if not is_done and elapsed > 0:
            time_tag = f"⏱ [{mins:02d}:{secs:02d}] "
            if not text.startswith("⏱"):
                text = f"{time_tag}{text}"
                
        if is_done:
            message_start_times.pop(msg_id, None)

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
                [InlineKeyboardButton("🎙 Voice Dub & Translate", callback_data=f"file_show_dub|{short_id}"), InlineKeyboardButton("✂️ Clip Video", callback_data=f"file_show_clip|{short_id}")],
                [InlineKeyboardButton("📝 AI Video Recap", callback_data=f"file_show_recap|{short_id}")]
            ]
        elif mime_type.startswith('audio/') or original_msg.voice:
            buttons = [
                [InlineKeyboardButton("🎵 MP3", callback_data=f"conv_aud|{short_id}")],
                [InlineKeyboardButton("🎙 Voice Dub & Translate", callback_data=f"file_show_dub|{short_id}"), InlineKeyboardButton("📝 AI Audio Recap", callback_data=f"file_show_recap|{short_id}")]
            ]
        else:
            # Document conversions (PDF, DOCX, TXT)
            buttons = [
                [InlineKeyboardButton("📄 PDF", callback_data=f"conv_doc|{short_id}|pdf"), InlineKeyboardButton("📝 DOCX", callback_data=f"conv_doc|{short_id}|docx"), InlineKeyboardButton("📄 TXT", callback_data=f"conv_doc|{short_id}|txt")]
            ]

        buttons.append([InlineKeyboardButton("🔙 Back", callback_data=f"file_show_main|{short_id}")])
        keyboard = InlineKeyboardMarkup(buttons)
        await safe_edit_text(query_msg, "🔄 **Choose conversion type:**", reply_markup=keyboard)

    elif data.startswith("file_show_clip|"):
        _, short_id = data.split("|")
        original_msg = url_cache.get(short_id)
        if not original_msg:
            await callback_query.answer("Session expired. Please send the file again.", show_alert=True)
            return
        from pyrogram.types import ForceReply
        await client.send_message(
            query_msg.chat.id,
            f"✂️ **How many clips do you want from this video?** [ID:{short_id}]\n\nPlease reply directly to this message with a number (e.g. 2, 3, 5):",
            reply_markup=ForceReply(selective=True)
        )

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

    elif data.startswith("file_show_recap|"):
        _, short_id = data.split("|")
        original_msg = url_cache.get(short_id)
        if not original_msg:
            await callback_query.answer("Session expired. Please send the file again.", show_alert=True)
            return
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🇰🇭 Khmer", callback_data=f"recap_file|{short_id}|km"),
                InlineKeyboardButton("🇬🇧 English", callback_data=f"recap_file|{short_id}|en"),
                InlineKeyboardButton("🇨🇳 Chinese", callback_data=f"recap_file|{short_id}|zh")
            ],
            [
                InlineKeyboardButton("🇫🇷 French", callback_data=f"recap_file|{short_id}|fr"),
                InlineKeyboardButton("🇪🇸 Spanish", callback_data=f"recap_file|{short_id}|es"),
                InlineKeyboardButton("🇯🇵 Japanese", callback_data=f"recap_file|{short_id}|ja")
            ],
            [InlineKeyboardButton("🔙 Back", callback_data=f"file_show_conv|{short_id}")]
        ])
        await safe_edit_text(query_msg, "📝 **Choose target language for AI Video Recap & Voiceover:**", reply_markup=keyboard)

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
                InlineKeyboardButton("🎙 Voice Dub & Translate", callback_data=f"url_show_dub|{short_id}"),
                InlineKeyboardButton("✂️ Clip Video", callback_data=f"url_show_clip|{short_id}")
            ],
            [
                InlineKeyboardButton("📝 AI Video Recap", callback_data=f"url_show_recap|{short_id}")
            ],
            [
                InlineKeyboardButton("🔙 Back", callback_data=f"url_show_main|{short_id}")
            ]
        ])
        await safe_edit_text(query_msg, f"📥 **Download Options for:** `{url}`", reply_markup=keyboard)

    elif data.startswith("url_show_dub|"):
        _, short_id = data.split("|")
        url = url_cache.get(short_id)
        if not url:
            await callback_query.answer("Session expired. Please send the link again.", show_alert=True)
            return
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🇰🇭 Khmer", callback_data=f"url_dub_lang|{short_id}|km"),
                InlineKeyboardButton("🇬🇧 English", callback_data=f"url_dub_lang|{short_id}|en"),
                InlineKeyboardButton("🇨🇳 Chinese", callback_data=f"url_dub_lang|{short_id}|zh")
            ],
            [
                InlineKeyboardButton("🇫🇷 French", callback_data=f"url_dub_lang|{short_id}|fr"),
                InlineKeyboardButton("🇪🇸 Spanish", callback_data=f"url_dub_lang|{short_id}|es"),
                InlineKeyboardButton("🇯🇵 Japanese", callback_data=f"url_dub_lang|{short_id}|ja")
            ],
            [InlineKeyboardButton("🔙 Back", callback_data=f"url_show_dl|{short_id}")]
        ])
        await safe_edit_text(query_msg, f"🎙 **Choose target language for Voice Dubbing:**\n`{url}`", reply_markup=keyboard)

    elif data.startswith("url_show_recap|"):
        _, short_id = data.split("|")
        url = url_cache.get(short_id)
        if not url:
            await callback_query.answer("Session expired. Please send the link again.", show_alert=True)
            return
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🇰🇭 Khmer", callback_data=f"recap_url|{short_id}|km"),
                InlineKeyboardButton("🇬🇧 English", callback_data=f"recap_url|{short_id}|en"),
                InlineKeyboardButton("🇨🇳 Chinese", callback_data=f"recap_url|{short_id}|zh")
            ],
            [
                InlineKeyboardButton("🇫🇷 French", callback_data=f"recap_url|{short_id}|fr"),
                InlineKeyboardButton("🇪🇸 Spanish", callback_data=f"recap_url|{short_id}|es"),
                InlineKeyboardButton("🇯🇵 Japanese", callback_data=f"recap_url|{short_id}|ja")
            ],
            [InlineKeyboardButton("🔙 Back", callback_data=f"url_show_dl|{short_id}")]
        ])
        await safe_edit_text(query_msg, f"📝 **Choose target language for AI Video Recap & Voiceover:**\n`{url}`", reply_markup=keyboard)

    elif data.startswith("url_show_clip|"):
        _, short_id = data.split("|")
        url = url_cache.get(short_id)
        if not url:
            await callback_query.answer("Session expired. Please send the link again.", show_alert=True)
            return
        from pyrogram.types import ForceReply
        await client.send_message(
            query_msg.chat.id,
            f"✂️ **How many clips do you want from this video link?** [ID:{short_id}]\n\nPlease reply directly to this message with a number (e.g. 2, 3, 5):",
            reply_markup=ForceReply(selective=True)
        )

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
        
        async with RealtimeTimer(query_msg, "Downloading... Please wait.") as timer:
            loop = asyncio.get_running_loop()
            
            def progress_callback(text):
                timer.update_text(text)

            try:
                filepath = await asyncio.to_thread(download_media, url, is_audio, progress_callback)
            except Exception as e:
                print(f"Download error: {e}")
                filepath = None
            
            if filepath == 'TOO_LARGE':
                await safe_edit_text(query_msg, "❌ File is too large to send via Telegram (limit is 1.95GB).")
            elif filepath == 'BOT_DETECTED':
                await safe_edit_text(query_msg, "❌ YouTube is blocking downloads from this server. Try running locally.")
            elif isinstance(filepath, str) and filepath.startswith('ERROR:'):
                await safe_edit_text(query_msg, f"❌ {filepath}")
            elif filepath and os.path.exists(filepath):
                timer.update_text("Download complete! Uploading...")
                
                try:
                    def pyrogram_upload_progress(current, total):
                        percent = current * 100 / total
                        timer.update_text(f"Uploading... {percent:.1f}% ({current/1024/1024:.1f}MB / {total/1024/1024:.1f}MB)")
                    
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
    elif data.startswith("url_dub_lang|"):
        parts = data.split("|")
        short_id = parts[1]
        target_lang = parts[2]
        url = url_cache.get(short_id)
        if not url:
            await safe_edit_text(query_msg, "Link expired or invalid. Please send it again.")
            return

        async with RealtimeTimer(query_msg, f"📥 Downloading video from link... `{url}`") as timer:
            def progress_cb(text):
                timer.update_text(text)

            try:
                dl_res = await asyncio.to_thread(download_media, url, False, progress_cb)
                input_path = dl_res[0] if isinstance(dl_res, tuple) else dl_res
                
                if input_path and os.path.exists(input_path):
                    from converter import translate_and_dub_media
                    output_path = await asyncio.to_thread(translate_and_dub_media, input_path, target_lang, True, progress_cb)
                    
                    if output_path and isinstance(output_path, str) and not output_path.startswith("ERROR:") and os.path.exists(output_path):
                        timer.update_text("Dubbing complete! Uploading translated video...")
                        
                        def pyrogram_upload_progress(current, total):
                            percent = current * 100 / total
                            timer.update_text(f"Uploading... {percent:.1f}% ({current/1024/1024:.1f}MB / {total/1024/1024:.1f}MB)")
                                    
                        await client.send_video(chat_id=query_msg.chat.id, video=output_path, supports_streaming=True, progress=pyrogram_upload_progress)
                        cleanup_file(output_path)
                        await safe_edit_text(query_msg, "Voice dubbing from link complete! ✅")
                    else:
                        err_msg = output_path if isinstance(output_path, str) else "Failed to dub media."
                        await safe_edit_text(query_msg, f"❌ {err_msg}")
                        
                    cleanup_file(input_path)
                else:
                    await safe_edit_text(query_msg, "❌ Failed to download video from link for dubbing.")
            except Exception as e:
                print(f"URL Dubbing error: {e}")
                await safe_edit_text(query_msg, f"❌ Dubbing failed: {e}")

    elif data.startswith("recap_url|"):
        parts = data.split("|")
        short_id = parts[1]
        lang = parts[2]
        url = url_cache.get(short_id)
        if not url:
            await safe_edit_text(query_msg, "Link expired or invalid. Please send it again.")
            return

        async with RealtimeTimer(query_msg, f"🧠 Analyzing video content & generating Voiceover Recap... `{url}`") as timer:
            def progress_cb(text):
                timer.update_text(text)

            try:
                dl_res = await asyncio.to_thread(download_media, url, False, progress_cb)
                input_path = dl_res[0] if isinstance(dl_res, tuple) else dl_res
                
                if input_path and os.path.exists(input_path):
                    from converter import recap_video_audio
                    recap_text, media_out = await asyncio.to_thread(recap_video_audio, input_path, lang, True, True, progress_cb)
                    
                    await safe_edit_text(query_msg, recap_text)
                    if media_out and os.path.exists(media_out):
                        await client.send_video(chat_id=query_msg.chat.id, video=media_out, caption=f"🎙 **Voiceover Recap Video ({lang.upper()})**", supports_streaming=True)
                        cleanup_file(media_out)
                    cleanup_file(input_path)
                else:
                    await safe_edit_text(query_msg, "❌ Failed to download video for recap.")
            except Exception as e:
                print(f"URL Recap error: {e}")
                await safe_edit_text(query_msg, f"❌ Recap failed: {e}")

    elif data.startswith("conv_") or data.startswith("dub_lang|") or data.startswith("recap_file|"):
        parts = data.split('|')
        action = parts[0]
        short_id = parts[1]
        cached_msg = url_cache.get(short_id)
        
        if not cached_msg:
            await safe_edit_text(query_msg, "Session expired. Please send the file again.")
            return
            
        async with RealtimeTimer(query_msg, "Downloading file from Telegram...") as timer:
            try:
                def pyrogram_download_progress(current, total):
                    percent = current * 100 / total
                    timer.update_text(f"Downloading... {percent:.1f}% ({current/1024/1024:.1f}MB / {total/1024/1024:.1f}MB)")
                
                input_path = await cached_msg.download(progress=pyrogram_download_progress)
                timer.update_text("Converting... Please wait.")
                output_path = None
                
                def progress_callback(text):
                    timer.update_text(text)
                            
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
                elif action == "recap_file":
                    lang = parts[2]
                    is_video = bool(cached_msg.video or (cached_msg.document and str(cached_msg.document.mime_type or "").startswith("video/")))
                    from converter import recap_video_audio
                    recap_text, media_out = await asyncio.to_thread(recap_video_audio, input_path, lang, is_video, True, progress_callback)
                    
                    await safe_edit_text(query_msg, recap_text)
                    if media_out and os.path.exists(media_out):
                        if is_video:
                            await client.send_video(chat_id=query_msg.chat.id, video=media_out, caption=f"🎙 **Voiceover Recap Video ({lang.upper()})**", supports_streaming=True)
                        else:
                            await client.send_audio(chat_id=query_msg.chat.id, audio=media_out, caption=f"🎙 **Voiceover Recap Audio ({lang.upper()})**")
                        cleanup_file(media_out)
                    cleanup_file(input_path)
                    return
                    
                if output_path and os.path.exists(output_path):
                    timer.update_text("Conversion complete! Uploading...")
                    
                    def pyrogram_upload_progress(current, total):
                        percent = current * 100 / total
                        timer.update_text(f"Uploading... {percent:.1f}% ({current/1024/1024:.1f}MB / {total/1024/1024:.1f}MB)")
                                
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

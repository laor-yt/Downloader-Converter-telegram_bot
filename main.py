import os
import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from dotenv import load_dotenv
from pyrogram import Client
from utils import get_temp_dir

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

class DummyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"Bot is running")

    def do_HEAD(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()

def run_dummy_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), DummyHandler)
    server.serve_forever()

def main():
    """Start the bot."""
    load_dotenv()
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    api_id = os.environ.get("API_ID")
    api_hash = os.environ.get("API_HASH")
    
    if not token or token == "your_bot_token_here":
        logger.error("No valid Telegram Bot Token found. Please update .env")
        return
        
    if not api_id or not api_hash:
        logger.error("API_ID and API_HASH are required for Pyrogram. Please add them to your environment variables.")
        return

    # Ensure temp dir exists
    get_temp_dir()

    # Start dummy web server to keep Render Web Service happy
    threading.Thread(target=run_dummy_server, daemon=True).start()

    logger.info("Bot started...")
    
    app = Client(
        "my_bot",
        bot_token=token,
        api_id=int(api_id),
        api_hash=api_hash,
        plugins=dict(root="plugins")
    )
    
    import time
    from pyrogram.errors import FloodWait

    while True:
        try:
            app.start()
            break
        except FloodWait as e:
            logger.warning(f"Telegram FloodWait: waiting {e.value}s before retrying auth...")
            try:
                from plugins.recovery import run_http_fallback_loop
                logger.info(f"[Fallback] Activating HTTP Bot API mode so bot can reply to /start and user messages now!")
                app.loop.run_until_complete(run_http_fallback_loop(token, e.value + 2))
            except Exception as fb_err:
                logger.error(f"[Fallback] Fallback error: {fb_err}")
                time.sleep(e.value + 2)
        except Exception as e:
            logger.error(f"Failed to start Pyrogram client: {e}")
            raise e

    # ── Non-blocking background startup tasks ────────────────────────────────
    async def post_startup_tasks():
        # 1. Set bot commands & descriptions
        try:
            from pyrogram.types import BotCommand
            await app.set_bot_commands([
                BotCommand("start", "Start the bot"),
                BotCommand("download", "Download media from a link"),
                BotCommand("convert", "Convert a media file"),
                BotCommand("video", "🎬 Generate AI video (text/image/audio)"),
                BotCommand("image", "Generate a professional AI image"),
                BotCommand("ask", "Ask the AI a question"),
                BotCommand("search", "Search the web with AI"),
                BotCommand("train", "Trigger AI self-training research session"),
                BotCommand("brainstats", "View brain knowledge base stats"),
                BotCommand("timezone", "Set your local timezone"),
                BotCommand("howto", "How to use this bot (Khmer/English)"),
                BotCommand("help", "Show all features & help info")
            ])
            import requests
            desc = "👋 Welcome to Telegram AI Bot (Udom)!\n\n⚠️ Note: Please wait a minute and ask again if Bot does not reply to you."
            requests.post(f"https://api.telegram.org/bot{token}/setMyDescription", json={"description": desc}, timeout=10)
            requests.post(f"https://api.telegram.org/bot{token}/setMyShortDescription", json={"short_description": "Telegram AI Bot (Udom) - Please wait a minute and ask again if Bot does not reply."}, timeout=10)
            logger.info("[Startup] Bot commands & descriptions updated.")
        except Exception as e:
            logger.error(f"[Startup] Error setting commands: {e}")

        # 2. Recover missed messages from while bot was offline
        try:
            from plugins.recovery import recover_missed_messages
            logger.info("[Recovery] Checking for missed messages...")
            await recover_missed_messages(token)
        except Exception as e:
            logger.error(f"[Recovery] Error during recovery: {e}")

        # 3. Start self-learning brain background loop
        try:
            from plugins.brain import auto_training_loop
            app.loop.create_task(auto_training_loop())
            logger.info("[Brain] Auto-training loop active.")
        except Exception as e:
            logger.error(f"[Brain] Error starting brain loop: {e}")

    # Launch background tasks asynchronously so idle() starts immediately
    app.loop.create_task(post_startup_tasks())

    logger.info("⚡ Bot is online and listening for messages!")
    import pyrogram
    pyrogram.idle()
    app.stop()

if __name__ == "__main__":
    main()

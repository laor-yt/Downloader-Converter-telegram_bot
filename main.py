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
    
    app.run()

if __name__ == "__main__":
    main()

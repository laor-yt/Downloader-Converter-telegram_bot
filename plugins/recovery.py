"""
plugins/recovery.py  —  Missed Message Recovery System
=======================================================
When Render (or any server) goes offline, Telegram queues all user messages.
This module fires on every bot startup, fetches ALL unprocessed messages via
the Bot API, and replies to each one — so no user message is ever silently ignored.

How it works:
1. Reads `last_update_offset.txt` to know the last update the bot processed.
2. Fetches all updates after that offset from Telegram's getUpdates API.
3. For each missed text message (< 48 hours old), generates an AI reply and sends it.
4. Skips /start, /help (they show menus, not useful when replying late).
5. Saves the new offset so the next startup only fetches truly new messages.
6. After recovery, switches to Pyrogram's normal event-driven mode.
"""

import os
import time
import asyncio
import logging
import requests as _requests
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

OFFSET_FILE = os.path.join(os.path.dirname(__file__), "..", "last_update_offset.txt")
MAX_AGE_HOURS = 48          # ignore messages older than 48 hours
REPLY_DELAY_SEC = 0.6       # delay between replies to avoid flooding
COMMANDS_TO_SKIP = {"/start", "/help", "/train", "/brainstats", "/timezone"}


def _load_offset() -> tuple[int, int]:
    """Return (last_update_id, last_msg_ts) from the offset file."""
    last_update_id = 0
    last_msg_ts = 0
    try:
        if os.path.exists(OFFSET_FILE):
            for line in open(OFFSET_FILE).readlines():
                line = line.strip()
                if line.startswith("msg_ts:"):
                    try:
                        ts = int(line.split(":", 1)[1])
                        if ts > last_msg_ts:
                            last_msg_ts = ts
                    except ValueError:
                        pass
                else:
                    try:
                        val = int(line)
                        if val > last_update_id:
                            last_update_id = val
                    except ValueError:
                        pass
    except Exception:
        pass
    return last_update_id, last_msg_ts


def _save_offset(update_id: int):
    """Save the latest processed update_id (overwrite entire file cleanly)."""
    try:
        with open(OFFSET_FILE, "w") as f:
            f.write(str(update_id) + "\n")
    except Exception as e:
        logger.warning(f"[Recovery] Could not save offset: {e}")


def _fetch_updates(token: str, offset: int) -> list:
    """Fetch pending Telegram updates starting from `offset`."""
    try:
        url = f"https://api.telegram.org/bot{token}/getUpdates"
        resp = _requests.get(url, params={
            "offset": offset + 1,
            "limit": 100,
            "timeout": 5,
            "allowed_updates": ["message", "callback_query"]
        }, timeout=15)
        data = resp.json()
        if data.get("ok"):
            return data.get("result", [])
    except Exception as e:
        logger.warning(f"[Recovery] getUpdates error: {e}")
    return []


def _send_reply(token: str, chat_id: int, text: str, reply_to_id: int | None = None):
    """Send a message via Bot API (no Pyrogram dependency needed at startup)."""
    try:
        payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
        if reply_to_id:
            payload["reply_to_message_id"] = reply_to_id
        _requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json=payload, timeout=15
        )
    except Exception as e:
        logger.warning(f"[Recovery] sendMessage error: {e}")


async def recover_missed_messages(token: str):
    """
    Main entry point. Call this once during bot startup (before pyrogram.idle).
    Fetches and replies to all unprocessed messages, then saves the new offset.
    """
    last_offset, last_seen_ts = _load_offset()
    updates = _fetch_updates(token, last_offset)

    if not updates:
        logger.info("[Recovery] No missed messages to process.")
        # Peek at the latest update_id and save it so next restart skips these
        try:
            url = f"https://api.telegram.org/bot{token}/getUpdates"
            resp = _requests.get(url, params={"offset": -1, "limit": 1, "timeout": 0}, timeout=10).json()
            results = resp.get("result", [])
            if results:
                _save_offset(results[-1]["update_id"])
        except Exception:
            pass
        return

    now_ts = time.time()
    new_offset = last_offset
    recovered = 0
    skipped = 0

    logger.info(f"[Recovery] Found {len(updates)} missed update(s) to process.")

    from plugins.ai_handler import get_ai_response

    for update in updates:
        update_id = update.get("update_id", 0)
        if update_id > new_offset:
            new_offset = update_id

        msg = update.get("message")
        if not msg:
            skipped += 1
            continue

        msg_ts = msg.get("date", 0)

        # Skip messages the bot already processed before going offline
        if last_seen_ts > 0 and msg_ts <= last_seen_ts:
            logger.info(f"[Recovery] Skipping already-seen message (ts={msg_ts})")
            skipped += 1
            continue

        chat_id = msg.get("chat", {}).get("id")
        text = msg.get("text", "").strip()
        msg_id = msg.get("message_id")

        # Skip if message is too old (> 48 hours)
        age_hours = (now_ts - msg_ts) / 3600
        if age_hours > MAX_AGE_HOURS:
            logger.info(f"[Recovery] Skipping old message ({age_hours:.1f}h old): {text[:40]}")
            skipped += 1
            continue

        # Skip empty text or non-text (photos handled by Pyrogram normally)
        if not text or not chat_id:
            skipped += 1
            continue

        # Skip ignored commands
        cmd_word = text.split()[0].lower().split("@")[0]
        if cmd_word in COMMANDS_TO_SKIP:
            skipped += 1
            continue

        # Skip download/convert commands — files are gone, can't process
        if cmd_word in {"/download", "/convert", "/image", "/ask", "/search"}:
            # For /ask, /search, /image we CAN still answer
            if cmd_word == "/ask":
                text = " ".join(text.split()[1:]).strip() or "Hello"
            elif cmd_word == "/search":
                text = " ".join(text.split()[1:]).strip()
                if text:
                    text = f"Search the web for: {text}"
                else:
                    skipped += 1
                    continue
            elif cmd_word == "/image":
                raw = " ".join(text.split()[1:]).strip()
                if raw:
                    from plugins.ai_handler import clean_and_generate_image_url
                    img_url = clean_and_generate_image_url(raw)
                    delay_notice = (
                        f"⚠️ _I was offline and just came back online._\n"
                        f"_Here's your image (delayed by ~{age_hours:.0f}h):_"
                    )
                    _send_reply(token, chat_id, delay_notice, reply_to_id=msg_id)
                    try:
                        _requests.post(
                            f"https://api.telegram.org/bot{token}/sendPhoto",
                            json={"chat_id": chat_id, "photo": img_url,
                                  "caption": f"🎨 `{raw}`", "parse_mode": "Markdown"},
                            timeout=30
                        )
                    except Exception as img_e:
                        logger.warning(f"[Recovery] Photo send error: {img_e}")
                    recovered += 1
                    await asyncio.sleep(REPLY_DELAY_SEC)
                else:
                    skipped += 1
                continue
            elif cmd_word in {"/download", "/convert"}:
                _send_reply(
                    token, chat_id,
                    f"⚠️ _I was offline when you sent this. I'm back now!_\n"
                    f"_Unfortunately I cannot process your `{cmd_word}` request retroactively "
                    f"(the file/link may have changed). Please send it again and I'll handle it right away!_ 🚀",
                    reply_to_id=msg_id
                )
                recovered += 1
                await asyncio.sleep(REPLY_DELAY_SEC)
                continue

        # For regular text messages and /ask — generate AI reply
        try:
            delay_str = f"{age_hours:.0f} hour{'s' if age_hours >= 2 else ''}"
            logger.info(f"[Recovery] Replying to chat {chat_id}: '{text[:50]}' (delayed {delay_str})")

            # Get AI answer
            ai_reply = await get_ai_response(chat_id, text)

            delay_notice = (
                f"⚠️ _I was offline and just came back online. "
                f"Here's my delayed reply (~{delay_str} late):_\n\n"
            )
            full_reply = delay_notice + ai_reply

            # Telegram message limit is 4096 chars
            if len(full_reply) > 4000:
                full_reply = full_reply[:4000] + "..."

            _send_reply(token, chat_id, full_reply, reply_to_id=msg_id)
            recovered += 1

        except Exception as reply_e:
            logger.warning(f"[Recovery] Failed to reply to message: {reply_e}")
            _send_reply(
                token, chat_id,
                "⚠️ _I was offline. I'm back now! Please resend your message and I'll reply right away._",
                reply_to_id=msg_id
            )

        await asyncio.sleep(REPLY_DELAY_SEC)

    # Save offset so next startup won't reprocess these
    _save_offset(new_offset)
    logger.info(
        f"[Recovery] Done. Recovered: {recovered}, Skipped: {skipped}, "
        f"New offset: {new_offset}"
    )

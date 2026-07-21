import os
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message
from g4f.client import AsyncClient

# Store recent conversation history per chat for context
chat_history = {}

async def get_ai_response(chat_id, user_prompt, image_url=None):
    client = AsyncClient()
    
    # Initialize history for chat if not exists
    if chat_id not in chat_history:
        chat_history[chat_id] = [{"role": "system", "content": "You are a helpful, friendly AI assistant integrated into a Telegram bot."}]
    
    # Add user message to history
    if image_url:
        message_content = f"{user_prompt}\n\nImage URL: {image_url}"
        chat_history[chat_id].append({"role": "user", "content": message_content})
    else:
        chat_history[chat_id].append({"role": "user", "content": user_prompt})
    
    # Keep only the last 10 messages to avoid huge context limits
    if len(chat_history[chat_id]) > 11:
        chat_history[chat_id] = [chat_history[chat_id][0]] + chat_history[chat_id][-10:]
        
    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=chat_history[chat_id]
        )
        reply = response.choices[0].message.content
        
        # Add AI reply to history
        chat_history[chat_id].append({"role": "assistant", "content": reply})
        return reply
    except Exception as e:
        print(f"AI Error: {e}")
        # Remove the failed user prompt from history
        chat_history[chat_id].pop()
        return "Sorry, I am having trouble thinking right now. Please try again later!"

@Client.on_message(filters.command("ask"), group=1)
async def ask_command(client: Client, message: Message):
    if len(message.command) < 2:
        await message.reply_text("Please ask a question! Example: `/ask What is the capital of France?`")
        return
        
    prompt = message.text.split(None, 1)[1]
    
    processing_msg = await message.reply_text("🤔 Thinking...")
    reply = await get_ai_response(message.chat.id, prompt)
    await processing_msg.edit_text(reply)

# Handle mentions and replies to the bot in groups
@Client.on_message(filters.text & filters.group & ~filters.command(["start", "help", "ask"]), group=1)
async def group_ai_chat(client: Client, message: Message):
    bot = await client.get_me()
    
    is_reply_to_bot = False
    if message.reply_to_message and message.reply_to_message.from_user:
        is_reply_to_bot = message.reply_to_message.from_user.id == bot.id
        
    is_mentioned = False
    if message.text and f"@{bot.username}" in message.text:
        is_mentioned = True
        
    if is_reply_to_bot or is_mentioned:
        # Clean the prompt from the bot's username
        prompt = message.text.replace(f"@{bot.username}", "").strip()
        if not prompt:
            prompt = "Hello!"
            
        processing_msg = await message.reply_text("🤔 Thinking...", reply_to_message_id=message.id)
        reply = await get_ai_response(message.chat.id, prompt)
        await processing_msg.edit_text(reply)

# Handle AI chat in private messages (if it's not a URL or command)
@Client.on_message(filters.text & filters.private & ~filters.command(["start", "help", "ask"]), group=1)
async def private_ai_chat(client: Client, message: Message):
    text = message.text
    # Let handlers.py handle URLs
    if "http://" in text or "https://" in text:
        return
        
    # Ignore predefined menu buttons
    if text in ["📥 Download Media", "🔄 Convert Media", "ℹ️ Help"]:
        return
        
    prompt = text
    processing_msg = await message.reply_text("🤔 Thinking...", reply_to_message_id=message.id)
    reply = await get_ai_response(message.chat.id, prompt)
    await processing_msg.edit_text(reply)

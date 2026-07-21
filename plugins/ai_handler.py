import os
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message
from g4f.client import AsyncClient
from ddgs import DDGS

# Store recent conversation history per chat for context
chat_history = {}

SYSTEM_PROMPT = """You are a highly capable AI assistant.
You are fully fluent in English and Khmer. 
- If the user asks in English, you MUST answer in English.
- If the user asks in Khmer, you MUST answer in Khmer.
- If the user asks you to translate something to Khmer, you MUST answer in Khmer.

CRITICAL INSTRUCTION FOR IMAGES:
You have a special built-in image generator. If the user asks you to generate, draw, or create an image/picture, DO NOT apologize and DO NOT say you reached a limit. You MUST reply with this exact URL format and NOTHING else:
https://image.pollinations.ai/prompt/{description_with_underscores},_photorealistic?width=1024&height=1024&nologo=true
Replace {description_with_underscores} with the requested image description (in English).

CRITICAL INSTRUCTION FOR VIDEOS:
If the user asks for a video, you must reply: "Sorry, I cannot generate videos because AI video generation requires expensive paid APIs. However, I can generate images for you! Just ask me to draw an image."
"""

async def get_ai_response(chat_id, user_prompt, image_url=None, context=""):
    # Initialize history for chat if not exists
    if chat_id not in chat_history:
        chat_history[chat_id] = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    # Add user message to history
    final_prompt = user_prompt
    if context:
        final_prompt = f"Context information:\n{context}\n\nUser Prompt:\n{user_prompt}"
        
    if image_url:
        message_content = f"{final_prompt}\n\nImage URL: {image_url}"
        chat_history[chat_id].append({"role": "user", "content": message_content})
    else:
        chat_history[chat_id].append({"role": "user", "content": final_prompt})
    
    # Keep only the last 10 messages to avoid huge context limits
    if len(chat_history[chat_id]) > 11:
        chat_history[chat_id] = [chat_history[chat_id][0]] + chat_history[chat_id][-10:]
        
    try:
        import requests
        def fetch_pollinations():
            headers = {'Content-Type': 'application/json'}
            data = {'messages': chat_history[chat_id], 'model': 'openai'}
            response = requests.post('https://text.pollinations.ai/', headers=headers, json=data, timeout=30)
            response.raise_for_status()
            return response.text
            
        reply = await asyncio.to_thread(fetch_pollinations)
        
        # Add AI reply to history
        chat_history[chat_id].append({"role": "assistant", "content": reply})
        return reply
    except Exception as e:
        print(f"Pollinations Error: {e}")
        # Fallback to g4f
        try:
            client = AsyncClient()
            response = await client.chat.completions.create(
                model="gpt-4o",
                messages=chat_history[chat_id]
            )
            reply = response.choices[0].message.content
            chat_history[chat_id].append({"role": "assistant", "content": reply})
            return reply
        except Exception as e2:
            print(f"AI Error with gpt-4o: {e2}")
            try:
                response = await client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=chat_history[chat_id]
                )
                reply = response.choices[0].message.content
                chat_history[chat_id].append({"role": "assistant", "content": reply})
                return reply
            except Exception as e3:
                print(f"AI Error with gpt-3.5-turbo: {e3}")
                chat_history[chat_id].pop()
                return f"Sorry, I am having trouble thinking right now. Error: {str(e3)}"

@Client.on_message(filters.command("ask"), group=1)
async def ask_command(client: Client, message: Message):
    if len(message.command) < 2:
        await message.reply_text("Please ask a question! Example: `/ask What is the capital of France?`")
        return
        
    prompt = message.text.split(None, 1)[1]
    
    processing_msg = await message.reply_text("🤔 Thinking...")
    reply = await get_ai_response(message.chat.id, prompt)
    
    if "image.pollinations.ai" in reply:
        await message.reply_photo(reply.strip())
        await processing_msg.delete()
    else:
        await processing_msg.edit_text(reply)

@Client.on_message(filters.command("image"), group=1)
async def image_command(client: Client, message: Message):
    if len(message.command) < 2:
        await message.reply_text("Please provide a description! Example: `/image a cute cat playing piano`")
        return
        
    prompt = message.text.split(None, 1)[1]
    prompt_formatted = prompt.replace(" ", "_")
    image_url = f"https://image.pollinations.ai/prompt/{prompt_formatted},_photorealistic,_highly_detailed,_4k_resolution,_cinematic_lighting?width=1024&height=1024&nologo=true"
    
    processing_msg = await message.reply_text("🎨 Drawing image...")
    try:
        await message.reply_photo(image_url, caption=prompt)
        await processing_msg.delete()
    except:
        await processing_msg.edit_text("Sorry, failed to generate or fetch the image.")

@Client.on_message(filters.command("search"), group=1)
async def search_command(client: Client, message: Message):
    if len(message.command) < 2:
        await message.reply_text("Please provide a search query! Example: `/search weather in Tokyo today`")
        return
        
    query = message.text.split(None, 1)[1]
    processing_msg = await message.reply_text(f"🔍 Searching the web for: `{query}`...")
    
    try:
        # Search web using DDGS
        results = DDGS().text(query, max_results=3)
        context = ""
        for r in results:
            context += f"- {r.get('title')}: {r.get('body')}\n"
            
        if not context:
            context = "No relevant search results found."
            
        reply = await get_ai_response(message.chat.id, query, context=context)
        await processing_msg.edit_text(reply)
    except Exception as e:
        print(f"Search Error: {e}")
        await processing_msg.edit_text("Sorry, an error occurred while searching the web.")

# Handle mentions and replies to the bot in groups
@Client.on_message(filters.text & filters.group & ~filters.command(["start", "help", "ask", "search", "image", "download", "convert", "finance", "market"]), group=1)
async def group_ai_chat(client: Client, message: Message):
    bot = await client.get_me()
    
    is_reply_to_bot = (
        message.reply_to_message and 
        message.reply_to_message.from_user and 
        message.reply_to_message.from_user.id == bot.id
    )
    
    is_mention = (
        message.text and 
        f"@{bot.username}" in message.text
    )
    
    if is_reply_to_bot or is_mention:
        prompt = message.text.replace(f"@{bot.username}", "").strip()
        if not prompt:
            return
            
        processing_msg = await message.reply_text("🤔 Thinking...", reply_to_message_id=message.id)
        reply = await get_ai_response(message.chat.id, prompt)
        
        if "image.pollinations.ai" in reply:
            await message.reply_photo(reply.strip())
            await processing_msg.delete()
        else:
            await processing_msg.edit_text(reply)

# Handle AI chat in private messages (if it's not a URL or command)
@Client.on_message(filters.text & filters.private & ~filters.command(["start", "help", "ask", "search", "image", "download", "convert", "finance", "market"]), group=1)
async def private_ai_chat(client: Client, message: Message):
    text = message.text
    # Ignore predefined menu buttons
    if text in ["📥 Download Media", "🔄 Convert Media", "ℹ️ Help"]:
        return
        
    prompt = text
    processing_msg = await message.reply_text("🤔 Thinking...", reply_to_message_id=message.id)
    reply = await get_ai_response(message.chat.id, prompt)
    
    if "image.pollinations.ai" in reply:
        await message.reply_photo(reply.strip())
        await processing_msg.delete()
    else:
        await processing_msg.edit_text(reply)

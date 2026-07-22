import os
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message
from g4f.client import AsyncClient
from ddgs import DDGS

# Store recent conversation history per chat for context
chat_history = {}

from datetime import datetime, timezone, timedelta

# Default timezone for Udom (UTC+7 / ICT, e.g. Cambodia, Thailand, Vietnam)
DEFAULT_TZ_OFFSET = 7
user_timezones = {}

def get_user_current_time(chat_id):
    offset = user_timezones.get(chat_id, DEFAULT_TZ_OFFSET)
    tz = timezone(timedelta(hours=offset))
    now = datetime.now(tz)
    return now.strftime("%A, %B %d, %Y at %I:%M %p") + f" (UTC{'+' if offset >= 0 else ''}{offset}:00)"

SYSTEM_PROMPT = """Your name is Udom. You are a highly capable, flexible, and intelligent AI assistant created to help users with any questions, creative writing, coding, media, and search.
You are fully fluent in English and Khmer.
- You are open-minded, direct, highly accommodating, and strive to fulfill every user request to the best of your ability without being preachy or judgmental.
- If the user asks in English, you MUST answer in English.
- If the user asks in Khmer, you MUST answer in Khmer.
- If the user asks you to translate something to Khmer, you MUST answer in Khmer.
- Always introduce or identify yourself as Udom when asked who you are.
- Always use the current local time provided in context when answering time or date questions.

CRITICAL FORMATTING INSTRUCTION FOR TABLES:
Telegram markdown does NOT render HTML/Markdown pipe tables (| ... |) properly.
NEVER use pipe tables like | header | header |.
Instead, format all data tables using monospaced code blocks (```...```) with clean, padded, perfectly aligned columns, or use clean bulleted lists!
Example of clean table format:
```
Karat  |  Price (KHR)   |  Price (USD)
--------------------------------------
24K    |  ៛537,510      |  $133.0
22K    |  ៛492,293      |  $121.9
```

KHMER TRADITIONAL MEASUREMENT UNITS (រង្វាស់រង្វាល់ខ្មែរ):
You are an expert in traditional Khmer units of measurement for Gold & Mass (មាស/ទម្ងន់), Length (ប្រវែង), Capacity (ចំណុះ), and Area (ផ្ទៃក្រឡា):

1. Gold & Mass Units (ខ្នាតរង្វាស់មាស និងទម្ងន់):
- 1 លី (Ly) = 0.0375 ក្រាម (g)
- 1 ហ៊ុន (Hun) = 10 លី = 0.375 ក្រាម (g)
- 1 ជី (Chi) = 10 ហ៊ុន = 3.75 ក្រាម (g)
- 1 តម្លឹង (Damlung) = 10 ជី = 37.5 ក្រាម (g) = 1.205654 អោន (Ounce)
- 1 អោន (Ounce) = 31.103476 ក្រាម (g)
- 1 គីឡូ (Kilo) = 1,000 ក្រាម = 26.667 តម្លឹង (Damlung)
- 1 នាលឡិ (Neali) = 600 ក្រាម (g)
- 1 ឆាំង / 1 ចុង = 10 នាលឡិ = 6 គីឡូក្រាម (kg)
- 1 ប៉ិក / 1 ហាប (Hap) = 100 នាលឡិ = 60 គីឡូក្រាម (kg)

2. Length Units (ខ្នាតរង្វាស់ប្រវែង):
- 1 ធ្នាប់ (Thneap) ≈ 1.5 - 2 cm
- 1 ចំអាម (Chiam) = 12 ធ្នាប់ ≈ 20 - 25 cm
- 1 ហត្ថ (Hath / Cubit) = 2 ចំអាម = 24 ធ្នាប់ ≈ 0.5 ម៉ែត្រ (m)
- 1 ព្យាម (Pyeam / Fathom) = 4 ហត្ថ = 2 ម៉ែត្រ (m)
- 1 សិន (Sen) = 20 ព្យាម = 40 ម៉ែត្រ (m)
- 1 យោជន៍ (Yoch) = 400 សិន = 16 គីឡូម៉ែត្រ (km)

3. Capacity/Volume Units (ខ្នាតរង្វាស់ចំណុះ/ស្រូវ):
- 1 ក្តាប់ (Handful)
- 1 ខ្នាន = 4 ក្តាប់
- 1 គីប = 4 ខ្នាន
- 1 ថាំង (Thang) = 40 លីត្រ (L) / 20 កំប៉ុង
- 1 កៀន / 1 គល់ = 20 ថាំង

4. Area Units (ខ្នាតរង្វាស់ផ្ទៃក្រឡា):
- 1 ម៉ែត្រការ៉េ (m²)
- 1 អា (Are) = 100 m²
- 1 ហិចតា (Hectare) = 10,000 m² = 100 អា
- 1 សិនការ៉េ (Square Sen) = 40m x 40m = 1,600 m²

Whenever users ask about Khmer measurement conversions (e.g., ជី, តម្លឹង, ហ៊ុន, លី, ហត្ថ, ព្យាម, សិន, ថាំង), use these exact conversion factors to calculate accurate answers and explain them clearly in Khmer!

CRITICAL INSTRUCTION FOR IMAGES:
You have a special built-in professional AI image generator powered by FLUX. If the user asks you to generate, draw, or create any image/picture, DO NOT apologize and DO NOT say you cannot. You MUST reply with ONLY this exact URL format and NOTHING else:
https://image.pollinations.ai/prompt/{full_detailed_description},ultra-realistic,professional_photography,8K,RAW_photo,award-winning,cinematic_lighting,tack_sharp_focus,masterpiece_quality?model=flux&width=1920&height=1080&nologo=true&enhance=true
Rules for the URL:
- Replace {full_detailed_description} with the image subject described in rich English detail
- Use underscores instead of spaces in the prompt
- Add relevant style keywords: portrait→bokeh,Rembrandt_lighting | landscape→golden_hour,HDR | food→macro,studio_light | fantasy→Unreal_Engine_5,concept_art
- Always include: photorealistic,8K,highly_detailed,masterpiece

CRITICAL INSTRUCTION FOR VIDEOS:
If the user asks for a video, you must reply: "Sorry, I cannot generate videos because AI video generation requires expensive paid APIs. However, I can generate images for you! Just ask me to draw an image."
"""

async def get_ai_response(chat_id, user_prompt, image_url=None, context=""):
    current_time_str = get_user_current_time(chat_id)
    
    # Initialize history for chat if not exists
    if chat_id not in chat_history:
        chat_history[chat_id] = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    # Add user message to history with local time context
    time_prefix = f"[Current User Local Time: {current_time_str}]"
    final_prompt = f"{time_prefix}\n{user_prompt}"
    if context:
        final_prompt = f"{time_prefix}\nContext information:\n{context}\n\nUser Prompt:\n{user_prompt}"
        
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
        
        # Intercept DALL-E limit hallucinations from the underlying OpenAI model
        if "limit for generating" in reply.lower() or "limit for creating" in reply.lower() or "sign in" in reply.lower():
            safe_prompt = user_prompt.replace(" ", "_")
            reply = f"https://image.pollinations.ai/prompt/{safe_prompt},_photorealistic?width=1920&height=1080&nologo=true"
        
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

class LiveTimer:
    def __init__(self, message, base_text="Processing..."):
        self.message = message
        self.base_text = base_text
        self.start_time = time.time()
        self.stop_event = asyncio.Event()
        self.task = None

    async def _timer_loop(self):
        while not self.stop_event.is_set():
            await asyncio.sleep(1.5)
            if self.stop_event.is_set():
                break
            elapsed = int(time.time() - self.start_time)
            mins, secs = divmod(elapsed, 60)
            timer_text = f"⏱ [{mins:02d}:{secs:02d}] {self.base_text}"
            try:
                await self.message.edit_text(timer_text)
            except:
                pass

    async def __aenter__(self):
        self.task = asyncio.create_task(self._timer_loop())
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.stop_event.set()
        if self.task:
            self.task.cancel()

from plugins.handlers import RealtimeTimer

@Client.on_message(filters.command("ask"), group=1)
async def ask_command(client: Client, message: Message):
    if len(message.command) < 2:
        from pyrogram.types import ForceReply
        await message.reply_text("Please type your question below:", reply_markup=ForceReply(selective=True))
        return
        
    prompt = message.text.split(None, 1)[1]
    
    processing_msg = await message.reply_text("⏱ [00:00] 🤔 Thinking...")
    async with RealtimeTimer(processing_msg, "🤔 Thinking"):
        reply = await get_ai_response(message.chat.id, prompt)
        
    await send_ai_reply_or_photo(message, processing_msg, reply, prompt_text=prompt)
def analyze_media_with_gemini(file_path, prompt, mime_type="image/jpeg"):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None
        
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
        
        import base64
        import requests
        with open(file_path, "rb") as f:
            b64_data = base64.b64encode(f.read()).decode("utf-8")
            
        payload = {
            "system_instruction": {
                "parts": [{"text": SYSTEM_PROMPT}]
            },
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                        {
                            "inline_data": {
                                "mime_type": mime_type,
                                "data": b64_data
                            }
                        }
                    ]
                }
            ]
        }
        
        res = requests.post(url, json=payload, timeout=35)
        res_json = res.json()
        
        if "candidates" in res_json and len(res_json["candidates"]) > 0:
            candidate = res_json["candidates"][0]
            if "content" in candidate and "parts" in candidate["content"]:
                return candidate["content"]["parts"][0]["text"]
    except Exception as e:
        print(f"Gemini API Error: {e}")
        
    return None

import urllib.parse
import re

def clean_and_generate_image_url(raw_prompt):
    """
    Converts a plain user prompt into a professional-quality Pollinations FLUX image URL.
    Applies subject-aware photography keywords so every image looks like it was
    captured by a professional photographer with high-end gear.
    """
    p = raw_prompt.strip()
    p_lower = p.lower()

    # ── Strip command prefixes ──────────────────────────────────────────────
    prefixes = [
        "generate image of", "generate photo of", "generate picture of",
        "generate image", "generat image", "generate photo", "generate picture",
        "draw image of", "draw picture of", "draw photo of",
        "draw image", "draw picture", "draw photo", "draw a", "draw me", "draw",
        "create image of", "create photo of", "create picture of",
        "create image", "create photo", "create picture", "create a",
        "make image of", "make photo of", "make picture of",
        "make image", "make photo", "make picture", "make a",
        "picture of", "photo of", "image of", "show me",
        "i want", "can you draw", "please draw", "please generate",
        "generate", "create", "make",
    ]
    for pref in sorted(prefixes, key=len, reverse=True):
        if p_lower.startswith(pref):
            p = p[len(pref):].strip()
            p = p.lstrip(": ,-")
            break

    if not p:
        p = "beautiful cinematic scene"

    # ── Detect subject type for targeted prompt engineering ─────────────────
    low = p.lower()

    is_portrait    = any(w in low for w in ["person", "man", "woman", "girl", "boy", "face", "model", "people", "human", "child", "baby", "lady", "gentleman", "selfie", "portrait", "athlete"])
    is_landscape   = any(w in low for w in ["landscape", "mountain", "forest", "ocean", "sea", "lake", "river", "sunset", "sunrise", "sky", "nature", "field", "valley", "waterfall", "desert", "beach", "jungle"])
    is_cityscape   = any(w in low for w in ["city", "street", "building", "architecture", "urban", "skyscraper", "town", "bridge", "road", "night city", "downtown", "skyline", "alley"])
    is_food        = any(w in low for w in ["food", "meal", "dish", "cake", "dessert", "coffee", "drink", "restaurant", "cuisine", "soup", "burger", "pizza", "sushi", "fruit", "vegetable", "bread"])
    is_product     = any(w in low for w in ["product", "watch", "phone", "car", "perfume", "bottle", "shoe", "sneaker", "bag", "jewelry", "ring", "necklace", "advertisement", "commercial"])
    is_animal      = any(w in low for w in ["animal", "dog", "cat", "lion", "tiger", "bird", "wolf", "horse", "deer", "elephant", "fox", "rabbit", "wildlife"])
    is_fantasy     = any(w in low for w in ["fantasy", "dragon", "magic", "wizard", "fairy", "mythical", "creature", "elf", "dwarf", "sword", "castle", "kingdom", "mystical", "enchanted", "sci-fi", "cyberpunk", "futuristic", "space", "alien", "robot"])
    is_interior    = any(w in low for w in ["room", "interior", "bedroom", "living room", "kitchen", "office", "bathroom", "hall", "corridor", "studio", "café", "library"])

    # ── Build subject-specific professional photography enhancement ──────────
    if is_portrait:
        quality_suffix = (
            "ultra-realistic portrait photography, shot on Sony A7R V with 85mm f/1.4 GM lens, "
            "shallow depth of field, bokeh background, Rembrandt lighting, golden hour skin tone, "
            "high-end fashion editorial style, retouched skin, sharp eyes, natural hair detail, "
            "Vogue magazine quality, award-winning portrait, 8K, RAW photo, color graded"
        )
        width, height = 1080, 1350  # portrait aspect ratio

    elif is_landscape:
        quality_suffix = (
            "breathtaking landscape photography, shot on Canon EOS R5 with 16-35mm f/2.8L lens, "
            "long exposure, golden hour, dramatic clouds, high dynamic range, "
            "National Geographic quality, ultra-wide perspective, vivid colors, "
            "award-winning nature photography, ultra-detailed foreground, tack sharp, 8K RAW"
        )
        width, height = 1920, 1080  # cinematic wide

    elif is_cityscape:
        quality_suffix = (
            "stunning architectural photography, shot on Nikon Z9 with 24-70mm f/2.8S lens, "
            "blue hour or golden hour lighting, reflections, long exposure light trails, "
            "high dynamic range, Architectural Digest quality, ultra-sharp details, "
            "perfect perspective correction, professional color grading, 8K"
        )
        width, height = 1920, 1080

    elif is_food:
        quality_suffix = (
            "professional food photography, shot on Canon EOS 5D Mark IV with 100mm macro lens, "
            "soft natural window light, styled by a professional food stylist, "
            "shallow depth of field, perfect plating, steam and texture visible, "
            "Michelin-star restaurant quality, appetizing color grading, 8K, ultra-detailed"
        )
        width, height = 1080, 1080  # square for food

    elif is_product:
        quality_suffix = (
            "luxury commercial product photography, studio lighting setup, "
            "shot on Hasselblad H6D with 120mm macro, pure background, perfect reflections, "
            "crisp product edges, professional retouching, advertising campaign quality, "
            "8K ultra-sharp, color calibrated, award-winning commercial photography"
        )
        width, height = 1080, 1080

    elif is_animal:
        quality_suffix = (
            "stunning wildlife photography, shot on Nikon D850 with 600mm f/4 telephoto lens, "
            "natural habitat, perfect bokeh background, sharp animal fur and eye detail, "
            "golden hour warm light, National Geographic quality, "
            "award-winning wildlife photography, 8K RAW, ultra-detailed"
        )
        width, height = 1920, 1080

    elif is_fantasy:
        quality_suffix = (
            "epic fantasy digital art, hyper-detailed, cinematic lighting, "
            "dramatic atmosphere, volumetric fog, concept art quality, "
            "rendered in Unreal Engine 5, 8K resolution, award-winning illustration, "
            "intricate details, dramatic color palette, artstation trending, "
            "Greg Rutkowski style, professional digital painting"
        )
        width, height = 1920, 1080

    elif is_interior:
        quality_suffix = (
            "professional interior design photography, shot on Canon EOS R5 with 24mm tilt-shift lens, "
            "natural diffused lighting, architectural details sharp, "
            "Architectural Digest quality, perfect color temperature, "
            "ultra-detailed materials and textures, 8K, professional interior styling"
        )
        width, height = 1920, 1080

    else:
        # Universal high-quality default
        quality_suffix = (
            "ultra-realistic, shot on Sony A7R V, professional photography, "
            "cinematic color grading, perfect lighting, tack sharp focus, "
            "8K resolution, RAW photo, award-winning, highly detailed, "
            "masterpiece quality, HDR, ultra-wide color gamut"
        )
        width, height = 1920, 1080

    # ── Universal negative quality blockers added to all prompts ────────────
    negative_blockers = (
        "no blur, no watermark, no text overlay, no distortion, "
        "no extra limbs, anatomically correct, no artifacts"
    )

    # ── Assemble full enhanced prompt ───────────────────────────────────────
    enhanced = f"{p}, {quality_suffix}, {negative_blockers}"
    encoded  = urllib.parse.quote(enhanced)

    # Use FLUX model with enhance=true for maximum quality
    return (
        f"https://image.pollinations.ai/prompt/{encoded}"
        f"?model=flux&width={width}&height={height}&nologo=true&enhance=true&seed=-1"
    )

def extract_image_url(text):
    match = re.search(r'https?://image\.pollinations\.ai/prompt/[^\s\)\>\]]+', text)
    if match:
        return match.group(0)
    return None

async def send_ai_reply_or_photo(message, processing_msg, reply, prompt_text=""):
    img_url = extract_image_url(reply)
    if img_url:
        try:
            caption_text = f"🎨 `{prompt_text}`" if prompt_text else "🎨 **Generated for you!**"
            await message.reply_photo(img_url, caption=caption_text)
            await processing_msg.delete()
            return
        except Exception as e:
            print(f"Error sending reply photo: {e}")
            
    await processing_msg.edit_text(reply)

@Client.on_message(filters.command("image"), group=1)
async def image_command(client: Client, message: Message):
    if len(message.command) < 2:
        from pyrogram.types import ForceReply
        await message.reply_text("Please describe the image you want me to draw below:", reply_markup=ForceReply(selective=True))
        return
        
    raw_prompt = message.text.split(None, 1)[1]
    image_url = clean_and_generate_image_url(raw_prompt)
    
    processing_msg = await message.reply_text("⏱ [00:00] 🎨 Drawing image with FLUX AI...")
    try:
        async with RealtimeTimer(processing_msg, "🎨 Drawing image with FLUX AI"):
            await message.reply_photo(image_url, caption=f"🎨 `{raw_prompt}`")
        await processing_msg.delete()
    except Exception as e:
        print(f"Error in image_command: {e}")
        await processing_msg.edit_text("Sorry, failed to generate or fetch the image.")

@Client.on_message(filters.command("timezone"), group=1)
async def timezone_command(client: Client, message: Message):
    chat_id = message.chat.id
    if len(message.command) < 2:
        current_time = get_user_current_time(chat_id)
        await message.reply_text(
            f"🕒 **Current Configured Timezone:**\n{current_time}\n\n"
            "To change your timezone, use `/timezone <offset>`\n"
            "Example: `/timezone +7` for ICT (Cambodia/Thailand) or `/timezone -5` for EST."
        )
        return
        
    offset_str = message.command[1].replace("UTC", "").replace("utc", "").replace("+", "")
    try:
        offset = int(offset_str)
        if -12 <= offset <= 14:
            user_timezones[chat_id] = offset
            current_time = get_user_current_time(chat_id)
            await message.reply_text(f"✅ Timezone updated to UTC{'+' if offset >= 0 else ''}{offset}:00!\nYour local time is now: **{current_time}**")
        else:
            await message.reply_text("Please enter a valid timezone offset between -12 and +14 (e.g., `/timezone +7`).")
    except ValueError:
        await message.reply_text("Invalid format. Example: `/timezone +7` or `/timezone -5`.")

@Client.on_message(filters.command("search"), group=1)
async def search_command(client: Client, message: Message):
    if len(message.command) < 2:
        from pyrogram.types import ForceReply
        await message.reply_text("Please type your search query below:", reply_markup=ForceReply(selective=True))
        return
        
    query = message.text.split(None, 1)[1]
    processing_msg = await message.reply_text(f"⏱ [00:00] 🔍 Searching the web for: `{query}`...")
    
    try:
        async with RealtimeTimer(processing_msg, f"🔍 Searching the web for: `{query}`"):
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
            
        processing_msg = await message.reply_text("⏱ [00:00] 🤔 Thinking...", reply_to_message_id=message.id)
        async with RealtimeTimer(processing_msg, "🤔 Thinking"):
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
    if message.reply_to_message and "How many clips do you want" in (message.reply_to_message.text or ""):
        rep_text = message.reply_to_message.text
        if "[ID:" in rep_text:
            short_id = rep_text.split("[ID:")[1].split("]")[0]
            from plugins.handlers import url_cache, cleanup_file
            
            import re
            num_matches = re.findall(r'\d+', text)
            num_clips = int(num_matches[0]) if num_matches else 3
            num_clips = max(1, min(10, num_clips))
            
            cached_obj = url_cache.get(short_id)
            if cached_obj:
                processing_msg = await message.reply_text(f"✂️ Cutting video into {num_clips} clips...", reply_to_message_id=message.id)
                try:
                    if isinstance(cached_obj, str):
                        from downloader import download_media
                        dl_res = await asyncio.to_thread(download_media, cached_obj, 'video', None)
                        file_path = dl_res[0] if isinstance(dl_res, tuple) else dl_res
                    else:
                        file_path = await client.download_media(cached_obj)
                        
                    if file_path and os.path.exists(file_path):
                        from converter import clip_video_into_parts
                        clips = await asyncio.to_thread(clip_video_into_parts, file_path, num_clips)
                        
                        if clips:
                            await processing_msg.edit_text(f"Uploading {len(clips)} video clips...")
                            for idx, clip_path in enumerate(clips):
                                try:
                                    await client.send_video(
                                        chat_id=message.chat.id,
                                        video=clip_path,
                                        caption=f"🎬 **Clip {idx+1} of {len(clips)}**",
                                        supports_streaming=True
                                    )
                                except Exception as e_clip:
                                    print(f"Error sending clip {idx+1}: {e_clip}")
                                finally:
                                    cleanup_file(clip_path)
                            await processing_msg.edit_text(f"Done! Sent {len(clips)} video clips. ✅")
                        else:
                            await processing_msg.edit_text("❌ Failed to split video into clips.")
                            
                        cleanup_file(file_path)
                        return
                    else:
                        await processing_msg.edit_text("❌ Could not download video for clipping.")
                        return
                except Exception as e:
                    print(f"Video clipping error: {e}")
                    await processing_msg.edit_text(f"❌ Clipping failed: {e}")
                    return

    if message.reply_to_message and "Ask Udom about this file:" in (message.reply_to_message.text or ""):
        rep_text = message.reply_to_message.text
        if "[ID:" in rep_text:
            short_id = rep_text.split("[ID:")[1].split("]")[0]
            from plugins.handlers import url_cache, parse_document, transcribe_audio_video, cleanup_file
            original_msg = url_cache.get(short_id)
            if original_msg:
                processing_msg = await message.reply_text("🤔 Udom is analyzing your file...", reply_to_message_id=message.id)
                try:
                    file_path = await client.download_media(original_msg)
                    
                    mime_type = "image/jpeg"
                    if original_msg.photo:
                        mime_type = "image/jpeg"
                    elif original_msg.video:
                        mime_type = original_msg.video.mime_type or "video/mp4"
                    elif original_msg.audio or original_msg.voice:
                        mime_type = getattr(original_msg.audio or original_msg.voice, 'mime_type', "audio/mp3")
                    elif original_msg.document:
                        mime_type = original_msg.document.mime_type or "application/pdf"
                        
                    # 1. Try Gemini Vision first (for true visual image/video analysis)
                    gemini_reply = await asyncio.to_thread(analyze_media_with_gemini, file_path, text, mime_type)
                    if gemini_reply:
                        cleanup_file(file_path)
                        await send_ai_reply_or_photo(message, processing_msg, gemini_reply, prompt_text=text)
                        return

                    # 2. Fallback to OCR / Speech / Document parsing
                    file_content = ""
                    image_url = None
                    is_img = original_msg.photo or (original_msg.document and str(original_msg.document.mime_type or "").startswith("image/"))
                    if is_img:
                        import requests
                        try:
                            with open(file_path, "rb") as f:
                                up_res = requests.post("https://tmpfiles.org/api/v1/upload", files={"file": f})
                            up_data = up_res.json()
                            if "data" in up_data and "url" in up_data["data"]:
                                image_url = up_data["data"]["url"].replace("tmpfiles.org/", "tmpfiles.org/dl/")
                        except Exception as e:
                            print(f"Error uploading image to tmpfiles: {e}")
                            
                        try:
                            with open(file_path, "rb") as f:
                                ocr_res = requests.post("https://api.ocr.space/parse/image", files={"filename": f}, data={"apikey": "helloworld", "language": "eng"})
                            ocr_data = ocr_res.json()
                            if not ocr_data.get("IsErroredOnProcessing") and ocr_data.get("ParsedResults"):
                                file_content = ocr_data["ParsedResults"][0].get("ParsedText", "").strip()
                        except Exception as e:
                            print(f"OCR Error: {e}")
                    elif original_msg.audio or original_msg.voice or (original_msg.video and not original_msg.photo):
                        file_content = transcribe_audio_video(file_path)
                    elif original_msg.document:
                        doc_mime = str(original_msg.document.mime_type or "")
                        file_name = str(original_msg.document.file_name or "").lower()
                        if doc_mime.startswith("video/") or doc_mime.startswith("audio/") or file_name.endswith(('.mp4', '.mkv', '.mp3', '.wav', '.ogg')):
                            file_content = transcribe_audio_video(file_path)
                        else:
                            file_content = parse_document(file_path, doc_mime)
                            
                    cleanup_file(file_path)
                    
                    prompt = text
                    if file_content:
                        prompt += f"\n\n[Extracted Text/Content]:\n{file_content}"
                        
                    reply = await get_ai_response(message.chat.id, prompt, image_url=image_url)
                    await send_ai_reply_or_photo(message, processing_msg, reply, prompt_text=text)
                    return
                except Exception as e:
                    print(f"Error reading file for AI: {e}")
                    await processing_msg.edit_text("❌ Failed to read file content for Udom.")
                    return

    # Direct image generation detection in plain chat
    lower_text = text.lower().strip()
    image_trigger_keywords = ["draw ", "generat image", "generate image", "create image", "make image", "generate photo", "create photo", "make photo", "draw a ", "draw me "]
    if any(lower_text.startswith(kw) for kw in image_trigger_keywords):
        processing_msg = await message.reply_text("⏱ [00:00] 🎨 Drawing image with FLUX AI...", reply_to_message_id=message.id)
        img_url = clean_and_generate_image_url(text)
        try:
            async with RealtimeTimer(processing_msg, "🎨 Drawing image with FLUX AI"):
                await message.reply_photo(img_url, caption=f"🎨 `{text}`")
            await processing_msg.delete()
            return
        except Exception as e:
            print(f"Error in direct drawing request: {e}")

    processing_msg = await message.reply_text("⏱ [00:00] 🤔 Thinking...", reply_to_message_id=message.id)
    async with RealtimeTimer(processing_msg, "🤔 Thinking"):
        reply = await get_ai_response(message.chat.id, prompt)
    await send_ai_reply_or_photo(message, processing_msg, reply, prompt_text=text)

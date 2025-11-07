# -*- coding: utf-8 -*-

# ---- Core Python Imports ----
import os
import io
import sys
import re
import base64
import asyncio
from threading import Thread

# --- Third-party Library Imports ---
import aiohttp  # <--- requests এর পরিবর্তে এটি ব্যবহার করা হয়েছে
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from flask import Flask
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# ---- CONFIGURATION ----
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
TMDB_API_KEY = os.getenv("TMDB_API_KEY")
IMGBB_API_KEY = os.getenv("IMGBB_API_KEY")

# --- Essential variable check ---
if not all([BOT_TOKEN, API_ID, API_HASH, TMDB_API_KEY, IMGBB_API_KEY]):
    print("❌ FATAL ERROR: One or more environment variables are missing.")
    sys.exit(1)

try:
    API_ID = int(API_ID)
except (ValueError, TypeError):
    print("❌ FATAL ERROR: API_ID must be an integer.")
    sys.exit(1)

# ---- GLOBAL VARIABLES ----
user_conversations = {}
user_channels = {}
AD_LINK_FILE = "ad_link.txt"
AD_LINK = "https://www.google.com"
AIOHTTP_SESSION = None # <--- aiohttp সেশন ম্যানেজ করার জন্য

# ---- FUNCTIONS to save and load ad link ----
def save_ad_link(link: str):
    global AD_LINK
    AD_LINK = link
    try:
        with open(AD_LINK_FILE, "w") as f: f.write(link)
    except IOError as e: print(f"⚠️ Error saving ad link: {e}")

def load_ad_link():
    global AD_LINK
    if os.path.exists(AD_LINK_FILE):
        try:
            with open(AD_LINK_FILE, "r") as f:
                link = f.read().strip()
                if link:
                    AD_LINK = link
                    print(f"✅ Ad link loaded: {AD_LINK}")
        except IOError as e: print(f"⚠️ Error loading ad link: {e}")

# ---- FLASK APP ----
app = Flask(__name__)
@app.route('/')
def home(): return "✅ Bot is up and running!"

def run_flask(): app.run(host='0.0.0.0', port=8080)

# ---- PYROGRAM BOT INITIALIZATION ----
try:
    bot = Client("moviebot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
except Exception as e:
    print(f"❌ FATAL ERROR: Could not initialize bot client: {e}")
    sys.exit(1)

# ---- FONT CONFIGURATION ----
try:
    FONT_BOLD = ImageFont.truetype("Poppins-Bold.ttf", 32)
    FONT_REGULAR = ImageFont.truetype("Poppins-Regular.ttf", 24)
    FONT_SMALL = ImageFont.truetype("Poppins-Regular.ttf", 18)
    FONT_BADGE = ImageFont.truetype("Poppins-Bold.ttf", 22)
except IOError:
    print("⚠️ Poppins fonts not found. Using default.")
    FONT_BOLD, FONT_REGULAR, FONT_SMALL, FONT_BADGE = (ImageFont.load_default(),)*4

# ==============================================================================
# ======[ কোডের এই অংশটি aiohttp ব্যবহারের জন্য আপডেট করা হয়েছে ]======
# ==============================================================================

async def get_session():
    """Initializes and returns the aiohttp ClientSession."""
    global AIOHTTP_SESSION
    if AIOHTTP_SESSION is None or AIOHTTP_SESSION.closed:
        AIOHTTP_SESSION = aiohttp.ClientSession()
    return AIOHTTP_SESSION

async def search_tmdb(query: str):
    session = await get_session()
    year = None
    match = re.search(r'(.+?)\s*\(?(\d{4})\)?$', query)
    name = match.group(1).strip() if match else query.strip()
    year = match.group(2) if match else None
    
    params = {'api_key': TMDB_API_KEY, 'query': name}
    if year: params['year'] = year
    
    try:
        async with session.get("https://api.themoviedb.org/3/search/multi", params=params, timeout=10) as response:
            response.raise_for_status()
            data = await response.json()
            return [r for r in data.get("results", []) if r.get("media_type") in ["movie", "tv"]][:15]
    except Exception as e:
        print(f"Error searching TMDB (aiohttp): {e}")
        return []

async def get_tmdb_details(media_type: str, media_id: int):
    session = await get_session()
    url = f"https://api.themoviedb.org/3/{media_type}/{media_id}"
    params = {'api_key': TMDB_API_KEY, 'append_to_response': 'credits,videos'}
    try:
        async with session.get(url, params=params, timeout=10) as response:
            response.raise_for_status()
            return await response.json()
    except Exception as e:
        print(f"Error fetching TMDB details (aiohttp): {e}")
        return None

def optimize_image(image_bytes_io: io.BytesIO, max_width=600, quality=85):
    try:
        img = Image.open(image_bytes_io)
        if img.mode not in ('RGB', 'L'): img = img.convert('RGB')
        if img.width > max_width:
            aspect_ratio = img.height / img.width
            new_height = int(max_width * aspect_ratio)
            img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)
        
        optimized_bytes = io.BytesIO()
        img.save(optimized_bytes, format='JPEG', quality=quality, optimize=True)
        optimized_bytes.seek(0)
        print(f"✅ Image optimized: {image_bytes_io.tell()/1024:.2f} KB -> {optimized_bytes.tell()/1024:.2f} KB")
        return optimized_bytes
    except Exception as e:
        print(f"⚠️ Could not optimize image: {e}")
        return image_bytes_io

async def upload_to_imgbb(image_bytes_io: io.BytesIO):
    session = await get_session()
    try:
        image_b64 = base64.b64encode(image_bytes_io.read())
        payload = {"key": IMGBB_API_KEY, "image": image_b64}
        async with session.post("https://api.imgbb.com/1/upload", data=payload, timeout=30) as response:
            response.raise_for_status()
            result = await response.json()
            if result.get("success"):
                image_url = result["data"]["url"]
                print(f"✅ Image uploaded to ImgBB: {image_url}")
                return image_url
            else:
                print(f"⚠️ ImgBB API error: {result.get('error', {}).get('message')}")
                return None
    except Exception as e:
        print(f"⚠️ Error uploading to ImgBB (aiohttp): {e}")
        return None

async def fetch_image_bytes(url: str):
    """Fetches an image from a URL and returns its bytes."""
    session = await get_session()
    try:
        async with session.get(url, timeout=15) as response:
            response.raise_for_status()
            return await response.read()
    except Exception as e:
        print(f"Failed to fetch image from URL {url}: {e}")
        return None

# ---- CONTENT GENERATION FUNCTIONS ----
def generate_formatted_caption(data: dict):
    title = data.get("title") or data.get("name") or "N/A"
    year = (data.get("release_date") or data.get("first_air_date") or "----")[:4]
    rating = f"⭐ {data.get('vote_average', 0):.1f}/10"
    genres = ", ".join([g["name"] for g in data.get("genres", [])] or ["N/A"])
    overview = data.get("overview", "No plot summary available.")
    director = next((m["name"] for m in data.get("credits", {}).get("crew", []) if m.get("job") == "Director"), "N/A")
    cast = ", ".join([a["name"] for a in data.get("credits", {}).get("cast", [])[:5]] or ["N/A"])
    language = data.get('custom_language', '').title()

    caption = f"🎬 **{title} ({year})**\n\n"
    caption += f"**Rating:** {rating}\n"
    caption += f"**Genres:** {genres}\n"
    if language: caption += f"**Language:** {language}\n"
    if director != "N/A": caption += f"**Director:** {director}\n"
    if cast != "N/A": caption += f"**Cast:** {cast}\n\n"
    caption += f"**Plot:** _{overview[:450]}{'...' if len(overview) > 450 else ''}_"
    return caption

def generate_html(data: dict, links: list):
    TOTAL_WAIT_SECONDS = 15 
    INITIAL_DOWNLOADS = 493
    TELEGRAM_LINK = "https://t.me/+60goZWp-FpkxNzVl"
    title = data.get("title") or data.get("name") or "N/A"
    year = (data.get("release_date") or data.get("first_air_date") or "----")[:4]
    language = data.get('custom_language', '').title()
    overview = data.get("overview", "No overview available.")
    
    poster_url = data.get('manual_poster_url') or (f"https://image.tmdb.org/t/p/w500{data['poster_path']}" if data.get('poster_path') else "https://via.placeholder.com/400x600.png?text=No+Poster")

    download_blocks_html = "".join([
        f"""<div class="dl-download-block">
            <button class="dl-download-button" data-url="{link['url']}" data-label="{link['label']}">⬇️ {link['label']}</button>
            <div class="dl-timer-display"></div>
            <a href="#" class="dl-real-download-link" target="_blank" rel="noopener noreferrer">✅ Get {link['label']}</a>
        </div>""" for link in links
    ]) or "<p>No download links available.</p>"

    return f"""
<!-- Bot Generated Content Starts -->
<div style="text-align: center;">
    <img src="{poster_url}" alt="{title} Poster" style="max-width: 280px; border-radius: 8px; margin-bottom: 15px;">
    <h2>{title} ({year}) - {language}</h2>
    <p style="text-align: left; padding: 0 10px;">{overview}</p>
</div>
<!--more-->
<div class="dl-body" style="font-family: 'Segoe UI', sans-serif; background-color: #f0f2f5; margin: 0; padding: 20px; display: flex; justify-content: center; align-items: center;">
    <style>.dl-main-content{{width:100%;max-width:500px;margin:auto}}.dl-post-container{{background:#fff;padding:20px;border-radius:20px;box-shadow:0 10px 30px rgba(0,0,0,.1);border:1px solid #e7eaf3}}.dl-instruction-box{{background-color:#e3f2fd;border:1px solid #90caf9;color:#1e88e5;padding:15px;border-radius:10px;margin-bottom:20px;text-align:center}}.dl-instruction-box h2{{margin:0 0 10px;font-size:18px}}.dl-instruction-box p{{margin:5px 0;font-size:14px;line-height:1.5}}.dl-download-block{{border:1px solid #ddd;border-radius:12px;padding:15px;margin-bottom:15px}}.dl-download-button,.dl-real-download-link{{display:block;width:100%;padding:15px;text-align:center;border-radius:12px;font-size:16px;font-weight:700;cursor:pointer;text-decoration:none;transition:.3s;box-sizing:border-box}}.dl-download-button{{background:#ff5722;color:#fff!important;border:none}}.dl-real-download-link{{background:#4caf50;color:#fff!important;display:none}}.dl-telegram-link{{display:block;width:100%;padding:15px;text-align:center;border-radius:12px;font-size:16px;font-weight:700;cursor:pointer;text-decoration:none;transition:.3s;box-sizing:border-box;background:#0088cc;color:#fff!important;margin-top:20px}}.dl-timer-display{{margin-top:10px;font-size:18px;font-weight:700;color:#d32f2f;background:#f0f0f0;padding:12px;border-radius:10px;text-align:center;display:none}}.dl-download-count-text{{margin-top:20px;font-size:15px;color:#555;text-align:center}}</style>
    <div class="dl-main-content">
        <div class="dl-post-container">
            <div class="dl-instruction-box">
                <h2>🎬 ডাউনলোড করার নিয়মাবলী</h2>
                <p>ডাউনলোড বাটনে ক্লিক করলে একটি বিজ্ঞাপন খুলবে।</p>
                <p>বিজ্ঞাপন খোলার পর টাইমার শেষ হওয়া পর্যন্ত অপেক্ষা করুন।</p>
                <p>টাইমার শেষ হলে আপনি ডাউনলোড লিঙ্কটি পাবেন।</p>
            </div>
            {download_blocks_html}
            <div class="dl-download-count-text">✅ মোট ডাউনলোড: <span id="download-counter">{INITIAL_DOWNLOADS}</span></div>
            <a class="dl-telegram-link" href="{TELEGRAM_LINK}" target="_blank" rel="noopener noreferrer">💋 Join Telegram Channel</a>
        </div>
    </div>
    <script>document.addEventListener("DOMContentLoaded",function(){{const e="{AD_LINK}",t={TOTAL_WAIT_SECONDS};document.querySelectorAll(".dl-download-button").forEach(n=>{{n.onclick=function(){{this.onclick=null,this.style.background="#aaa",this.style.cursor="not-allowed";const o=this.parentElement,l=o.querySelector(".dl-timer-display"),r=o.querySelector(".dl-real-download-link"),c=this.dataset.url;window.open(e,"_blank"),this.style.display="none",l.style.display="block",r.href=c;let s=t;l.innerText=`বিজ্ঞাপনটি দেখুন... লিঙ্ক পেতে অপেক্ষা করুন: ${{s}}s`;const i=setInterval(()=>{{s--,l.innerText=`অনুগ্রহ করে অপেক্ষা করুন: ${{s}}s`,s<=0&&(clearInterval(i),l.style.display="none",r.style.display="block",document.getElementById("download-counter")&&(document.getElementById("download-counter").innerText=parseInt(document.getElementById("download-counter").innerText)+1))}},1e3)}}}})}});</script>
</div>
<!-- Bot Generated Content Ends -->
"""

async def generate_image(data: dict):
    try:
        poster_bytes = await fetch_image_bytes(data['manual_poster_url']) if data.get('manual_poster_url') else \
                       (await fetch_image_bytes(f"https://image.tmdb.org/t/p/w500{data['poster_path']}") if data.get('poster_path') else None)
        if not poster_bytes: return None
        
        poster_img = Image.open(io.BytesIO(poster_bytes)).convert("RGBA").resize((400, 600))
        bg_img = Image.new('RGBA', (1280, 720), (10, 10, 20))

        if data.get('backdrop_path'):
            backdrop_bytes = await fetch_image_bytes(f"https://image.tmdb.org/t/p/w1280{data['backdrop_path']}")
            if backdrop_bytes:
                try:
                    backdrop_img = Image.open(io.BytesIO(backdrop_bytes)).convert("RGBA").resize((1280, 720))
                    bg_img = Image.alpha_composite(backdrop_img.filter(ImageFilter.GaussianBlur(4)), Image.new('RGBA', bg_img.size, (0,0,0,150)))
                except Exception as e: print(f"Could not process backdrop: {e}")

        lang_text = data.get('custom_language', '').title()
        if lang_text:
            try:
                ribbon = Image.new('RGBA', (poster_img.width, 40), (220, 20, 60, 200))
                draw_ribbon = ImageDraw.Draw(ribbon)
                text_bbox = draw_ribbon.textbbox((0, 0), lang_text, font=FONT_BADGE)
                text_x = (poster_img.width - (text_bbox[2] - text_bbox[0])) / 2
                draw_ribbon.text((text_x, 5), lang_text, font=FONT_BADGE, fill="#FFFFFF")
                poster_img.paste(ribbon, (0, 0), ribbon)
            except Exception as e: print(f"Could not add language ribbon: {e}")

        bg_img.paste(poster_img, (50, 60), poster_img)
        draw = ImageDraw.Draw(bg_img)
        title = data.get("title") or data.get("name") or "N/A"
        year = (data.get("release_date") or data.get("first_air_date") or "----")[:4]
        draw.text((480, 80), f"{title} ({year})", font=FONT_BOLD, fill="white", stroke_width=1, stroke_fill="black")
        draw.text((480, 140), f"⭐ {data.get('vote_average', 0):.1f}/10", font=FONT_REGULAR, fill="#00e676")
        genres_text = " | ".join([g["name"] for g in data.get("genres", [])])
        draw.text((480, 180), genres_text, font=FONT_SMALL, fill="#00bcd4")
        
        overview, y_text, max_chars = data.get("overview", ""), 250, 80
        for line in [overview[i:i+max_chars] for i in range(0, len(overview), max_chars)][:7]:
            draw.text((480, y_text), line, font=FONT_REGULAR, fill="#E0E0E0")
            y_text += 30

        img_buffer = io.BytesIO()
        bg_img.save(img_buffer, format="PNG")
        img_buffer.seek(0)
        return img_buffer
    except Exception as e:
        print(f"Error generating image: {e}")
        return None

# ---- BOT HANDLERS ----
@bot.on_message(filters.command("start") & filters.private)
async def start_command(_, message: Message):
    user_conversations.pop(message.from_user.id, None)
    await message.reply_text(
        "👋 **Welcome!** Send a movie/series name (e.g., `Inception 2010`) to start.\n\n"
        "**Commands:**\n`/setchannel` `/manual` `/setadlink` `/myadlink` `/cancel`"
    )

@bot.on_message(filters.command("setchannel") & filters.private)
async def set_channel_command(_, message: Message):
    if len(message.command) > 1 and message.command[1].startswith('@'):
        user_channels[message.from_user.id] = message.command[1]
        await message.reply_text(f"✅ Channel set to `{message.command[1]}`.")
    else:
        await message.reply_text("⚠️ Usage: `/setchannel @yourchannelusername`")

@bot.on_message(filters.command("cancel") & filters.private)
async def cancel_command(_, message: Message):
    if message.from_user.id in user_conversations:
        del user_conversations[message.from_user.id]
        await message.reply_text("✅ Operation cancelled.")
    else:
        await message.reply_text("👍 Nothing to cancel.")

@bot.on_message(filters.command("manual") & filters.private)
async def manual_add_command(_, message: Message):
    user_id = message.from_user.id
    user_conversations[user_id] = {"state": "manual_wait_title", "details": {}, "links": []}
    await message.reply_text("🎬 **Manual Entry**\n\nPlease send the **Title**.")

@bot.on_message(filters.command("setadlink") & filters.private)
async def set_ad_link_command(_, message: Message):
    if len(message.command) > 1 and message.command[1].startswith("https://"):
        save_ad_link(message.command[1])
        await message.reply_text(f"✅ Ad Link Updated to: `{message.command[1]}`")
    else:
        await message.reply_text("⚠️ Usage: `/setadlink https://your-ad-link.com`")

@bot.on_message(filters.command("myadlink") & filters.private)
async def my_ad_link_command(_, message: Message):
    await message.reply_text(f"🔗 **Current Ad Link:**\n`{AD_LINK}`")

async def process_text_input(client, message: Message):
    user_id = message.from_user.id
    text = message.text.strip()
    
    if (convo := user_conversations.get(user_id)) and convo.get("state") != "done":
        # Handle ongoing conversations (manual entry, links, etc.)
        state_handlers = {
            "manual_wait_title": manual_conversation_handler, "manual_wait_year": manual_conversation_handler,
            "manual_wait_overview": manual_conversation_handler, "manual_wait_genres": manual_conversation_handler,
            "manual_wait_rating": manual_conversation_handler,
            "wait_custom_language": language_conversation_handler,
            "wait_link_label": link_conversation_handler, "wait_link_url": link_conversation_handler
        }
        if handler := state_handlers.get(convo.get("state")):
            await handler(client, message)
            return

    processing_msg = await message.reply_text("🔍 Searching...")
    results = await search_tmdb(text) # <--- Awaited async function
    if not results:
        await processing_msg.edit_text("❌ No content found. Try a more specific name (e.g., `Movie Name 2023`) or use `/manual`."); return
    
    buttons = []
    for r in results:
        title = r.get('title') or r.get('name')
        year = (r.get('release_date') or r.get('first_air_date') or '----').split('-')[0]
        icon = '🎬' if r['media_type'] == 'movie' else '📺'
        buttons.append([InlineKeyboardButton(f"{icon} {title} ({year})", callback_data=f"select_{r['media_type']}_{r['id']}")])
    await processing_msg.edit_text("**👇 Choose the correct one:**", reply_markup=InlineKeyboardMarkup(buttons))

@bot.on_message(filters.text & filters.private & ~filters.command())
async def text_handler(client, message: Message):
    await process_text_input(client, message)

@bot.on_message(filters.photo & filters.private)
async def photo_handler(client, message: Message):
    user_id = message.from_user.id
    if not ((convo := user_conversations.get(user_id)) and convo.get("state") == "manual_wait_poster"): return

    processing_msg = await message.reply_text("🖼️ Optimizing and uploading poster...")
    photo_bytes = await client.download_media(message.photo.file_id, in_memory=True)
    optimized_bytes = optimize_image(photo_bytes)
    poster_url = await upload_to_imgbb(optimized_bytes) # <--- Awaited async function

    if poster_url:
        convo["details"]["manual_poster_url"] = poster_url
        convo["state"] = "wait_custom_language"
        await processing_msg.edit_text("✅ Poster uploaded!\n\n**🗣️ Now, enter the language** (e.g., `Bengali Dubbed`).")
    else:
        convo["state"] = "wait_custom_language"
        await processing_msg.edit_text("⚠️ **Poster Upload Failed!**\n\n**🗣️ Please enter the language** to continue without a poster.")

@bot.on_callback_query(filters.regex("^select_"))
async def selection_callback(client, cb: Message):
    await cb.answer("Fetching details...", show_alert=False)
    _, media_type, media_id = cb.data.split("_")
    details = await get_tmdb_details(media_type, int(media_id)) # <--- Awaited async function
    if not details:
        await cb.message.edit_text("❌ Failed to get details. Please try again."); return
    
    user_id = cb.from_user.id
    user_conversations[user_id] = {"details": details, "links": [], "state": "wait_custom_language"}
    await cb.message.edit_text("✅ Details fetched!\n\n**🗣️ Please enter the language** (e.g., `Hindi Dubbed`, `English`).")

@bot.on_callback_query(filters.regex("^addlink_"))
async def add_link_callback(_, cb: Message):
    action, user_id_str = cb.data.rsplit("_", 1)
    user_id = int(user_id_str)
    if cb.from_user.id != user_id: return await cb.answer("This is not for you!", show_alert=True)
    if not (convo := user_conversations.get(user_id)): return await cb.answer("Session expired. Start over.", show_alert=True)
    
    if action == "addlink_yes":
        convo["state"] = "wait_link_label"
        await cb.message.edit_text("**🔗 Step 1/2: Link Label**\nExample: `Download 720p`")
    elif action == "addlink_no":
        await cb.message.edit_text("✅ No links added. Generating final content...")
        await generate_final_content(bot, user_id, cb.message)

async def link_conversation_handler(_, message: Message):
    user_id = message.from_user.id
    convo = user_conversations[user_id]
    text = message.text.strip()
    if convo.get("state") == "wait_link_label":
        convo["current_label"] = text
        convo["state"] = "wait_link_url"
        await message.reply_text(f"**🔗 Step 2/2: Link URL**\n\nNow send the URL for **'{text}'**.")
    elif convo.get("state") == "wait_link_url":
        if not text.startswith("https://"):
            return await message.reply_text("⚠️ Invalid URL. Please send a valid link starting with `https://`.")
        convo["links"].append({"label": convo["current_label"], "url": text})
        del convo["current_label"]
        convo["state"] = "ask_another"
        buttons = [[InlineKeyboardButton("➕ Add Another", callback_data=f"addlink_yes_{user_id}")], 
                   [InlineKeyboardButton("✅ Done, Generate", callback_data=f"addlink_no_{user_id}")]]
        await message.reply_text("✅ Link added! Add another?", reply_markup=InlineKeyboardMarkup(buttons))

async def language_conversation_handler(_, message: Message):
    user_id = message.from_user.id
    convo = user_conversations[user_id]
    convo["details"]["custom_language"] = message.text.strip()
    convo["state"] = "ask_links"
    buttons = [[InlineKeyboardButton("✅ Yes, add links", callback_data=f"addlink_yes_{user_id}")], 
               [InlineKeyboardButton("❌ No, skip", callback_data=f"addlink_no_{user_id}")]]
    await message.reply_text(f"✅ Language set to **{convo['details']['custom_language']}**.\n\n**🔗 Add Download Links?**", reply_markup=InlineKeyboardMarkup(buttons))

async def manual_conversation_handler(_, message: Message):
    user_id, convo, text = message.from_user.id, user_conversations[message.from_user.id], message.text.strip()
    state_prompts = {
        "manual_wait_title": ("title", "manual_wait_year", "✅ Title set. Now send the 4-digit **Year** (e.g., `2023`)."),
        "manual_wait_year": ("release_date", "manual_wait_overview", "✅ Year set. Now send the **Plot/Overview**."),
        "manual_wait_overview": ("overview", "manual_wait_genres", "✅ Plot set. Send **Genres**, comma-separated."),
        "manual_wait_genres": ("genres", "manual_wait_rating", "✅ Genres set. What's the **Rating**? (e.g., `8.5`)."),
        "manual_wait_rating": ("vote_average", "manual_wait_poster", "✅ Rating set. Finally, send the **Poster Image**."),
    }
    current_state = convo.get("state")
    if current_state in state_prompts:
        key, next_state, prompt = state_prompts[current_state]
        # Data validation and formatting
        if key == "release_date" and (not text.isdigit() or len(text) != 4): return await message.reply_text("⚠️ Invalid. Please send a 4-digit year.")
        value = f"{text}-01-01" if key == "release_date" else \
                [{"name": g.strip()} for g in text.split(",")] if key == "genres" else \
                (0.0 if text.upper() == "N/A" else round(float(text), 1)) if key == "vote_average" else text
        convo["details"][key] = value
        convo["state"] = next_state
        await message.reply_text(prompt)

async def generate_final_content(client, user_id, msg_to_edit: Message):
    if not (convo := user_conversations.get(user_id)): return
    await msg_to_edit.edit_text("⏳ Generating content...")
    caption = generate_formatted_caption(convo["details"])
    html_code = generate_html(convo["details"], convo["links"])
    await msg_to_edit.edit_text("🎨 Generating image...")
    image_file = await generate_image(convo["details"]) # <--- Awaited async function
    
    convo["generated"] = {"caption": caption, "html": html_code, "image": image_file}
    convo["state"] = "done"
    
    buttons = [[InlineKeyboardButton("📝 Get Blogger HTML", callback_data=f"get_html_{user_id}")],
               [InlineKeyboardButton("📄 Copy Caption", callback_data=f"get_caption_{user_id}")]]
    if user_id in user_channels:
        buttons.append([InlineKeyboardButton("📢 Post to Channel", callback_data=f"post_channel_{user_id}")])
    
    await msg_to_edit.delete()
    
    if image_file:
        await client.send_photo(msg_to_edit.chat.id, photo=image_file, caption=caption, reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await client.send_message(msg_to_edit.chat.id, caption, reply_markup=InlineKeyboardMarkup(buttons))

@bot.on_callback_query(filters.regex("^(get_|post_)"))
async def final_action_callback(client, cb: Message):
    try:
        action, user_id_str = cb.data.rsplit("_", 1)
        user_id = int(user_id_str)
    except (ValueError, IndexError): return await cb.answer("Error: Invalid callback data.", show_alert=True)
    if cb.from_user.id != user_id: return await cb.answer("This is not for you!", show_alert=True)
    if not (convo := user_conversations.get(user_id)) or "generated" not in convo: return await cb.answer("Session expired. Start over.", show_alert=True)
    
    generated = convo["generated"]
    
    if action == "get_html":
        await cb.answer("🔗 Creating a link for your code...", show_alert=False)
        html_code = generated.get("html", "")
        session = await get_session()
        try:
            async with session.post("https://dpaste.com/api/", data={"content": html_code, "syntax": "html"}) as response:
                response.raise_for_status()
                paste_url = await response.text()
                await cb.message.reply_text(
                    "✅ **Your Blogger code is ready!**\n\nClick the button below to open and copy the code.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔗 Click Here to Copy Code", url=paste_url.strip())]])
                )
        except Exception as e:
            print(f"Error creating paste link: {e}")
            title = (convo["details"].get("title") or "post").replace(" ", "_")
            file_bytes = io.BytesIO(html_code.encode('utf-8'))
            file_bytes.name = f"{title}.html"
            await cb.message.reply_document(document=file_bytes, caption="⚠️ Could not create a link. Here is the code as a file.")

    elif action == "get_caption":
        await cb.answer()
        await client.send_message(cb.message.chat.id, generated["caption"])
    
    elif action == "post_channel":
        if not (channel_id := user_channels.get(user_id)): return await cb.answer("Channel not set. Use /setchannel.", show_alert=True)
        await cb.answer("🚀 Posting to channel...", show_alert=False)
        try:
            if image_file := generated.get("image"):
                image_file.seek(0)
                await client.send_photo(channel_id, photo=image_file, caption=generated["caption"])
            else:
                await client.send_message(channel_id, generated["caption"])
            await cb.edit_message_reply_markup(reply_markup=None)
            await cb.message.reply_text(f"✅ Successfully posted to `{channel_id}`!")
        except Exception as e:
            await cb.message.reply_text(f"❌ Failed to post. **Error:** `{e}`")

# ---- MAIN EXECUTION ----
async def main():
    print("🚀 Starting the bot...")
    load_ad_link()
    
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    await bot.start()
    print("✅ Bot is online!")
    await asyncio.Event().wait() # Keep it running
    await bot.stop()
    if AIOHTTP_SESSION:
        await AIOHTTP_SESSION.close()

if __name__ == "__main__":
    asyncio.run(main())

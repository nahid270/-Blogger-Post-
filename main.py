# -*- coding: utf-8 -*-

# ---- Core Python Imports ----
import os
import io
import sys
import re
import json
import requests
from threading import Thread

# --- Third-party Library Imports ---
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from pyrogram import Client, filters, enums
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

# --- Essential variable check ---
if not all([BOT_TOKEN, API_ID, API_HASH, TMDB_API_KEY]):
    print("❌ FATAL ERROR: One or more environment variables are missing. Please check your .env file.")
    sys.exit(1)

try:
    API_ID = int(API_ID)
except (ValueError, TypeError):
    print("❌ FATAL ERROR: API_ID must be an integer. Please check your .env file.")
    sys.exit(1)

# ---- GLOBAL VARIABLES for state management & AD LINK ----
user_conversations = {}
user_channels = {}
USER_AD_LINKS_FILE = "user_ad_links.json"
DEFAULT_AD_LINK = "https://www.google.com"  # Default Ad Link if a user hasn't set one
user_ad_links = {}

# ---- FUNCTIONS to save and load user-specific ad links ----
def save_user_ad_links():
    """Saves the user ad links dictionary to a JSON file."""
    try:
        with open(USER_AD_LINKS_FILE, "w") as f:
            json.dump(user_ad_links, f, indent=4)
    except IOError as e:
        print(f"⚠️ Error saving user ad links: {e}")

def load_user_ad_links():
    """Loads user ad links from a JSON file on startup."""
    global user_ad_links
    if os.path.exists(USER_AD_LINKS_FILE):
        try:
            with open(USER_AD_LINKS_FILE, "r") as f:
                user_ad_links = json.load(f)
                # Ensure keys are integers if JSON saves them as strings
                user_ad_links = {int(k): v for k, v in user_ad_links.items()}
                print(f"✅ User ad links loaded from file.")
        except (IOError, json.JSONDecodeError) as e:
            print(f"⚠️ Error loading user ad links: {e}")

# ---- FLASK APP FOR KEEP-ALIVE ----
app = Flask(__name__)
@app.route('/')
def home():
    return "✅ Final Movie/Series Bot is up and running!"

def run_flask():
    app.run(host='0.0.0.0', port=8080)

# ---- PYROGRAM BOT INITIALIZATION ----
try:
    bot = Client("moviebot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
except Exception as e:
    print(f"❌ FATAL ERROR: Could not initialize the bot client. Error: {e}")
    sys.exit(1)

# ---- FONT CONFIGURATION for Image Generation ----
try:
    FONT_BOLD = ImageFont.truetype("Poppins-Bold.ttf", 32)
    FONT_REGULAR = ImageFont.truetype("Poppins-Regular.ttf", 24)
    FONT_SMALL = ImageFont.truetype("Poppins-Regular.ttf", 18)
    FONT_BADGE = ImageFont.truetype("Poppins-Bold.ttf", 22)
except IOError:
    print("⚠️ Warning: Poppins font files not found. Image generation will use default fonts.")
    FONT_BOLD = ImageFont.load_default()
    FONT_REGULAR = ImageFont.load_default()
    FONT_SMALL = ImageFont.load_default()
    FONT_BADGE = ImageFont.load_default()

# ---- TMDB API FUNCTIONS ----
def search_tmdb(query: str):
    year = None
    match = re.search(r'(.+?)\s*\(?(\d{4})\)?$', query)
    if match:
        name = match.group(1).strip()
        year = match.group(2)
    else:
        name = query.strip()
    try:
        search_url = f"https://api.themoviedb.org/3/search/multi?api_key={TMDB_API_KEY}&query={name}"
        if year:
            search_url += f"&year={year}"
        response = requests.get(search_url, timeout=10)
        response.raise_for_status()
        results = [r for r in response.json().get("results", []) if r.get("media_type") in ["movie", "tv"]]
        return results[:5]
    except requests.exceptions.RequestException as e:
        print(f"Error searching TMDB: {e}")
        return []

def get_tmdb_details(media_type: str, media_id: int):
    try:
        details_url = f"https://api.themoviedb.org/3/{media_type}/{media_id}?api_key={TMDB_API_KEY}&append_to_response=credits,videos,similar"
        response = requests.get(details_url, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching TMDB details: {e}")
        return None

# ---- CONTENT GENERATION FUNCTIONS ----
def generate_formatted_caption(data: dict):
    title = data.get("title") or data.get("name") or "N/A"
    year = (data.get("release_date") or data.get("first_air_date") or "----")[:4]
    
    runtime_str = "N/A"
    if runtime_minutes := data.get("runtime"):
        hours = runtime_minutes // 60
        minutes = runtime_minutes % 60
        runtime_str = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"
        
    rating = f"⭐ {data.get('vote_average', 0):.1f}/10"
    genres = ", ".join([g["name"] for g in data.get("genres", [])] or ["N/A"])
    cast = ", ".join([actor["name"] for actor in data.get("credits", {}).get("cast", [])[:5]] or ["N/A"])
    language = data.get('custom_language', '').title()
    overview = data.get("overview", "No plot summary available.")
    
    similar_movies = data.get("similar", {}).get("results", [])
    similar_movies_list = [
        f"» {movie.get('title') or movie.get('name')}" for movie in similar_movies[:4]
    ]

    caption_text = f"🎬 **{title} ({year})**\n\n"
    
    if language:
        caption_text += f"**🎭 Genres:** {genres}\n"
        caption_text += f"**🗣️ Language:** {language}\n"
        caption_text += f"**⏳ Runtime:** {runtime_str}\n"
        caption_text += f"**⭐ Rating:** {rating}\n\n"
    else:
        caption_text += f"**🎭 Genres:** {genres}\n"
        caption_text += f"**⏳ Runtime:** {runtime_str} | **⭐ Rating:** {rating}\n\n"

    if cast != "N/A":
        caption_text += f"**👥 Cast:** _{cast}_\n\n"

    caption_text += f"**📝 Plot:** _{overview[:400]}{'...' if len(overview) > 400 else ''}_"
    
    if similar_movies_list:
        caption_text += "\n\n**💡 You Might Also Like:**\n" + "\n".join(similar_movies_list)
        
    return caption_text

def generate_html(data: dict, links: list, user_id: int):
    ad_link = user_ad_links.get(user_id, DEFAULT_AD_LINK)
    
    TIMER_SECONDS = 10
    INITIAL_DOWNLOADS = 493
    TELEGRAM_LINK = "https://t.me/+60goZWp-FpkxNzVl"
    title = data.get("title") or data.get("name") or "N/A"
    year = (data.get("release_date") or data.get("first_air_date") or "----")[:4]
    language = data.get('custom_language', '').title()
    overview = data.get("overview", "No overview available.")
    
    if data.get('manual_poster_url'):
        poster_url = data['manual_poster_url']
    elif data.get('poster_path'):
        poster_url = f"https://image.tmdb.org/t/p/w500{data['poster_path']}"
    else:
        poster_url = "https://via.placeholder.com/400x600.png?text=No+Poster"

    cast_html = ""
    cast_members = data.get("credits", {}).get("cast", [])
    if cast_members:
        cast_html += '<h3 style="text-align:center; margin-top: 25px;">🎭 Meet the Cast 🎭</h3>'
        cast_html += '<div class="cast-container">'
        
        for member in cast_members[:8]:
            member_name = member.get("name")
            profile_path = member.get("profile_path")
            
            if profile_path:
                member_image_url = f"https://image.tmdb.org/t/p/w185{profile_path}"
            else:
                member_image_url = "https://via.placeholder.com/185x278.png?text=No+Image"

            cast_html += f"""
            <div class="cast-member">
                <img src="{member_image_url}" alt="{member_name}" class="cast-photo">
                <p class="cast-name">{member_name}</p>
            </div>
            """
        cast_html += '</div>'

    download_blocks_html = ""
    if not links:
        download_blocks_html = "<p>No download links available.</p>"
    else:
        for link in links:
            download_blocks_html += f"""
            <div class="dl-download-block">
                <button class="dl-download-button" data-url="{link['url']}" data-label="{link['label']}" data-click-count="0">⬇️ {link['label']}</button>
                <div class="dl-timer-display"></div>
                <a href="#" class="dl-real-download-link" target="_blank" rel="noopener noreferrer">✅ Get {link['label']}</a>
            </div>
            """

    final_html = f"""
<!-- Bot Generated Content Starts -->
<div style="text-align: center;">
    <img src="{poster_url}" alt="{title} Poster" style="max-width: 280px; border-radius: 8px; margin-bottom: 15px;">
    <h2>{title} ({year}) - {language}</h2>
    <p style="text-align: left; padding: 0 10px;">{overview}</p>
</div>
<!--more-->
{cast_html}
<div class="dl-body" style="font-family: 'Segoe UI', sans-serif; background-color: #f0f2f5; margin: 0; padding: 20px; display: flex; justify-content: center; align-items: center;">
    <style>
        .cast-container {{ display: flex; flex-wrap: wrap; justify-content: center; gap: 15px; margin-top: 20px; padding: 10px; }}
        .cast-member {{ text-align: center; width: 100px; }}
        .cast-photo {{ width: 80px; height: 80px; border-radius: 50%; object-fit: cover; border: 2px solid #ddd; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }}
        .cast-name {{ font-size: 13px; font-weight: 500; color: #333; margin-top: 8px; }}
        .dl-main-content {{ width: 100%; max-width: 500px; margin: auto; }}
        .dl-post-container {{ background: #ffffff; padding: 20px; border-radius: 20px; box-shadow: 0 10px 30px rgba(0, 0, 0, 0.1); border: 1px solid #e7eaf3; }}
        .dl-instruction-box {{ background-color: #fffbe6; border: 1px solid #ffe58f; color: #333; padding: 15px; border-radius: 10px; margin-bottom: 20px; text-align: center; }}
        .dl-instruction-box h2 {{ margin: 0 0 10px; font-size: 18px; }}
        .dl-instruction-box p {{ margin: 5px 0; font-size: 14px; line-height: 1.5; }}
        .dl-download-block {{ border: 1px solid #ddd; border-radius: 12px; padding: 15px; margin-bottom: 15px; }}
        .dl-download-button, .dl-real-download-link {{ display: block; width: 100%; padding: 15px; text-align: center; border-radius: 12px; font-size: 16px; font-weight: bold; cursor: pointer; text-decoration: none; transition: 0.3s; box-sizing: border-box; }}
        .dl-download-button {{ background: #ff5722; color: white !important; border: none; }}
        .dl-real-download-link {{ background: #4caf50; color: white !important; display: none; }}
        .dl-telegram-link {{ display: block; width: 100%; padding: 15px; text-align: center; border-radius: 12px; font-size: 16px; font-weight: bold; cursor: pointer; text-decoration: none; transition: 0.3s; box-sizing: border-box; background: #0088cc; color: white !important; margin-top: 20px; }}
        .dl-timer-display {{ margin-top: 10px; font-size: 18px; font-weight: bold; color: #d32f2f; background: #f0f0f0; padding: 12px; border-radius: 10px; text-align: center; display: none; }}
        .dl-download-count-text {{ margin-top: 20px; font-size: 15px; color: #555; text-align: center; }}
    </style>
    <div class="dl-main-content">
        <div class="dl-post-container">
            <div class="dl-instruction-box">
                <h2>🎬 ডাউনলোড করার নিয়মাবলী</h2>
                <p>প্রথমবার ক্লিক করলে একটি বিজ্ঞাপন খুলবে।</p>
                <p>দ্বিতীয়বার ক্লিক করলে <strong>টাইমার</strong> শুরু হবে।</p>
                <p>টাইমার শেষ হলে আপনি ডাউনলোড লিঙ্কটি পাবেন।</p>
            </div>
            {download_blocks_html}
            <div class="dl-download-count-text">✅ মোট ডাউনলোড: <span id="download-counter">{INITIAL_DOWNLOADS}</span></div>
            <a class="dl-telegram-link" href="{TELEGRAM_LINK}" target="_blank" rel="noopener noreferrer">💋 Join Telegram Channel</a>
        </div>
    </div>
    <script>
    document.addEventListener('DOMContentLoaded', function() {{
        const AD_LINK = "{ad_link}";
        const TIMER_SECONDS = {TIMER_SECONDS};
        document.querySelectorAll('.dl-download-button').forEach(button => {{
            button.onclick = () => {{
                let clickCount = parseInt(button.dataset.clickCount);
                const block = button.parentElement;
                const timerDisplay = block.querySelector('.dl-timer-display');
                const realDownloadLink = block.querySelector('.dl-real-download-link');
                const downloadUrl = button.dataset.url;
                if (clickCount === 0) {{
                    window.open(AD_LINK, "_blank");
                    button.innerText = "Click Again to Start Timer";
                    button.dataset.clickCount = 1;
                }} else if (clickCount === 1) {{
                    button.style.display = 'none';
                    timerDisplay.style.display = 'block';
                    realDownloadLink.href = downloadUrl;
                    let timeLeft = TIMER_SECONDS;
                    timerDisplay.innerText = `Please Wait: ${{timeLeft}}s`;
                    const timer = setInterval(() => {{
                        timeLeft--;
                        timerDisplay.innerText = `Please Wait: ${{timeLeft}}s`;
                        if (timeLeft <= 0) {{
                            clearInterval(timer);
                            timerDisplay.style.display = 'none';
                            realDownloadLink.style.display = 'block';
                            const counter = document.getElementById('download-counter');
                            if(counter) {{ counter.innerText = parseInt(counter.innerText) + 1; }}
                        }}
                    }}, 1000);
                    button.dataset.clickCount = 2;
                }}
            }};
        }});
    }});
    </script>
</div>
<!-- Bot Generated Content Ends -->
"""
    return final_html

def generate_image(data: dict):
    try:
        poster_bytes = None
        if data.get("manual_poster_url"):
            try:
                poster_response = requests.get(data["manual_poster_url"], timeout=15)
                if poster_response.ok: poster_bytes = poster_response.content
            except requests.exceptions.RequestException as e:
                print(f"⚠️ Could not download manual poster from URL: {e}")
        elif data.get('poster_path'):
            poster_url = f"https://image.tmdb.org/t/p/w500{data['poster_path']}"
            poster_response = requests.get(poster_url)
            if poster_response.ok: poster_bytes = poster_response.content
        
        if not poster_bytes: return None

        poster_img = Image.open(io.BytesIO(poster_bytes)).convert("RGBA").resize((400, 600))
        bg_img = Image.new('RGBA', (1280, 720), (10, 10, 20))
        if data.get('backdrop_path'):
            try:
                backdrop_url = f"https://image.tmdb.org/t/p/w1280{data['backdrop_path']}"
                backdrop_response = requests.get(backdrop_url)
                if backdrop_response.ok:
                    bg_img = Image.open(io.BytesIO(backdrop_response.content)).convert("RGBA").resize((1280, 720))
                    bg_img = bg_img.filter(ImageFilter.GaussianBlur(4))
                    darken_layer = Image.new('RGBA', bg_img.size, (0, 0, 0, 150))
                    bg_img = Image.alpha_composite(bg_img, darken_layer)
            except Exception as e:
                print(f"Could not process backdrop image: {e}")
        lang_text = data.get('custom_language', '').title()
        if lang_text:
            try:
                ribbon = Image.new('RGBA', (poster_img.width, 40), (220, 20, 60, 200))
                draw_ribbon = ImageDraw.Draw(ribbon)
                text_bbox = draw_ribbon.textbbox((0, 0), lang_text, font=FONT_BADGE)
                text_x = (poster_img.width - (text_bbox[2] - text_bbox[0])) / 2
                draw_ribbon.text((text_x, 5), lang_text, font=FONT_BADGE, fill="#FFFFFF")
                poster_img.paste(ribbon, (0, 0), ribbon)
            except Exception as e:
                print(f"Could not add language ribbon: {e}")
        bg_img.paste(poster_img, (50, 60), poster_img)
        draw = ImageDraw.Draw(bg_img)
        title = data.get("title") or data.get("name") or "N/A"
        year = (data.get("release_date") or data.get("first_air_date") or "----")[:4]
        draw.text((480, 80), f"{title} ({year})", font=FONT_BOLD, fill="white", stroke_width=1, stroke_fill="black")
        draw.text((480, 140), f"⭐ {data.get('vote_average', 0):.1f}/10", font=FONT_REGULAR, fill="#00e676")
        genres_text = " | ".join([g["name"] for g in data.get("genres", [])])
        draw.text((480, 180), genres_text, font=FONT_SMALL, fill="#00bcd4")
        overview, y_text, max_chars_per_line = data.get("overview", ""), 250, 80
        lines = [overview[i:i+max_chars_per_line] for i in range(0, len(overview), max_chars_per_line)]
        for line in lines[:7]:
            draw.text((480, y_text), line, font=FONT_REGULAR, fill="#E0E0E0")
            y_text += 30
        img_buffer = io.BytesIO()
        img_buffer.name = "poster.png"
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
        "👋 **Welcome to the Movie & Series Bot!**\n\n"
        "Send me a movie or series name (e.g., `Inception 2010`) to get started.\n\n"
        "**Available Commands:**\n"
        "`/setchannel` - Set your channel for posting.\n"
        "`/manual` - Add content details manually.\n"
        "`/setadlink` - Update your personal advertisement link.\n"
        "`/myadlink` - View your current ad link.\n"
        "`/cancel` - Cancel the current operation."
    )

@bot.on_message(filters.command("setchannel") & filters.private)
async def set_channel_command(_, message: Message):
    if len(message.command) > 1 and message.command[1].startswith('@'):
        user_channels[message.from_user.id] = message.command[1]
        await message.reply_text(f"✅ Channel successfully set to `{message.command[1]}`.")
    else:
        await message.reply_text("⚠️ **Usage:** `/setchannel @yourchannelusername`")

@bot.on_message(filters.command("cancel") & filters.private)
async def cancel_command(_, message: Message):
    if message.from_user.id in user_conversations:
        del user_conversations[message.from_user.id]
        await message.reply_text("✅ Operation successfully cancelled.")
    else:
        await message.reply_text("👍 Nothing to cancel.")

@bot.on_message(filters.command("manual") & filters.private)
async def manual_add_command(_, message: Message):
    user_id = message.from_user.id
    user_conversations[user_id] = {"state": "manual_wait_title", "details": {}, "links": []}
    await message.reply_text("🎬 **Manual Content Entry**\n\nFirst, please send the **Title** of the movie/series.")

@bot.on_message(filters.command("setadlink") & filters.private)
async def set_ad_link_command(_, message: Message):
    user_id = message.from_user.id
    if len(message.command) > 1 and (message.command[1].startswith("http://") or message.command[1].startswith("https://")):
        new_link = message.command[1]
        user_ad_links[user_id] = new_link
        save_user_ad_links()
        await message.reply_text(f"✅ **Your Ad Link Updated!**\n\nNew Link: `{new_link}`")
    else:
        await message.reply_text("⚠️ **Usage:** `/setadlink https://your-ad-link.com`")

@bot.on_message(filters.command("myadlink") & filters.private)
async def my_ad_link_command(_, message: Message):
    user_id = message.from_user.id
    link = user_ad_links.get(user_id, DEFAULT_AD_LINK)
    await message.reply_text(f"🔗 **Your Current Ad Link:**\n`{link}`")

# ----- THIS IS THE CORRECTED LINE -----
@bot.on_message(filters.text & filters.private & ~filters.command(["start", "setchannel", "cancel", "manual", "setadlink", "myadlink"]))
async def text_handler(client, message: Message):
    user_id = message.from_user.id
    text = message.text.strip()
    if convo := user_conversations.get(user_id):
        state = convo.get("state")
        if state and state != "done":
            handlers = {
                "manual_wait_title": manual_conversation_handler, "manual_wait_year": manual_conversation_handler,
                "manual_wait_overview": manual_conversation_handler, "manual_wait_genres": manual_conversation_handler,
                "manual_wait_rating": manual_conversation_handler, "manual_wait_poster_url": manual_conversation_handler,
                "wait_custom_language": language_conversation_handler,
                "wait_link_label": link_conversation_handler, "wait_link_url": link_conversation_handler
            }
            if handler := handlers.get(state):
                return await handler(client, message)
    processing_msg = await message.reply_text("🔍 Searching...")
    results = search_tmdb(text)
    if not results:
        return await processing_msg.edit_text("❌ No content found. Try a more specific name (e.g., `Movie Name 2023`) or use `/manual`.")
    buttons = []
    for r in results:
        title = r.get('title') or r.get('name')
        year = (r.get('release_date') or r.get('first_air_date') or '----').split('-')[0]
        icon = '🎬' if r['media_type'] == 'movie' else '📺'
        buttons.append([InlineKeyboardButton(f"{icon} {title} ({year})", callback_data=f"select_{r['media_type']}_{r['id']}")])
    await processing_msg.edit_text("**👇 Choose the correct one:**", reply_markup=InlineKeyboardMarkup(buttons))

@bot.on_message(filters.photo & filters.private)
async def photo_handler(_, message: Message):
    if message.from_user.id in user_conversations:
        await message.reply_text("⚠️ Currently, I can only accept poster URLs during manual entry. Please use the `/manual` command and provide a URL when prompted.")

@bot.on_callback_query(filters.regex("^select_"))
async def selection_callback(_, cb):
    await cb.answer("Fetching details...", show_alert=False)
    _, media_type, media_id = cb.data.split("_")
    details = get_tmdb_details(media_type, int(media_id))
    if not details:
        return await cb.message.edit_text("❌ Failed to get details. Please try again.")
    user_id = cb.from_user.id
    user_conversations[user_id] = {"details": details, "links": [], "state": "wait_custom_language"}
    await cb.message.edit_text("✅ Details fetched!\n\n**🗣️ Please enter the language** (e.g., `Hindi Dubbed`, `English`, `Dual Audio`).")

@bot.on_callback_query(filters.regex("^addlink_"))
async def add_link_callback(client, cb):
    action, user_id_str = cb.data.rsplit("_", 1)
    user_id = int(user_id_str)
    if cb.from_user.id != user_id: return await cb.answer("This is not for you!", show_alert=True)
    if not (convo := user_conversations.get(user_id)): return await cb.answer("Session expired. Please start over.", show_alert=True)
    if action == "addlink_yes":
        convo["state"] = "wait_link_label"
        await cb.message.edit_text("**🔗 Step 1/2: Link Label**\n\nExample: `Download 720p` or `Watch Online`")
    elif action == "addlink_no":
        await cb.message.edit_text("✅ No links will be added. Generating final content...")
        await generate_final_content(client, user_id, cb.message)

async def link_conversation_handler(_, message: Message):
    user_id = message.from_user.id
    convo = user_conversations[user_id]
    text = message.text.strip()
    if convo.get("state") == "wait_link_label":
        convo["current_label"] = text
        convo["state"] = "wait_link_url"
        await message.reply_text(f"**🔗 Step 2/2: Link URL**\n\nNow send the URL for **'{text}'**.")
    elif convo.get("state") == "wait_link_url":
        if not (text.startswith("http://") or text.startswith("https://")):
            return await message.reply_text("⚠️ Invalid URL. Please send a valid link starting with `http://` or `https://`.")
        convo["links"].append({"label": convo["current_label"], "url": text})
        del convo["current_label"]
        convo["state"] = "ask_another"
        buttons = [[InlineKeyboardButton("➕ Add Another Link", callback_data=f"addlink_yes_{user_id}")], 
                   [InlineKeyboardButton("✅ Done, Generate Post", callback_data=f"addlink_no_{user_id}")]]
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
    user_id = message.from_user.id
    convo = user_conversations[user_id]
    text = message.text.strip()
    state = convo.get("state")
    if state == "manual_wait_title":
        convo["details"]["title"] = text
        convo["state"] = "manual_wait_year"
        await message.reply_text("✅ Title set. Now send the 4-digit **Year** (e.g., `2023`).")
    elif state == "manual_wait_year":
        if text.isdigit() and len(text) == 4:
            convo["details"]["release_date"] = f"{text}-01-01"
            convo["state"] = "manual_wait_overview"
            await message.reply_text("✅ Year set. Now send the **Plot/Overview**.")
        else: await message.reply_text("⚠️ Invalid. Please send a 4-digit year.")
    elif state == "manual_wait_overview":
        convo["details"]["overview"] = text
        convo["state"] = "manual_wait_genres"
        await message.reply_text("✅ Plot set. Send **Genres**, comma-separated (e.g., `Action, Drama`).")
    elif state == "manual_wait_genres":
        convo["details"]["genres"] = [{"name": g.strip()} for g in text.split(",")]
        convo["state"] = "manual_wait_rating"
        await message.reply_text("✅ Genres set. What's the **Rating**? (e.g., `8.5`). Send `N/A` if none.")
    elif state == "manual_wait_rating":
        try:
            convo["details"]["vote_average"] = 0.0 if text.upper() == "N/A" else round(float(text), 1)
            convo["state"] = "manual_wait_poster_url"
            await message.reply_text("✅ Rating set. Finally, send the **Poster Image URL**.")
        except ValueError: await message.reply_text("⚠️ Invalid rating. Send a number (e.g., `7.8`) or `N/A`.")
    elif state == "manual_wait_poster_url":
        if text.startswith("http://") or text.startswith("https://"):
            convo["details"]["manual_poster_url"] = text
            convo["state"] = "wait_custom_language"
            await message.reply_text(f"✅ Poster URL set!\n\n**🗣️ Now, enter the language for this post** (e.g., `Bengali Dubbed`).")
        else: await message.reply_text("⚠️ Invalid URL. Please send a valid link.")

async def generate_final_content(client, user_id, msg_to_edit: Message):
    if not (convo := user_conversations.get(user_id)): return
    await msg_to_edit.edit_text("⏳ Generating content...")
    caption = generate_formatted_caption(convo["details"])
    html_code = generate_html(convo["details"], convo["links"], user_id)
    await msg_to_edit.edit_text("🎨 Generating image...")
    image_file = generate_image(convo["details"])
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
        await client.send_message(msg_to_edit.chat.id, "⚠️ **Image could not be generated.**\n\n" + caption, reply_markup=InlineKeyboardMarkup(buttons))

@bot.on_callback_query(filters.regex("^(get_|post_)"))
async def final_action_callback(client, cb):
    try:
        action, user_id_str = cb.data.rsplit("_", 1)
        user_id = int(user_id_str)
    except (ValueError, IndexError): return await cb.answer("Error: Invalid callback data.", show_alert=True)
    
    if cb.from_user.id != user_id: return await cb.answer("This is not for you!", show_alert=True)
    if not (convo := user_conversations.get(user_id)) or "generated" not in convo:
        return await cb.answer("Session expired. Please start over.", show_alert=True)
    
    generated = convo["generated"]
    
    if action == "get_html":
        await cb.answer("🔗 আপনার কোডের জন্য একটি লিংক তৈরি করা হচ্ছে...", show_alert=False)
        html_code = generated.get("html", "")
        try:
            response = requests.post("https://dpaste.com/api/", data={"content": html_code, "syntax": "html"})
            response.raise_for_status()
            await cb.message.reply_text(
                "✅ **আপনার ব্লগার কোড প্রস্তুত!**",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔗 কোড কপি করতে এখানে ক্লিক করুন", url=response.text.strip())]])
            )
        except requests.exceptions.RequestException as e:
            print(f"Error creating paste link: {e}")
            await cb.message.reply_text("⚠️ **দুঃখিত!** কোডটির জন্য লিংক তৈরি করা সম্ভব হয়নি। ফাইল হিসেবে পাঠানো হলো।")
            file_bytes = io.BytesIO(html_code.encode('utf-8'))
            file_bytes.name = f"{(convo['details'].get('title') or 'post').replace(' ', '_')}.html"
            await client.send_document(cb.message.chat.id, document=file_bytes)

    elif action == "get_caption":
        await cb.answer()
        await client.send_message(cb.message.chat.id, generated["caption"])
    
    elif action == "post_channel":
        if not (channel_id := user_channels.get(user_id)):
            return await cb.answer("Channel not set. Use /setchannel first.", show_alert=True)
        
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
if __name__ == "__main__":
    print("🚀 Starting the bot...")
    load_user_ad_links()
    flask_thread = Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    bot.run()
    print("👋 Bot has stopped.")

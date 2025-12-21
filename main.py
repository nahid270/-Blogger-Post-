# -*- coding: utf-8 -*-

# ---- Core Python Imports ----
import os
import io
import sys
import re
import json
import requests
import urllib3
from threading import Thread
import logging

# --- Third-party Library Imports ---
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from pyrogram import Client, filters, enums
from pyrogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton, Message,
    InlineQuery, InlineQueryResultArticle, InputTextMessageContent, CallbackQuery
)
from flask import Flask
from dotenv import load_dotenv

# --- Disable SSL Warnings ---
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- Basic Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()

# ---- CONFIGURATION ----
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
TMDB_API_KEY = os.getenv("TMDB_API_KEY")

# --- Essential variable check ---
if not all([BOT_TOKEN, API_ID, API_HASH, TMDB_API_KEY]):
    logger.critical("❌ FATAL ERROR: One or more environment variables are missing. Please check your .env file.")
    sys.exit(1)

try:
    API_ID = int(API_ID)
except (ValueError, TypeError):
    logger.critical("❌ FATAL ERROR: API_ID must be an integer. Please check your .env file.")
    sys.exit(1)

# ---- GLOBAL VARIABLES for state management ----
user_conversations = {}
user_channels = {}
USER_AD_LINKS_FILE = "user_ad_links.json"
DEFAULT_AD_LINK = "https://www.google.com"
user_ad_links = {}

# --- CHANNEL POST CONFIGURATION ---
USER_PROMO_CONFIG_FILE = "user_promo_config.json"
user_promo_config = {} 

# ---- FUNCTIONS to save and load user-specific data ----
def save_user_ad_links():
    try:
        with open(USER_AD_LINKS_FILE, "w") as f:
            json.dump(user_ad_links, f, indent=4)
    except IOError as e:
        logger.warning(f"⚠️ Error saving user ad links: {e}")

def load_user_ad_links():
    global user_ad_links
    if os.path.exists(USER_AD_LINKS_FILE):
        try:
            with open(USER_AD_LINKS_FILE, "r") as f:
                user_ad_links = {int(k): v for k, v in json.load(f).items()}
                logger.info("✅ User ad links loaded.")
        except (IOError, json.JSONDecodeError) as e:
            logger.warning(f"⚠️ Error loading user ad links: {e}")

def save_promo_config():
    try:
        with open(USER_PROMO_CONFIG_FILE, "w") as f:
            json.dump(user_promo_config, f, indent=4)
    except IOError as e:
        logger.warning(f"⚠️ Error saving promo config: {e}")

def load_promo_config():
    global user_promo_config
    if os.path.exists(USER_PROMO_CONFIG_FILE):
        try:
            with open(USER_PROMO_CONFIG_FILE, "r") as f:
                user_promo_config = {int(k): v for k, v in json.load(f).items()}
                logger.info("✅ User promo configs loaded.")
        except (IOError, json.JSONDecodeError) as e:
            logger.warning(f"⚠️ Error loading promo config: {e}")

# ---- FORCE DPASTE FUNCTION (SSL BYPASS) ----
def create_paste_link(content: str):
    """
    Generates a link using dpaste.com.
    FORCE FIX: Disables SSL verification (verify=False) to bypass connection errors.
    """
    if not content:
        return None

    # Using User-Agent to look like a real browser
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    try:
        # verify=False is the KEY FIX here
        response = requests.post(
            "https://dpaste.com/api/",
            data={
                "content": content,
                "syntax": "html",
                "expiry_days": 14, 
                "title": "Blogger Code"
            },
            headers=headers,
            timeout=20,
            verify=False  # <--- This fixes "Connection not private"
        )
        
        if response.status_code == 201 or response.status_code == 200:
            return response.text.strip()
            
    except Exception as e:
        logger.error(f"❌ Dpaste failed: {e}")
        
    return None

# ---- FLASK APP FOR KEEP-ALIVE ----
app = Flask(__name__)
@app.route('/')
def home():
    return "✅ Final Bot (Dpaste Fixed SSL) is running!"

def run_flask():
    app.run(host='0.0.0.0', port=8080)

# ---- PYROGRAM BOT INITIALIZATION ----
try:
    bot = Client("moviebot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
except Exception as e:
    logger.critical(f"❌ FATAL ERROR: Could not initialize bot client. Error: {e}")
    sys.exit(1)

# ---- FONT CONFIGURATION ----
try:
    FONT_BOLD = ImageFont.truetype("Poppins-Bold.ttf", 32)
    FONT_REGULAR = ImageFont.truetype("Poppins-Regular.ttf", 24)
    FONT_SMALL = ImageFont.truetype("Poppins-Regular.ttf", 18)
    FONT_BADGE = ImageFont.truetype("Poppins-Bold.ttf", 22)
except IOError:
    logger.warning("⚠️ Poppins font files not found. Using default fonts.")
    FONT_BOLD, FONT_REGULAR, FONT_SMALL, FONT_BADGE = (ImageFont.load_default(),)*4

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
        search_url = f"https://api.themoviedb.org/3/search/multi?api_key={TMDB_API_KEY}&query={name}&include_adult=true"
        if year:
            search_url += f"&year={year}"
        response = requests.get(search_url, timeout=10)
        response.raise_for_status()
        results = [r for r in response.json().get("results", []) if r.get("media_type") in ["movie", "tv"]]
        return results[:15]
    except requests.exceptions.RequestException as e:
        logger.error(f"Error searching TMDB: {e}")
        return []

def get_tmdb_details(media_type: str, media_id: int):
    try:
        details_url = f"https://api.themoviedb.org/3/{media_type}/{media_id}?api_key={TMDB_API_KEY}&append_to_response=credits,videos,similar"
        response = requests.get(details_url, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching TMDB details: {e}")
        return None

def extract_tmdb_id(query: str):
    query = query.strip()
    tmdb_url_pattern = r"themoviedb\.org/(movie|tv)/(\d+)"
    match = re.search(tmdb_url_pattern, query)
    if match:
        return match.group(1), int(match.group(2))

    imdb_match = re.search(r"(tt\d+)", query)
    if imdb_match:
        imdb_id = imdb_match.group(1)
        try:
            find_url = f"https://api.themoviedb.org/3/find/{imdb_id}?api_key={TMDB_API_KEY}&external_source=imdb_id"
            response = requests.get(find_url, timeout=10)
            response.raise_for_status()
            data = response.json()
            if data.get("movie_results"):
                return "movie", data["movie_results"][0]["id"]
            elif data.get("tv_results"):
                return "tv", data["tv_results"][0]["id"]
        except Exception as e:
            logger.error(f"Error finding IMDb ID: {e}")
            return None, None

    if "/" in query:
        parts = query.split("/")
        if len(parts) == 2 and parts[0] in ["movie", "tv"] and parts[1].isdigit():
            return parts[0], int(parts[1])

    return None, None

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
        caption_text += f"**🎭 Genres:** {genres}\n**🗣️ Language:** {language}\n**⏳ Runtime:** {runtime_str}\n**⭐ Rating:** {rating}\n\n"
    else:
        caption_text += f"**🎭 Genres:** {genres}\n**⏳ Runtime:** {runtime_str} | **⭐ Rating:** {rating}\n\n"

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
    TELEGRAM_LINK = "https://t.me/YourChannelLink"
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
            member_image_url = f"https://image.tmdb.org/t/p/w185{profile_path}" if profile_path else "https://via.placeholder.com/185x278.png?text=No+Image"
            cast_html += f"""
            <div class="cast-member">
                <img src="{member_image_url}" alt="{member_name}" class="cast-photo">
                <p class="cast-name">{member_name}</p>
            </div>
            """
        cast_html += '</div>'

    download_blocks_html = ""
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

def generate_filedl_html(title, links_list):
    css = """
    <style>
        .fdl-container { font-family: 'Segoe UI', sans-serif; text-align: center; max-width: 600px; margin: 0 auto; padding: 20px; background: #fff; }
        .fdl-title { font-size: 20px; font-weight: 600; margin-bottom: 25px; color: #333; line-height: 1.4; }
        .fdl-btn-container { display: flex; flex-wrap: wrap; justify-content: center; gap: 10px; margin-bottom: 20px; }
        .fdl-btn {
            display: inline-block; padding: 12px 15px; border-radius: 4px; text-decoration: none;
            color: white !important; font-weight: 500; font-size: 14px; flex: 1 1 45%; 
            background-color: #007bff;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1); transition: 0.2s; text-align: center; border: none; margin-bottom: 5px;
        }
        .fdl-btn:hover { opacity: 0.9; transform: translateY(-1px); background-color: #0056b3; }
        .fdl-footer { font-size: 13px; color: #666; margin-top: 20px; line-height: 1.5; border-top: 1px solid #eee; padding-top: 15px;}
    </style>
    """
    
    buttons_html = ""
    for link_data in links_list:
        label = link_data['label']
        url = link_data['url']
        buttons_html += f'<a href="{url}" class="fdl-btn" target="_blank">{label}</a>\n'

    html = f"""
    {css}
    <div class="fdl-container">
        <div class="fdl-title">{title}</div>
        <div class="fdl-btn-container">
            {buttons_html}
        </div>
        <div class="fdl-footer">
            Thank you for using our site — enjoy ultra-fast downloads Speed.<br>
            If one server is busy or slow, simply switch to another with one click for Fast speed :)
        </div>
    </div>
    """
    return html

def generate_image(data: dict):
    try:
        poster_bytes = None
        if data.get("manual_poster_url"):
            try:
                poster_response = requests.get(data["manual_poster_url"], timeout=15)
                if poster_response.ok: poster_bytes = poster_response.content
            except requests.exceptions.RequestException as e:
                logger.warning(f"⚠️ Could not download manual poster from URL: {e}")
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
                logger.warning(f"Could not process backdrop image: {e}")
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
                logger.warning(f"Could not add language ribbon: {e}")
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
        logger.error(f"Error generating image: {e}")
        return None

# ---- BOT HANDLERS ----
@bot.on_message(filters.command("start") & filters.private)
async def start_command(client, message: Message):
    user_conversations.pop(message.from_user.id, None)
    await message.reply_text(
        f"👋 **Welcome to the Movie & Series Bot!**\n\n"
        f"**New:** Use `/post` to create content easily!\n\n"
        f"**Commands:**\n"
        f"1️⃣ `/post <Name>` - Search by Name (e.g. `/post Inception`)\n"
        f"2️⃣ `/post <Link>` - By TMDB Link (e.g. `/post https://...`)\n"
        f"3️⃣ `/post <IMDb>` - By IMDb Link/ID (e.g. `/post https://imdb...`)\n\n"
        "**Other Commands:**\n"
        "`/filedl` - 🆕 Create FilesDL Style Button Post\n"
        "`/poster` - Get HD posters.\n"
        "`/setchannel` - Set main channel.\n"
        "`/manual` - Add content manually.\n"
        "`/setadlink` - Update ad link.\n\n"
        "**Auto-Post Config:**\n"
        "`/setpromochannel`, `/setpromoname`, `/setwatchlink`..."
    )

@bot.on_message(filters.command("poster") & filters.private)
async def poster_command(client, message: Message):
    if len(message.command) < 2:
        await message.reply_text("⚠️ **Usage:** `/poster <movie or series name>`")
        return

    query = message.text.split(" ", 1)[1]
    processing_msg = await message.reply_text(f"🔎 **Searching {query}...**")

    results = search_tmdb(query)
    if not results:
        await processing_msg.edit_text(f"❌ No results found for **{query}**.")
        return

    top_result = results[0]
    title = top_result.get("title") or top_result.get("name")
    year = (top_result.get("release_date") or top_result.get("first_air_date") or "----")[:4]
    
    poster_path = top_result.get("poster_path")
    backdrop_path = top_result.get("backdrop_path")

    await processing_msg.delete()

    sent_any = False
    if poster_path:
        portrait_url = f"https://image.tmdb.org/t/p/original{poster_path}"
        try:
            await client.send_photo(chat_id=message.chat.id, photo=portrait_url, caption=f"✅ **{title} ({year})**\nPortrait Poster")
            sent_any = True
        except Exception as e:
            logger.error(f"Failed to send portrait poster: {e}")

    if backdrop_path:
        landscape_url = f"https://image.tmdb.org/t/p/original{backdrop_path}"
        try:
            await client.send_photo(chat_id=message.chat.id, photo=landscape_url, caption=f"✅ **{title} ({year})**\nLandscape Poster")
            sent_any = True
        except Exception as e:
            logger.error(f"Failed to send landscape poster: {e}")

    if not sent_any:
        await message.reply_text(f"Sorry, no valid images found for **{title} ({year})**.")

@bot.on_message(filters.command("setchannel") & filters.private)
async def set_channel_command(_, message: Message):
    if len(message.command) > 1:
        channel_input = message.command[1]
        target_channel = None
        
        if channel_input.startswith('@'):
            target_channel = channel_input
        else:
            try:
                target_channel = int(channel_input)
            except ValueError:
                await message.reply_text("⚠️ Invalid ID/Username format.")
                return
        
        user_channels[message.from_user.id] = target_channel
        await message.reply_text(f"✅ Main channel set to: `{target_channel}`.")
    else:
        await message.reply_text("⚠️ **Usage:** `/setchannel <@username or ID>`")

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
    await message.reply_text("🎬 **Manual Content Entry**\n\nFirst, please send the **Title**.")

@bot.on_message(filters.command("setadlink") & filters.private)
async def set_ad_link_command(_, message: Message):
    user_id = message.from_user.id
    if len(message.command) > 1 and (message.command[1].startswith("http://") or message.command[1].startswith("https://")):
        user_ad_links[user_id] = message.command[1]
        save_user_ad_links()
        await message.reply_text(f"✅ **Ad Link Updated!**")
    else:
        await message.reply_text("⚠️ **Usage:** `/setadlink https://your-ad-link.com`")

# ---- FILEDL COMMAND HANDLERS (UPDATED TO USE LINK) ----
@bot.on_message(filters.command("filedl") & filters.private)
async def filedl_command(client, message: Message):
    user_id = message.from_user.id
    user_conversations.pop(user_id, None)
    
    user_conversations[user_id] = {
        "state": "filedl_wait_title", 
        "data": {"links": []} 
    }
    
    await message.reply_text("📂 **FilesDL Post Creator**\n\nPlease send the **Title** of the post.")

async def filedl_title_handler(client, message: Message):
    user_id = message.from_user.id
    title = message.text.strip()
    
    user_conversations[user_id]["data"]["title"] = title
    user_conversations[user_id]["state"] = "filedl_wait_btn_name"
    
    await message.reply_text(f"✅ Title: **{title}**\n\n👉 Now enter **Button 1 Name** (e.g. `Download 720p`)")

async def filedl_name_handler(client, message: Message):
    user_id = message.from_user.id
    text = message.text.strip()
    
    if text.upper() in ["DONE", "FINISH", "OK", "END", "SES"]:
        data = user_conversations[user_id]["data"]
        if not data["links"]:
            await message.reply_text("❌ No buttons added.")
            return
            
        final_html = generate_filedl_html(data["title"], data["links"])
        
        await message.reply_text("⏳ Generating online link for your code...")
        
        # Call the new robust function
        paste_link = create_paste_link(final_html)
        
        if paste_link:
            await message.reply_text(
                "✅ **Code Generated Successfully!**\n\n"
                "👇 Click below to View & Copy the code.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔗 View & Copy Code", url=paste_link)]
                ])
            )
        else:
            file_bytes = io.BytesIO(final_html.encode('utf-8'))
            file_bytes.name = "filesdl_code.html"
            await message.reply_document(document=file_bytes, caption="⚠️ Link generation failed. Here is the file.")

        user_conversations.pop(user_id, None)
        return

    user_conversations[user_id]["temp_btn_name"] = text
    user_conversations[user_id]["state"] = "filedl_wait_btn_url"
    
    await message.reply_text(f"📝 Button: **{text}**\n🔗 Now send the **URL**.")

async def filedl_url_handler(client, message: Message):
    user_id = message.from_user.id
    url = message.text.strip()
    
    if not (url.startswith("http://") or url.startswith("https://")):
        await message.reply_text("⚠️ Invalid URL. Must start with http/https.")
        return

    btn_name = user_conversations[user_id]["temp_btn_name"]
    user_conversations[user_id]["data"]["links"].append({"label": btn_name, "url": url})
    
    del user_conversations[user_id]["temp_btn_name"]
    user_conversations[user_id]["state"] = "filedl_wait_btn_name"
    
    total = len(user_conversations[user_id]["data"]["links"])
    
    await message.reply_text(f"✅ **Button Added!** (Total: {total})\n\n👉 Enter **Next Button Name** OR type **DONE**.")

# ---- CHANNEL POST CONFIGURATION COMMANDS ----
def get_user_promo_config(user_id: int):
    if user_id not in user_promo_config:
        user_promo_config[user_id] = {}
    return user_promo_config[user_id]

@bot.on_message(filters.command("setpromochannel") & filters.private)
async def set_promo_channel_command(_, message: Message):
    user_id = message.from_user.id
    if len(message.command) > 1:
        channel_input = message.command[1]
        config = get_user_promo_config(user_id)
        target_channel = None

        if channel_input.startswith('@'):
            target_channel = channel_input
        else:
            try:
                target_channel = int(channel_input)
            except ValueError:
                await message.reply_text("⚠️ Invalid format. Use @channel or ID.")
                return
        
        config["channel"] = target_channel
        save_promo_config()
        await message.reply_text(f"✅ Promo channel set to: `{config['channel']}`.")
    else:
        await message.reply_text("⚠️ **Usage:** `/setpromochannel <@username or ID>`")

@bot.on_message(filters.command("setpromoname") & filters.private)
async def set_promo_name_command(_, message: Message):
    user_id = message.from_user.id
    if len(message.command) > 1:
        name = message.text.split(" ", 1)[1]
        config = get_user_promo_config(user_id)
        config["name"] = name
        save_promo_config()
        await message.reply_text(f"✅ Auto-post brand name set to: **{name}**")
    else:
        await message.reply_text("⚠️ **Usage:** `/setpromoname Your Website Name`")

@bot.on_message(filters.command("setwatchlink") & filters.private)
async def set_watch_link_command(_, message: Message):
    user_id = message.from_user.id
    if len(message.command) > 1 and message.command[1].startswith("https://"):
        config = get_user_promo_config(user_id)
        config["watch_link"] = message.command[1]
        save_promo_config()
        await message.reply_text(f"✅ 'Watch on Website' link updated.")
    else:
        await message.reply_text("⚠️ **Usage:** `/setwatchlink https://your-link.com`")

@bot.on_message(filters.command("setdownloadlink") & filters.private)
async def set_download_link_command(_, message: Message):
    user_id = message.from_user.id
    if len(message.command) > 1 and message.command[1].startswith("https://"):
        config = get_user_promo_config(user_id)
        config["download_link"] = message.command[1]
        save_promo_config()
        await message.reply_text(f"✅ 'How to Download?' link updated.")
    else:
        await message.reply_text("⚠️ **Usage:** `/setdownloadlink https://your-link.com`")

@bot.on_message(filters.command("setrequestlink") & filters.private)
async def set_request_link_command(_, message: Message):
    user_id = message.from_user.id
    if len(message.command) > 1 and message.command[1].startswith("https://"):
        config = get_user_promo_config(user_id)
        config["request_link"] = message.command[1]
        save_promo_config()
        await message.reply_text(f"✅ 'Request any Movie' link updated.")
    else:
        await message.reply_text("⚠️ **Usage:** `/setrequestlink https://your-link.com`")

# ---- INLINE & DETAILS HANDLERS ----
@bot.on_inline_query()
async def inline_query_handler(client, query: InlineQuery):
    search_query = query.query.strip()
    if not search_query:
        await query.answer(results=[], switch_pm_text="Type a movie/series name...", switch_pm_parameter="start", cache_time=0)
        return

    results = search_tmdb(search_query)
    inline_results = []
    for r in results:
        title = r.get('title') or r.get('name')
        year = (r.get('release_date') or r.get('first_air_date') or '----').split('-')[0]
        media_type_icon = '🎬' if r.get('media_type') == 'movie' else '📺'
        description = f"{media_type_icon} {r.get('media_type', '').title()} | {year}"
        command_to_send = f"/details {r['media_type']}_{r['id']}"
        poster_url = f"https://image.tmdb.org/t/p/w200{r.get('poster_path')}" if r.get('poster_path') else "https://via.placeholder.com/200x300.png?text=No+Poster"

        inline_results.append(
            InlineQueryResultArticle(title=f"{title} ({year})", description=description, thumb_url=poster_url,
                                     input_message_content=InputTextMessageContent(command_to_send))
        )
    await query.answer(results=inline_results, cache_time=10)

@bot.on_message(filters.command("details") & filters.private)
async def details_command_handler(client, message: Message):
    try:
        _, data = message.text.split(" ", 1)
        media_type, media_id = data.split("_")
    except ValueError:
        return await message.reply_text("❌ Invalid selection. Please try searching again.")

    processing_msg = await message.reply_text("⏳ Fetching details...")
    details = get_tmdb_details(media_type, int(media_id))
    if not details:
        return await processing_msg.edit_text("❌ Failed to get details. Please try again.")

    user_id = message.from_user.id
    user_conversations[user_id] = {"details": details, "links": [], "state": "wait_custom_language"}
    await processing_msg.edit_text("✅ Details fetched!\n\n**🗣️ Please enter the language** (e.g., `Hindi Dubbed`).")

# ---- NEW: /post COMMAND HANDLER ----
@bot.on_message(filters.command("post") & filters.private)
async def post_command_handler(client, message: Message):
    if len(message.command) < 2:
        await message.reply_text(
            "⚠️ **Usage:**\n"
            "1️⃣ `/post https://www.themoviedb.org/movie/550` (Link)\n"
            "2️⃣ `/post https://imdb.com/title/tt0137523` (Link)\n"
            "3️⃣ `/post Inception` (Name Search)"
        )
        return

    query = message.text.split(" ", 1)[1].strip()
    processing_msg = await message.reply_text(f"🔎 **Processing:** `{query}`...")

    media_type, media_id = extract_tmdb_id(query)

    if media_type and media_id:
        details = get_tmdb_details(media_type, media_id)
        if details:
            user_id = message.from_user.id
            user_conversations[user_id] = {
                "details": details, 
                "links": [], 
                "state": "wait_custom_language"
            }
            await processing_msg.edit_text(
                f"✅ **Found:** {details.get('title') or details.get('name')}\n"
                "**🗣️ Please enter the Language** (e.g., `English`, `Hindi`)."
            )
        else:
            await processing_msg.edit_text("❌ Failed to fetch details from TMDB.")
        return

    results = search_tmdb(query)
    if not results:
        await processing_msg.edit_text(f"❌ No results found for **{query}**.")
        return

    buttons = []
    for r in results:
        title = r.get("title") or r.get("name")
        year = (r.get("release_date") or r.get("first_air_date") or "----")[:4]
        m_type = r.get("media_type")
        m_id = r.get("id")
        buttons.append([InlineKeyboardButton(f"{title} ({year}) [{m_type.upper()}]", callback_data=f"sel_{m_type}_{m_id}")])
    
    await processing_msg.edit_text("👇 **Select your content:**", reply_markup=InlineKeyboardMarkup(buttons))

@bot.on_callback_query(filters.regex("^sel_"))
async def selection_callback(client, cb):
    try:
        _, media_type, media_id = cb.data.split("_")
        
        await cb.message.edit_text("⏳ Fetching details...")
        details = get_tmdb_details(media_type, int(media_id))
        
        if not details:
            await cb.message.edit_text("❌ Error fetching details.")
            return

        user_id = cb.from_user.id
        user_conversations[user_id] = {
            "details": details, 
            "links": [], 
            "state": "wait_custom_language"
        }
        
        await cb.message.edit_text(
            f"✅ **Selected:** {details.get('title') or details.get('name')}\n\n"
            "**🗣️ Please enter the Language** (e.g., `Hindi Dubbed`)."
        )
    except Exception as e:
        logger.error(f"Selection error: {e}")
        await cb.answer("Error occurred.", show_alert=True)

# ---- CONVERSATION HANDLERS (MAIN ROUTER) ----
@bot.on_message(
    filters.text & 
    filters.private & 
    ~filters.command([
        "start", "poster", "setchannel", "cancel", "manual", "setadlink", "details", "filedl", "post",
        "setpromochannel", "setpromoname", "setwatchlink", "setdownloadlink", "setrequestlink"
    ])
)
async def conversation_text_handler(client, message: Message):
    user_id = message.from_user.id
    if convo := user_conversations.get(user_id):
        state = convo.get("state")
        
        if state == "filedl_wait_title":
            await filedl_title_handler(client, message)
            return
        elif state == "filedl_wait_btn_name":
            await filedl_name_handler(client, message)
            return
        elif state == "filedl_wait_btn_url":
            await filedl_url_handler(client, message)
            return

        if state and state != "done":
            handlers = {
                "manual_wait_title": manual_conversation_handler, "manual_wait_year": manual_conversation_handler,
                "manual_wait_overview": manual_conversation_handler, "manual_wait_genres": manual_conversation_handler,
                "manual_wait_rating": manual_conversation_handler, "manual_wait_poster_url": manual_conversation_handler,
                "wait_custom_language": language_conversation_handler,
                "wait_quality": quality_conversation_handler,
                "wait_link_label": link_conversation_handler, "wait_link_url": link_conversation_handler
            }
            if handler := handlers.get(state):
                await handler(client, message)
            else:
                await message.reply_text("I'm waiting for a specific input. Use /cancel to restart.")
    else:
        await message.reply_text("Please use `/post Movie Name` or `/post URL` to start.")

@bot.on_callback_query(filters.regex("^addlink_"))
async def add_link_callback(client, cb):
    action, user_id_str = cb.data.rsplit("_", 1)
    user_id = int(user_id_str)
    if cb.from_user.id != user_id: return await cb.answer("This is not for you!", show_alert=True)
    if not (convo := user_conversations.get(user_id)): return await cb.answer("Session expired.", show_alert=True)
    
    if action == "addlink_yes":
        convo["state"] = "wait_link_label"
        await cb.message.edit_text("**🔗 Step 1/2: Link Label**\n\nExample: `Download 720p`")
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
            return await message.reply_text("⚠️ Invalid URL.")
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
    convo["state"] = "wait_quality"
    await message.reply_text(f"✅ Language set to: **{message.text.strip()}**\n\n**💿 Now, please enter the Quality.**\nExample: `1080p | 720p WEB-DL`")

async def quality_conversation_handler(_, message: Message):
    user_id = message.from_user.id
    convo = user_conversations[user_id]
    convo["details"]["custom_quality"] = message.text.strip()
    convo["state"] = "ask_links"
    buttons = [[InlineKeyboardButton("✅ Yes, add links", callback_data=f"addlink_yes_{user_id}")], 
               [InlineKeyboardButton("❌ No, skip", callback_data=f"addlink_no_{user_id}")]]
    await message.reply_text(f"✅ Quality set.\n\n**🔗 Add Download Links for Blogger?**", reply_markup=InlineKeyboardMarkup(buttons))

async def manual_conversation_handler(_, message: Message):
    user_id = message.from_user.id
    convo = user_conversations[user_id]
    text = message.text.strip()
    state = convo.get("state")
    if state == "manual_wait_title":
        convo["details"]["title"] = text
        convo["state"] = "manual_wait_year"
        await message.reply_text("✅ Title set. Now send the 4-digit **Year**.")
    elif state == "manual_wait_year":
        if text.isdigit() and len(text) == 4:
            convo["details"]["release_date"] = f"{text}-01-01"
            convo["state"] = "manual_wait_overview"
            await message.reply_text("✅ Year set. Now send the **Plot/Overview**.")
        else: await message.reply_text("⚠️ Invalid year.")
    elif state == "manual_wait_overview":
        convo["details"]["overview"] = text
        convo["state"] = "manual_wait_genres"
        await message.reply_text("✅ Plot set. Send **Genres**, comma-separated.")
    elif state == "manual_wait_genres":
        convo["details"]["genres"] = [{"name": g.strip()} for g in text.split(",")]
        convo["state"] = "manual_wait_rating"
        await message.reply_text("✅ Genres set. What's the **Rating**? (e.g., `8.5`).")
    elif state == "manual_wait_rating":
        try:
            convo["details"]["vote_average"] = 0.0 if text.upper() == "N/A" else round(float(text), 1)
            convo["state"] = "manual_wait_poster_url"
            await message.reply_text("✅ Rating set. Send the **Poster Image URL**.")
        except ValueError: await message.reply_text("⚠️ Invalid rating.")
    elif state == "manual_wait_poster_url":
        if text.startswith("http://") or text.startswith("https://"):
            convo["details"]["manual_poster_url"] = text
            convo["state"] = "wait_custom_language"
            await message.reply_text(f"✅ Poster URL set! Now, enter the language.")
        else: await message.reply_text("⚠️ Invalid URL.")

# ---- AUTOMATED CHANNEL POST FUNCTION ----
async def send_channel_post(client, user_id: int, confirmation_chat_id: int):
    convo = user_conversations.get(user_id)
    promo_config = user_promo_config.get(user_id)
    
    if not promo_config or not promo_config.get("channel"):
        logger.warning(f"User {user_id} has no promo channel. Skipping auto-post.")
        await client.send_message(confirmation_chat_id, "⚠️ **Auto-Post Skipped:** No channel configured. Use `/setpromochannel`.")
        return

    if not all(k in promo_config for k in ["name", "watch_link", "download_link", "request_link"]):
        await client.send_message(confirmation_chat_id, "❌ **Auto-Post Failed:** Config incomplete.")
        return
        
    details = convo["details"]
    title = details.get("title") or details.get("name") or "N/A"
    year = (details.get("release_date") or details.get("first_air_date") or "----")[:4]
    language = details.get('custom_language', 'N/A')
    quality = details.get('custom_quality', 'N/A')
    rating = f"⭐ {details.get('vote_average', 0):.1f}/10"
    
    runtime_str = "N/A"
    if runtime_minutes := details.get("runtime"):
        hours = runtime_minutes // 60
        minutes = runtime_minutes % 60
        runtime_str = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"

    photo_to_send = None
    if details.get("manual_poster_url"):
        photo_to_send = details["manual_poster_url"]
    elif details.get("poster_path"):
        photo_to_send = f"https://image.tmdb.org/t/p/original{details['poster_path']}"
    else:
        photo_to_send = convo.get("generated", {}).get("image")
        if photo_to_send:
            photo_to_send.seek(0)

    caption = (
        f"🎬 **{title} ({year})**\n\n"
        f"**🎭 Genres:** {', '.join([g['name'] for g in details.get('genres', [])] or ['N/A'])}\n"
        f"**🗣️ Language:** {language}\n"
        f"**💿 Quality:** {quality}\n"
        f"**⏳ Runtime:** {runtime_str}\n"
        f"**⭐ Rating:** {rating}\n"
        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        f"👇 Click Below to Watch or Download on {promo_config['name']}! 👇"
    )

    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Watch on Website", url=promo_config["watch_link"])],
        [InlineKeyboardButton("🤔 How to Download?", url=promo_config["download_link"])],
        [InlineKeyboardButton("✅ ReQuest any Movie ✅", url=promo_config["request_link"])]
    ])

    try:
        channel_id = promo_config["channel"]
        if photo_to_send:
            await client.send_photo(channel_id, photo=photo_to_send, caption=caption, reply_markup=buttons)
        else:
            await client.send_message(channel_id, text=caption, reply_markup=buttons)
        await client.send_message(confirmation_chat_id, f"✅ Auto-post sent to `{channel_id}`!")
    except Exception as e:
        logger.error(f"Failed to send auto-post to {promo_config.get('channel')}: {e}")
        await client.send_message(confirmation_chat_id, f"❌ Failed to send auto-post. **Error:** `{e}`")


# ---- FINAL CONTENT GENERATION (UPDATED FOR DPASTE) ----
async def generate_final_content(client, user_id, msg_to_edit: Message):
    if not (convo := user_conversations.get(user_id)): return
    
    await msg_to_edit.edit_text("⏳ Generating main post for you...")
    caption = generate_formatted_caption(convo["details"])
    html_code = generate_html(convo["details"], convo["links"], user_id)
    
    await msg_to_edit.edit_text("🎨 Generating image...")
    image_file = generate_image(convo["details"])
    
    convo["generated"] = {"caption": caption, "html": html_code, "image": image_file}
    convo["state"] = "done"
    
    buttons = [
        [InlineKeyboardButton("📝 Get Blogger Code (Link)", callback_data=f"get_html_{user_id}")],
        [InlineKeyboardButton("📄 Copy Caption", callback_data=f"get_caption_{user_id}")]
    ]
    if user_id in user_channels:
        buttons.append([InlineKeyboardButton("📢 Post to Main Channel", callback_data=f"post_channel_{user_id}")])

    await msg_to_edit.delete()
    if image_file:
        image_copy_for_channel = io.BytesIO(image_file.getvalue())
        convo["generated"]["image"] = image_copy_for_channel
        
        image_file.seek(0)
        await client.send_photo(msg_to_edit.chat.id, photo=image_file, caption=caption, reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await client.send_message(msg_to_edit.chat.id, "⚠️ **Image could not be generated.**\n\n" + caption, reply_markup=InlineKeyboardMarkup(buttons))
        
    await client.send_message(msg_to_edit.chat.id, "⏳ Sending automatic post to channel...")
    await send_channel_post(client, user_id, msg_to_edit.chat.id)

@bot.on_callback_query(filters.regex("^(get_|post_)"))
async def final_action_callback(client, cb):
    try:
        action, user_id_str = cb.data.rsplit("_", 1)
        user_id = int(user_id_str)
    except (ValueError, IndexError): return await cb.answer("Error.", show_alert=True)
    
    if cb.from_user.id != user_id: return await cb.answer("This is not for you!", show_alert=True)
    if not (convo := user_conversations.get(user_id)) or "generated" not in convo:
        return await cb.answer("Session expired. Please start over.", show_alert=True)
    
    generated = convo["generated"]
    
    if action == "get_html":
        await cb.answer("🔗 Creating link (Spacebin/Hastebin)...", show_alert=False)
        html_code = generated.get("html", "")
        
        # Call the ROBUST paste function
        paste_link = create_paste_link(html_code)
        
        if paste_link:
            await cb.message.reply_text(
                "✅ **Blogger Code Ready!**\n\n"
                "👇 Click below to View & Copy the code.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔗 View & Copy Code", url=paste_link)]
                ])
            )
        else:
            await cb.message.reply_text("⚠️ **All Link Services Failed!** Sending file instead.")
            file_bytes = io.BytesIO(html_code.encode('utf-8'))
            file_bytes.name = f"{(convo['details'].get('title') or 'post').replace(' ', '_')}.html"
            await client.send_document(cb.message.chat.id, document=file_bytes)
            
    elif action == "get_caption":
        await cb.answer()
        await client.send_message(cb.message.chat.id, generated["caption"])
    elif action == "post_channel":
        if not (channel_id := user_channels.get(user_id)):
            return await cb.answer("Main channel not set.", show_alert=True)
        await cb.answer("🚀 Posting to main channel...", show_alert=False)
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
    logger.info("🚀 Starting the bot...")
    load_user_ad_links()
    load_promo_config()
    flask_thread = Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    bot.run()
    logger.info("👋 Bot has stopped.")

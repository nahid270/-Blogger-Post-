import os
import io
import sys
import re
import requests
from threading import Thread

# --- Third-party library imports ---
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
    print("❌ ERROR: One or more environment variables are missing. Check your .env file.")
    sys.exit(1)

API_ID = int(API_ID)

# ---- GLOBAL VARIABLES for state management ----
# These dictionaries will store user-specific data in memory.
user_conversations = {} # To handle download link conversation
user_channels = {}      # To store user's target channel {user_id: channel_id}

# ---- FLASK APP FOR KEEP-ALIVE (for hosting platforms like Render/Heroku) ----
app = Flask(__name__)
@app.route('/')
def home():
    return "✅ Advanced Movie Bot is up and running!"

def run_flask():
    app.run(host='0.0.0.0', port=8080)

flask_thread = Thread(target=run_flask)
flask_thread.start()

# ---- PYROGRAM BOT INITIALIZATION ----
bot = Client("moviebot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ---- FONT CONFIGURATION for Image Generation ----
try:
    FONT_BOLD = ImageFont.truetype("Poppins-Bold.ttf", 32)
    FONT_REGULAR = ImageFont.truetype("Poppins-Regular.ttf", 24)
    FONT_SMALL = ImageFont.truetype("Poppins-Regular.ttf", 18)
except IOError:
    print("⚠️ Warning: Font files (Poppins-Bold.ttf, Poppins-Regular.ttf) not found. Image generation will use default fonts.")
    FONT_BOLD = FONT_REGULAR = FONT_SMALL = ImageFont.load_default()

# ---- TMDB API FUNCTIONS (UPGRADED) ----
def search_tmdb(query: str):
    """Searches TMDB for movies and TV shows and returns top 5 results."""
    year = None
    # Extract year from query if present (e.g., "Inception 2010")
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
        
        response = requests.get(search_url)
        response.raise_for_status()
        results = response.json().get("results", [])
        
        # Filter out persons and return top 5 valid results (movie or tv)
        valid_results = [r for r in results if r.get("media_type") in ["movie", "tv"]]
        return valid_results[:5]
    except requests.exceptions.RequestException as e:
        print(f"Error searching TMDB: {e}")
        return []

def get_tmdb_details(media_type: str, media_id: int):
    """Fetches detailed information including credits (cast/crew) and videos (trailers)."""
    try:
        details_url = f"https://api.themoviedb.org/3/{media_type}/{media_id}?api_key={TMDB_API_KEY}&append_to_response=credits,videos"
        response = requests.get(details_url)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching details from TMDB: {e}")
        return None

# ---- CONTENT GENERATION FUNCTIONS (UPGRADED) ----
def generate_formatted_caption(data: dict, media_type: str):
    """Generates a rich, formatted text caption for Telegram."""
    title = data.get("title") or data.get("name")
    year = (data.get("release_date") or data.get("first_air_date") or "----")[:4]
    rating = f"⭐ {round(data.get('vote_average', 0), 1)}/10"
    genres = ", ".join([g["name"] for g in data.get("genres", [])])
    overview = data.get("overview", "N/A")
    
    # Get Director from credits
    director = "N/A"
    for member in data.get("credits", {}).get("crew", []):
        if member.get("job") == "Director":
            director = member["name"]
            break
            
    # Get top 5 Cast members
    cast = ", ".join([actor["name"] for actor in data.get("credits", {}).get("cast", [])[:5]])

    caption = (
        f"🎬 **{title} ({year})**\n\n"
        f"**Rating:** {rating}\n"
        f"**Genres:** {genres}\n"
        f"**Director:** {director}\n"
        f"**Cast:** {cast}\n\n"
        f"**Plot:** _{overview[:500]}{'...' if len(overview) > 500 else ''}_"
    )
    return caption

def generate_html(data: dict, media_type: str, links: dict):
    """Generates a styled HTML snippet with provided download links."""
    title = data.get("title") or data.get("name")
    year = (data.get("release_date") or data.get("first_air_date") or "----")[:4]
    rating = round(data.get("vote_average", 0), 1)
    overview = data.get("overview", "")
    genres = ", ".join([g["name"] for g in data.get("genres", [])])
    poster_path = data.get('poster_path')
    backdrop_path = data.get('backdrop_path')
    poster = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else "https://via.placeholder.com/400x600.png?text=No+Poster"
    backdrop = f"https://image.tmdb.org/t/p/original{backdrop_path}" if backdrop_path else "https://via.placeholder.com/1280x720.png?text=No+Backdrop"
    
    # Find the first YouTube Trailer
    trailer_key = next((v['key'] for v in data.get('videos', {}).get('results', []) if v['site'] == 'YouTube' and v['type'] == 'Trailer'), None)
    trailer_button = f'<a href="https://www.youtube.com/watch?v={trailer_key}" class="trailer-button">🎬 Watch Trailer</a>' if trailer_key else ""
    
    buttons_html = ""
    if links.get("480p"): buttons_html += f'<a href="{links["480p"]}">🔽 Download 480p</a>\n'
    if links.get("720p"): buttons_html += f'<a href="{links["720p"]}">🎥 Download 720p</a>\n'
    if links.get("1080p"): buttons_html += f'<a href="{links["1080p"]}">💎 Download 1080p</a>\n'

    html_content = f"""
    <!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><title>{title} Post</title><style>body{{background-color:#1a1a1a;color:#e0e0e0;font-family:sans-serif;}}.movie-card{{max-width:700px;margin:20px auto;background:#1c1c1c;border-radius:20px;padding:20px;box-shadow:0 8px 25px rgba(0,0,0,0.5);}}.poster{{width:200px;border-radius:15px;float:left;margin-right:20px;}}.movie-card h2{{color:#00bcd4;}}b{{color:#00e676;}}.backdrop-image{{width:100%;border-radius:15px;margin-top:20px;}}.download-buttons,.trailer-section{{text-align:center;margin-top:20px;clear:both;}}.download-buttons a,.trailer-button{{display:inline-block;background:linear-gradient(45deg,#ff512f,#dd2476);color:white;padding:12px 25px;margin:8px;border-radius:25px;text-decoration:none;font-weight:600;}}.trailer-button{{background:#c4302b;}}</style></head><body><div class="movie-card"><h2>{title} ({year})</h2><img class="poster" src="{poster}" alt="{title} Poster"/><p><b>Genre:</b> {genres}</p><p><b>Rating:</b> ⭐ {rating}/10</p><p><b>Overview:</b> {overview}</p><div class="trailer-section">{trailer_button}</div><img class="backdrop-image" src="{backdrop}" alt="{title} Backdrop"/><div class="download-buttons">{buttons_html if buttons_html else '<!-- Download links not provided -->'}</div></div></body></html>
    """
    return html_content

def generate_image(data: dict):
    """Generates a custom promotional image using Pillow."""
    try:
        poster_path = data.get("poster_path")
        if not poster_path: return None
        
        poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}"
        poster_img = Image.open(io.BytesIO(requests.get(poster_url).content)).convert("RGBA").resize((400, 600))

        backdrop_path = data.get("backdrop_path")
        if backdrop_path:
            backdrop_url = f"https://image.tmdb.org/t/p/w1280{backdrop_path}"
            bg_img = Image.open(io.BytesIO(requests.get(backdrop_url).content)).convert("RGBA").resize((1280, 720))
            bg_img = bg_img.filter(ImageFilter.GaussianBlur(5))
            darken_layer = Image.new('RGBA', bg_img.size, (0, 0, 0, 150))
            bg_img = Image.alpha_composite(bg_img, darken_layer)
        else:
            bg_img = Image.new('RGBA', (1280, 720), (10, 10, 20))
            
        bg_img.paste(poster_img, (50, 60), poster_img)

        draw = ImageDraw.Draw(bg_img)
        title = data.get("title") or data.get("name")
        year = (data.get("release_date") or data.get("first_air_date") or "----")[:4]
        
        draw.text((480, 80), f"{title} ({year})", font=FONT_BOLD, fill="white")
        rating = f"⭐ {round(data.get('vote_average', 0), 1)}/10"
        draw.text((480, 140), rating, font=FONT_REGULAR, fill="#00e676")
        genres = " | ".join([g["name"] for g in data.get("genres", [])])
        draw.text((480, 180), genres, font=FONT_SMALL, fill="#00bcd4")
        
        overview = data.get("overview", "")
        lines = [overview[i:i+80] for i in range(0, len(overview), 80)]
        y_text = 250
        for line in lines[:7]:
            draw.text((480, y_text), line, font=FONT_REGULAR, fill="#E0E0E0")
            y_text += 30

        img_buffer = io.BytesIO()
        bg_img.save(img_buffer, format="PNG")
        img_buffer.name = "poster.png"
        img_buffer.seek(0)
        return img_buffer
    except Exception as e:
        print(f"Error generating image: {e}")
        return None

# ---- BOT HANDLERS ----
@bot.on_message(filters.command("start") & filters.private)
async def start_command(_, message: Message):
    await message.reply_text(
        "👋 **Welcome to the Advanced Movie & Series Bot!**\n\n"
        "Send me a movie/series name to get started. I can create:\n"
        "✅ An HTML post file.\n"
        "✅ A formatted text caption.\n"
        "✅ A custom image poster.\n\n"
        "**Available Commands:**\n"
        "`/setchannel @username` - Set a channel for direct posting.\n"
        "`/cancel` - Cancel the current operation."
    )

@bot.on_message(filters.command("setchannel") & filters.private)
async def set_channel_command(_, message: Message):
    if len(message.command) > 1:
        channel = message.command[1]
        user_channels[message.from_user.id] = channel
        await message.reply_text(f"✅ Channel set to `{channel}`.")
    else:
        await message.reply_text("Usage: `/setchannel @yourchannel` or `/setchannel -100123456789`")

@bot.on_message(filters.command("cancel") & filters.private)
async def cancel_command(_, message: Message):
    user_id = message.from_user.id
    if user_id in user_conversations:
        del user_conversations[user_id]
        await message.reply_text("✅ Operation cancelled.")
    else:
        await message.reply_text("Nothing to cancel.")

@bot.on_message(filters.text & filters.private & ~filters.command(["start", "setchannel", "cancel"]))
async def text_handler(client, message: Message):
    user_id = message.from_user.id
    if user_id in user_conversations and user_conversations[user_id].get("state") != "done":
        await link_conversation_handler(client, message)
        return

    query = message.text.strip()
    if not query: return

    processing_msg = await message.reply_text("🔍 Searching for content...")
    results = search_tmdb(query)

    if not results:
        await processing_msg.edit_text("❌ No content found. Please check spelling or include the year.")
        return

    buttons = []
    for r in results:
        media_type = r['media_type']
        title = r.get('title') or r.get('name')
        date = r.get('release_date') or r.get('first_air_date') or ""
        year = f"({date.split('-')[0]})" if date else ""
        icon = "🎬" if media_type == 'movie' else "📺"
        buttons.append([InlineKeyboardButton(f"{icon} {title} {year}", callback_data=f"select_{media_type}_{r['id']}")])
    
    await processing_msg.edit_text(
        "**👇 Please choose one from the search results:**",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

@bot.on_callback_query(filters.regex("^select_"))
async def selection_callback(_, callback_query):
    await callback_query.answer("Fetching details...")
    _, media_type, media_id = callback_query.data.split("_")
    
    details = get_tmdb_details(media_type, int(media_id))
    if not details:
        await callback_query.message.edit_text("❌ Failed to get details. Please try again.")
        return

    user_id = callback_query.from_user.id
    user_conversations[user_id] = {"state": "wait_480p", "details": details, "media_type": media_type, "links": {}}

    await callback_query.message.delete()
    await bot.send_message(
        chat_id=callback_query.message.chat.id,
        text="🔗 **Step 1/3: Add Download Links**\n\nPlease send the download link for **480p** quality.\n\n"
             "Type `skip` to omit this. Use /cancel to stop.",
        disable_web_page_preview=True
    )

async def link_conversation_handler(client, message: Message):
    user_id = message.from_user.id
    convo = user_conversations.get(user_id)
    if not convo: return

    text, state = message.text.strip(), convo["state"]

    if text.lower() != 'skip' and not (text.startswith("http://") or text.startswith("https://")):
        await message.reply_text("⚠️ Invalid URL. Please send a valid link or type `skip`.")
        return
        
    if state == "wait_480p":
        if text.lower() != 'skip': convo["links"]["480p"] = text
        convo["state"] = "wait_720p"
        await message.reply_text("🔗 **Step 2/3: 720p Link**\n\nSend the link for **720p** or type `skip`.")
    elif state == "wait_720p":
        if text.lower() != 'skip': convo["links"]["720p"] = text
        convo["state"] = "wait_1080p"
        await message.reply_text("🔗 **Step 3/3: 1080p Link**\n\nSend the link for **1080p** or type `skip`.")
    elif state == "wait_1080p":
        if text.lower() != 'skip': convo["links"]["1080p"] = text
        processing_msg = await message.reply_text("✅ Links collected! Generating your content now...", quote=True)
        await generate_final_content(client, user_id, message.chat.id, processing_msg)

async def generate_final_content(client, user_id, chat_id, processing_msg):
    convo = user_conversations.get(user_id)
    if not convo: return

    await processing_msg.edit_text("📝 Generating caption...")
    caption = generate_formatted_caption(convo["details"], convo["media_type"])
    
    await processing_msg.edit_text("📄 Generating HTML...")
    html_code = generate_html(convo["details"], convo["media_type"], convo["links"])
    
    await processing_msg.edit_text("🎨 Generating image...")
    image_file = generate_image(convo["details"])

    user_conversations[user_id]["generated"] = {"caption": caption, "html": html_code, "image": image_file}

    buttons = [[InlineKeyboardButton("📝 Get HTML Code", callback_data=f"get_html_{user_id}")],
               [InlineKeyboardButton("📄 Copy Text Caption", callback_data=f"get_caption_{user_id}")]]
    if user_id in user_channels:
        buttons.append([InlineKeyboardButton("📢 Post to Channel", callback_data=f"post_channel_{user_id}")])

    await processing_msg.delete()
    if image_file:
        await client.send_photo(chat_id, photo=image_file, caption=caption, reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await client.send_message(chat_id, text=caption, reply_markup=InlineKeyboardMarkup(buttons))
    
    user_conversations[user_id]["state"] = "done"

@bot.on_callback_query(filters.regex("^(get_|post_)"))
async def final_action_callback(client, callback_query):
    # Fixed the bug by using rsplit to correctly parse the callback data
    try:
        action, user_id_str = callback_query.data.rsplit("_", 1)
        user_id = int(user_id_str)
    except (ValueError, IndexError):
        await callback_query.answer("Error: Invalid callback data.", show_alert=True)
        print(f"Could not parse callback_data: {callback_query.data}")
        return
    
    if callback_query.from_user.id != user_id:
        await callback_query.answer("This button is not for you!", show_alert=True)
        return

    convo = user_conversations.get(user_id)
    if not convo or "generated" not in convo:
        await callback_query.answer("Session expired. Please start over.", show_alert=True)
        return
    
    generated = convo["generated"]
    
    if action == "get_html":
        await callback_query.answer()
        html_code = generated["html"]
        title = (convo["details"].get("title") or convo["details"].get("name") or "post").replace(" ", "_")
        if len(html_code) > 4000:
            html_file = io.BytesIO(html_code.encode('utf-8'))
            html_file.name = f"{title}.html"
            await client.send_document(callback_query.message.chat.id, document=html_file, caption="Here is your HTML file.")
        else:
            await client.send_message(callback_query.message.chat.id, f"```html\n{html_code}\n```", parse_mode=enums.ParseMode.MARKDOWN)

    elif action == "get_caption":
        await callback_query.answer()
        await client.send_message(callback_query.message.chat.id, generated["caption"])
        
    elif action == "post_channel":
        channel_id = user_channels.get(user_id)
        if not channel_id:
            await callback_query.answer("Channel not set. Use /setchannel first.", show_alert=True)
            return
        
        await callback_query.answer("Posting to channel...", show_alert=False)
        try:
            image_file = generated.get("image")
            if image_file:
                image_file.seek(0)
                await client.send_photo(channel_id, photo=image_file, caption=generated["caption"])
            else:
                await client.send_message(channel_id, generated["caption"])
            
            await callback_query.edit_message_reply_markup(reply_markup=None)
            await client.send_message(callback_query.message.chat.id, f"✅ Successfully posted to `{channel_id}`!")
        except Exception as e:
            await client.send_message(callback_query.message.chat.id, f"❌ Failed to post. Error: {e}")
            print(f"Error posting to channel {channel_id}: {e}")

# ---- START THE BOT ----
if __name__ == "__main__":
    print("🚀 Bot is starting...")
    bot.run()
    print("👋 Bot has stopped.")

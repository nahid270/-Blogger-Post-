import os
import io
import sys
import re
import requests
from threading import Thread

# --- New Imports for Advanced Features ---
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from flask import Flask
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ---- CONFIGURATION ----
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
TMDB_API_KEY = os.getenv("TMDB_API_KEY")

# --- Essential variable check ---
if not all([BOT_TOKEN, API_ID, API_HASH, TMDB_API_KEY]):
    print("❌ ERROR: One or more environment variables are missing.")
    sys.exit(1)

API_ID = int(API_ID)

# ---- GLOBAL VARIABLES for state management ----
user_conversations = {} # To handle download link conversation
user_channels = {} # To store user's target channel {user_id: channel_id}

# ---- FLASK APP FOR KEEP-ALIVE ----
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
    print("⚠️ Warning: Font files (Poppins-Bold.ttf, Poppins-Regular.ttf) not found. Image generation will fail.")
    FONT_BOLD = FONT_REGULAR = FONT_SMALL = ImageFont.load_default()

# ---- TMDB API FUNCTIONS (UPGRADED) ----
def search_tmdb(query: str):
    """Searches TMDB for movies and TV shows and returns top 5 results."""
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
        
        response = requests.get(search_url)
        response.raise_for_status()
        results = response.json().get("results", [])
        
        # Filter out persons and return top 5 valid results
        valid_results = [r for r in results if r.get("media_type") in ["movie", "tv"]]
        return valid_results[:5]
    except requests.exceptions.RequestException as e:
        print(f"Error searching TMDB: {e}")
        return []

def get_tmdb_details(media_type: str, media_id: int):
    """Fetches detailed information including credits and videos."""
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
    
    # Get Director
    director = "N/A"
    for member in data.get("credits", {}).get("crew", []):
        if member["job"] == "Director":
            director = member["name"]
            break
            
    # Get Cast
    cast = ", ".join([actor["name"] for actor in data.get("credits", {}).get("cast", [])[:5]])

    caption = (
        f"🎬 **{title} ({year})**\n\n"
        f"**Rating:** {rating}\n"
        f"**Genres:** {genres}\n"
        f"**Director:** {director}\n"
        f"**Cast:** {cast}\n\n"
        f"**Plot:** _{overview[:500]}..._"
    )
    return caption

def generate_html(data: dict, media_type: str, links: dict):
    """Generates a styled HTML snippet with download links."""
    title = data.get("title") or data.get("name")
    year = (data.get("release_date") or data.get("first_air_date") or "----")[:4]
    rating = round(data.get("vote_average", 0), 1)
    overview = data.get("overview", "")
    genres = ", ".join([g["name"] for g in data.get("genres", [])])
    poster_path = data.get('poster_path')
    backdrop_path = data.get('backdrop_path')
    poster = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else ""
    backdrop = f"https://image.tmdb.org/t/p/original{backdrop_path}" if backdrop_path else ""
    
    # Find YouTube Trailer
    trailer_key = next((v['key'] for v in data.get('videos', {}).get('results', []) if v['site'] == 'YouTube' and v['type'] == 'Trailer'), None)
    trailer_button = f'<a href="https://www.youtube.com/watch?v={trailer_key}" class="trailer-button">🎬 Watch Trailer</a>' if trailer_key else ""
    
    buttons_html = ""
    if links.get("480p"): buttons_html += f'<a href="{links["480p"]}">🔽 Download 480p</a>\n'
    if links.get("720p"): buttons_html += f'<a href="{links["720p"]}">🎥 Download 720p</a>\n'
    if links.get("1080p"): buttons_html += f'<a href="{links["1080p"]}">💎 Download 1080p</a>\n'

    html_content = f"""
    <!-- HTML content remains largely the same, but with dynamic buttons and trailer -->
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>{title} Post</title>
        <style>
            body {{ background-color: #1a1a1a; color: #e0e0e0; font-family: 'Poppins', sans-serif; }}
            .movie-card {{ max-width: 700px; margin: 20px auto; background: #1c1c1c; border-radius: 20px; padding: 20px; box-shadow: 0 8px 25px rgba(0,0,0,0.5); }}
            .poster {{ width: 200px; border-radius: 15px; float: left; margin-right: 20px; }}
            h2 {{ color: #00bcd4; }}
            b {{ color: #00e676; }}
            .backdrop-image {{ width: 100%; border-radius: 15px; margin-top: 20px; }}
            .download-buttons, .trailer-section {{ text-align: center; margin-top: 20px; clear: both; }}
            .download-buttons a, .trailer-button {{ display: inline-block; background: linear-gradient(45deg, #ff512f, #dd2476); color: white; padding: 12px 25px; margin: 8px; border-radius: 25px; text-decoration: none; font-weight: 600; }}
            .trailer-button {{ background: #1DA1F2; }}
        </style>
    </head>
    <body>
        <div class="movie-card">
            <h2>{title} ({year})</h2>
            <img class="poster" src="{poster}" alt="{title} Poster"/>
            <p><b>Genre:</b> {genres}</p>
            <p><b>Rating:</b> ⭐ {rating}/10</p>
            <p><b>Overview:</b> {overview}</p>
            <div class="trailer-section">{trailer_button}</div>
            <img class="backdrop-image" src="{backdrop}" alt="{title} Backdrop"/>
            <div class="download-buttons">{buttons_html}</div>
        </div>
    </body>
    </html>
    """
    return html_content

def generate_image(data: dict):
    """Generates a custom promotional image."""
    try:
        poster_path = data.get("poster_path")
        if not poster_path:
            return None
        
        poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}"
        poster_img_data = requests.get(poster_url).content
        poster_img = Image.open(io.BytesIO(poster_img_data)).convert("RGBA")
        poster_img = poster_img.resize((400, 600))

        # Create a background with backdrop
        backdrop_path = data.get("backdrop_path")
        if backdrop_path:
            backdrop_url = f"https://image.tmdb.org/t/p/w1280{backdrop_path}"
            backdrop_img_data = requests.get(backdrop_url).content
            bg_img = Image.open(io.BytesIO(backdrop_img_data)).convert("RGBA")
            bg_img = bg_img.resize((1280, 720))
            # Apply blur and darken
            bg_img = bg_img.filter(ImageFilter.GaussianBlur(5))
            darken_layer = Image.new('RGBA', bg_img.size, (0, 0, 0, 150))
            bg_img = Image.alpha_composite(bg_img, darken_layer)
        else:
            bg_img = Image.new('RGBA', (1280, 720), (10, 10, 20))
            
        # Paste poster onto background
        bg_img.paste(poster_img, (50, 60), poster_img)

        # Add text
        draw = ImageDraw.Draw(bg_img)
        title = data.get("title") or data.get("name")
        year = (data.get("release_date") or data.get("first_air_date") or "----")[:4]
        
        # Title
        draw.text((480, 80), f"{title} ({year})", font=FONT_BOLD, fill="white")
        # Rating
        rating = f"⭐ {round(data.get('vote_average', 0), 1)}/10"
        draw.text((480, 140), rating, font=FONT_REGULAR, fill="#00e676")
        # Genres
        genres = " | ".join([g["name"] for g in data.get("genres", [])])
        draw.text((480, 180), genres, font=FONT_SMALL, fill="#00bcd4")
        # Overview
        overview = data.get("overview", "")
        # word wrap
        lines = []
        words = overview.split()
        line = ""
        for word in words:
            if FONT_REGULAR.getlength(line + word) <= 750:
                line += word + " "
            else:
                lines.append(line)
                line = word + " "
        lines.append(line)

        y_text = 250
        for line in lines[:7]: # Limit to 7 lines
            draw.text((480, y_text), line, font=FONT_REGULAR, fill="#E0E0E0")
            y_text += 30

        # Save to buffer
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
        "Send me a movie/series name (you can include the year).\n"
        "I will generate:\n"
        "✅ An HTML post file.\n"
        "✅ A formatted text caption.\n"
        "✅ A custom image poster.\n\n"
        "Use `/setchannel @username` to set a channel for direct posting."
    )

@bot.on_message(filters.command("setchannel") & filters.private)
async def set_channel_command(_, message: Message):
    if len(message.command) > 1:
        channel = message.command[1]
        user_channels[message.from_user.id] = channel
        await message.reply_text(f"✅ Channel set to `{channel}`. I will now be able to post there.")
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

# Main handler for text messages (searches)
@bot.on_message(filters.text & filters.private & ~filters.command(["start", "setchannel", "cancel"]))
async def text_handler(client, message: Message):
    user_id = message.from_user.id
    
    # Check if user is in a conversation for links
    if user_id in user_conversations:
        await link_conversation_handler(client, message)
        return

    query = message.text.strip()
    if not query: return

    processing_msg = await message.reply_text("🔍 Searching...")
    results = search_tmdb(query)

    if not results:
        await processing_msg.edit_text("❌ No content found. Check spelling or add the year.")
        return

    buttons = []
    for r in results:
        media_type = r['media_type']
        title = r.get('title') or r.get('name')
        date = r.get('release_date') or r.get('first_air_date') or ""
        year = f"({date.split('-')[0]})" if date else ""
        icon = "🎬" if media_type == 'movie' else "📺"
        callback_data = f"select_{media_type}_{r['id']}"
        buttons.append([InlineKeyboardButton(f"{icon} {title} {year}", callback_data=callback_data)])
    
    await processing_msg.edit_text(
        "**👇 Choose one from the search results:**",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

# Handler for inline button presses
@bot.on_callback_query(filters.regex("^select_"))
async def selection_callback(client, callback_query):
    await callback_query.answer("Fetching details...")
    _, media_type, media_id = callback_query.data.split("_")
    
    details = get_tmdb_details(media_type, int(media_id))
    if not details:
        await callback_query.message.edit_text("❌ Failed to get details. Please try again.")
        return

    user_id = callback_query.from_user.id
    user_conversations[user_id] = {
        "state": "wait_480p",
        "details": details,
        "media_type": media_type,
        "links": {}
    }

    await callback_query.message.edit_text(
        "🔗 **Step 1/3: Add Download Links**\n\n"
        "Please send the download link for **480p** quality.\n\n"
        "Type `skip` to omit this quality. Use /cancel to stop.",
        disable_web_page_preview=True
    )

async def link_conversation_handler(client, message: Message):
    user_id = message.from_user.id
    convo = user_conversations.get(user_id)
    if not convo: return

    text = message.text.strip()
    state = convo["state"]

    if text.lower() != 'skip':
        # Simple URL validation
        if not (text.startswith("http://") or text.startswith("https://")):
             await message.reply_text("⚠️ Invalid URL. Please send a valid link or type `skip`.")
             return
        
    if state == "wait_480p":
        if text.lower() != 'skip': convo["links"]["480p"] = text
        convo["state"] = "wait_720p"
        await message.reply_text(
            "🔗 **Step 2/3: 720p Link**\n\nSend the link for **720p** quality or type `skip`."
        )
    elif state == "wait_720p":
        if text.lower() != 'skip': convo["links"]["720p"] = text
        convo["state"] = "wait_1080p"
        await message.reply_text(
            "🔗 **Step 3/3: 1080p Link**\n\nSend the link for **1080p** quality or type `skip`."
        )
    elif state == "wait_1080p":
        if text.lower() != 'skip': convo["links"]["1080p"] = text
        
        await message.reply_text("✅ All links collected! Generating your content now...", quote=True)
        await generate_final_content(client, user_id, message.chat.id)

async def generate_final_content(client, user_id, chat_id):
    convo = user_conversations.get(user_id)
    if not convo: return

    details = convo["details"]
    media_type = convo["media_type"]
    links = convo["links"]

    # --- Generate all content ---
    await client.send_chat_action(chat_id, enums.ChatAction.TYPING)
    caption = generate_formatted_caption(details, media_type)
    html_code = generate_html(details, media_type, links)
    
    await client.send_chat_action(chat_id, enums.ChatAction.UPLOAD_PHOTO)
    image_file = generate_image(details)

    # Store generated content for posting to channel
    user_conversations[user_id]["generated"] = {
        "caption": caption,
        "html": html_code,
        "image": image_file
    }

    # --- Send content to user ---
    buttons = [
        [InlineKeyboardButton("📝 Get HTML Code", callback_data=f"get_html_{user_id}")],
        [InlineKeyboardButton("📄 Copy Text Caption", callback_data=f"get_caption_{user_id}")]
    ]
    if user_id in user_channels:
        buttons.append([InlineKeyboardButton("📢 Post to Channel", callback_data=f"post_channel_{user_id}")])

    if image_file:
        await client.send_photo(
            chat_id,
            photo=image_file,
            caption=caption,
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    else:
        await client.send_message(
            chat_id,
            text=caption,
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    
    user_conversations[user_id]["state"] = "done"


@bot.on_callback_query(filters.regex("^(get_|post_)"))
async def final_action_callback(client, callback_query):
    action, user_id_str = callback_query.data.split("_", 1)
    user_id = int(user_id_str)
    
    if callback_query.from_user.id != user_id:
        await callback_query.answer("This is not for you!", show_alert=True)
        return

    convo = user_conversations.get(user_id)
    if not convo or "generated" not in convo:
        await callback_query.answer("Session expired or data not found. Please start over.", show_alert=True)
        return
    
    generated = convo["generated"]
    
    if action == "get_html":
        await callback_query.answer()
        html_code = generated["html"]
        if len(html_code) > 4000:
            html_file = io.BytesIO(html_code.encode('utf-8'))
            html_file.name = "post.html"
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
            if generated["image"]:
                # Rewind the buffer before sending again
                generated["image"].seek(0)
                await client.send_photo(channel_id, photo=generated["image"], caption=generated["caption"])
            else:
                await client.send_message(channel_id, generated["caption"])
            
            await callback_query.edit_message_reply_markup(reply_markup=None) # Remove buttons after posting
            await client.send_message(callback_query.message.chat.id, f"✅ Successfully posted to `{channel_id}`!")
        except Exception as e:
            await client.send_message(callback_query.message.chat.id, f"❌ Failed to post to channel. Error: {e}")
            print(f"Error posting to channel {channel_id}: {e}")

    # Clean up conversation after final action
    if user_id in user_conversations:
        del user_conversations[user_id]


# ---- START THE BOT ----
if __name__ == "__main__":
    print("🚀 Bot is starting...")
    bot.run()
    print("👋 Bot has stopped.")

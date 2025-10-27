# -*- coding: utf-8 -*-

# ---- Core Python Imports ----
import os
import io
import sys
import re
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

API_ID = int(API_ID)

# ---- GLOBAL VARIABLES for state management ----
user_conversations = {}
user_channels = {}

# ---- FLASK APP FOR KEEP-ALIVE ----
app = Flask(__name__)
@app.route('/')
def home():
    return "✅ Final Movie/Series Bot is up and running!"

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
    FONT_BADGE = ImageFont.truetype("Poppins-Bold.ttf", 20)
except IOError:
    print("⚠️ Warning: Font files not found. Image generation will use default fonts.")
    FONT_BOLD = FONT_REGULAR = FONT_SMALL = FONT_BADGE = ImageFont.load_default()

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
        if year: search_url += f"&year={year}"
        
        response = requests.get(search_url)
        response.raise_for_status()
        results = [r for r in response.json().get("results", []) if r.get("media_type") in ["movie", "tv"]]
        return results[:5]
    except requests.exceptions.RequestException as e:
        print(f"Error searching TMDB: {e}")
        return []

def get_tmdb_details(media_type: str, media_id: int):
    try:
        details_url = f"https://api.themoviedb.org/3/{media_type}/{media_id}?api_key={TMDB_API_KEY}&append_to_response=credits,videos,production_countries"
        response = requests.get(details_url)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching TMDB details: {e}")
        return None

# ---- CONTENT GENERATION FUNCTIONS ----
# <<< MODIFIED: Caption generation to prioritize custom language >>>
def generate_formatted_caption(data: dict):
    title = data.get("title") or data.get("name") or "N/A"
    year = (data.get("release_date") or data.get("first_air_date") or "----")[:4]
    rating = f"⭐ {data.get('vote_average', 'N/A')}/10"
    genres = ", ".join([g["name"] for g in data.get("genres", [])] or ["N/A"])
    overview = data.get("overview", "N/A")
    director = next((member["name"] for member in data.get("credits", {}).get("crew", []) if member.get("job") == "Director"), "N/A")
    cast = ", ".join([actor["name"] for actor in data.get("credits", {}).get("cast", [])[:5]] or ["N/A"])
    
    # Use custom language if provided, otherwise fallback
    language = data.get('custom_language', data.get('original_language', '')).title()

    caption_text = (
        f"🎬 **{title} ({year})**\n\n"
        f"**Rating:** {rating}\n"
        f"**Genres:** {genres}\n"
    )
    if language:
        caption_text += f"**Language:** {language}\n"
        
    caption_text += (
        f"**Director:** {director}\n"
        f"**Cast:** {cast}\n\n"
        f"**Plot:** _{overview[:500]}{'...' if len(overview) > 500 else ''}_"
    )
    return caption_text

# <<< MODIFIED: HTML generation to prioritize custom language and enhance styles >>>
def generate_html(data: dict, links: list):
    title = data.get("title") or data.get("name") or "N/A"
    year = (data.get("release_date") or data.get("first_air_date") or "----")[:4]
    rating = data.get('vote_average', 'N/A')
    overview = data.get("overview", "No overview available.")
    genres = ", ".join([g["name"] for g in data.get("genres", [])] or ["N/A"])
    language = data.get('custom_language', data.get('original_language', '')).title()

    if data.get("manual_poster"):
        poster_url = "https://via.placeholder.com/400x600.png?text=Manual+Poster"
    elif data.get('poster_path'):
        poster_url = f"https://image.tmdb.org/t/p/w500{data['poster_path']}"
    else:
        poster_url = "https://via.placeholder.com/400x600.png?text=No+Poster"

    backdrop_url = f"https://image.tmdb.org/t/p/original{data['backdrop_path']}" if data.get('backdrop_path') else ""

    css_styles = """
<style>
    @keyframes rgb-glow {
        0% { border-color: red; box-shadow: 0 0 10px red; } 15% { border-color: orange; box-shadow: 0 0 10px orange; } 30% { border-color: yellow; box-shadow: 0 0 10px yellow; } 45% { border-color: lime; box-shadow: 0 0 10px lime; } 60% { border-color: cyan; box-shadow: 0 0 10px cyan; } 75% { border-color: blue; box-shadow: 0 0 10px blue; } 90% { border-color: magenta; box-shadow: 0 0 10px magenta; } 100% { border-color: red; box-shadow: 0 0 10px red; }
    }
    .download-section ul { list-style: none; padding: 0; text-align: center; }
    .download-section li { margin: 10px 0; }
    .download-button { display: inline-block; padding: 12px 25px; font-size: 16px; font-weight: bold; color: white; background-color: #1a2a40; border: 2px solid; border-radius: 8px; text-decoration: none; transition: transform 0.2s; animation: rgb-glow 4s linear infinite; }
    .download-button:hover { transform: scale(1.05); }
    .poster-container { position: relative; display: inline-block; }
    .language-badge { position: absolute; top: 10px; left: 10px; background-color: #FF007F; /* Hot Pink */ color: white; padding: 5px 12px; border-radius: 5px; font-size: 14px; font-weight: bold; text-shadow: 1px 1px 2px black; border: 1px solid #fff; }
</style>
"""

    poster_html = f'<div class="poster-container"><img src="{poster_url}" alt="{title} Poster" style="max-width: 350px; height: auto; border-radius: 8px; display: block; border: 2px solid #ddd;">'
    if language:
        poster_html += f'<span class="language-badge">{language}</span>'
    poster_html += '</div>'

    movie_info_html = f"""<div class="movie-info-section"><h3>Movie Information</h3><p><strong>Full Name:</strong> {title}</p><p><strong>Release Year:</strong> {year}</p><p><strong>Genres:</strong> {genres}</p><p><strong>Rating:</strong> ⭐ {rating}/10</p>"""
    if language:
        movie_info_html += f"""<p><strong>Language:</strong> {language}</p>"""
    movie_info_html += "</div>"
    
    storyline_html = f"""<div class="storyline-section"><h3>Storyline</h3><p>{overview}</p></div>"""
    screenshots_html = ""
    if backdrop_url:
        screenshots_html = f"""<div class="screenshots-section"><h3>Screenshots</h3><p style="text-align: center;"><a href="{backdrop_url}" target="_blank" rel="noopener noreferrer"><img src="{backdrop_url}" alt="{title} Screenshot" style="max-width:100%;height:auto;border-radius:8px;display:block;margin:0 auto;"></a></p></div>"""
    
    download_buttons_html = ""
    if links:
        link_items = "".join([f'<li><a href="{link['url']}" target="_blank" rel="noopener noreferrer" class="download-button">🔽 {link["label"]}</a></li>' for link in links])
        download_buttons_html = f"""<div class="download-section"><h3>Download Links</h3><ul>{link_items}</ul></div>"""
    
    return f"""{css_styles}<!-- Generated by Movie Bot --><div class="movie-post-container" style="text-align: left;"><h2 style="text-align: center;">{title} ({year})</h2><p style="text-align: center;">{poster_html}</p>{movie_info_html}{storyline_html}{screenshots_html}{download_buttons_html}</div>"""

# <<< MODIFIED: Image generation to use custom language for the badge >>>
def generate_image(data: dict):
    try:
        if data.get("manual_poster"):
            poster_img = Image.open(data["manual_poster"]).convert("RGBA").resize((400, 600))
        elif data.get('poster_path'):
            poster_url = f"https://image.tmdb.org/t/p/w500{data['poster_path']}"
            poster_img = Image.open(io.BytesIO(requests.get(poster_url).content)).convert("RGBA").resize((400, 600))
        else:
            return None

        if data.get('backdrop_path'):
            backdrop_url = f"https://image.tmdb.org/t/p/w1280{data['backdrop_path']}"
            bg_img = Image.open(io.BytesIO(requests.get(backdrop_url).content)).convert("RGBA").resize((1280, 720))
            bg_img = bg_img.filter(ImageFilter.GaussianBlur(3))
            darken_layer = Image.new('RGBA', bg_img.size, (0, 0, 0, 128))
            bg_img = Image.alpha_composite(bg_img, darken_layer)
        else:
            bg_img = Image.new('RGBA', (1280, 720), (10, 10, 20))

        # --- Custom Language Badge Logic ---
        lang_text = data.get('custom_language', '').title()
        if lang_text:
            try:
                badge_font = ImageFont.truetype("Poppins-Bold.ttf", 18)
                # Calculate text size to make badge dynamic
                text_bbox = ImageDraw.Draw(Image.new('RGB', (1,1))).textbbox((0, 0), lang_text, font=badge_font)
                text_width, text_height = text_bbox[2] - text_bbox[0], text_bbox[3] - text_bbox[1]

                badge_size = (text_width + 20, text_height + 10) # 10px padding
                badge = Image.new('RGBA', badge_size, (255, 0, 127, 200)) # Hot Pink with transparency
                draw_badge = ImageDraw.Draw(badge)
                
                text_x, text_y = (badge_size[0] - text_width) / 2, (badge_size[1] - text_height) / 2
                draw_badge.text((text_x, text_y-2), lang_text, font=badge_font, fill="#FFFFFF")
                
                # Paste on top left corner of the poster
                poster_img.paste(badge, (10, 10), badge)
            except Exception as e: print(f"Could not add custom language badge: {e}")
        
        bg_img.paste(poster_img, (50, 60), poster_img)
        draw = ImageDraw.Draw(bg_img)
        title = data.get("title") or data.get("name") or "N/A"
        year = (data.get("release_date") or data.get("first_air_date") or "----")[:4]
        
        draw.text((480, 80), f"{title} ({year})", font=FONT_BOLD, fill="white")
        draw.text((480, 140), f"⭐ {data.get('vote_average', 'N/A')}/10", font=FONT_REGULAR, fill="#00e676")
        draw.text((480, 180), " | ".join([g["name"] for g in data.get("genres", [])]), font=FONT_SMALL, fill="#00bcd4")
        
        overview, y_text = data.get("overview", ""), 250
        lines = [overview[i:i+80] for i in range(0, len(overview), 80)]
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
    await message.reply_text(
        "👋 **Welcome to the Movie & Series Bot!**\n\n"
        "Send me a movie or series name to get started, or use the commands below.\n\n"
        "**Available Commands:**\n"
        "`/setchannel @your_channel_username` - Set the channel for posting.\n"
        "`/manual` - Add content that is not found in the database.\n"
        "`/cancel` - Cancel the current operation."
    )

# ... (setchannel and cancel commands remain the same) ...
@bot.on_message(filters.command("setchannel") & filters.private)
async def set_channel_command(_, message: Message):
    if len(message.command) > 1:
        user_channels[message.from_user.id] = message.command[1]
        await message.reply_text(f"✅ Channel successfully set to `{message.command[1]}`.")
    else:
        await message.reply_text("⚠️ **Usage:** `/setchannel @yourchannel`")

@bot.on_message(filters.command("cancel") & filters.private)
async def cancel_command(_, message: Message):
    if message.from_user.id in user_conversations:
        del user_conversations[message.from_user.id]
        await message.reply_text("✅ Operation successfully cancelled.")
    else:
        await message.reply_text("👍 Nothing to cancel.")


@bot.on_message(filters.command("manual") & filters.private)
async def manual_add_command(client, message: Message):
    user_id = message.from_user.id
    user_conversations[user_id] = {
        "state": "manual_wait_title",
        "details": {},
        "links": []
    }
    await message.reply_text(
        "🎬 **Manual Content Entry Started**\n\n"
        "First, please send me the **Title** of the movie or series."
    )

# <<< MODIFIED: Main text handler to include the new language step >>>
@bot.on_message(filters.text & filters.private & ~filters.command(["start", "setchannel", "cancel", "manual"]))
async def text_handler(client, message: Message):
    user_id = message.from_user.id
    convo = user_conversations.get(user_id)

    if convo and convo.get("state") != "done":
        state = convo.get("state", "")
        if state.startswith("manual_"):
            await manual_conversation_handler(client, message)
            return
        # <<< NEW: State to handle custom language input >>>
        elif state == "wait_custom_language":
            await language_conversation_handler(client, message)
            return
        elif state in ["wait_link_label", "wait_link_url"]:
            await link_conversation_handler(client, message)
            return

    # If no active conversation, perform a search
    processing_msg = await message.reply_text("🔍 Searching for content...")
    results = search_tmdb(message.text.strip())
    if not results:
        await processing_msg.edit_text(
            "❌ Sorry, no content found for your query.\n"
            "If you are sure it exists, try again with a more specific name (e.g., `Movie Name 2023`).\n\n"
            "Alternatively, you can add it manually using the `/manual` command."
        )
        return

    buttons = [[InlineKeyboardButton(f"{'🎬' if r['media_type'] == 'movie' else '📺'} {r.get('title') or r.get('name')} ({(r.get('release_date') or r.get('first_air_date') or '----').split('-')[0]})", callback_data=f"select_{r['media_type']}_{r['id']}")] for r in results]
    await processing_msg.edit_text("**👇 Please choose the correct one from the search results:**", reply_markup=InlineKeyboardMarkup(buttons))

# <<< MODIFIED: After getting poster in manual mode, ask for language >>>
@bot.on_message(filters.photo & filters.private)
async def photo_handler(client, message: Message):
    user_id = message.from_user.id
    convo = user_conversations.get(user_id)
    if not convo or convo.get("state") != "manual_wait_poster":
        return

    await message.reply_text("🖼️ Poster received, processing...")
    photo_file = await client.download_media(message.photo.file_id, in_memory=True)
    convo["details"]["manual_poster"] = photo_file
    
    # <<< NEW: Transition to wait for language input >>>
    convo["state"] = "wait_custom_language"
    await message.reply_text(
        "✅ All manual data collected successfully!\n\n"
        "**🗣️ Now, please enter the language for this post** (e.g., `Bengali Dubbed`, `Hindi`, `Dual Audio`)."
    )

# <<< MODIFIED: After selecting from TMDB, ask for language >>>
@bot.on_callback_query(filters.regex("^select_"))
async def selection_callback(client, cb):
    await cb.answer("Fetching details, please wait...", show_alert=False)
    _, media_type, media_id = cb.data.split("_")
    
    details = get_tmdb_details(media_type, int(media_id))
    if not details:
        await cb.message.edit_text("❌ Oops! Failed to get details. Please try again.")
        return

    user_id = cb.from_user.id
    user_conversations[user_id] = {"details": details, "links": []}

    # <<< NEW: Ask for custom language instead of links directly >>>
    user_conversations[user_id]["state"] = "wait_custom_language"
    await cb.message.edit_text(
        "✅ Details fetched successfully!\n\n"
        "**🗣️ Please enter the language for this post** (e.g., `Hindi Dubbed`, `English`, `Dual Audio`)."
    )

# ... (add_link_callback and link_conversation_handler remain the same) ...
@bot.on_callback_query(filters.regex("^addlink_"))
async def add_link_callback(client, cb):
    action, user_id_str = cb.data.rsplit("_", 1)
    user_id = int(user_id_str)
    
    if cb.from_user.id != user_id: return await cb.answer("This is not for you!", show_alert=True)
    convo = user_conversations.get(user_id)
    if not convo: return await cb.answer("Your session has expired. Please start over.", show_alert=True)

    if action == "addlink_yes":
        convo["state"] = "wait_link_label"
        await cb.message.edit_text("**Step 1 of 2: Link Label**\n\nExample: `Download 720p` or `Episode 01 (480p)`")
    elif action == "addlink_no":
        await cb.message.edit_text("✅ No links will be added. Generating final content...")
        await generate_final_content(client, user_id, cb.message)

async def link_conversation_handler(client, message: Message):
    user_id = message.from_user.id
    convo = user_conversations.get(user_id)
    if not convo: return
    
    state = convo.get("state")
    text = message.text.strip()

    if state == "wait_link_label":
        convo["current_label"] = text
        convo["state"] = "wait_link_url"
        await message.reply_text(f"**Step 2 of 2: Link URL**\n\nNow send the download URL for **'{text}'**.")
    
    elif state == "wait_link_url":
        if not (text.startswith("http://") or text.startswith("https://")):
            return await message.reply_text("⚠️ Invalid URL. Please send a valid link starting with `http://` or `https://`.")
        
        convo["links"].append({"label": convo["current_label"], "url": text})
        del convo["current_label"]
        convo["state"] = "ask_another"
        buttons = [[InlineKeyboardButton("➕ Add Another Link", callback_data=f"addlink_yes_{user_id}")], [InlineKeyboardButton("✅ Done, Generate Post", callback_data=f"addlink_no_{user_id}")]]
        await message.reply_text(f"✅ Link added successfully!\n\nDo you want to add another link?", reply_markup=InlineKeyboardMarkup(buttons))

# <<< NEW: Conversation handler for custom language >>>
async def language_conversation_handler(client, message: Message):
    user_id = message.from_user.id
    convo = user_conversations.get(user_id)
    if not convo: return

    # Save the custom language provided by the user
    convo["details"]["custom_language"] = message.text.strip()
    
    # Now, proceed to ask for download links
    convo["state"] = "ask_links" # a neutral state before link decision
    buttons = [[InlineKeyboardButton("✅ Yes, add links", callback_data=f"addlink_yes_{user_id}")], [InlineKeyboardButton("❌ No, skip and generate", callback_data=f"addlink_no_{user_id}")]]
    await message.reply_text(
        f"✅ Language set to: **{convo['details']['custom_language']}**\n\n"
        "**🔗 Add Download Links?**",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

# <<< MODIFIED: Manual conversation handler (removed language step from here) >>>
async def manual_conversation_handler(client, message: Message):
    user_id = message.from_user.id
    convo = user_conversations.get(user_id)
    state = convo.get("state")
    text = message.text.strip()

    if state == "manual_wait_title":
        convo["details"]["title"] = text
        convo["state"] = "manual_wait_year"
        await message.reply_text("✅ **Title set.**\n\nNext, send the 4-digit **Year** (e.g., `2023`).")
    
    elif state == "manual_wait_year":
        if not text.isdigit() or len(text) != 4:
            return await message.reply_text("⚠️ Invalid year. Please send a 4-digit year (e.g., `2023`).")
        convo["details"]["release_date"] = f"{text}-01-01"
        convo["state"] = "manual_wait_overview"
        await message.reply_text("✅ **Year set.**\n\nNow, please send the **Plot/Overview**.")

    elif state == "manual_wait_overview":
        convo["details"]["overview"] = text
        convo["state"] = "manual_wait_genres"
        await message.reply_text("✅ **Plot set.**\n\nSend the **Genres**, separated by commas (e.g., `Action, Drama, Thriller`).")

    elif state == "manual_wait_genres":
        genres = [{"name": g.strip()} for g in text.split(",")]
        convo["details"]["genres"] = genres
        convo["state"] = "manual_wait_rating"
        await message.reply_text("✅ **Genres set.**\n\nWhat is the **Rating**? (e.g., `8.5`). Send `N/A` if not available.")

    elif state == "manual_wait_rating":
        try:
            rating = "N/A" if text.upper() == "N/A" else round(float(text), 1)
            convo["details"]["vote_average"] = rating
            convo["state"] = "manual_wait_poster"
            await message.reply_text("✅ **Rating set.**\n\nFinally, please send the **Poster Image** for this content.")
        except ValueError:
            await message.reply_text("⚠️ Invalid rating. Please send a number (e.g., `7.8`) or `N/A`.")


# ... (generate_final_content and final_action_callback remain the same) ...
async def generate_final_content(client, user_id, msg_to_edit: Message):
    convo = user_conversations.get(user_id)
    if not convo: return
    
    await msg_to_edit.edit_text("⏳ Processing...\n\n📝 Generating caption & HTML...")
    caption = generate_formatted_caption(convo["details"])
    html_code = generate_html(convo["details"], convo["links"])
    
    await msg_to_edit.edit_text("⏳ Processing...\n\n🎨 Generating a cool image poster...")
    image_file = generate_image(convo["details"])

    convo["generated"] = {"caption": caption, "html": html_code, "image": image_file}
    convo["state"] = "done"

    buttons = [[InlineKeyboardButton("📝 Get Blogger HTML Code", callback_data=f"get_html_{user_id}")], [InlineKeyboardButton("📄 Copy Text Caption", callback_data=f"get_caption_{user_id}")]]
    if user_id in user_channels:
        buttons.append([InlineKeyboardButton("📢 Post to Channel", callback_data=f"post_channel_{user_id}")])
    
    await msg_to_edit.delete()
    
    if image_file:
        await client.send_photo(msg_to_edit.chat.id, photo=image_file, caption=caption, reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await client.send_message(msg_to_edit.chat.id, caption, reply_markup=InlineKeyboardMarkup(buttons))

@bot.on_callback_query(filters.regex("^(get_|post_)"))
async def final_action_callback(client, cb):
    try:
        action, user_id_str = cb.data.rsplit("_", 1)
        user_id = int(user_id_str)
    except (ValueError, IndexError): return await cb.answer("Error: Invalid callback data.", show_alert=True)
    
    if cb.from_user.id != user_id: return await cb.answer("This button is not for you!", show_alert=True)
    if user_id not in user_conversations or "generated" not in user_conversations[user_id]:
        return await cb.answer("Session expired. Please start over.", show_alert=True)
    
    generated = user_conversations[user_id]["generated"]
    
    if action == "get_html":
        await cb.answer()
        html_code = generated["html"]
        if len(html_code) > 4000:
            await client.send_message(cb.message.chat.id, "⚠️ HTML code is too long. Sending it as a file.")
            title = (user_conversations[user_id]["details"].get("title") or "post").replace(" ", "_")
            file_bytes = io.BytesIO(html_code.encode('utf-8'))
            file_bytes.name = f"{title}.html"
            await client.send_document(cb.message.chat.id, document=file_bytes, caption="Here is your HTML file.")
        else:
            await client.send_message(cb.message.chat.id, f"```html\n{html_code}\n```", parse_mode=enums.ParseMode.MARKDOWN)

    elif action == "get_caption":
        await cb.answer()
        await client.send_message(cb.message.chat.id, generated["caption"])
        
    elif action == "post_channel":
        channel_id = user_channels.get(user_id)
        if not channel_id: return await cb.answer("Channel not set. Use /setchannel first.", show_alert=True)
        
        await cb.answer("🚀 Posting to your channel...", show_alert=False)
        try:
            image_file = generated.get("image")
            if image_file:
                image_file.seek(0)
                await client.send_photo(channel_id, photo=image_file, caption=generated["caption"])
            else:
                await client.send_message(channel_id, generated["caption"])
            
            await cb.edit_message_reply_markup(reply_markup=None)
            await cb.message.reply_text(f"✅ Successfully posted to `{channel_id}`!")
        except Exception as e:
            await cb.message.reply_text(f"❌ Failed to post to channel.\n**Error:** `{e}`")

# ---- START THE BOT ----
if __name__ == "__main__":
    print("🚀 Bot is starting... Interactive Language & Style Features Added.")
    bot.run()
    print("👋 Bot has stopped.")

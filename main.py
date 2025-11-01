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

try:
    API_ID = int(API_ID)
except (ValueError, TypeError):
    print("❌ FATAL ERROR: API_ID must be an integer. Please check your .env file.")
    sys.exit(1)

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
        details_url = f"https://api.themoviedb.org/3/{media_type}/{media_id}?api_key={TMDB_API_KEY}&append_to_response=credits,videos"
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
    rating = f"⭐ {data.get('vote_average', 0):.1f}/10"
    genres = ", ".join([g["name"] for g in data.get("genres", [])] or ["N/A"])
    overview = data.get("overview", "No plot summary available.")
    director = next((member["name"] for member in data.get("credits", {}).get("crew", []) if member.get("job") == "Director"), "N/A")
    cast = ", ".join([actor["name"] for actor in data.get("credits", {}).get("cast", [])[:5]] or ["N/A"])
    language = data.get('custom_language', '').title()

    caption_text = f"🎬 **{title} ({year})**\n\n"
    caption_text += f"**Rating:** {rating}\n"
    caption_text += f"**Genres:** {genres}\n"
    if language:
        caption_text += f"**Language:** {language}\n"
    if director != "N/A":
        caption_text += f"**Director:** {director}\n"
    if cast != "N/A":
        caption_text += f"**Cast:** {cast}\n\n"
    
    caption_text += f"**Plot:** _{overview[:450]}{'...' if len(overview) > 450 else ''}_"
    return caption_text

def generate_html(data: dict, links: list):
    title = data.get("title") or data.get("name") or "N/A"
    year = (data.get("release_date") or data.get("first_air_date") or "----")[:4]
    rating = f"{data.get('vote_average', 0):.1f}"
    overview = data.get("overview", "No overview available.")
    genres = ", ".join([g["name"] for g in data.get("genres", [])] or ["N/A"])
    language = data.get('custom_language', '').title()

    if data.get('poster_path'):
        poster_url = f"https://image.tmdb.org/t/p/w500{data['poster_path']}"
    else:
        poster_url = "https://www.prokerala.com/movies/assets/img/no-poster-available.jpg"
    
    backdrop_url = f"https://image.tmdb.org/t/p/original{data['backdrop_path']}" if data.get('backdrop_path') else ""

    css_styles = """
<style>
.movie-post-container {font-family: Arial, sans-serif; color: #333; line-height: 1.6;}
.movie-post-container h2.post-title {text-align: center; font-size: 1.8em; margin-top: 15px; margin-bottom: 20px; font-weight: bold;}
.movie-post-container h3.section-heading {background-color: #2c3e50; color: #ffffff; padding: 10px 15px; margin-top: 25px; margin-bottom: 15px; border-left: 5px solid #e74c3c; text-transform: uppercase; font-size: 1.2em; border-radius: 4px;}
.movie-post-container p {margin: 8px 0; font-size: 1em;}
.screenshots-div img {max-width: 100%; height: auto; border-radius: 8px; border: 3px solid #34495e;}
.info-section p strong {min-width: 120px; display: inline-block;}
.download-section ul {list-style: none; padding: 0; text-align: center;}
.download-section li {margin: 10px 0;}
.download-button {display: inline-block; background-color: #3498db; color: #ffffff !important; padding: 12px 25px; text-decoration: none; border-radius: 5px; font-weight: bold; font-size: 1em; border: none; transition: background-color 0.3s ease, transform 0.2s;}
.download-button:hover {background-color: #2980b9; transform: scale(1.05); color: #ffffff !important;}
</style>
"""
    poster_html = f'<img src="{poster_url}" alt="{title} Poster" style="display: block; margin-left: auto; margin-right: auto; max-width: 350px; height: auto; border-radius: 8px; border: 3px solid #34495e; margin-bottom: 20px;" />'
    post_title_html = f'<h2 class="post-title">{title} ({year}) {language}</h2>'
    jump_break_html = '<!--more-->'
    movie_info_html = (
        f'<h3 class="section-heading">Movie Information</h3>'
        f'<div class="info-section">'
        f'<p><strong>Full Name:</strong> {title}</p>'
        f'<p><strong>Release Year:</strong> {year}</p>'
        f'<p><strong>Genres:</strong> {genres}</p>'
        f'<p><strong>Rating:</strong> ⭐ {rating}/10</p>'
    )
    if language: movie_info_html += f'<p><strong>Language:</strong> {language}</p>'
    movie_info_html += '</div>'
    storyline_html = f'<h3 class="section-heading">Storyline</h3><p>{overview}</p>'
    screenshots_html = ""
    if backdrop_url: screenshots_html = f'<h3 class="section-heading">Screenshots</h3><div class="screenshots-div"><a href="{backdrop_url}" target="_blank" rel="noopener noreferrer"><img src="{backdrop_url}" alt="{title} Screenshot"></a></div>'
    download_buttons_html = ""
    if links:
        link_items = "".join([f'<li><a href="{link["url"]}" target="_blank" rel="noopener noreferrer" class="download-button">🔽 {link["label"]}</a></li>' for link in links])
        download_buttons_html = f'<h3 class="section-heading">Download Links</h3><div class="download-section"><ul>{link_items}</ul></div>'
    
    final_html = (
        f'{css_styles}'
        f'<!-- Bot Generated Content Starts -->'
        f'<div class="movie-post-container">'
        f'{poster_html}'
        f'{post_title_html}'
        f'{jump_break_html}'
        f'{movie_info_html}'
        f'{storyline_html}'
        f'{screenshots_html}'
        f'{download_buttons_html}'
        f'</div>'
        f'<!-- Bot Generated Content Ends -->'
    )
    return final_html

def generate_image(data: dict):
    try:
        poster_bytes = None
        if data.get("manual_poster"):
            poster_bytes = data["manual_poster"].getvalue()
        elif data.get('poster_path'):
            poster_url = f"https://image.tmdb.org/t/p/w500{data['poster_path']}"
            poster_response = requests.get(poster_url)
            if poster_response.ok:
                poster_bytes = poster_response.content
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

async def process_text_input(client, message: Message):
    user_id = message.from_user.id
    text = message.text.strip()
    
    if convo := user_conversations.get(user_id):
        state = convo.get("state")
        if state and state != "done":
            handlers = {
                "manual_wait_title": manual_conversation_handler, "manual_wait_year": manual_conversation_handler,
                "manual_wait_overview": manual_conversation_handler, "manual_wait_genres": manual_conversation_handler,
                "manual_wait_rating": manual_conversation_handler,
                "wait_custom_language": language_conversation_handler,
                "wait_link_label": link_conversation_handler, "wait_link_url": link_conversation_handler
            }
            if handler := handlers.get(state):
                await handler(client, message)
                return

    processing_msg = await message.reply_text("🔍 Searching...")
    results = search_tmdb(text)
    if not results:
        await processing_msg.edit_text("❌ No content found. Try a more specific name (e.g., `Movie Name 2023`) or use `/manual`."); return
    
    buttons = []
    for r in results:
        title = r.get('title') or r.get('name')
        year = (r.get('release_date') or r.get('first_air_date') or '----').split('-')[0]
        icon = '🎬' if r['media_type'] == 'movie' else '📺'
        buttons.append([InlineKeyboardButton(f"{icon} {title} ({year})", callback_data=f"select_{r['media_type']}_{r['id']}")])
    
    await processing_msg.edit_text("**👇 Choose the correct one:**", reply_markup=InlineKeyboardMarkup(buttons))

# ############### THIS IS THE CORRECTED LINE ###############
@bot.on_message(filters.text & filters.private & ~filters.command(["start", "setchannel", "cancel", "manual"]))
async def text_handler(client, message: Message):
    await process_text_input(client, message)
# ##########################################################

@bot.on_message(filters.photo & filters.private)
async def photo_handler(client, message: Message):
    user_id = message.from_user.id
    if (convo := user_conversations.get(user_id)) and convo.get("state") == "manual_wait_poster":
        processing_msg = await message.reply_text("🖼️ Receiving poster...")
        photo_file = await client.download_media(message.photo.file_id, in_memory=True)
        convo["details"]["manual_poster"] = photo_file
        convo["state"] = "wait_custom_language"
        await processing_msg.edit_text("✅ Poster received!\n\n**🗣️ Now, enter the language for this post** (e.g., `Bengali Dubbed`, `Hindi`, `Dual Audio`).")

@bot.on_callback_query(filters.regex("^select_"))
async def selection_callback(client, cb):
    await cb.answer("Fetching details...", show_alert=False)
    _, media_type, media_id = cb.data.split("_")
    details = get_tmdb_details(media_type, int(media_id))
    if not details:
        await cb.message.edit_text("❌ Failed to get details. Please try again."); return
    
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

async def link_conversation_handler(client, message: Message):
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

async def language_conversation_handler(client, message: Message):
    user_id = message.from_user.id
    convo = user_conversations[user_id]
    convo["details"]["custom_language"] = message.text.strip()
    convo["state"] = "ask_links"
    buttons = [[InlineKeyboardButton("✅ Yes, add links", callback_data=f"addlink_yes_{user_id}")], 
               [InlineKeyboardButton("❌ No, skip", callback_data=f"addlink_no_{user_id}")]]
    await message.reply_text(f"✅ Language set to **{convo['details']['custom_language']}**.\n\n**🔗 Add Download Links?**", reply_markup=InlineKeyboardMarkup(buttons))

async def manual_conversation_handler(client, message: Message):
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
        else:
            await message.reply_text("⚠️ Invalid. Please send a 4-digit year.")
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
            rating = 0.0 if text.upper() == "N/A" else round(float(text), 1)
            convo["details"]["vote_average"] = rating
            convo["state"] = "manual_wait_poster"
            await message.reply_text("✅ Rating set. Finally, send the **Poster Image**.")
        except ValueError:
            await message.reply_text("⚠️ Invalid rating. Send a number (e.g., `7.8`) or `N/A`.")

async def generate_final_content(client, user_id, msg_to_edit: Message):
    if not (convo := user_conversations.get(user_id)): return
    
    await msg_to_edit.edit_text("⏳ Generating content...")
    caption = generate_formatted_caption(convo["details"])
    html_code = generate_html(convo["details"], convo["links"])
    
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
        await client.send_message(msg_to_edit.chat.id, caption, reply_markup=InlineKeyboardMarkup(buttons))

@bot.on_callback_query(filters.regex("^(get_|post_)"))
async def final_action_callback(client, cb):
    try:
        action, user_id_str = cb.data.rsplit("_", 1)
        user_id = int(user_id_str)
    except (ValueError, IndexError):
        return await cb.answer("Error: Invalid callback data.", show_alert=True)
    
    if cb.from_user.id != user_id:
        return await cb.answer("This button is not for you!", show_alert=True)
    if not (convo := user_conversations.get(user_id)) or "generated" not in convo:
        return await cb.answer("Session expired. Please start over.", show_alert=True)
    
    generated = convo["generated"]
    
    if action == "get_html":
        await cb.answer()
        html_code = generated["html"]
        if len(html_code) > 4000:
            title = (convo["details"].get("title") or "post").replace(" ", "_")
            file_bytes = io.BytesIO(html_code.encode('utf-8'))
            file_bytes.name = f"{title}.html"
            await client.send_document(cb.message.chat.id, document=file_bytes, caption="HTML code is too long. Here it is as a file.")
        else:
            await client.send_message(cb.message.chat.id, f"```html\n{html_code}\n```", parse_mode=enums.ParseMode.MARKDOWN)
    
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
    flask_thread = Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    
    bot.run()
    
    print("👋 Bot has stopped.")

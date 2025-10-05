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
except IOError:
    print("⚠️ Warning: Font files not found. Image generation will use default fonts.")
    FONT_BOLD = FONT_REGULAR = FONT_SMALL = ImageFont.load_default()

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
        details_url = f"https://api.themoviedb.org/3/{media_type}/{media_id}?api_key={TMDB_API_KEY}&append_to_response=credits,videos"
        response = requests.get(details_url)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching TMDB details: {e}")
        return None

# ---- CONTENT GENERATION FUNCTIONS ----
def generate_formatted_caption(data: dict):
    title = data.get("title") or data.get("name") or "N/A"
    year = (data.get("release_date") or data.get("first_air_date") or "----")[:4]
    rating = f"⭐ {round(data.get('vote_average', 0), 1)}/10"
    genres = ", ".join([g["name"] for g in data.get("genres", [])] or ["N/A"])
    overview = data.get("overview", "N/A")
    director = next((member["name"] for member in data.get("credits", {}).get("crew", []) if member.get("job") == "Director"), "N/A")
    cast = ", ".join([actor["name"] for actor in data.get("credits", {}).get("cast", [])[:5]] or ["N/A"])

    return (
        f"🎬 **{title} ({year})**\n\n"
        f"**Rating:** {rating}\n"
        f"**Genres:** {genres}\n"
        f"**Director:** {director}\n"
        f"**Cast:** {cast}\n\n"
        f"**Plot:** _{overview[:500]}{'...' if len(overview) > 500 else ''}_"
    )

def generate_html(data: dict, links: list):
    title = data.get("title") or data.get("name") or "N/A"
    year = (data.get("release_date") or data.get("first_air_date") or "----")[:4]
    rating = round(data.get("vote_average", 0), 1)
    overview = data.get("overview", "No overview available.")
    genres = ", ".join([g["name"] for g in data.get("genres", [])] or ["N/A"])
    poster = f"https://image.tmdb.org/t/p/w500{data['poster_path']}" if data.get('poster_path') else "https://via.placeholder.com/400x600.png?text=No+Poster"
    backdrop = f"https://image.tmdb.org/t/p/original{data['backdrop_path']}" if data.get('backdrop_path') else "https://via.placeholder.com/1280x720.png?text=No+Backdrop"
    trailer_key = next((v['key'] for v in data.get('videos', {}).get('results', []) if v['site'] == 'YouTube' and v['type'] == 'Trailer'), None)
    
    trailer_button = f'<a href="https://www.youtube.com/watch?v={trailer_key}" target="_blank" class="trailer-button">🎬 Watch Trailer</a>' if trailer_key else ""
    # <<< DYNAMIC LINK GENERATION FOR ANY NUMBER OF LINKS >>>
    download_buttons = "".join([f'<a href="{link["url"]}" target="_blank">🔽 {link["label"]}</a>' for link in links])

    return f"""
<!-- Generated by Advanced Movie Bot -->
<style>.movie-card-container{{max-width:700px;margin:20px auto;background:#1c1c1c;border-radius:20px;padding:20px;box-shadow:0 8px 25px rgba(0,0,0,0.5);color:#e0e0e0;font-family:sans-serif;overflow:hidden;}}.movie-header{{text-align:center;color:#00bcd4;margin-bottom:20px;}}.movie-content{{display:flex;flex-wrap:wrap;align-items:flex-start;}}.movie-poster-container{{flex:1 1 200px;margin-right:20px;}}.movie-poster-container img{{width:100%;height:auto;border-radius:15px;display:block;}}.movie-details{{flex:2 1 300px;}}.movie-details p{{margin:0 0 10px 0;}}.movie-details b{{color:#00e676;}}.backdrop-container{{width:100%;margin-top:20px;}}.backdrop-container img{{max-width:100%;height:auto;border-radius:15px;display:block;margin:auto;}}.action-buttons{{text-align:center;margin-top:20px;width:100%;}}.action-buttons a{{display:inline-block;background:linear-gradient(45deg,#ff512f,#dd2476);color:white!important;padding:12px 25px;margin:8px;border-radius:25px;text-decoration:none;font-weight:600;}}.action-buttons .trailer-button{{background:#c4302b;}}</style>
<div class="movie-card-container">
<h2 class="movie-header">{title} ({year})</h2>
<div class="movie-content">
<div class="movie-poster-container"><img src="{poster}" alt="{title} Poster"/></div>
<div class="movie-details"><p><b>Genre:</b> {genres}</p><p><b>Rating:</b> ⭐ {rating}/10</p><p><b>Overview:</b> {overview}</p></div>
</div>
<div class="backdrop-container"><a href="{backdrop}" target="_blank"><img src="{backdrop}" alt="{title} Backdrop"/></a></div>
<div class="action-buttons">{trailer_button}{download_buttons or '<!-- No download links provided -->'}</div>
</div>
"""

def generate_image(data: dict):
    try:
        poster_url = f"https://image.tmdb.org/t/p/w500{data['poster_path']}" if data.get('poster_path') else None
        if not poster_url: return None
        poster_img = Image.open(io.BytesIO(requests.get(poster_url).content)).convert("RGBA").resize((400, 600))

        if data.get('backdrop_path'):
            backdrop_url = f"https://image.tmdb.org/t/p/w1280{data['backdrop_path']}"
            bg_img = Image.open(io.BytesIO(requests.get(backdrop_url).content)).convert("RGBA").resize((1280, 720))
            bg_img = bg_img.filter(ImageFilter.GaussianBlur(3))
            darken_layer = Image.new('RGBA', bg_img.size, (0, 0, 0, 128))
            bg_img = Image.alpha_composite(bg_img, darken_layer)
        else:
            bg_img = Image.new('RGBA', (1280, 720), (10, 10, 20))
            
        bg_img.paste(poster_img, (50, 60), poster_img)

        draw = ImageDraw.Draw(bg_img)
        title = data.get("title") or data.get("name") or "N/A"
        year = (data.get("release_date") or data.get("first_air_date") or "----")[:4]
        
        draw.text((480, 80), f"{title} ({year})", font=FONT_BOLD, fill="white")
        draw.text((480, 140), f"⭐ {round(data.get('vote_average', 0), 1)}/10", font=FONT_REGULAR, fill="#00e676")
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
        "Send me a name to get started.\n\n"
        "**Commands:**\n`/setchannel @username`\n`/cancel`"
    )

@bot.on_message(filters.command("setchannel") & filters.private)
async def set_channel_command(_, message: Message):
    if len(message.command) > 1:
        user_channels[message.from_user.id] = message.command[1]
        await message.reply_text(f"✅ Channel set to `{message.command[1]}`.")
    else:
        await message.reply_text("Usage: `/setchannel @yourchannel`")

@bot.on_message(filters.command("cancel") & filters.private)
async def cancel_command(_, message: Message):
    if message.from_user.id in user_conversations:
        del user_conversations[message.from_user.id]
        await message.reply_text("✅ Operation cancelled.")
    else:
        await message.reply_text("Nothing to cancel.")

@bot.on_message(filters.text & filters.private & ~filters.command(["start", "setchannel", "cancel"]))
async def text_handler(client, message: Message):
    if message.from_user.id in user_conversations and user_conversations[message.from_user.id].get("state") != "done":
        await link_conversation_handler(client, message)
        return

    processing_msg = await message.reply_text("🔍 Searching...")
    results = search_tmdb(message.text.strip())
    if not results:
        await processing_msg.edit_text("❌ No content found.")
        return

    buttons = [[InlineKeyboardButton(
        f"{'🎬' if r['media_type'] == 'movie' else '📺'} {r.get('title') or r.get('name')} ({(r.get('release_date') or r.get('first_air_date') or '----').split('-')[0]})",
        callback_data=f"select_{r['media_type']}_{r['id']}"
    )] for r in results]
    await processing_msg.edit_text("**👇 Choose from the results:**", reply_markup=InlineKeyboardMarkup(buttons))

@bot.on_callback_query(filters.regex("^select_"))
async def selection_callback(client, cb):
    await cb.answer("Fetching details...")
    _, media_type, media_id = cb.data.split("_")
    
    details = get_tmdb_details(media_type, int(media_id))
    if not details:
        await cb.message.edit_text("❌ Failed to get details.")
        return

    user_id = cb.from_user.id
    user_conversations[user_id] = {"details": details, "links": []}

    buttons = [
        [InlineKeyboardButton("✅ Yes, add links", callback_data=f"addlink_yes_{user_id}")],
        [InlineKeyboardButton("❌ No, skip", callback_data=f"addlink_no_{user_id}")]
    ]
    await cb.message.edit_text(
        "**🔗 Add Download Links?**\n\nDo you want to add any download links to this post?",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

@bot.on_callback_query(filters.regex("^addlink_"))
async def add_link_callback(client, cb):
    action, user_id_str = cb.data.rsplit("_", 1)
    user_id = int(user_id_str)
    
    if cb.from_user.id != user_id:
        return await cb.answer("This is not for you!", show_alert=True)
    
    convo = user_conversations.get(user_id)
    if not convo: return await cb.answer("Session expired.", show_alert=True)

    if action == "addlink_yes":
        convo["state"] = "wait_link_label"
        await cb.message.edit_text(
            "**Step 1: Link Label**\n\n"
            "Please send the text for the download button.\n\n"
            "**Example:** `Season 1 Complete 720p` or `Episode 01`"
        )
    elif action == "addlink_no":
        await cb.message.edit_text("✅ No links will be added. Generating content...")
        await generate_final_content(client, user_id, cb.message.chat.id, cb.message)

async def link_conversation_handler(client, message: Message):
    user_id = message.from_user.id
    convo = user_conversations.get(user_id)
    if not convo: return
    
    state = convo.get("state")
    text = message.text.strip()

    if state == "wait_link_label":
        convo["current_label"] = text
        convo["state"] = "wait_link_url"
        await message.reply_text(f"**Step 2: Link URL**\n\nNow send the download URL for **'{text}'**.")
    
    elif state == "wait_link_url":
        if not text.startswith("http"):
            return await message.reply_text("⚠️ Invalid URL. Please send a valid link starting with http/https.")
        
        convo["links"].append({"label": convo["current_label"], "url": text})
        del convo["current_label"]
        convo["state"] = "ask_another"

        buttons = [
            [InlineKeyboardButton("✅ Yes, add another", callback_data=f"addlink_yes_{user_id}")],
            [InlineKeyboardButton("✅ No, I'm done", callback_data=f"addlink_no_{user_id}")]
        ]
        await message.reply_text(
            f"✅ Link for **'{convo['links'][-1]['label']}'** added!\n\nDo you want to add another link?",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

async def generate_final_content(client, user_id, chat_id, msg):
    convo = user_conversations.get(user_id)
    if not convo: return
    
    await msg.edit_text("📝 Generating caption & HTML...")
    caption = generate_formatted_caption(convo["details"])
    html_code = generate_html(convo["details"], convo["links"])
    
    await msg.edit_text("🎨 Generating image...")
    image_file = generate_image(convo["details"])

    convo["generated"] = {"caption": caption, "html": html_code, "image": image_file}
    convo["state"] = "done"

    buttons = [[InlineKeyboardButton("📝 Get HTML Code", callback_data=f"get_html_{user_id}")],
               [InlineKeyboardButton("📄 Copy Text Caption", callback_data=f"get_caption_{user_id}")]]
    if user_id in user_channels:
        buttons.append([InlineKeyboardButton("📢 Post to Channel", callback_data=f"post_channel_{user_id}")])
    
    if msg.from_user.is_self: await msg.delete()
    
    if image_file:
        await client.send_photo(chat_id, photo=image_file, caption=caption, reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await client.send_message(chat_id, caption, reply_markup=InlineKeyboardMarkup(buttons))

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
            await client.send_message(cb.message.chat.id, "⚠️ HTML is too long. Sending as a file.")
            title = (user_conversations[user_id]["details"].get("title") or user_conversations[user_id]["details"].get("name") or "post").replace(" ", "_")
            await client.send_document(cb.message.chat.id, document=io.BytesIO(html_code.encode('utf-8')), file_name=f"{title}.html", caption="HTML file.")
        else:
            await client.send_message(cb.message.chat.id, f"```html\n{html_code}\n```", parse_mode=enums.ParseMode.MARKDOWN)

    elif action == "get_caption":
        await cb.answer()
        await client.send_message(cb.message.chat.id, generated["caption"])
        
    elif action == "post_channel":
        channel_id = user_channels.get(user_id)
        if not channel_id: return await cb.answer("Channel not set. Use /setchannel first.", show_alert=True)
        
        await cb.answer("Posting to channel...", show_alert=False)
        try:
            image_file = generated.get("image")
            if image_file:
                image_file.seek(0)
                await client.send_photo(channel_id, photo=image_file, caption=generated["caption"])
            else:
                await client.send_message(channel_id, generated["caption"])
            
            await cb.edit_message_reply_markup(reply_markup=None)
            await client.send_message(cb.message.chat.id, f"✅ Successfully posted to `{channel_id}`!")
        except Exception as e:
            await client.send_message(cb.message.chat.id, f"❌ Failed to post. Error: {e}")

# ---- START THE BOT ----
if __name__ == "__main__":
    print("🚀 Bot is starting... Final Flexible Version.")
    bot.run()
    print("👋 Bot has stopped.")

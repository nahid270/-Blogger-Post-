import os
import io
import sys
import re # সাল বের করার জন্য re মডিউল ইম্পোর্ট করা হয়েছে
import requests
from pyrogram import Client, filters
from pyrogram.enums import ChatAction, ParseMode
from flask import Flask
from threading import Thread
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# ---- CONFIGURATION ----
# Load credentials from environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
TMDB_API_KEY = os.getenv("TMDB_API_KEY")

# --- Essential variable check ---
# Exit if any essential variable is missing
if not all([BOT_TOKEN, API_ID, API_HASH, TMDB_API_KEY]):
    print("❌ ERROR: One or more environment variables are missing.")
    print("Please check your .env file or environment configuration.")
    sys.exit(1)

API_ID = int(API_ID) # Ensure API_ID is an integer

# ---- FLASK APP FOR KEEP-ALIVE ----
app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Movie & Series Bot is up and running!"

def run_flask():
    app.run(host='0.0.0.0', port=8080)

flask_thread = Thread(target=run_flask)
flask_thread.start()


# ---- PYROGRAM BOT INITIALIZATION ----
bot = Client("moviebot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)


# ---- TMDB API FUNCTION (UPGRADED FOR MOVIE & TV) ----
def get_tmdb_details(query: str):
    """
    Fetches movie or TV series details from The Movie Database (TMDB) API.
    Supports queries with a year, e.g., "Interstellar 2014".
    """
    # সার্চ কোয়েরি থেকে নাম এবং সাল আলাদা করা
    year = None
    match = re.search(r'(.+?)\s*\(?(\d{4})\)?$', query)
    if match:
        name = match.group(1).strip()
        year = match.group(2)
    else:
        name = query.strip()

    try:
        # মাল্টি-সার্চ ব্যবহার করে মুভি এবং সিরিজ উভয়ই খোঁজা হবে
        search_url = f"https://api.themoviedb.org/3/search/multi?api_key={TMDB_API_KEY}&query={name}"
        if year:
            search_url += f"&year={year}"

        search_response = requests.get(search_url)
        search_response.raise_for_status()
        search_data = search_response.json()

        if search_data.get("results"):
            # প্রথম উপযুক্ত রেজাল্টটি (মুভি বা টিভি) খুঁজে বের করা
            first_result = None
            for result in search_data["results"]:
                if result.get("media_type") in ["movie", "tv"]:
                    first_result = result
                    break
            
            if not first_result:
                return None, None

            media_type = first_result["media_type"]
            media_id = first_result["id"]

            # নির্দিষ্ট আইডি দিয়ে সম্পূর্ণ তথ্য আনা হচ্ছে
            details_url = f"https://api.themoviedb.org/3/{media_type}/{media_id}?api_key={TMDB_API_KEY}&language=en-US"
            details_response = requests.get(details_url)
            details_response.raise_for_status()
            
            return details_response.json(), media_type
            
    except requests.exceptions.RequestException as e:
        print(f"Error fetching data from TMDB: {e}")
        return None, None
    return None, None

# ---- HTML GENERATOR FUNCTION (UPGRADED FOR MOVIE & TV) ----
def generate_html(data: dict, media_type: str):
    """Generates a styled HTML snippet for a movie or TV series blog post."""
    # মুভির জন্য 'title' এবং সিরিজের জন্য 'name' ব্যবহৃত হয়
    title = data.get("title") or data.get("name") or "Unknown Title"
    
    # মুভির জন্য 'release_date' এবং সিরিজের জন্য 'first_air_date' ব্যবহৃত হয়
    release_date = data.get("release_date") or data.get("first_air_date") or "N/A"
    year = release_date[:4] if release_date != "N/A" else "N/A"
    
    rating = round(data.get("vote_average", 0), 1)
    overview = data.get("overview", "No overview available.")
    genres = ", ".join([g["name"] for g in data.get("genres", [])]) or "N/A"
    poster_path = data.get('poster_path')
    backdrop_path = data.get('backdrop_path')

    poster = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else "https://via.placeholder.com/500x750.png?text=No+Poster"
    backdrop = f"https://image.tmdb.org/t/p/original{backdrop_path}" if backdrop_path else "https://via.placeholder.com/1280x720.png?text=No+Backdrop"
    
    # সিরিজের জন্য অতিরিক্ত তথ্য
    series_info = ""
    if media_type == "tv":
        seasons = data.get("number_of_seasons", "N/A")
        episodes = data.get("number_of_episodes", "N/A")
        series_info = f"""
        <p><b>Seasons:</b> {seasons}</p>
        <p><b>Total Episodes:</b> {episodes}</p>
        """

    html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;600;700&display=swap" rel="stylesheet">
    <title>{title} Post</title>
    <style>
        body {{ background-color: #1a1a1a; color: #e0e0e0; font-family: 'Poppins', sans-serif; }}
        .movie-card {{ max-width: 700px; margin: 20px auto; background: linear-gradient(135deg, #1c1c1c, #2a2a2a); border-radius: 20px; padding: 20px; box-shadow: 0 8px 25px rgba(0, 0, 0, 0.5); border: 1px solid #333; }}
        .movie-card .poster {{ width: 200px; border-radius: 15px; display: block; margin: 0 auto 20px auto; box-shadow: 0 4px 15px rgba(0, 0, 0, 0.4); }}
        .movie-card h2 {{ text-align: center; color: #00bcd4; margin-bottom: 20px; font-weight: 700; }}
        .movie-card p {{ line-height: 1.6; margin-bottom: 10px; }}
        .movie-card b {{ color: #00e676; }}
        .backdrop-image {{ width: 100%; border-radius: 15px; margin-top: 20px; margin-bottom: 20px; }}
        .download-buttons {{ text-align: center; margin-top: 20px; }}
        .download-buttons a {{ display: inline-block; background: linear-gradient(45deg, #ff512f, #dd2476); color: white; padding: 12px 25px; margin: 8px; border-radius: 25px; text-decoration: none; font-weight: 600; transition: all 0.3s ease; box-shadow: 0 4px 10px rgba(0, 0, 0, 0.3); }}
        .download-buttons a:hover {{ transform: translateY(-3px) scale(1.05); box-shadow: 0 6px 15px rgba(255, 81, 47, 0.4); }}
    </style>
</head>
<body>
    <div class="movie-card">
        <h2>🎬 {title} ({year})</h2>
        <img class="poster" src="{poster}" alt="{title} Poster"/>
        <p><b>Genre:</b> {genres}</p>
        <p><b>IMDB Rating:</b> ⭐ {rating}/10</p>
        {series_info}
        <p><b>Overview:</b> {overview}</p>
        <img class="backdrop-image" src="{backdrop}" alt="{title} Backdrop"/>
        <div class="download-buttons">
            <!-- আপনার ডাউনলোড লিংকগুলো এখানে # এর জায়গায় বসান -->
            <a href="#">🔽 Download 480p</a>
            <a href="#">🎥 Download 720p</a>
            <a href="#">💎 Download 1080p</a>
        </div>
    </div>
</body>
</html>
"""
    return html_content

# ---- BOT HANDLERS ----

@bot.on_message(filters.command("start") & filters.private)
async def start_command(client, message):
    await message.reply_text(
        "👋 **Welcome to the Movie & Series Post Generator Bot!**\n\n"
        "Just send me the name of any movie or web series, and I will create a beautiful, "
        "styled HTML post for your blog.\n\n"
        "**Examples:**\n"
        "🔹 `Interstellar 2014`\n"
        "🔹 `Breaking Bad`\n"
        "🔹 `The Dark Knight`"
    )

@bot.on_message(filters.text & filters.private & ~filters.command("start"))
async def content_info_handler(client, message):
    query = message.text.strip()
    if not query:
        await message.reply_text("🤔 Please send a movie or series name.")
        return

    processing_message = await message.reply_text("🎬 Searching for your content, please wait...")
    await client.send_chat_action(message.chat.id, ChatAction.TYPING)

    details, media_type = get_tmdb_details(query)
    
    if not details:
        await processing_message.edit_text("❌ **Content not found.**\n\nPlease check the spelling or try including the year (e.g., `Dune 2021`).")
        return

    html_code = generate_html(details, media_type)
    content_title = details.get('title') or details.get('name') or 'content'

    await processing_message.edit_text(
        f"✅ Here is the HTML code for **{content_title}**!\n\n"
        "_Just copy the code below and paste it into your Blogger post's HTML mode._"
    )

    if len(html_code) > 4000:
        await message.reply_text("⚠️ The HTML code is too long to be sent as a message. Sending it as a file instead.")
        html_file = io.BytesIO(html_code.encode('utf-8'))
        html_file.name = f"{content_title.replace(' ', '_')}_post.html"
        await message.reply_document(
            document=html_file,
            caption="💾 Here is your HTML file."
        )
    else:
        await message.reply_text(
            text=f"```html\n{html_code}\n```",
            parse_mode=ParseMode.MARKDOWN
        )

# ---- START THE BOT ----
print("🚀 Bot is starting...")
bot.run()
print("👋 Bot has stopped.")

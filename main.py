import os
import io
import requests
import sys
from pyrogram import Client, filters
from pyrogram.enums import ChatAction
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
# This is a simple web server to keep the bot alive on hosting platforms like Replit/Render
app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Movie Bot is up and running!"

def run_flask():
    app.run(host='0.0.0.0', port=8080)

# Run the Flask app in a separate thread
flask_thread = Thread(target=run_flask)
flask_thread.start()


# ---- PYROGRAM BOT INITIALIZATION ----
bot = Client("moviebot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)


# ---- TMDB API FUNCTION ----
def get_movie_details(movie_name: str):
    """Fetches movie details from The Movie Database (TMDB) API."""
    try:
        search_url = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={movie_name}"
        search_response = requests.get(search_url)
        search_response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)
        search_data = search_response.json()

        if search_data.get("results"):
            # Get the first movie from the search results
            first_result = search_data["results"][0]
            movie_id = first_result["id"]
            
            # Fetch detailed information for that movie ID
            details_url = f"https://api.themoviedb.org/3/movie/{movie_id}?api_key={TMDB_API_KEY}&language=en-US"
            details_response = requests.get(details_url)
            details_response.raise_for_status()
            
            return details_response.json()
            
    except requests.exceptions.RequestException as e:
        print(f"Error fetching data from TMDB: {e}")
        return None # Return None on network or API errors
        
    return None # Return None if no results are found

# ---- HTML GENERATOR FUNCTION ----
def generate_html(movie: dict):
    """Generates a styled HTML snippet for a movie blog post."""
    title = movie.get("title", "Unknown Title")
    release_date = movie.get("release_date", "N/A")
    year = release_date[:4] if release_date != "N/A" else "N/A"
    rating = round(movie.get("vote_average", 0), 1)
    overview = movie.get("overview", "No overview available.")
    genres = ", ".join([g["name"] for g in movie.get("genres", [])]) or "N/A"
    poster_path = movie.get('poster_path')
    backdrop_path = movie.get('backdrop_path')

    # Use a placeholder if images are not available
    poster = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else "https://via.placeholder.com/500x750.png?text=No+Poster"
    backdrop = f"https://image.tmdb.org/t/p/original{backdrop_path}" if backdrop_path else "https://via.placeholder.com/1280x720.png?text=No+Backdrop"

    html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;600;700&display=swap" rel="stylesheet">
    <title>{title} Post</title>
    <style>
        body {{
            background-color: #1a1a1a;
            color: #e0e0e0;
            font-family: 'Poppins', sans-serif;
        }}
        .movie-card {{
            max-width: 700px;
            margin: 20px auto;
            background: linear-gradient(135deg, #1c1c1c, #2a2a2a);
            border-radius: 20px;
            padding: 20px;
            box-shadow: 0 8px 25px rgba(0, 0, 0, 0.5);
            border: 1px solid #333;
        }}
        .movie-card .poster {{
            width: 200px;
            border-radius: 15px;
            display: block;
            margin: 0 auto 20px auto;
            box-shadow: 0 4px 15px rgba(0, 0, 0, 0.4);
        }}
        .movie-card h2 {{
            text-align: center;
            color: #00bcd4; /* Cyan color */
            margin-bottom: 20px;
            font-weight: 700;
        }}
        .movie-card p {{
            line-height: 1.6;
            margin-bottom: 10px;
        }}
        .movie-card b {{
            color: #00e676; /* Green accent */
        }}
        .backdrop-image {{
            width: 100%;
            border-radius: 15px;
            margin-top: 20px;
            margin-bottom: 20px;
        }}
        .download-buttons {{
            text-align: center;
            margin-top: 20px;
        }}
        .download-buttons a {{
            display: inline-block;
            background: linear-gradient(45deg, #ff512f, #dd2476); /* Orange to Pink Gradient */
            color: white;
            padding: 12px 25px;
            margin: 8px;
            border-radius: 25px;
            text-decoration: none;
            font-weight: 600;
            transition: all 0.3s ease;
            box-shadow: 0 4px 10px rgba(0, 0, 0, 0.3);
        }}
        .download-buttons a:hover {{
            transform: translateY(-3px) scale(1.05);
            box-shadow: 0 6px 15px rgba(255, 81, 47, 0.4);
        }}
    </style>
</head>
<body>
    <div class="movie-card">
        <h2>🎬 {title} ({year})</h2>
        <img class="poster" src="{poster}" alt="{title} Poster"/>
        <p><b>Genre:</b> {genres}</p>
        <p><b>IMDB Rating:</b> ⭐ {rating}/10</p>
        <p><b>Overview:</b> {overview}</p>
        <img class="backdrop-image" src="{backdrop}" alt="{title} Backdrop"/>
        <div class="download-buttons">
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
    """Handles the /start command."""
    await message.reply_text(
        "👋 **Welcome to the Movie Post Generator Bot!**\n\n"
        "Just send me the name of any movie, and I will create a beautiful, "
        "styled HTML post for your blog.\n\n"
        "**Example:** `Interstellar`"
    )

@bot.on_message(filters.text & filters.private & ~filters.command("start"))
async def movie_info_handler(client, message):
    """Handles movie search requests."""
    movie_name = message.text.strip()
    if not movie_name:
        await message.reply_text("🤔 Please send a movie name.")
        return

    # Let the user know the bot is working
    processing_message = await message.reply_text("🎬 Searching for your movie, please wait...")
    await client.send_chat_action(message.chat.id, ChatAction.TYPING)

    # Fetch movie details
    movie = get_movie_details(movie_name)
    
    if not movie:
        await processing_message.edit_text("❌ **Movie not found.**\n\nPlease check the spelling or try another name.")
        return

    # Generate HTML content
    html_code = generate_html(movie)
    movie_title = movie.get('title', 'movie')

    # Send the result to the user
    await processing_message.edit_text(
        f"✅ Here is the HTML post for **{movie_title}**!\n\n"
        "_Copy the content of the file and paste it into your Blogger post's HTML mode._"
    )

    # Create an in-memory file to send
    html_file = io.BytesIO(html_code.encode('utf-8'))
    html_file.name = f"{movie_title.replace(' ', '_')}_post.html"

    await message.reply_document(
        document=html_file,
        caption="💾 Here is your HTML file. Ready to be pasted into Blogger!"
    )

# ---- START THE BOT ----
print("🚀 Bot is starting...")
bot.run()
print("👋 Bot has stopped.")

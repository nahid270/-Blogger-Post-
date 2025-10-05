import os
import io
import requests
from pyrogram import Client, filters
from flask import Flask
from threading import Thread
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ---- CONFIG ----
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
TMDB_API_KEY = os.getenv("TMDB_API_KEY")

app = Flask(__name__)
bot = Client("moviebot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ---- SERVER KEEP ALIVE ----
@app.route('/')
def home():
    return "✅ Movie Bot is Running!"

def run():
    app.run(host='0.0.0.0', port=8080)

Thread(target=run).start()

# ---- TMDB FETCH FUNCTION ----
def get_movie_details(movie_name):
    url = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={movie_name}"
    response = requests.get(url).json()
    if response.get("results"):
        data = response["results"][0]
        movie_id = data["id"]
        details_url = f"https://api.themoviedb.org/3/movie/{movie_id}?api_key={TMDB_API_KEY}&language=en-US"
        details = requests.get(details_url).json()
        return details
    return None

# ---- HTML GENERATOR ----
def generate_html(movie):
    title = movie.get("title", "Unknown Title")
    year = movie.get("release_date", "N/A")[:4]
    rating = movie.get("vote_average", "N/A")
    overview = movie.get("overview", "No overview available.")
    genres = ", ".join([g["name"] for g in movie.get("genres", [])]) or "N/A"
    poster = f"https://image.tmdb.org/t/p/w500{movie.get('poster_path', '')}"
    backdrop = f"https://image.tmdb.org/t/p/original{movie.get('backdrop_path', '')}"

    html = f"""
<style>
.movie-card {{
  background: linear-gradient(135deg, #0f0f0f, #1f1f1f);
  color: #fff;
  font-family: 'Poppins', sans-serif;
  border-radius: 15px;
  padding: 15px;
  box-shadow: 0 0 10px #000;
}}
.movie-card img.poster {{
  width: 220px;
  border-radius: 10px;
  display: block;
  margin: auto;
}}
.movie-card h2 {{
  text-align: center;
  color: #00bcd4;
}}
.download-buttons a {{
  display: inline-block;
  background: linear-gradient(45deg, #ff512f, #dd2476);
  color: white;
  padding: 10px 20px;
  margin: 5px;
  border-radius: 10px;
  text-decoration: none;
  font-weight: bold;
  transition: 0.3s;
}}
.download-buttons a:hover {{
  transform: scale(1.1);
  background: linear-gradient(45deg, #24c6dc, #514a9d);
}}
</style>

<div class="movie-card">
  <h2>🎬 {title} ({year})</h2>
  <img class="poster" src="{poster}" alt="{title} Poster"/>
  <p><b>Genre:</b> {genres}</p>
  <p><b>IMDB:</b> ⭐ {rating}/10</p>
  <p><b>Overview:</b> {overview}</p>
  <img src="{backdrop}" width="100%" style="border-radius:10px;margin-top:10px;" alt="Backdrop"/>
  <div class="download-buttons">
    <a href="#">🔽 480p Download</a>
    <a href="#">🎥 720p Download</a>
    <a href="#">💎 1080p Download</a>
  </div>
</div>
"""
    return html

# ---- MOVIE SEARCH HANDLER ----
@bot.on_message(filters.private & ~filters.command("start"))
async def movie_info(client, message):
    movie_name = message.text.strip()
    await message.reply_text("🎬 Fetching movie details, please wait...")

    movie = get_movie_details(movie_name)
    if not movie:
        await message.reply_text("❌ Movie not found. Try again with a different name.")
        return

    html_code = generate_html(movie)

    await message.reply_text(
        f"✅ Here's your Blogger HTML post for **{movie.get('title')}**!\n\n"
        "_Just copy this and paste it in Blogger HTML mode._"
    )

    file = io.BytesIO(html_code.encode('utf-8'))
    file.name = "movie_post.html"

    await message.reply_document(
        document=file,
        caption="💾 Copy this HTML and paste into Blogger!"
    )

# ---- START ----
bot.run()

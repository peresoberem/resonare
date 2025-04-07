from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
import os
import logging
import requests
import json

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("main")

# Загрузка переменных окружения
load_dotenv()

client_id = os.getenv("SPOTIFY_CLIENT_ID")
client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")

if not client_id or not client_secret:
    logger.error("SPOTIFY_CLIENT_ID или SPOTIFY_CLIENT_SECRET не найдены в .env")
    raise ValueError("Missing Spotify credentials")

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Простейшая модель формы
class MoodForm(BaseModel):
    intention: str

# Привязка намерения к категории
MOOD_TO_CATEGORY = {
    "energy": "workout",
    "reflection": "mood",
    "relax": "chill",
    "focus": "focus",
    "party": "party"
}

def get_spotify_token():
    logger.info("\n\n🎫 Получаем токен Spotify...")
    try:
        auth_response = requests.post(
            'https://accounts.spotify.com/api/token',
            data={'grant_type': 'client_credentials'},
            auth=(client_id, client_secret)
        )
        auth_response.raise_for_status()
        token = auth_response.json().get("access_token")
        if not token:
            logger.error("❌ Не удалось получить access token")
            raise HTTPException(status_code=500, detail="Token missing")
        logger.info("✅ Токен получен")
        return token
    except Exception as e:
        logger.error(f"Ошибка при получении токена: {e}")
        raise HTTPException(status_code=500, detail="Token error")

@app.post("/api/generate_playlist")
async def generate_playlist(data: MoodForm):
    logger.info(f"Получены данные формы: intention='{data.intention}'")
    category_id = MOOD_TO_CATEGORY.get(data.intention, "mood")
    logger.info(f"Категория: {category_id}")

    token = get_spotify_token()
    headers = {"Authorization": f"Bearer {token}"}

    try:
        # Шаг 1: получить плейлисты из категории
        playlist_resp = requests.get(
            f"https://api.spotify.com/v1/browse/categories/{category_id}/playlists",
            headers=headers,
            params={"limit": 1}
        )
        playlist_resp.raise_for_status()
        playlists_data = playlist_resp.json()

        playlist_items = playlists_data.get("playlists", {}).get("items", [])
        if not playlist_items:
            logger.warning("Нет плейлистов в категории")
            return {"error": "No playlists found"}

        playlist_id = playlist_items[0]["id"]
        logger.info(f"Используем плейлист: {playlist_id}")

        # Шаг 2: получить треки из плейлиста
        tracks_resp = requests.get(
            f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks",
            headers=headers,
            params={"limit": 10}
        )
        tracks_resp.raise_for_status()
        tracks_data = tracks_resp.json()

        tracks = []
        for item in tracks_data.get("items", []):
            track = item.get("track")
            if not track:
                continue
            tracks.append({
                "name": track["name"],
                "artist": track["artists"][0]["name"] if track["artists"] else "Unknown",
                "url": track["external_urls"]["spotify"],
                "preview_url": track.get("preview_url")
            })

        return {"tracks": tracks}
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка при получении плейлиста: {e}")
        raise HTTPException(status_code=500, detail=str(e))

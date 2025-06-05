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

# Привязка намерения к строкам поиска (альтернатива сломанным категориям)
MOOD_TO_QUERY = {
    "energy": "energetic workout",
    "reflection": "ambient reflective",
    "relax": "relaxing instrumental",
    "focus": "deep focus",
    "party": "party hits"
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
            logger.error("\u274c Не удалось получить access token")
            raise HTTPException(status_code=500, detail="Token missing")
        logger.info("\u2705 Токен получен")
        return token
    except Exception as e:
        logger.error(f"Ошибка при получении токена: {e}")
        raise HTTPException(status_code=500, detail="Token error")

@app.post("/api/generate_playlist")
async def generate_playlist(data: MoodForm):
    logger.info(f"Получены данные формы: intention='{data.intention}'")
    query = MOOD_TO_QUERY.get(data.intention, "chill")
    logger.info(f"🔍 Поисковый запрос: {query}")

    token = get_spotify_token()
    headers = {"Authorization": f"Bearer {token}"}

    try:
        search_resp = requests.get(
            "https://api.spotify.com/v1/search",
            headers=headers,
            params={"q": query, "type": "playlist", "limit": 1}
        )
        search_resp.raise_for_status()
        playlists_data = search_resp.json()

        playlists = playlists_data.get("playlists")
        if not playlists:
            logger.warning("Нет объекта playlists в ответе Spotify")
            return {"error": "No playlists object in response"}

        items = playlists.get("items")
        if not items or not isinstance(items, list) or not items[0]:
            logger.warning("Нет доступных или валидных плейлистов")
            return {"error": "No valid playlist found"}

        playlist_id = items[0].get("id")
        playlist_url = items[0].get("external_urls", {}).get("spotify")
        if not playlist_id:
            logger.warning("ID плейлиста отсутствует")
            return {"error": "Playlist ID not found"}

        logger.info(f"🎶 Используем найденный плейлист: {playlist_id}")

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

        logger.info(f"\u2705 Получено {len(tracks)} треков")
        return {
            "playlist_url": playlist_url,
            "tracks": tracks
        }
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка при получении данных: {e}")
        raise HTTPException(status_code=500, detail=str(e))

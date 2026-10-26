"""Minimal official VK API audio-search client; never downloads audio."""
import json
import urllib.error
import urllib.parse
import urllib.request

API_URL = "https://api.vk.com/method/audio.search"
API_VERSION = "5.199"
MAX_RESULTS = 10


class VKCatalogError(RuntimeError):
    """Raised when VK's API cannot complete a catalog search."""


def track_url(owner_id: int, audio_id: int) -> str:
    """Return the canonical VK page URL for a track, not its media file URL."""
    return f"https://vk.com/audio{int(owner_id)}_{int(audio_id)}"


def search_vk_audio(query: str, access_token: str, count: int = MAX_RESULTS) -> list[dict]:
    """Search audio metadata through VK API; does not download audio."""
    query = query.strip()
    token = access_token.strip()
    if not query:
        raise VKCatalogError("Search query cannot be empty")
    if not token:
        raise VKCatalogError("VK access token is not configured")
    count = min(max(int(count), 1), MAX_RESULTS)
    payload = urllib.parse.urlencode({
        "access_token": token, "v": API_VERSION, "q": query,
        "count": count, "auto_complete": 1, "sort": 2,
    }).encode("utf-8")
    request = urllib.request.Request(
        API_URL, data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise VKCatalogError("VK API request failed") from exc
    if not isinstance(data, dict):
        raise VKCatalogError("Unexpected VK API response")
    if data.get("error"):
        error = data["error"]
        code = error.get("error_code", "unknown") if isinstance(error, dict) else "unknown"
        raise VKCatalogError(f"VK API returned error {code}")
    response_data = data.get("response", {})
    items = response_data.get("items", []) if isinstance(response_data, dict) else []
    tracks = []
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            owner_id, audio_id = int(item["owner_id"]), int(item["id"])
        except (KeyError, TypeError, ValueError):
            continue
        title = str(item.get("title") or "").strip()
        artist = str(item.get("artist") or "").strip()
        if not title:
            continue
        tracks.append({
            "owner_id": owner_id, "id": audio_id, "title": title,
            "artist": artist or "Неизвестный исполнитель",
            "duration": max(0, int(item.get("duration") or 0)),
            "url": track_url(owner_id, audio_id),
        })
        if len(tracks) >= count:
            break
    return tracks

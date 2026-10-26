"""Application configuration loaded from environment variables."""
import os

from dotenv import load_dotenv

load_dotenv()


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(
            f"Missing required environment variable {name}. "
            "Copy .env.example to .env and configure it."
        )
    return value


BOT_TOKEN = required_env("BOT_TOKEN")
DATABASE_PATH = os.getenv("DATABASE_PATH", "data/music_bridge.db").strip()

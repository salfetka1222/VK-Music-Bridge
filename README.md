# VK Music Bridge

Telegram bot for keeping VK music links organized in a private Telegram chat.

## VK Music Bridge 2.0 preview (feature branch)

The `feature/v2-telegram-library-playlists` branch adds a Telegram button menu, per-user favorites, and per-user playlists. Existing `saved_links` rows and IDs are preserved; new tables are created additively (`favorites`, `playlists`, `playlist_links`).

- `/newplaylist Name` creates a playlist (name length up to 40 characters).
- Open **📚 Библиотека** from `/start`, then use each link's buttons to favorite it or add it to a playlist.
- **⭐ Избранное** shows links saved to favorites.
- **🎼 Плейлисты** lists playlists; select one to view its saved links.

Catalog search uses VK's official API method `audio.search` when a valid, authorized `VK_ACCESS_TOKEN` is configured. `/search query` searches the catalog; `/searchlinks query` searches the user's saved URLs. API availability depends on VK's permissions for the configured token. Results open the canonical VK track page and can be saved as links. The bot does not download audio.

## Current features

- Responds to `/start` and `/help`.
- Saves links from approved VK domains in a per-user SQLite library.
- Shows the latest saved links with `/library`.
- Searches the requesting user's saved URLs with `/search query` (up to 10 results).
- Deletes one of the user's own saved links with `/delete ID`.
- Avoids saving the same URL twice for the same Telegram user.

**Search scope:** `/search` searches URL text already saved in the user's library. It does not search VK's full audio catalog, because that requires a separately authorized and supported catalog API integration.

**This version saves links only. It does not download audio files.** Any future audio-import feature must use a permitted access method and only handle content the user is authorized to copy or share.

## Run locally

Requires Python 3.10 or newer.

1. Create a Telegram bot with [@BotFather](https://t.me/BotFather) and copy its token.
2. Install dependencies:

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

   On Windows, activate the environment with `.venv\\Scripts\\activate`.

3. Copy `.env.example` to `.env` and set `BOT_TOKEN` to your token.
4. If you have an access token obtained through a permitted official VK flow and the required API access, set `VK_ACCESS_TOKEN` in the hosting environment. Do not commit it to GitHub or send it in chat. If `audio.search` is not available for that token, catalog search will report that the API request failed.\n5. Start the bot:

   ```bash
   python bot.py
   ```

The SQLite database is created automatically at `data/music_bridge.db` by default. Set `DATABASE_PATH` to change the location.

## Commands

- `/start` — welcome message
- `/help` — instructions
- `/library` — latest saved links
- `/search Queen` — search the VK audio catalog (requires an authorized `VK_ACCESS_TOKEN`)\n- `/searchlinks vk.com` — search saved URLs by part of their address
- `/delete ID` — delete one of your saved links

## Deploy

The included `Procfile` starts the bot as a worker with `python bot.py`. Configure `BOT_TOKEN` as a secret/environment variable in your hosting provider. If the host has an ephemeral filesystem, attach persistent storage and point `DATABASE_PATH` to it, otherwise saved links may be lost on redeploy.

## Security

- Never commit `.env` or real bot tokens.
- Do not send your bot token in chat or in a public issue.
- The bot accepts only links whose hostname is on the VK allowlist; it does not fetch the URLs.
- SQL search uses parameterized queries and escapes LIKE wildcards.
- Search results and saved links are isolated by Telegram user ID.

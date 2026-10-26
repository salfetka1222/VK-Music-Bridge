# VK Music Bridge

Telegram bot for keeping VK music links organized in a private Telegram chat.

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
4. Start the bot:

   ```bash
   python bot.py
   ```

The SQLite database is created automatically at `data/music_bridge.db` by default. Set `DATABASE_PATH` to change the location.

## Commands

- `/start` — welcome message
- `/help` — instructions
- `/library` — latest saved links
- `/search vk.com` — search saved URLs by part of their address
- `/delete ID` — delete one of your saved links

## Deploy

The included `Procfile` starts the bot as a worker with `python bot.py`. Configure `BOT_TOKEN` as a secret/environment variable in your hosting provider. If the host has an ephemeral filesystem, attach persistent storage and point `DATABASE_PATH` to it, otherwise saved links may be lost on redeploy.

## Security

- Never commit `.env` or real bot tokens.
- Do not send your bot token in chat or in a public issue.
- The bot accepts only links whose hostname is on the VK allowlist; it does not fetch the URLs.
- SQL search uses parameterized queries and escapes LIKE wildcards.
- Search results and saved links are isolated by Telegram user ID.

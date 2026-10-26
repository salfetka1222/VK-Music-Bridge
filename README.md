# VK Music Bridge

Telegram bot for keeping VK music links organized in a private Telegram chat.

## Current status

The initial MVP is in place. It can:
- respond to `/start` and `/help`;
- save links from approved VK domains in a per-user SQLite library;
- show the latest saved links with `/library`;
- delete one of the user's own saved links with `/delete ID`;
- avoid saving the same URL twice for the same Telegram user.

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

## Deploy

The included `Procfile` starts the bot as a worker with `python bot.py`. Configure `BOT_TOKEN` as a secret/environment variable in your hosting provider. If the host has an ephemeral filesystem, attach persistent storage and point `DATABASE_PATH` to it, otherwise saved links may be lost on redeploy.

## Security

- Never commit `.env` or real bot tokens.
- Do not send your bot token in chat or in a public issue.
- The bot accepts only links whose hostname is on the VK allowlist; it does not fetch the URLs.
- Saved links are separated by Telegram user ID.

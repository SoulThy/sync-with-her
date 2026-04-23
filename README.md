# sync-with-her

A small **Telegram bot** workflow that downloads audio sent by whitelisted chats, runs **beets** to import it into your library, removes **duplicates** by artist/title (keeping the oldest copy), appends new tracks to an **M3U playlist**, and cleans the download folder.

Beets is used as a **command-line tool** (`beet`), not as a Python library inside this script.

## Requirements

- **Python** 3.10+ (the code uses modern type hints)
- A **Telegram bot token** from [@BotFather](https://t.me/BotFather)
- [**beets**](https://beets.io/) installed and available as `beet` on your `PATH`, with a working `~/.config/beets/config.yaml` (see `config.yaml.example` for a suggested plugin set: `chroma`, `spotify`, `deezer`, `fromfilename`)

## Setup

1. Clone the repository and create a virtual environment:

   ```bash
   cd sync-with-her
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env` and fill in the variables (see table below).

3. Configure beets (library path, plugins, etc.). You can start from `config.yaml.example` and install it as `~/.config/beets/config.yaml`.

4. Run once per invocation (the bot polls updates, processes them, then exits):

   ```bash
   python main.py
   ```

   This workflow is intended to be run **periodically** via a scheduler (e.g. cron, systemd timer) so new messages are picked up without keeping a long-lived process. **Run it at least once every 24 hours:** the Telegram Bot API does not keep pending updates indefinitely, so if you go longer than that between runs you can miss messages that arrived while the bot was idle.

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | yes | Bot token from BotFather |
| `DOWNLOADS_DIR_PATH` | yes | Directory where incoming audio is saved before `beet import` |
| `WHITELIST_CHAT_IDS` | yes | Comma-separated Telegram chat IDs (no spaces), e.g. `-1001234567890` for groups |
| `M3U_PLAYLIST_PATH` | no | If set, new imports are appended to this M3U file |
| `LOG_LEVEL` | no | `DEBUG`, `INFO`, … (default: `INFO`) |

## How it behaves

1. Starts the Telegram app, fetches pending updates, downloads **audio** messages from whitelisted chats into `DOWNLOADS_DIR_PATH`.
2. If the downloads directory is non-empty: `beet update`, then `beet import -qs` on that directory, duplicate removal by artist/title, optional playlist update, then emptying the downloads folder.

Ensure your beets `directory` / `library` paths and import options match how you want files moved or copied.

## Files

| File | Purpose |
|------|---------|
| `main.py` | Bot + beets orchestration |
| `.env.example` | Template for secrets and paths |
| `config.yaml.example` | Example beets configuration (install under `~/.config/beets/config.yaml`) |
| `requirements.txt` | Python packages for the bot and documented beets-related deps |

## Security

- Never commit `.env` or real tokens.
- Restrict `WHITELIST_CHAT_IDS` to chats you control.

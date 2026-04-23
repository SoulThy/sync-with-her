import logging
import os
import sys
import asyncio
import re
import subprocess
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Set, Optional

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ContextTypes, ApplicationBuilder, MessageHandler, filters

# --- Loading environment variables and logging ---
ENV_FILE = Path(".env")
load_dotenv(ENV_FILE)

log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=getattr(logging, log_level, logging.INFO)
)
logger = logging.getLogger(__name__)

# --- Configuration ---
@dataclass
class Config:
    token: str
    path_to_m3u: Optional[Path]
    downloads_path: Path
    whitelist_chat_ids: Set[int]

def load_config() -> Config:
    try:
        p_env = os.environ.get("M3U_PLAYLIST_PATH")

        return Config(
            token=os.environ["TELEGRAM_BOT_TOKEN"],
            path_to_m3u=Path(p_env) if p_env else None,
            downloads_path=Path(os.environ["DOWNLOADS_DIR_PATH"]),
            whitelist_chat_ids=set(map(int, os.environ["WHITELIST_CHAT_IDS"].split(","))),
        )
    except KeyError as e:
        logger.error(f"Variable {e} is missing from the environment")
        sys.exit(1)
    except ValueError as e:
        logger.error(f"Variable {e} is not a valid value")
        sys.exit(1)

# --- Telegram bot logic ---
class HerEchoBot:
    def __init__(self, config: Config):
        self.config = config
        self.app = ApplicationBuilder().token(config.token).build()
        self._add_handlers()

    def _add_handlers(self):
        """Adds handlers for the bot"""
        whitelist_filter = filters.Chat(chat_id=self.config.whitelist_chat_ids)
        self.app.add_handler(MessageHandler(
            filters.AUDIO & whitelist_filter,
            self._handle_audio_message
        ))

    def _sanitize_filename(self, name: str) -> str:
        """Sanitizes a filename by removing special characters and whitespace"""
        return re.sub(r'[<>:"/\\|?*]', '', name).strip()

    def _generate_file_name(self, audio) -> str:
        """Generates a file name for the audio file based on the title and artist, 
            if available. If not, it uses the file name or "audio" as a fallback."""
        title = audio.title
        performer = audio.performer
        extension = Path(audio.file_name).suffix if audio.file_name else ".mp3"

        # 1. Title and performer
        if title and performer and performer.lower() != "unknown artist":
            base_name = f"{performer} - {title}"
        # 2. Title only
        elif title:
            base_name = title
        # 3. Fallback, cleaned name of the file
        else:
            raw_name = re.sub(r'^\d{10,}|\[\d+\]', '', audio.file_name or "audio").strip()
            base_name = Path(raw_name).stem or "audio"

        clean_name = self._sanitize_filename(base_name)
        return f"{clean_name}{extension}"

    async def _handle_audio_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handles an audio message"""
        audio = update.message.audio
        if not audio:
            return

        final_name = self._generate_file_name(audio)
        custom_path = self.config.downloads_path / final_name

        file = await context.bot.get_file(file_id=audio.file_id)
        path = await file.download_to_drive(custom_path=custom_path)

        logger.info(f"Audio file downloaded to {path}")

    async def execute_once(self):
        """Executes the bot once, processing all the updates 
            it has received and stopping"""

        try:
            await self.app.initialize()
            await self.app.start()

            logger.info("Bot is checking for messages...")
            updates = await self.app.bot.get_updates(timeout=5)

            if updates:
                for update in updates:
                    await self.app.process_update(update)

                await self.app.bot.get_updates(offset=updates[-1].update_id + 1)
                logger.info(f"Bot has processed {len(updates)} updates")
            else:
                logger.info("No updates found.")

        except Exception as e:
            logger.error(f"Error while processing updates: {e}")

        finally:
            await self.app.stop()
            await self.app.shutdown()

# --- Beets Logic ---
def run_beets_update():
    logger.info("Running beets update to sync with beetsdb")
    subprocess.run(["beet", "update"], check=True)

def run_beets_import(downloads_path: Path):
    logger.info("Running beets import")
    subprocess.run(["beet", "import", "-qs", downloads_path], check=True)

def get_added_tracks_info(start_time: str) -> list[dict]:
    query = f"added:{start_time}.."
    output = subprocess.run(
            ["beet", "ls", "-f", "$id\t$artist\t$title\t$path", query],
            text=True,
            check=True,
            capture_output=True
    )

    tracks_info = []
    for line in output.stdout.splitlines():
        if "\t" in line:
            t_id, artist, title, path = line.split("\t", 3)
            tracks_info.append({
                "id": t_id, 
                "artist": artist,
                "title": title, 
                "path": path
            })

    return tracks_info

def update_playlist(path_to_m3u: Path, track_paths: list[Path]):
    logger.info(f"Updating playlist {path_to_m3u}")

    path_to_m3u.parent.mkdir(parents=True, exist_ok=True)
    # Check if the file is empty or doesn't exist to add the header
    write_header = not path_to_m3u.exists() or path_to_m3u.stat().st_size == 0
    with open(path_to_m3u, "a", encoding="utf-8") as f:
        if write_header:
            f.write("#EXTM3U\n")
        for track_path in track_paths:
            relative_path = os.path.relpath(track_path, start=path_to_m3u.parent)
            f.write(f"{relative_path}\n")
    
def add_tracks_to_playlist(path_to_m3u: Path, start_time: str):
    track_info = get_added_tracks_info(start_time)
    track_paths = [Path(track["path"]) for track in track_info]

    update_playlist(path_to_m3u, track_paths)

def remove_duplicates(start_time: str):
    logger.info("Removing duplicate tracks, leaving the oldest")

    tracks_info = get_added_tracks_info(start_time)
    recent_tracks = set((track["artist"], track["title"]) for track in tracks_info)

    for artist, title in recent_tracks:
        output = subprocess.run(
                     ["beet", "ls", "-f", "$id", f"artist:{artist}", f"title:{title}", "added+"],
                     text=True,
                     check=True,
                     capture_output=True
        )
        track_ids = output.stdout.splitlines()

        for duplicate_id in track_ids[1:]:
            logger.info(f"Removing duplicate ID {duplicate_id} ({artist} - {title})")
            subprocess.run(
                ["beet", "rm", "-d", "-f", f"id:{duplicate_id}"], 
                check=True
            )

def clean_downloads(downloads_path: Path):
    logger.info(f"Cleaning up downloads in {downloads_path}")
    for file in downloads_path.iterdir():
        if file.is_file():
            file.unlink()

# --- Main ---
async def main():
    start_time = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')

    config = load_config()
    bot = HerEchoBot(config)
    await bot.execute_once()

    if any(config.downloads_path.iterdir()):
        run_beets_import(config.downloads_path)
        remove_duplicates(start_time)
        if config.path_to_m3u:
            add_tracks_to_playlist(config.path_to_m3u, start_time)
        run_beets_update()

    if any(config.downloads_path.iterdir()):
        clean_downloads(config.downloads_path)



if __name__ == "__main__":
    asyncio.run(main())

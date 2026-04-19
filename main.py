import logging
import os
import sys
import asyncio
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Set

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
    downloads_path: Path
    checkpoints_path: Path
    whitelist_chat_ids: Set[int]

def load_config() -> Config:
    try:
        return Config(
            token=os.environ["TELEGRAM_BOT_TOKEN"],
            downloads_path=Path(os.environ["DOWNLOADS_DIR_PATH"]),
            checkpoints_path=Path(os.environ["CHECKPOINTS_DIR_PATH"]),
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

# --- Main ---
async def main():
    config = load_config()
    bot = HerEchoBot(config)
    await bot.execute_once()

if __name__ == "__main__":
    asyncio.run(main())

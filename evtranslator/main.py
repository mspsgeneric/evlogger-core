# main.py
import logging
from evtranslator.config import DISCORD_TOKEN, DB_PATH
from evtranslator.bot import EVTranslatorBot

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s"
)

if __name__ == "__main__":
    bot = EVTranslatorBot(db_path=DB_PATH)
    bot.run(DISCORD_TOKEN)

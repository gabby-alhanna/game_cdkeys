import asyncio
import os
import logging
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, BaseMiddleware
from aiogram.types import Update
from aiogram.exceptions import TelegramNetworkError, TelegramRetryAfter
from handlers import all_routers
from database import db
from static_lists import load_special_buttons, SPECIAL_BUTTONS

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TypingMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: Update, data: dict):
        if event.message:
            chat_id = event.message.from_user.id
        elif event.callback_query:
            chat_id = event.callback_query.from_user.id
        else:
            return await handler(event, data)
        await data['bot'].send_chat_action(chat_id=chat_id, action="typing")
        return await handler(event, data)

async def on_startup():
    await db.connect()
    await db.create_tables()
    await load_special_buttons()
    logger.info(SPECIAL_BUTTONS)
    logger.info("🚀 Bot Started Successfully")

async def on_shutdown():
    await db.close()
    logger.info("🛑 Bot Stopped")

async def start_with_retry(bot, dp):
    """Start polling with retries on network errors."""
    max_retries = 5
    for attempt in range(1, max_retries + 1):
        try:
            await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
            break  # success
        except TelegramNetworkError as e:
            logger.warning(f"Network error on attempt {attempt}/{max_retries}: {e}")
            if attempt == max_retries:
                raise
            wait = 2 ** attempt  # exponential backoff
            logger.info(f"Retrying in {wait} seconds...")
            await asyncio.sleep(wait)

async def main():
    bot = Bot(token=os.getenv("BOT_TOKEN"), timeout=30)
    dp = Dispatcher()

    dp.update.middleware(TypingMiddleware())

    for router in all_routers:
        dp.include_router(router)

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    except Exception as e:
        logger.critical(f"Unexpected error: {e}")
    finally:
        await bot.session.close()
if __name__ == "__main__":
    asyncio.run(main())
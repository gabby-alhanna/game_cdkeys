import asyncio
import os
import logging
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher
from handlers import all_routers
from database import db 
from static_lists import load_special_buttons
from aiogram import BaseMiddleware
from aiogram.types import Update, Message, CallbackQuery

load_dotenv()


class TypingMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: Update, data: dict):
        # Check if the update contains a message or callback
        if event.message:
            chat_id = event.message.from_user.id
        elif event.callback_query:
            chat_id = event.callback_query.from_user.id
        else:
            return await handler(event, data)
        
        # Send typing action
        await data['bot'].send_chat_action(chat_id=chat_id, action="typing")
        
        # Process the actual handler
        return await handler(event, data)

# Register middleware

async def main():
    logging.basicConfig(level=logging.INFO)
    
    bot = Bot(token=os.getenv("BOT_TOKEN"))
    dp = Dispatcher()

    dp.update.middleware(TypingMiddleware())    
    
    # Include routers
    for router in all_routers:
        dp.include_router(router)

    async def on_startup():
        await db.connect()
        await db.create_tables()
        await load_special_buttons()
        print("🚀 Bot Started Successfully")

    dp.startup.register(on_startup)

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
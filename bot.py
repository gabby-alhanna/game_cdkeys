import asyncio
import os
import logging
from aiohttp import web  # Ensure aiohttp is in your requirements.txt
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher
from handlers import all_routers
from database import db 
from static_lists import load_special_buttons
from aiogram import BaseMiddleware
from aiogram.types import Update

load_dotenv()

# --- Middleware ---
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

# --- Health Check Logic ---
async def handle_ping(request):
    """Answers the Koyeb/UptimeRobot health check."""
    return web.Response(text="Bot is active and polling!", status=200)

async def main():
    logging.basicConfig(level=logging.INFO)
    
    bot = Bot(token=os.getenv("BOT_TOKEN"))
    dp = Dispatcher()

    # Register middleware
    dp.update.middleware(TypingMiddleware())    
    
    # Include routers
    for router in all_routers:
        dp.include_router(router)

    # Startup logic
    async def on_startup():
        await db.connect()
        await db.create_tables()
        await load_special_buttons()
        print("🚀 Bot Started Successfully")

    dp.startup.register(on_startup)

    # --- Setup Web Server for Health Check ---
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    
    # Koyeb passes the port as an environment variable, usually 8000
    port = int(os.getenv("PORT", 8000)) 
    site = web.TCPSite(runner, '0.0.0.0', port)
    
    await site.start()
    print(f"🌍 Health check server listening on port {port}")

    try:
        # Start bot polling
        await dp.start_polling(bot)
    finally:
        # Clean up
        await bot.session.close()
        await runner.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
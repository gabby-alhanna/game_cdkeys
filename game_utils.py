from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram import types
from database import db

PAGE_SIZE = 3

async def get_games(page: int = 0, only_active: bool = True):
    """Fetch games with pagination."""
    offset = page * PAGE_SIZE
    query = "SELECT id, name, image_file_id, description FROM games"
    if only_active:
        query += " WHERE is_active = TRUE"
    query += " ORDER BY name LIMIT $1 OFFSET $2"
    return await db.fetch(query, PAGE_SIZE, offset)

async def count_games(only_active: bool = True):
    query = "SELECT COUNT(*) FROM games"
    if only_active:
        query += " WHERE is_active = TRUE"
    return await db.fetchval(query)

async def get_game(game_id: str):
    return await db.fetchrow("SELECT * FROM games WHERE id = $1", game_id)

async def get_packages(game_id: str, page: int = 0):
    offset = page * PAGE_SIZE
    return await db.fetch(
        "SELECT id, name, price FROM game_packages WHERE game_id = $1 ORDER BY name LIMIT $2 OFFSET $3",
        game_id, PAGE_SIZE, offset
    )

async def count_packages(game_id: str):
    return await db.fetchval("SELECT COUNT(*) FROM game_packages WHERE game_id = $1", game_id)

def pagination_keyboard(prefix: str, current_page: int, total_pages: int, extra_buttons=None):
    """Build inline keyboard with prev/next and extra buttons."""
    builder = InlineKeyboardBuilder()
    if total_pages > 1:
        row = []
        if current_page > 0:
            row.append(types.InlineKeyboardButton(text="◀️", callback_data=f"{prefix}_page:{current_page-1}"))
        row.append(types.InlineKeyboardButton(text=f"{current_page+1}/{total_pages}", callback_data="ignore"))
        if current_page < total_pages-1:
            row.append(types.InlineKeyboardButton(text="▶️", callback_data=f"{prefix}_page:{current_page+1}"))
        builder.row(*row)
    if extra_buttons:
        for btn in extra_buttons:
            builder.row(btn)
    return builder
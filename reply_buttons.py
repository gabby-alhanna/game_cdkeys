from database import db
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

async def get_button(button_key: str):
    return await db.fetchrow("SELECT * FROM reply_buttons WHERE button_key = $1", button_key)

async def get_all_buttons():
    return await db.fetch("SELECT * FROM reply_buttons ORDER BY button_key")

async def update_button(button_key: str, display_text: str = None, image_file_id: str = None, description: str = None):
    sets = []
    args = []
    if display_text is not None:
        sets.append(f"display_text = ${len(args)+1}")
        args.append(display_text)
    if image_file_id is not None:
        sets.append(f"image_file_id = ${len(args)+1}")
        args.append(image_file_id)
    if description is not None:
        sets.append(f"description = ${len(args)+1}")
        args.append(description)
    if not sets:
        return
    args.append(button_key)
    query = f"UPDATE reply_buttons SET {', '.join(sets)}, updated_at = NOW() WHERE button_key = ${len(args)}"
    await db.execute(query, *args)

async def build_reply_keyboard(is_admin: bool):
    buttons = await get_all_buttons()
    rows = []
    main_btn = next((b for b in buttons if b['button_key'] == 'main'), None)
    help_btn = next((b for b in buttons if b['button_key'] == 'help'), None)
    about_btn = next((b for b in buttons if b['button_key'] == 'about'), None)

    if main_btn:
        rows.append([KeyboardButton(text=main_btn['display_text'])])
    if help_btn and about_btn:
        rows.append([KeyboardButton(text=help_btn['display_text']),
                     KeyboardButton(text=about_btn['display_text'])])

    if is_admin:
        rows.append([KeyboardButton(text="⚙️ الإعدادات")])

    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, one_time_keyboard=False)
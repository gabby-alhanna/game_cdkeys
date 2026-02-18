from database import db

SPECIAL_BUTTONS = set()

async def load_special_buttons():
    """Fetch all display_text from reply_buttons and add Settings button and /start."""
    rows = await db.fetch("SELECT display_text FROM reply_buttons")
    texts = {row['display_text'] for row in rows}
    texts.add("⚙️ الإعدادات")   # admin settings button
    texts.add("/start")          # command

    global SPECIAL_BUTTONS
    # Mutate the existing set, do NOT reassign
    SPECIAL_BUTTONS.clear()
    SPECIAL_BUTTONS.update(texts)
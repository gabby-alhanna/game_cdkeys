from database import db

SPECIAL_BUTTONS = set()

async def load_special_buttons():
    """Fetch all display_text from reply_buttons and add Settings button."""
    rows = await db.fetch("SELECT display_text FROM reply_buttons")
    texts = {row['display_text'] for row in rows}
    texts.add("⚙️ الإعدادات")   # always include admin settings button
    global SPECIAL_BUTTONS
    SPECIAL_BUTTONS = texts
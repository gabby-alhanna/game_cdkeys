from database import db

async def get_or_create_user(chat_id, full_name):
    user = await db.fetchrow("SELECT * FROM users WHERE chat_id = $1", chat_id)
    if not user:
        await db.execute(
            "INSERT INTO users (chat_id, full_name, balance) VALUES ($1, $2, 0.00)",
            chat_id, full_name
        )
        user = await db.fetchrow("SELECT * FROM users WHERE chat_id = $1", chat_id)
    return user

async def get_system_settings():
    return await db.fetchrow("SELECT superadmin_shamcash_code, superadmin_qr_file_id FROM system_settings WHERE id=1")

async def is_system_ready():
    s = await get_system_settings()
    if not s or not s['superadmin_shamcash_code'] or not s['superadmin_qr_file_id']:
        return False, {}
    return True, dict(s)
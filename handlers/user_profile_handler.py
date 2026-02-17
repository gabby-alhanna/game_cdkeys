import os
import html
from aiogram import Router, types, F
from database import db

router = Router()

def escape_html(text):
    return html.escape(str(text) if text is not None else "")

@router.callback_query(F.data.startswith("admin_user_info:"))
async def admin_user_info(callback: types.CallbackQuery):
    user_chat_id = int(callback.data.split(":")[1])
    user = await db.fetchrow("SELECT * FROM users WHERE chat_id = $1", user_chat_id)
    if not user:
        await callback.answer("المستخدم غير موجود.", show_alert=True)
        return
    # آخر 5 عمليات
    txs = await db.fetch("""
        SELECT amount, type, description, created_at
        FROM transactions
        WHERE user_id = $1
        ORDER BY created_at DESC
        LIMIT 5
    """, user['id'])
    tx_lines = []
    for tx in txs:
        type_ar = "شحن" if tx['type'] == 'charge' else "شراء"
        line = f"• {tx['created_at'].strftime('%Y-%m-%d %H:%M')} – {type_ar}: {tx['amount']} ل.س"
        if tx['description']:
            line += f" ({escape_html(tx['description'])})"
        tx_lines.append(line)
    tx_text = "\n".join(tx_lines) if tx_lines else "لا توجد عمليات بعد."

    text = (
        f"👤 **ملف المستخدم**\n\n"
        f"ID: <code>{user['chat_id']}</code>\n"
        f"الاسم: {escape_html(user['full_name'])}\n"
        f"الرصيد: {user['balance']} ل.س\n"
        f"تاريخ الانضمام: {user['created_at'].strftime('%Y-%m-%d') if user.get('created_at') else 'غير معروف'}\n\n"
        f"**آخر العمليات:**\n{tx_text}"
    )
    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()
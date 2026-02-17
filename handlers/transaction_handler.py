from aiogram import Router, types, F
from database import db
import html
from datetime import datetime
from aiogram.utils.keyboard import InlineKeyboardBuilder

router = Router()

def escape_html(text):
    return html.escape(str(text) if text is not None else "")

def format_datetime(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M")

@router.callback_query(F.data == "view_history")
async def view_history(callback: types.CallbackQuery):
    user_chat_id = callback.from_user.id
    user_uuid = await db.fetchval("SELECT id FROM users WHERE chat_id = $1", user_chat_id)
    if not user_uuid:
        await callback.answer("❌ المستخدم غير موجود. الرجاء بدء البوت أولاً.", show_alert=True)
        await callback.answer()
        return

    transactions = await db.fetch("""
        SELECT amount, type, description, created_at
        FROM transactions
        WHERE user_id = $1
        ORDER BY created_at DESC
        LIMIT 20
    """, user_uuid)

    if not transactions:
        await callback.answer("📭 لا توجد عمليات حتى الآن.", show_alert=True)
        return
    else:
        lines = ["📜 <b>سجل عملياتك</b>\n"]
        for tx in transactions:
            emoji = "💰" if tx['type'] == 'charge' else "🛒"
            amount = tx['amount']
            if amount == amount.to_integral():
                amount_str = f"{amount:.0f}"
            else:
                amount_str = f"{amount:.2f}"
            date_str = format_datetime(tx['created_at'])
            desc = tx['description']
            desc_text = f" — {escape_html(desc)}" if desc else ""
            line = (
                f"{emoji} <b>{'شحن' if tx['type'] == 'charge' else 'شراء'}</b>  |  "
                f"{amount_str} ل.س  |  {date_str}{desc_text}"
            )
            lines.append(line)
        if len(transactions) == 20:
            lines.append("\n⏳ عرض آخر 20 عملية. للعمليات الأقدم، اتصل بالدعم.")
        full_text = "\n".join(lines)
        kb = InlineKeyboardBuilder()
        kb.row(types.InlineKeyboardButton(text="🔙 رجوع", callback_data="back_to_main"))
        
        await callback.message.answer(
            full_text, 
            parse_mode="HTML", 
            reply_markup=kb.as_markup()
        )

    # حذف الرسالة الأصلية التي تحتوي على الزر
    await callback.message.delete()
    await callback.answer()
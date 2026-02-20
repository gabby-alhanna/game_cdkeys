import os
import html
import random
import string
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from database import db
from static_lists import SPECIAL_BUTTONS
from .common_handlers import get_cancel_button
from datetime import datetime

router = Router()
ADMIN_ID = int(os.getenv("ADMIN_CHAT_ID"))

def escape_html(text):
    return html.escape(str(text) if text is not None else "")

PAGE_SIZE = 10

class ReferralSettings(StatesGroup):
    waiting_milestone = State()

async def get_referral_count(user_uuid: str) -> int:
    return await db.fetchval("SELECT COUNT(*) FROM referrals WHERE inviter_id = $1", user_uuid) or 0

def generate_referral_code(length=8):
    chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for _ in range(length))

async def get_or_create_referral_code(user_id: str) -> str:
    code = await db.fetchval("SELECT code FROM referral_links WHERE user_id = $1", user_id)
    if code:
        return code
    while True:
        new_code = generate_referral_code()
        exists = await db.fetchval("SELECT 1 FROM referral_links WHERE code = $1", new_code)
        if not exists:
            await db.execute(
                "INSERT INTO referral_links (user_id, code) VALUES ($1, $2)",
                user_id, new_code
            )
            return new_code

@router.callback_query(F.data == "referral_menu")
async def referral_menu(callback: types.CallbackQuery, state: FSMContext):
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="👥 الأشخاص المدعون من قبلك", callback_data="referral_list:0"))
    builder.row(types.InlineKeyboardButton(text="🔗 رابط الانضمام", callback_data="referral_link"))
    builder.row(types.InlineKeyboardButton(text="🔙 رجوع إلى الرئيسية", callback_data="back_to_main"))
    await callback.message.edit_text(
        "🎁 **نظام الإحالة**\nاختر أحد الخيارات:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data == "referral_link")
async def referral_link_handler(callback: types.CallbackQuery):
    user_id = await db.fetchval("SELECT id FROM users WHERE chat_id = $1", callback.from_user.id)
    if not user_id:
        await callback.answer("حدث خطأ. حاول مرة أخرى.", show_alert=True)
        return
    code = await get_or_create_referral_code(user_id)
    bot_username = (await callback.bot.me()).username
    link = f"https://t.me/{bot_username}?start={code}"
    text = (
        f"🔗 **رابط الدعوة الخاص بك:**\n\n"
        f"<code>{link}</code>\n\n"
        f"أرسل هذا الرابط لأصدقائك. كلما انضم أحدهم عبر الرابط، سيتم احتسابه في قائمة المدعين."
    )
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🔙 رجوع", callback_data="referral_menu"))
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.startswith("referral_list:"))
async def referral_list(callback: types.CallbackQuery):
    page = int(callback.data.split(":")[1])
    await show_referrals_page(callback, page)

async def show_referrals_page(target, page: int):
    if isinstance(target, types.CallbackQuery):
        message = target.message
        is_callback = True
        user_chat_id = target.from_user.id
    else:
        message = target
        is_callback = False
        user_chat_id = target.chat.id

    inviter_uuid = await db.fetchval("SELECT id FROM users WHERE chat_id = $1", user_chat_id)
    if not inviter_uuid:
        await message.answer("حدث خطأ.")
        return

    offset = page * PAGE_SIZE
    referrals = await db.fetch("""
        SELECT u.chat_id, u.full_name, r.created_at
        FROM referrals r
        JOIN users u ON u.id = r.invited_id
        WHERE r.inviter_id = $1
        ORDER BY r.created_at DESC
        LIMIT $2 OFFSET $3
    """, inviter_uuid, PAGE_SIZE, offset)

    total = await db.fetchval("SELECT COUNT(*) FROM referrals WHERE inviter_id = $1", inviter_uuid)
    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE

    if not referrals:
        text = "لم تقم بدعوة أي شخص بعد."
    else:
        lines = [f"📋 **المدعون من قبلك (صفحة {page+1}/{total_pages})**\n"]
        for ref in referrals:
            try:
                chat = await message.bot.get_chat(ref['chat_id'])
                username = f"@{chat.username}" if chat.username else "—"
            except:
                username = "—"
            created = ref['created_at'].strftime('%Y-%m-%d %H:%M')
            lines.append(
                f"👤 {escape_html(ref['full_name'])} | {username}\n"
                f"📅 {created}\n"
                + "-"*30
            )
        text = "\n".join(lines)

    builder = InlineKeyboardBuilder()
    if total_pages > 1:
        nav_row = []
        if page > 0:
            nav_row.append(types.InlineKeyboardButton(text="◀️", callback_data=f"referral_list:{page-1}"))
        nav_row.append(types.InlineKeyboardButton(text=f"{page+1}/{total_pages}", callback_data="ignore"))
        if page < total_pages-1:
            nav_row.append(types.InlineKeyboardButton(text="▶️", callback_data=f"referral_list:{page+1}"))
        builder.row(*nav_row)
    builder.row(types.InlineKeyboardButton(text="🔙 رجوع", callback_data="referral_menu"))

    if is_callback:
        await message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    else:
        await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")

# -------------------------------------------------------------------
# Admin referral settings
# -------------------------------------------------------------------
@router.callback_query(F.data == "admin_referral_settings")
async def admin_referral_settings(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("غير مصرح.", show_alert=True)
        return
    milestone = await db.fetchval("SELECT referral_milestone FROM system_settings WHERE id=1") or 15
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text=f"🔢 تغيير العدد (الحالي: {milestone})", callback_data="change_milestone"))
    builder.row(types.InlineKeyboardButton(text="🔙 رجوع", callback_data="back_to_settings"))
    await callback.message.edit_text(
        "⚙️ **إعدادات الإحالة**\n"
        f"العدد الحالي للإشعار: {milestone}\n"
        "سيتم إشعار المشرف عند وصول المستخدم لهذا العدد.",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data == "change_milestone")
async def change_milestone_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(ReferralSettings.waiting_milestone)
    builder = get_cancel_button()
    await callback.message.edit_text(
        "✏️ أدخل العدد الجديد (يجب أن يكون رقماً صحيحاً موجباً):",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()

@router.message(ReferralSettings.waiting_milestone, F.text.not_in(SPECIAL_BUTTONS))
async def set_milestone(message: types.Message, state: FSMContext):
    try:
        new_milestone = int(message.text)
        if new_milestone <= 0:
            raise ValueError
    except:
        await message.answer("❌ الرجاء إدخال رقم صحيح موجب.")
        return
    await db.execute("UPDATE system_settings SET referral_milestone = $1 WHERE id=1", new_milestone)
    await message.answer(f"✅ تم تحديث العدد إلى {new_milestone}.")
    await state.clear()
    # Return to referral settings
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🔙 العودة إلى إعدادات الإحالة", callback_data="admin_referral_settings"))
    await message.answer("يمكنك العودة إلى الإعدادات.", reply_markup=builder.as_markup())

@router.callback_query(F.data == "back_to_settings")
async def back_to_settings(callback: types.CallbackQuery, state: FSMContext):
    from .settings_handler import show_settings_menu
    await show_settings_menu(callback.message, state)
    await callback.message.delete()
    await callback.answer()

# -------------------------------------------------------------------
# Process referral when user joins via link
# -------------------------------------------------------------------
async def process_referral(new_user_chat_id: int, code: str, bot):
    inviter_id = await db.fetchval("SELECT user_id FROM referral_links WHERE code = $1", code)
    if not inviter_id:
        return

    inviter_chat_id = await db.fetchval("SELECT chat_id FROM users WHERE id = $1", inviter_id)
    if not inviter_chat_id:
        return

    if inviter_chat_id == new_user_chat_id:
        return

    new_user_id = await db.fetchval("SELECT id FROM users WHERE chat_id = $1", new_user_chat_id)
    if not new_user_id:
        return

    existing = await db.fetchval("SELECT 1 FROM referrals WHERE invited_id = $1", new_user_id)
    if existing:
        return

    await db.execute("INSERT INTO referrals (inviter_id, invited_id) VALUES ($1, $2)", inviter_id, new_user_id)

    # Notify inviter
    invited_user = await db.fetchrow("SELECT full_name FROM users WHERE id = $1", new_user_id)
    invited_name = invited_user['full_name'] if invited_user else "شخص"
    invite_count = await db.fetchval("SELECT COUNT(*) FROM referrals WHERE inviter_id = $1", inviter_id)
    notification = (
        f"🎉 شخص جديد انضم عبر رابطك!\n"
        f"👤 {escape_html(invited_name)}\n"
        f"📊 لديك الآن {invite_count} دعوة."
    )
    await bot.send_message(inviter_chat_id, notification, parse_mode="HTML")

    # Check for milestone
    milestone = await db.fetchval("SELECT referral_milestone FROM system_settings WHERE id=1") or 15
    if invite_count % milestone == 0:
        inviter_user = await db.fetchrow("SELECT chat_id, full_name FROM users WHERE id = $1", inviter_id)
        if inviter_user:
            text = f"🎉 **مبروك!** المستخدم {escape_html(inviter_user['full_name'])} (ID: {inviter_user['chat_id']}) وصل إلى {invite_count} دعوة! يمكنك الآن مكافأته."
            await bot.send_message(ADMIN_ID, text, parse_mode="HTML")
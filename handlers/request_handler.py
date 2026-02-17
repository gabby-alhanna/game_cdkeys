from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database import db  # assuming db has execute, fetch, fetchrow, fetchval
from aiogram.utils.keyboard import InlineKeyboardBuilder
from database_methods import is_system_ready
from .common_handlers import get_cancel_button
from aiogram.exceptions import TelegramBadRequest
import os
import html
import logging
from decimal import Decimal, InvalidOperation
from static_lists import SPECIAL_BUTTONS

router = Router()
ADMIN_ID = int(os.getenv("ADMIN_CHAT_ID"))

# تخزين معرفات آخر رسائل "عرض الطلبات" لكل مشرف
# المفتاح: chat_id المشرف، القيمة: قائمة معرفات الرسائل
_last_request_messages = {}

class UserCharge(StatesGroup):
    waiting_transfer_code = State()
    waiting_description = State()
    waiting_amount = State()  # للمشرف

async def get_username_display(bot, user_id: int, full_name: str) -> str:
    """الحصول على اسم المستخدم مع @ إن وجد، وإلا الاسم الكامل."""
    try:
        chat = await bot.get_chat(user_id)
        if chat.username:
            return f"@{chat.username}"
    except:
        pass
    return full_name

async def format_balance_request(
    data: dict,
    bot,
    include_user_info: bool = True,
    include_request_id: bool = False,
    include_balance: bool = False,
    status: str = None,
    new_balance: Decimal = None
) -> str:
    """تنسيق تفاصيل طلب شحن الرصيد في رسالة HTML متسقة."""
    lines = []
    if include_request_id and data.get('id'):
        lines.append(f"🆔 <b>رقم الطلب:</b> <code>{escape_html(data['id'])}</code>")
    
    if include_user_info and data.get('chat_id'):
        username_display = await get_username_display(bot, data['chat_id'], data['full_name'])
        lines.append(f"👤 <b>المستخدم:</b> {escape_html(username_display)} (ID: <code>{data['chat_id']}</code>)")
    
    if include_balance and 'old_balance' in data:
        lines.append(f"💰 <b>رصيد المستخدم:</b> {data['old_balance']} ل.س")
    
    if 'transfer_code' in data:
        lines.append(f"🔑 <b>رمز التحويل:</b> <code>{escape_html(data['transfer_code'])}</code>")
    
    if 'description' in data:
        lines.append(f"📝 <b>الوصف:</b> {escape_html(data['description'] or '—')}")
    
    if 'amount' in data:
        lines.append(f"💰 <b>المبلغ المضاف:</b> {data['amount']} ل.س")
    
    if data.get('created_at'):
        lines.append(f"🕐 <b>تاريخ الطلب:</b> {data['created_at'].strftime('%Y-%m-%d %H:%M')}")
    
    if new_balance is not None:
        lines.append(f"💳 <b>الرصيد الجديد:</b> {new_balance} ل.س")
    
    if status:
        if status.lower() == 'approved':
            lines.append(f"\n✅ <b>الحالة: تمت الموافقة</b>")
        elif status.lower() == 'rejected':
            lines.append(f"\n❌ <b>الحالة: مرفوض</b>")
        else:
            lines.append(f"\n⏳ <b>الحالة: {status.capitalize()}</b>")
    
    return "\n".join(lines)

def escape_html(text):
    return html.escape(str(text) if text is not None else "")

@router.callback_query(F.data == "show_balance")
async def show_balance(callback: types.CallbackQuery):
    balance = await db.fetchval("SELECT balance FROM users WHERE chat_id=$1", callback.from_user.id)
    await callback.message.delete()
    await callback.message.answer(f"💰 رصيدك هو **{balance} ل.س**. \nاضغط /start")

# -------------------------------------------------------------------
# المستخدم: بدء طلب شحن
# -------------------------------------------------------------------
@router.callback_query(F.data == "charge_balance")
async def start_charge(callback: types.CallbackQuery, state: FSMContext):
    ready, config = await is_system_ready()
    if not ready:
        return await callback.answer("⚠️ النظام غير متاح حالياً.", show_alert=True)

    # التحقق من وجود رمز QR صالح
    if not config.get('superadmin_qr_file_id'):
        await callback.message.answer("❌ لم يتم تعيين رمز QR للشحن بعد. يرجى إبلاغ المشرف.")
        await callback.answer()
        return

    # التحقق من وجود طلب معلق
    pending = await db.fetchval(
        "SELECT 1 FROM balance_requests WHERE user_id=(SELECT id FROM users WHERE chat_id=$1) AND status='pending'",
        callback.from_user.id
    )
    if pending:
        return await callback.answer("🚫 لديك طلب معلق بالفعل.", show_alert=True)

    await state.set_state(UserCharge.waiting_transfer_code)
    builder = get_cancel_button()
    try:
        await callback.message.answer_photo(
            photo=config['superadmin_qr_file_id'],
            caption=f"💳 <b>رمز ShamCash:</b> <code>{escape_html(config['superadmin_shamcash_code'])}</code>\n\nالخطوة 1: أرسل <b>رمز التحويل</b>:",
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
    except TelegramBadRequest as e:
        # إذا كان معرف الصورة غير صالح، نرسل رسالة نصية بدلاً من ذلك
        logging.error(f"QR code file ID invalid: {e}")
        await callback.message.answer(
            f"💳 <b>رمز ShamCash:</b> <code>{escape_html(config['superadmin_shamcash_code'])}</code>\n\n"
            f"⚠️ تعذر إرسال صورة رمز QR. يرجى إبلاغ المشرف.\n\n"
            f"الخطوة 1: أرسل <b>رمز التحويل</b>:",
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
    await callback.message.delete()
    await callback.answer()


@router.message(UserCharge.waiting_transfer_code, F.text.not_in(SPECIAL_BUTTONS))
async def user_code(message: types.Message, state: FSMContext):
    await state.update_data(t_code=message.text)
    await state.set_state(UserCharge.waiting_description)
    builder = get_cancel_button()
    await message.answer(
        "📝 الخطوة 2: أرسل <b>وصفاً</b> مختصراً (أو أرسل '.' للتخطي):",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )

@router.message(UserCharge.waiting_description, F.text.not_in(SPECIAL_BUTTONS))
async def user_done(message: types.Message, state: FSMContext, bot):
    data = await state.get_data()
    user_uuid = await db.fetchval("SELECT id FROM users WHERE chat_id=$1", message.from_user.id)
    req_id = await db.fetchval(
        "INSERT INTO balance_requests (user_id, transfer_code, description) VALUES ($1, $2, $3) RETURNING id",
        user_uuid, data['t_code'], message.text
    )
    await state.clear()
    await message.answer("✅ تم إرسال الطلب! يرجى انتظار موافقة المشرف.")

    # إعداد البيانات للتنسيق
    req_data = {
        'id': req_id,
        'chat_id': message.from_user.id,
        'full_name': message.from_user.full_name,
        'transfer_code': data['t_code'],
        'description': message.text if message.text != '.' else None,
    }
    admin_text = await format_balance_request(
        req_data,
        bot,
        include_user_info=True,
        include_request_id=True,
        status="pending"
    )
    kb = InlineKeyboardBuilder()
    kb.row(
        types.InlineKeyboardButton(text="✅ قبول", callback_data=f"adm_acc_{req_id}"),
        types.InlineKeyboardButton(text="❌ رفض", callback_data=f"adm_den_{req_id}")
    )
    await bot.send_message(ADMIN_ID, admin_text, reply_markup=kb.as_markup(), parse_mode="HTML")

# -------------------------------------------------------------------
# المشرف: عرض جميع الطلبات المعلقة (مع منع التكرار)
# -------------------------------------------------------------------
@router.callback_query(F.data == "admin_requests")
async def show_requests(callback: types.CallbackQuery):
    admin_id = callback.from_user.id
    # حذف الرسائل السابقة إن وجدت
    if admin_id in _last_request_messages:
        for msg_id in _last_request_messages[admin_id]:
            try:
                await callback.bot.delete_message(chat_id=admin_id, message_id=msg_id)
            except TelegramBadRequest as e:
                logging.debug(f"تعذر حذف الرسالة {msg_id}: {e}")
        _last_request_messages[admin_id] = []

    rows = await db.fetch("""
        SELECT br.id, br.transfer_code, br.description, br.created_at,
               u.full_name, u.chat_id
        FROM balance_requests br
        JOIN users u ON u.id = br.user_id
        WHERE br.status = 'pending'
        ORDER BY br.created_at DESC
    """)
    if not rows:
        await callback.answer("لا توجد طلبات معلقة.", show_alert=True)
        return

    sent_ids = []
    for row in rows:
        text = (
            f"🆔 <b>رقم الطلب:</b> <code>{escape_html(row['id'])}</code>\n"
            f"👤 <b>المستخدم:</b> {escape_html(row['full_name'])} (ID: <code>{escape_html(row['chat_id'])}</code>)\n"
            f"🔑 <b>رمز التحويل:</b> <code>{escape_html(row['transfer_code'])}</code>\n"
            f"📝 <b>الوصف:</b> {escape_html(row['description'] or '—')}\n"
            f"🕐 <b>تاريخ الإنشاء:</b> {escape_html(row['created_at'].strftime('%Y-%m-%d %H:%M'))}"
        )
        kb = InlineKeyboardBuilder()
        kb.row(
            types.InlineKeyboardButton(text="✅ قبول", callback_data=f"adm_acc_{row['id']}"),
            types.InlineKeyboardButton(text="❌ رفض", callback_data=f"adm_den_{row['id']}")
        )
        sent = await callback.message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")
        sent_ids.append(sent.message_id)

    _last_request_messages[admin_id] = sent_ids
    await callback.message.delete()
    await callback.answer()

# -------------------------------------------------------------------
# المشرف: رفض الطلب
# -------------------------------------------------------------------
@router.callback_query(F.data.startswith("adm_den_"))
async def admin_deny(callback: types.CallbackQuery, bot):
    req_id = callback.data.split("_")[-1]

    req = await db.fetchrow("""
        SELECT br.id, br.transfer_code, br.description, br.created_at, br.status,
               u.full_name, u.chat_id, u.balance as old_balance, u.id as user_id
        FROM balance_requests br
        JOIN users u ON u.id = br.user_id
        WHERE br.id = $1
    """, req_id)

    if not req:
        await callback.message.edit_text("❌ الطلب غير موجود.")
        await callback.answer()
        return

    if req['status'] != 'pending':
        await callback.message.edit_text(f"❌ هذا الطلب {req['status']} بالفعل.")
        await callback.answer()
        return

    await db.execute("UPDATE balance_requests SET status='rejected' WHERE id=$1", req_id)

    # رسالة للمشرف
    admin_text = await format_balance_request(
        dict(req),
        bot,
        include_user_info=True,
        include_request_id=True,
        include_balance=True,
        status="rejected"
    )
    await callback.message.edit_text(admin_text, parse_mode="HTML")

    # إشعار المستخدم
    user_text = await format_balance_request(
        dict(req),
        bot,
        include_user_info=False,
        include_request_id=False,
        include_balance=False,
        status="rejected"
    )
    user_kb = InlineKeyboardBuilder()
    user_kb.row(types.InlineKeyboardButton(text="💰 شحن الرصيد", callback_data="charge_balance"))
    user_kb.row(types.InlineKeyboardButton(text="📊 عرض الرصيد", callback_data="show_balance"))
    await bot.send_message(req['chat_id'], user_text, reply_markup=user_kb.as_markup(), parse_mode="HTML")
    await callback.answer()
    
# -------------------------------------------------------------------
# المشرف: بدء قبول الطلب (طلب المبلغ)
# -------------------------------------------------------------------
@router.callback_query(F.data.startswith("adm_acc_"))
async def admin_accept_start(callback: types.CallbackQuery, state: FSMContext):
    req_id = callback.data.split("_")[-1]

    # التحقق من أن الطلب لا يزال معلقاً
    req = await db.fetchrow("SELECT status FROM balance_requests WHERE id=$1", req_id)
    if not req:
        await callback.message.edit_text("❌ الطلب غير موجود.")
        await callback.answer()
        return
    
    if req['status'] != 'pending':
        await callback.message.edit_text("❌ هذا الطلب لم يعد معلقاً.")
        await callback.answer()
        return

    # حذف الأزرار من الرسالة الأصلية وإظهار التقدم
    await callback.message.delete()
    await state.set_state(UserCharge.waiting_amount)
    await state.update_data(req_id=req_id)

    # طلب المبلغ مع زر إلغاء
    builder = get_cancel_button()
    await callback.message.answer(
        "💰 أدخل <b>المبلغ</b> لإضافته إلى رصيد المستخدم:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()

# -------------------------------------------------------------------
# المشرف: إتمام القبول (استلام المبلغ)
# -------------------------------------------------------------------
@router.message(UserCharge.waiting_amount, F.text.not_in(SPECIAL_BUTTONS))
async def admin_final_accept(message: types.Message, state: FSMContext, bot):
    data = await state.get_data()
    try:
        amount = Decimal(message.text)
    except InvalidOperation:
        await message.answer("❌ الرجاء إدخال رقم صحيح.")
        return

    req_id = data['req_id']

    async with db.pool.acquire() as conn:
        async with conn.transaction():
            request = await conn.fetchrow(
                """SELECT br.id, br.transfer_code, br.status, br.created_at,
                          u.id AS user_id, u.chat_id, u.full_name AS username,
                          u.balance AS old_balance
                   FROM balance_requests br
                   JOIN users u ON u.id = br.user_id
                   WHERE br.id = $1 FOR UPDATE""",
                req_id
            )
            if not request:
                await message.answer("❌ الطلب غير موجود.")
                await state.clear()
                return

            if request['status'] != 'pending':
                await message.answer("❌ تمت معالجة الطلب بالفعل.")
                await state.clear()
                return

            new_balance = request['old_balance'] + amount
            await conn.execute(
                "UPDATE users SET balance = $1 WHERE id = $2",
                new_balance, request['user_id']
            )
            await conn.execute(
                "UPDATE balance_requests SET status='approved' WHERE id=$1",
                req_id
            )
            await conn.execute(
                "INSERT INTO transactions (user_id, amount, type) VALUES ($1, $2, 'charge')",
                request['user_id'], amount
            )

    await state.clear()

    req_data = dict(request)
    req_data['amount'] = amount
    req_data['full_name'] = request['username']

    admin_text = await format_balance_request(
        req_data,
        bot,
        include_user_info=True,
        include_request_id=True,
        include_balance=True,
        status="approved",
        new_balance=new_balance
    )
    await message.answer(admin_text, parse_mode="HTML")

    user_text = await format_balance_request(
        req_data,
        bot,
        include_user_info=False,
        include_request_id=False,
        include_balance=False,
        status="approved",
        new_balance=new_balance
    )
    user_kb = InlineKeyboardBuilder()
    user_kb.row(types.InlineKeyboardButton(text="💰 شحن الرصيد", callback_data="charge_balance"))
    user_kb.row(types.InlineKeyboardButton(text="📊 عرض الرصيد", callback_data="show_balance"))
    await bot.send_message(
        request['chat_id'],
        user_text,
        parse_mode="HTML",
        reply_markup=user_kb.as_markup()
    )
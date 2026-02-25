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


class AdminAccept(StatesGroup):
    waiting_amount = State()

class UserCharge(StatesGroup):
    waiting_payment_method = State()
    waiting_name = State()               # 1. الاسم في ShamCash
    waiting_amount = State()              # 2. المبلغ
    waiting_transfer_code = State()       # 3. رمز التحويل
    waiting_confirmation = State()        # 4. التأكيد

async def get_username_display(bot, user_id: int, full_name: str) -> str:
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
    lines.append(f"#طلب_شحن_رصيد\n\n")
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
        lines.append(f"📝 <b>الوصف:</b>\n{escape_html(data['description'] or '—')}")
    
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

def method_display(method: str) -> str:
    return {
        'sham': 'شام كاش',
        'syriatel': 'سيريتيل كاش',
        'mtn': 'إم تي إن كاش'
    }.get(method, method)


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

    pending = await db.fetchval(
        "SELECT 1 FROM balance_requests WHERE user_id=(SELECT id FROM users WHERE chat_id=$1) AND status='pending'",
        callback.from_user.id
    )
    if pending:
        return await callback.answer("🚫 لديك طلب معلق بالفعل.", show_alert=True)

    # قائمة طرق الدفع
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="💰 شام كاش", callback_data="pay_method:sham"))
    builder.row(types.InlineKeyboardButton(text="📱 سيريتيل كاش", callback_data="pay_method:syriatel"))
    builder.row(types.InlineKeyboardButton(text="📱 إم تي إن كاش", callback_data="pay_method:mtn"))
    builder.row(types.InlineKeyboardButton(text="🔙 تراجع", callback_data="back_to_main"))
    await callback.message.edit_text(
        "🔹 **اختر طريقة الدفع** 🔹\n\n"
        "يرجى اختيار إحدى طرق الدفع المتاحة:",
        reply_markup=builder.as_markup()
    )
    await callback.answer()
    await state.set_state(UserCharge.waiting_payment_method)
@router.callback_query(UserCharge.waiting_payment_method, F.data.startswith("pay_method:"))
async def payment_method_selected(callback: types.CallbackQuery, state: FSMContext):
    method = callback.data.split(":")[1]
    ready, config = await is_system_ready()

    if method == "sham":
        code = config.get('superadmin_shamcash_code')
        qr = config.get('superadmin_qr_file_id')
    elif method == "syriatel":
        code = config.get('syriatel_code')
        qr = config.get('syriatel_qr_file_id')
    elif method == "mtn":
        code = config.get('mtn_code')
        qr = config.get('mtn_qr_file_id')
    else:
        await callback.answer("طريقة دفع غير صالحة", show_alert=True)
        return

    if not code:
        await callback.message.edit_text(f"❌ لم يتم تعيين رمز {method_display(method)} بعد. يرجى إبلاغ المشرف.")
        return
    if not qr:
        await callback.message.edit_text(f"❌ لم يتم تعيين صورة QR لـ {method_display(method)} بعد. يرجى إبلاغ المشرف.")
        return

    await state.update_data(payment_method=method)
    await state.set_state(UserCharge.waiting_name)
    builder = get_cancel_button()
    caption = f"💳 <b>رمز {method_display(method)}:</b> <code>{escape_html(code)}</code>\n\nالخطوة 1: أرسل <b>الاسم كما يظهر في الدفع</b>:"
    try:
        await callback.message.answer_photo(
            photo=qr,
            caption=caption,
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
    except Exception as e:
        logging.error(f"فشل إرسال صورة QR: {e}")
        await callback.message.answer(caption, reply_markup=builder.as_markup(), parse_mode="HTML")
    await callback.message.delete()
    await callback.answer()

# -------------------------------------------------------------------
# 1. استقبال الاسم
# -------------------------------------------------------------------
@router.message(UserCharge.waiting_name, F.text.not_in(SPECIAL_BUTTONS))
async def user_name(message: types.Message, state: FSMContext):
    name = message.text.strip()
    if not name:
        await message.answer("❌ الاسم لا يمكن أن يكون فارغاً.")
        return
    await state.update_data(name=name)
    await state.set_state(UserCharge.waiting_amount)
    builder = get_cancel_button()
    await message.answer(
        "💰 الخطوة 2: أرسل <b>المبلغ المحول</b> (بالليرة السورية، رقم فقط):",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )

# -------------------------------------------------------------------
# 2. استقبال المبلغ
# -------------------------------------------------------------------
@router.message(UserCharge.waiting_amount, F.text.not_in(SPECIAL_BUTTONS))
async def user_amount(message: types.Message, state: FSMContext):
    builder = get_cancel_button()
    try:
        amount = Decimal(message.text)
        if amount <= 0:
            raise ValueError
    except (InvalidOperation, ValueError):
        await message.answer("❌ الرجاء إدخال رقم موجب صحيح.", reply_markup=builder.as_markup())
        return
    await state.update_data(amount=amount)
    await state.set_state(UserCharge.waiting_transfer_code)
    await message.answer(
        "🔑 الخطوة 3: أرسل <b>رمز التحويل</b> (أرقام فقط):",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )

# -------------------------------------------------------------------
# 3. استقبال رمز التحويل (يجب أن يكون أرقاماً)
# -------------------------------------------------------------------
@router.message(UserCharge.waiting_transfer_code, F.text.not_in(SPECIAL_BUTTONS))
async def user_code(message: types.Message, state: FSMContext):
    builder = get_cancel_button()
    code = message.text.strip()
    if not code.isdigit():
        await message.answer("❌ رمز التحويل يجب أن يتكون من أرقام فقط. حاول مرة أخرى.", reply_markup=builder.as_markup())
        return
    await state.update_data(transfer_code=code)
    data = await state.get_data()
    # بناء رسالة التأكيد
    description = (
        f"الاسم: {data['name']}\n"
        f"المبلغ المحول: {data['amount']} ل.س\n"
        f"رمز التحويل: {data['transfer_code']}"
    )
    text = (
        f"📝 **تأكيد طلب الشحن**\n\n"
        f"{description}\n\n"
        f"هل البيانات صحيحة؟"
    )
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="✅ تأكيد", callback_data="confirm_charge"),
        types.InlineKeyboardButton(text="❌ حذف", callback_data="cancel_charge")
    )
    await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await state.set_state(UserCharge.waiting_confirmation)

# -------------------------------------------------------------------
# 4. تأكيد الطلب وإرساله للمشرف
# -------------------------------------------------------------------
@router.callback_query(UserCharge.waiting_confirmation, F.data == "confirm_charge")
async def confirm_charge(callback: types.CallbackQuery, state: FSMContext, bot):
    data = await state.get_data()
    user_uuid = await db.fetchval("SELECT id FROM users WHERE chat_id=$1", callback.from_user.id)
    method_name = method_display(data['payment_method'])
    description = (
        f"طريقة الدفع: {method_name}\n"
        f"الاسم: {data['name']}\n"
        f"المبلغ المحول: {data['amount']} ل.س\n"
        f"رمز التحويل: {data['transfer_code']}"
    )
    req_id = await db.fetchval(
        "INSERT INTO balance_requests (user_id, transfer_code, description) VALUES ($1, $2, $3) RETURNING id",
        user_uuid, data['transfer_code'], description
    )
    await state.clear()
    await callback.message.edit_text("✅ تم إرسال الطلب! يرجى انتظار موافقة المشرف.")

    req_data = {
        'id': req_id,
        'chat_id': callback.from_user.id,
        'full_name': callback.from_user.full_name,
        'transfer_code': data['transfer_code'],
        'description': description,
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
    await callback.answer()

@router.callback_query(UserCharge.waiting_confirmation, F.data == "cancel_charge")
async def cancel_charge(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ تم إلغاء الطلب.")
    await callback.answer()

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
            f"📝 <b>الوصف:</b>\n{escape_html(row['description'] or '—')}\n"
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

    req = await db.fetchrow("SELECT status FROM balance_requests WHERE id=$1", req_id)
    if not req:
        await callback.message.edit_text("❌ الطلب غير موجود.")
        await callback.answer()
        return
    
    if req['status'] != 'pending':
        await callback.message.edit_text("❌ هذا الطلب لم يعد معلقاً.")
        await callback.answer()
        return

    await callback.message.delete()
    await state.set_state(AdminAccept.waiting_amount)   # تغيير الحالة
    await state.update_data(req_id=req_id)

    builder = get_cancel_button()
    await callback.message.answer(
        "💰 أدخل <b>المبلغ</b> لإضافته إلى رصيد المستخدم:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()

@router.message(AdminAccept.waiting_amount, F.text.not_in(SPECIAL_BUTTONS))
async def admin_accept_amount(message: types.Message, state: FSMContext, bot):
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
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from .common_handlers import get_cancel_button
from database import db
from static_lists import SPECIAL_BUTTONS
from aiogram.exceptions import TelegramBadRequest
from decimal import Decimal, InvalidOperation
import os
import html
import logging

router = Router()
ADMIN_ID = int(os.getenv("ADMIN_CHAT_ID"))

class PurchaseRequest(StatesGroup):
    waiting_account_id = State()
    waiting_confirmation = State()

# Store message IDs of the last "admin_purchases" output per admin
_last_purchase_messages = {}

def escape_html(text):
    return html.escape(str(text) if text is not None else "")

def format_user_display(chat_id: int, full_name: str, username: str = None) -> str:
    """إرجاع عرض المستخدم مع اسم المستخدم إن وجد، وإلا الاسم الكامل."""
    if username:
        return f"@{username} ({escape_html(full_name)})"
    return escape_html(full_name)

async def format_purchase_request(
    data: dict,
    bot,
    include_user_info: bool = True,
    include_request_id: bool = False,
    include_balance: bool = False,
    status: str = None
) -> str:
    """
    تنسيق تفاصيل طلب الشراء في رسالة HTML متسقة.
    data: قاموس يحتوي على الحقول التالية:
        - id (اختياري)
        - chat_id (معرف المستخدم في تليغرام)
        - full_name (الاسم الكامل للمستخدم)
        - game_name, package_name, price, game_account_id
        - game_description (اختياري)
        - balance (اختياري)
        - created_at (اختياري datetime)
    """
    lines = []
    if include_request_id and data.get('id'):
        lines.append(f"🆔 <b>رقم الطلب:</b> <code>{escape_html(data['id'])}</code>")
    
    if include_user_info and data.get('chat_id'):
        username_display = await get_username_display(bot, data['chat_id'], data['full_name'])
        lines.append(f"👤 <b>المستخدم:</b> {escape_html(username_display)} (ID: <code>{data['chat_id']}</code>)")
    
    if include_balance and 'balance' in data:
        lines.append(f"💰 <b>رصيد المستخدم:</b> {data['balance']} ل.س")
    
    if 'game_name' in data:
        lines.append(f"🎮 <b>اللعبة:</b> {escape_html(data['game_name'])}")
    if 'package_name' in data:
        lines.append(f"📦 <b>الحزمة:</b> {escape_html(data['package_name'])}")
    if 'price' in data:
        lines.append(f"💵 <b>السعر:</b> {data['price']} ل.س")
    
    acc = data.get('game_account_id') or data.get('account_id')
    if acc:
        lines.append(f"🆔 <b>معرف حساب اللعبة:</b> <code>{escape_html(acc)}</code>")
    
    if data.get('game_description'):
        lines.append(f"📝 <b>وصف اللعبة:</b> {escape_html(data['game_description'])}")
    
    if data.get('created_at'):
        lines.append(f"🕐 <b>تاريخ الطلب:</b> {data['created_at'].strftime('%Y-%m-%d %H:%M')}")
    
    if status:
        if status.lower() == 'approved':
            lines.append(f"\n✅ <b>الحالة: تمت الموافقة</b>")
        elif status.lower() == 'rejected':
            lines.append(f"\n❌ <b>الحالة: مرفوض</b>")
        else:
            lines.append(f"\n⏳ <b>الحالة: معلق</b>")
    
    return "\n".join(lines)


async def get_username_display(bot, user_id: int, full_name: str) -> str:
    try:
        chat = await bot.get_chat(user_id)
        if chat.username:
            return f"@{chat.username}"
    except:
        pass
    return full_name

@router.callback_query(F.data.startswith("buy_package:"))
async def buy_package_start(callback: types.CallbackQuery, state: FSMContext):
    package_id = callback.data.split(":")[1]
    pkg = await db.fetchrow("""
        SELECT gp.id, gp.name, gp.price, g.id as game_id, g.name as game_name
        FROM game_packages gp
        JOIN games g ON g.id = gp.game_id
        WHERE gp.id = $1
    """, package_id)
    if not pkg:
        await callback.answer("الحزمة غير موجودة.", show_alert=True)
        return

    user = await db.fetchrow("SELECT id, balance FROM users WHERE chat_id = $1", callback.from_user.id)
    if not user:
        await callback.answer("يجب أن تبدأ البوت أولاً.", show_alert=True)
        return

    balance = user['balance']
    price = pkg['price']

    if balance < price:
        builder = InlineKeyboardBuilder()
        builder.row(types.InlineKeyboardButton(text="💰 شحن الرصيد", callback_data="charge_balance"))
        await callback.message.answer(
            f"❌ رصيد غير كاف.\nرصيدك: {balance} ل.س\nسعر الحزمة: {price} ل.س\nيرجى شحن رصيدك.",
            reply_markup=builder.as_markup()
        )
        await callback.answer()
        return

    await state.update_data(
        package_id=package_id,
        game_id=pkg['game_id'],
        game_name=pkg['game_name'],
        package_name=pkg['name'],
        price=price,
        user_id=user['id']
    )
    await state.set_state(PurchaseRequest.waiting_account_id)
    builder = get_cancel_button()
    await callback.message.answer(
        "🎮 ارسل معرفك داخل اللعبة",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    await callback.message.delete()
    await callback.answer()

@router.message(PurchaseRequest.waiting_account_id, F.text.not_in(SPECIAL_BUTTONS))
async def receive_account_id(message: types.Message, state: FSMContext):
    account_id = message.text.strip()
    if not account_id:
        await message.answer("❌ لا يمكن أن يكون معرف الحساب فارغاً. الرجاء إدخال معرف صحيح.")
        return
    await state.update_data(account_id=account_id)
    data = await state.get_data()
    text = (
        f"📝 **يرجى تأكيد عملية الشراء**\n\n"
        f"🎮 اللعبة: {escape_html(data['game_name'])}\n"
        f"📦 الحزمة: {escape_html(data['package_name'])}\n"
        f"💰 السعر: {data['price']} ل.س\n"
        f"🆔 معرف الحساب: <code>{escape_html(account_id)}</code>\n\n"
        f"هل هذه المعلومات صحيحة؟"
    )
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="✅ نعم، متابعة", callback_data="purchase_confirm_yes"),
        types.InlineKeyboardButton(text="❌ لا، إلغاء", callback_data="purchase_confirm_no")
    )
    await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await state.set_state(PurchaseRequest.waiting_confirmation)

@router.callback_query(PurchaseRequest.waiting_confirmation, F.data == "purchase_confirm_yes")
@router.callback_query(PurchaseRequest.waiting_confirmation, F.data == "purchase_confirm_yes")
async def purchase_confirm_yes(callback: types.CallbackQuery, state: FSMContext, bot):
    data = await state.get_data()
    request_id = await db.fetchval("""
        INSERT INTO purchase_requests (user_id, game_id, package_id, game_account_id, price)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING id
    """, data['user_id'], data['game_id'], data['package_id'], data['account_id'], data['price'])
    await state.clear()
    await callback.message.edit_text("✅ تم إرسال طلب الشراء إلى المشرف. سيتم إعلامك عند الموافقة.")
    
    # أزرار للمستخدم بعد الطلب
    # user_kb = InlineKeyboardBuilder()
    # user_kb.row(types.InlineKeyboardButton(text="💰 شحن الرصيد", callback_data="charge_balance"))
    # user_kb.row(types.InlineKeyboardButton(text="📊 عرض الرصيد", callback_data="show_balance"))
    # await callback.message.answer("ماذا تريد أن تفعل بعد ذلك؟", reply_markup=user_kb.as_markup())
    await callback.message.answer("قد تستغرق العملية يوم كامل كحد اقصى")
    # جلب تفاصيل الطلب كاملة للمشرف
    req_row = await db.fetchrow("""
        SELECT pr.id, pr.game_account_id, pr.price, pr.created_at,
               u.chat_id, u.full_name, u.balance,
               g.name as game_name, g.description as game_description,
               gp.name as package_name
        FROM purchase_requests pr
        JOIN users u ON u.id = pr.user_id
        JOIN games g ON g.id = pr.game_id
        JOIN game_packages gp ON gp.id = pr.package_id
        WHERE pr.id = $1
    """, request_id)

    admin_text = await format_purchase_request(
        req_row,
        bot,
        include_user_info=True,
        include_request_id=True,
        include_balance=True,
        status="pending"
    )
    admin_kb = InlineKeyboardBuilder()
    admin_kb.row(
        types.InlineKeyboardButton(text="✅ موافقة", callback_data=f"purchase_approve:{request_id}"),
        types.InlineKeyboardButton(text="❌ رفض", callback_data=f"purchase_reject:{request_id}")
    )
    admin_kb.row(types.InlineKeyboardButton(text="👤 ملف المستخدم", callback_data=f"admin_user_info:{callback.from_user.id}"))
    await bot.send_message(ADMIN_ID, admin_text, reply_markup=admin_kb.as_markup(), parse_mode="HTML")
    await callback.answer()

@router.callback_query(PurchaseRequest.waiting_confirmation, F.data == "purchase_confirm_no")
async def purchase_confirm_no(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ تم إلغاء الشراء.")
    await callback.answer()


# ------------------ قائمة طلبات الشراء المعلقة للمشرف (مع التنظيف) ------------------
@router.callback_query(F.data == "admin_purchases")
async def admin_purchases_list(callback: types.CallbackQuery, bot):
    admin_id = callback.from_user.id
    # حذف الرسائل السابقة
    if admin_id in _last_purchase_messages:
        for msg_id in _last_purchase_messages[admin_id]:
            try:
                await callback.bot.delete_message(chat_id=admin_id, message_id=msg_id)
            except TelegramBadRequest as e:
                logging.debug(f"تعذر حذف الرسالة {msg_id}: {e}")
        _last_purchase_messages[admin_id] = []

    rows = await db.fetch("""
       SELECT pr.id, pr.game_account_id, pr.price, pr.created_at,
            u.chat_id, u.full_name, u.balance,
            g.name as game_name, g.description as game_description,
            gp.name as package_name
        FROM purchase_requests pr
        JOIN users u ON u.id = pr.user_id
        JOIN games g ON g.id = pr.game_id
        JOIN game_packages gp ON gp.id = pr.package_id
        WHERE pr.status = 'pending'
        ORDER BY pr.created_at DESC
    """)
    if not rows:
        await callback.answer("لا توجد طلبات شراء معلقة.", show_alert=True)
        return

    sent_ids = []
    for row in rows:
        text = await format_purchase_request(
            row,
            bot,
            include_user_info=True,
            include_request_id=True,
            include_balance=True,
            status="pending"
        )
        kb = InlineKeyboardBuilder()
        kb.row(
            types.InlineKeyboardButton(text="✅ موافقة", callback_data=f"purchase_approve:{row['id']}"),
            types.InlineKeyboardButton(text="❌ رفض", callback_data=f"purchase_reject:{row['id']}")
        )
        kb.row(types.InlineKeyboardButton(text="👤 ملف المستخدم", callback_data=f"admin_user_info:{row['chat_id']}"))
        sent = await callback.message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")
        sent_ids.append(sent.message_id)

    _last_purchase_messages[admin_id] = sent_ids
    await callback.message.delete()
    await callback.answer()

# -------------------------------------------------------------------
# موافقة المشرف على الشراء
# -------------------------------------------------------------------
@router.callback_query(F.data.startswith("purchase_approve:"))
async def purchase_approve(callback: types.CallbackQuery, bot):
    request_id = callback.data.split(":")[1]
    req = await db.fetchrow("""
        SELECT pr.*, u.chat_id, u.full_name, u.balance,
               g.name as game_name, g.description as game_description,
               gp.name as package_name
        FROM purchase_requests pr
        JOIN users u ON u.id = pr.user_id
        JOIN games g ON g.id = pr.game_id
        JOIN game_packages gp ON gp.id = pr.package_id
        WHERE pr.id = $1
    """, request_id)
    if not req:
        await callback.message.edit_text("الطلب غير موجود.")
        return
    if req['status'] != 'pending':
        await callback.message.edit_text(f"الطلب {req['status']} بالفعل.")
        return

    if req['balance'] < req['price']:
        await db.execute("UPDATE purchase_requests SET status='rejected' WHERE id=$1", request_id)
        # تحديث رسالة المشرف
        admin_text = await format_purchase_request(
            dict(req),
            bot,
            include_user_info=True,
            include_request_id=True,
            include_balance=True,
            status="مرفوض (رصيد غير كاف)"
        )
        await callback.message.edit_text(admin_text, parse_mode="HTML")
        # إشعار المستخدم
        user_text = await format_purchase_request(
            dict(req),
            bot,
            include_user_info=False,
            include_request_id=False,
            include_balance=False,
            status="مرفوض (رصيد غير كاف)"
        )
        await bot.send_message(req['chat_id'], user_text, parse_mode="HTML")
        return

    async with db.pool.acquire() as conn:
        async with conn.transaction():
            new_balance = req['balance'] - req['price']
            await conn.execute("UPDATE users SET balance = $1 WHERE id = $2", new_balance, req['user_id'])
            await conn.execute("UPDATE purchase_requests SET status='approved' WHERE id=$1", request_id)
            await conn.execute(
                "INSERT INTO transactions (user_id, amount, type, description) VALUES ($1, $2, 'purchase', $3)",
                req['user_id'], req['price'], f"شراء {req['package_name']} للعبة {req['game_name']}"
            )

    req_data = dict(req)
    req_data['new_balance'] = new_balance

    admin_text = await format_purchase_request(
        req_data,
        bot,
        include_user_info=True,
        include_request_id=True,
        include_balance=True,
        status="approved"
    )
    admin_text += f"\n💳 <b>الرصيد الجديد:</b> {new_balance} ل.س"
    await callback.message.edit_text(admin_text, parse_mode="HTML")

    user_text = await format_purchase_request(
        req_data,
        bot,
        include_user_info=False,
        include_request_id=False,
        include_balance=False,
        status="approved"
    )
    user_text += f"\n💳 <b>المبلغ المخصوم:</b> {req['price']} ل.س\n💳 <b>الرصيد الجديد:</b> {new_balance} ل.س\n\nسيقوم المشرف بإداع المبلغ لحسابك في اللعبة"
    await bot.send_message(req['chat_id'], user_text, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("purchase_reject:"))
async def purchase_reject(callback: types.CallbackQuery, bot):
    request_id = callback.data.split(":")[1]
    req = await db.fetchrow("""
        SELECT pr.*, u.chat_id, u.full_name, u.balance,
               g.name as game_name, g.description as game_description,
               gp.name as package_name
        FROM purchase_requests pr
        JOIN users u ON u.id = pr.user_id
        JOIN games g ON g.id = pr.game_id
        JOIN game_packages gp ON gp.id = pr.package_id
        WHERE pr.id = $1
    """, request_id)
    if not req:
        await callback.message.edit_text("الطلب غير موجود.")
        return
    if req['status'] != 'pending':
        await callback.message.edit_text(f"الطلب {req['status']} بالفعل.")
        return

    await db.execute("UPDATE purchase_requests SET status='rejected' WHERE id=$1", request_id)

    admin_text = await format_purchase_request(
        dict(req),
        bot,
        include_user_info=True,
        include_request_id=True,
        include_balance=True,
        status="rejected"
    )
    await callback.message.edit_text(admin_text, parse_mode="HTML")

    user_text = await format_purchase_request(
        dict(req),
        bot,
        include_user_info=False,
        include_request_id=False,
        include_balance=False,
        status="rejected"
    )
    user_text += "\n\nإذا كنت تعتقد أن هذا خطأ، يرجى الاتصال بالدعم."
    await bot.send_message(req['chat_id'], user_text, parse_mode="HTML")
    await callback.answer()

# ------------------ معالج ملف المستخدم للمشرف ------------------
@router.callback_query(F.data.startswith("admin_user_info:"))
async def admin_user_info(callback: types.CallbackQuery, bot):
    user_chat_id = int(callback.data.split(":")[1])
    user = await db.fetchrow("SELECT * FROM users WHERE chat_id = $1", user_chat_id)
    if not user:
        await callback.answer("المستخدم غير موجود.", show_alert=True)
        return
    # الحصول على اسم المستخدم
    username_display = await get_username_display(bot, user_chat_id, user['full_name'])
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
        line = f"• {tx['created_at'].strftime('%Y-%m-%d %H:%M')} – {tx['type']}: {tx['amount']} ل.س"
        if tx['description']:
            line += f" ({escape_html(tx['description'])})"
        tx_lines.append(line)
    tx_text = "\n".join(tx_lines) if tx_lines else "لا توجد عمليات بعد."

    text = (
        f"👤 **ملف المستخدم**\n\n"
        f"ID: <code>{user['chat_id']}</code>\n"
        f"الاسم: {escape_html(user['full_name'])}\n"
        f"اسم المستخدم: {escape_html(username_display)}\n"
        f"الرصيد: {user['balance']} ل.س\n"
        f"تاريخ الانضمام: {user['created_at'].strftime('%Y-%m-%d') if user.get('created_at') else 'غير معروف'}\n\n"
        f"**آخر العمليات:**\n{tx_text}"
    )
    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()
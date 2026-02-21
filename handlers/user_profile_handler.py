import os
import html
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from database import db
from .common_handlers import get_cancel_button
from static_lists import SPECIAL_BUTTONS
from decimal import Decimal, InvalidOperation
import logging
import tempfile
import csv
from .referral_handler import get_referral_count
from aiogram.types import FSInputFile

router = Router()
ADMIN_ID = int(os.getenv("ADMIN_CHAT_ID"))

def escape_html(text):
    return html.escape(str(text) if text is not None else "")

class AdminBalanceAdjust(StatesGroup):
    waiting_chat_id = State()
    waiting_operation = State()
    waiting_amount = State()
    waiting_confirm = State()

class AdminViewUser(StatesGroup):
    waiting_chat_id = State()

@router.callback_query(F.data == "admin_user_management")
async def admin_user_management(callback: types.CallbackQuery):
    """Show submenu for user management."""
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="📋 عرض كل المستخدمين", callback_data="admin_list_users"))
    builder.row(types.InlineKeyboardButton(text="👤 عرض حساب مستخدم", callback_data="admin_view_user"))
    builder.row(types.InlineKeyboardButton(text="💰 تعديل رصيد مستخدم", callback_data="admin_adjust_balance"))
    builder.row(types.InlineKeyboardButton(text="🔙 رجوع", callback_data="admin_back_to_main"))
    await callback.message.edit_text(
        "📋 **إدارة المستخدمين**\nاختر العملية:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()

# -------------------------------------------------------------------
# Admin: Start balance adjustment
# -------------------------------------------------------------------
@router.callback_query(F.data == "admin_adjust_balance")
async def admin_adjust_start(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("غير مصرح.", show_alert=True)
        return
    await state.set_state(AdminBalanceAdjust.waiting_chat_id)
    builder = get_cancel_button()
    await callback.message.edit_text(
        "✏️ أدخل **معرف المستخدم** (chat ID) لضبط رصيده:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()

@router.message(AdminBalanceAdjust.waiting_chat_id, F.text.not_in(SPECIAL_BUTTONS))
async def admin_adjust_chat_id(message: types.Message, state: FSMContext):
    try:
        chat_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ معرف غير صالح. الرجاء إدخال رقم.")
        return

    # Fetch user
    user = await db.fetchrow("SELECT * FROM users WHERE chat_id = $1", chat_id)
    if not user:
        await message.answer("❌ المستخدم غير موجود.")
        await state.clear()
        return

    await state.update_data(target_chat_id=chat_id, target_user_id=user['id'])
    await state.set_state(AdminBalanceAdjust.waiting_operation)

    # Show user info and ask for operation
    text = (
        f"👤 **معلومات المستخدم**\n\n"
        f"الاسم: {escape_html(user['full_name'])}\n"
        f"الرصيد الحالي: {user['balance']} ل.س\n"
        f"تاريخ الانضمام: {user['created_at'].strftime('%Y-%m-%d') if user.get('created_at') else 'غير معروف'}\n\n"
        f"اختر العملية:"
    )
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="➕ زيادة", callback_data="op_add"),
        types.InlineKeyboardButton(text="➖ نقصان", callback_data="op_sub")
    )
    builder.row(types.InlineKeyboardButton(text="❌ إلغاء", callback_data="cancel_action"))
    await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")

@router.callback_query(AdminBalanceAdjust.waiting_operation, F.data.in_(["op_add", "op_sub"]))
async def admin_adjust_operation(callback: types.CallbackQuery, state: FSMContext):
    operation = "add" if callback.data == "op_add" else "sub"
    await state.update_data(operation=operation)
    await state.set_state(AdminBalanceAdjust.waiting_amount)
    builder = get_cancel_button()
    await callback.message.edit_text(
        f"💰 أدخل المبلغ (بالليرة السورية):",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()

@router.message(AdminBalanceAdjust.waiting_amount, F.text.not_in(SPECIAL_BUTTONS))
async def admin_adjust_amount(message: types.Message, state: FSMContext):
    try:
        amount = Decimal(message.text)
        if amount <= 0:
            raise ValueError
    except (InvalidOperation, ValueError):
        builder = get_cancel_button()
        await message.answer("❌ الرجاء إدخال رقم موجب صحيح.", reply_markup=builder.as_markup())
        return
    await state.update_data(amount=amount)
    data = await state.get_data()

    # Fetch user again for fresh info
    user = await db.fetchrow("SELECT * FROM users WHERE id = $1", data['target_user_id'])
    new_balance = user['balance'] + amount if data['operation'] == 'add' else user['balance'] - amount
    if data['operation'] == 'sub' and new_balance < 0:
        await message.answer("❌ لا يمكن أن يصبح الرصيد سالباً.")
        return

    op_text = "زيادة" if data['operation'] == 'add' else "خصم"
    text = (
        f"📝 **تأكيد العملية**\n\n"
        f"المستخدم: {escape_html(user['full_name'])} (ID: {user['chat_id']})\n"
        f"الرصيد الحالي: {user['balance']} ل.س\n"
        f"العملية: {op_text} {amount} ل.س\n"
        f"الرصيد بعد العملية: {new_balance} ل.س\n\n"
        f"هل أنت متأكد؟"
    )
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="✅ تأكيد", callback_data="confirm_adjust"),
        types.InlineKeyboardButton(text="❌ إلغاء", callback_data="cancel_action")
    )
    await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await state.set_state(AdminBalanceAdjust.waiting_confirm)

@router.callback_query(AdminBalanceAdjust.waiting_confirm, F.data == "confirm_adjust")
async def admin_adjust_confirm(callback: types.CallbackQuery, state: FSMContext, bot):
    data = await state.get_data()
    user = await db.fetchrow("SELECT * FROM users WHERE id = $1", data['target_user_id'])
    if not user:
        await callback.message.edit_text("❌ المستخدم غير موجود.")
        await state.clear()
        return

    old_balance = user['balance']
    amount = data['amount']
    if data['operation'] == 'add':
        new_balance = old_balance + amount
        tx_type = 'charge'  # or 'adjustment' if you added it
        op_desc = "زيادة"
    else:
        new_balance = old_balance - amount
        if new_balance < 0:
            await callback.message.edit_text("❌ لا يمكن أن يصبح الرصيد سالباً.")
            return
        tx_type = 'adjustment'  # we'll use 'adjustment' for both directions
        op_desc = "خصم"

    async with db.pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("UPDATE users SET balance = $1 WHERE id = $2", new_balance, user['id'])
            # Insert transaction
            await conn.execute(
                "INSERT INTO transactions (user_id, amount, type, description) VALUES ($1, $2, $3, $4)",
                user['id'], amount, tx_type, f"تعديل رصيد بواسطة المشرف ({op_desc})"
            )

    await state.clear()
    await callback.message.edit_text(
        f"✅ تم تعديل الرصيد بنجاح.\n"
        f"المستخدم: {escape_html(user['full_name'])}\n"
        f"الرصيد الجديد: {new_balance} ل.س",
        parse_mode="HTML"
    )

    # Notify user
    user_text = (
        f"🔔 تم تعديل رصيدك بواسطة المشرف.\n"
        f"العملية: {op_desc} {amount} ل.س\n"
        f"الرصيد الجديد: {new_balance} ل.س"
    )
    await bot.send_message(user['chat_id'], user_text, parse_mode="HTML")
    await callback.answer()

# -------------------------------------------------------------------
# Existing admin_user_info handler (unchanged)
# -------------------------------------------------------------------
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
        type_ar = "شحن" if tx['type'] == 'charge' else "شراء" if tx['type'] == 'purchase' else "تعديل"
        line = f"• {tx['created_at'].strftime('%Y-%m-%d %H:%M')} – {type_ar}: {tx['amount']} ل.س"
        if tx['description']:
            line += f" ({escape_html(tx['description'])})"
        tx_lines.append(line)
    tx_text = "\n".join(tx_lines) if tx_lines else "لا توجد عمليات بعد."

    ref_count = await get_referral_count(user['id'])
    text = (
        f"👤 **ملف المستخدم**\n\n"
        f"ID: <code>{user['chat_id']}</code>\n"
        f"الاسم: {escape_html(user['full_name'])}\n"
        f"الرصيد: {user['balance']} ل.س\n"
        f"تاريخ الانضمام: {user['created_at'].strftime('%Y-%m-%d') if user.get('created_at') else 'غير معروف'}\n"
        f"عدد المدعوين: {ref_count}\n\n"
        f"**آخر العمليات:**\n{tx_text}"
    )
    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "admin_back_to_main")
async def admin_back_to_main(callback: types.CallbackQuery, state: FSMContext):
    """Return to main admin menu."""
    from .commands_handler import show_main_menu
    await show_main_menu(
        callback.message,
        state,
        set_reply_keyboard=False,
        user_id=callback.from_user.id,
        user_name=callback.from_user.full_name
    )
    await callback.answer()
    await callback.message.delete()

@router.callback_query(F.data == "admin_view_user")
async def admin_view_user_start(callback: types.CallbackQuery, state: FSMContext):
    """Start the view user flow: ask for chat ID."""
    await state.set_state(AdminViewUser.waiting_chat_id)
    builder = get_cancel_button()
    await callback.message.edit_text(
        "✏️ أدخل **معرف المستخدم** (chat ID) لعرض معلوماته:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()

@router.message(AdminViewUser.waiting_chat_id, F.text.not_in(SPECIAL_BUTTONS))
async def admin_view_user_chat_id(message: types.Message, state: FSMContext):
    try:
        chat_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ معرف غير صالح. الرجاء إدخال رقم.")
        return

    user = await db.fetchrow("SELECT * FROM users WHERE chat_id = $1", chat_id)
    if not user:
        await message.answer("❌ المستخدم غير موجود.")
        await state.clear()
        return

    # Get last 5 transactions
    txs = await db.fetch("""
        SELECT amount, type, description, created_at
        FROM transactions
        WHERE user_id = $1
        ORDER BY created_at DESC
        LIMIT 5
    """, user['id'])
    tx_lines = []
    for tx in txs:
        type_ar = "شحن" if tx['type'] == 'charge' else "شراء" if tx['type'] == 'purchase' else "تعديل"
        line = f"• {tx['created_at'].strftime('%Y-%m-%d %H:%M')} – {type_ar}: {tx['amount']} ل.س"
        if tx['description']:
            line += f" ({escape_html(tx['description'])})"
        tx_lines.append(line)
    tx_text = "\n".join(tx_lines) if tx_lines else "لا توجد عمليات بعد."

    ref_count = await get_referral_count(user['id'])
    text = (
        f"👤 **ملف المستخدم**\n\n"
        f"ID: <code>{user['chat_id']}</code>\n"
        f"الاسم: {escape_html(user['full_name'])}\n"
        f"الرصيد: {user['balance']} ل.س\n"
        f"تاريخ الانضمام: {user['created_at'].strftime('%Y-%m-%d') if user.get('created_at') else 'غير معروف'}\n"
        f"عدد المدعوين: {ref_count}\n\n"
        f"**آخر العمليات:**\n{tx_text}"
    )

    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="💰 تعديل رصيد", callback_data=f"admin_adjust_balance_for:{user['chat_id']}"))
    builder.row(types.InlineKeyboardButton(text="🔙 رجوع", callback_data="admin_user_management"))
    await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await state.clear()

# Modify the existing admin_adjust_start to also accept a direct chat_id from callback
@router.callback_query(F.data == "admin_adjust_balance")
async def admin_adjust_start_no_id(callback: types.CallbackQuery, state: FSMContext):
    """Start balance adjustment without pre-filled chat ID."""
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("غير مصرح.", show_alert=True)
        return
    await state.set_state(AdminBalanceAdjust.waiting_chat_id)
    builder = get_cancel_button()
    await callback.message.edit_text(
        "✏️ أدخل **معرف المستخدم** (chat ID) لضبط رصيده:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("admin_adjust_balance_for:"))
async def admin_adjust_start_with_id(callback: types.CallbackQuery, state: FSMContext):
    """Start balance adjustment with pre-filled chat ID from view user."""
    chat_id = int(callback.data.split(":")[1])
    user = await db.fetchrow("SELECT * FROM users WHERE chat_id = $1", chat_id)
    if not user:
        await callback.answer("المستخدم غير موجود.", show_alert=True)
        return
    await state.update_data(target_chat_id=chat_id, target_user_id=user['id'])
    await state.set_state(AdminBalanceAdjust.waiting_operation)
    # Show user info and ask for operation (same as before)
    text = (
        f"👤 **معلومات المستخدم**\n\n"
        f"الاسم: {escape_html(user['full_name'])}\n"
        f"الرصيد الحالي: {user['balance']} ل.س\n"
        f"تاريخ الانضمام: {user['created_at'].strftime('%Y-%m-%d') if user.get('created_at') else 'غير معروف'}\n\n"
        f"اختر العملية:"
    )
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="➕ زيادة", callback_data="op_add"),
        types.InlineKeyboardButton(text="➖ نقصان", callback_data="op_sub")
    )
    builder.row(types.InlineKeyboardButton(text="❌ إلغاء", callback_data="cancel_action"))
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await callback.answer()

PAGE_SIZE = 5 
@router.callback_query(F.data == "admin_list_users")
async def admin_list_users(callback: types.CallbackQuery):
    total = await db.fetchval("SELECT COUNT(*) FROM users")
    # 1. Send full list (text or file)
    if total < 10:
        full_text = await generate_full_users_text(callback.bot)
        await callback.message.answer(full_text, parse_mode="HTML")
    else:
        # Generate a temporary file
        full_text = await generate_full_users_text(callback.bot)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
            f.write(full_text)
            tmp_path = f.name
        await callback.message.answer_document(
            document=FSInputFile(tmp_path, filename="users_list.txt"),
            caption=f"إجمالي المستخدمين: {total}"
        )
        # Clean up
        import os
        os.unlink(tmp_path)

    # 2. Send paginated interactive list
    await show_users_page(callback, bot=callback.bot, page=0)

async def show_users_page(target, bot, page: int):
    """Display users list with pagination, fetching usernames live."""
    if isinstance(target, types.CallbackQuery):
        message = target.message
        is_callback = True
    else:
        message = target
        is_callback = False

    offset = page * PAGE_SIZE
    users = await db.fetch("""
        SELECT chat_id, full_name, balance, created_at
        FROM users
        ORDER BY created_at DESC
        LIMIT $1 OFFSET $2
    """, PAGE_SIZE, offset)

    total = await db.fetchval("SELECT COUNT(*) FROM users")
    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE

    if not users:
        text = "لا يوجد مستخدمين بعد."
        builder = InlineKeyboardBuilder()
        builder.row(types.InlineKeyboardButton(text="🔙 رجوع", callback_data="admin_user_management"))
        if is_callback:
            await message.edit_text(text, reply_markup=builder.as_markup())
        else:
            await message.answer(text, reply_markup=builder.as_markup())
        return

    # Build message text with live usernames
    lines = [f"📋 **قائمة المستخدمين (صفحة {page+1}/{total_pages})**\n"]
    for u in users:
        # Try to get username from Telegram
        try:
            chat = await bot.get_chat(u['chat_id'])
            username_display = f"@{chat.username}" if chat.username else "—"
        except:
            username_display = "—"

        created = u['created_at'].strftime('%Y-%m-%d') if u['created_at'] else "—"
        lines.append(
            f"🆔 <code>{u['chat_id']}</code> | {username_display}\n"
            f"👤 {escape_html(u['full_name'])}\n"
            f"💰 {u['balance']} ل.س | 📅 {created}\n"
        )
    text = "\n".join(lines)

    builder = InlineKeyboardBuilder()
    # User buttons – each opens admin_user_info
    for u in users:
        display_name = u['full_name'][:20] + "..." if len(u['full_name']) > 20 else u['full_name']
        builder.row(types.InlineKeyboardButton(
            text=display_name,
            callback_data=f"admin_user_info:{u['chat_id']}"
        ))

    # Pagination buttons
    if total_pages > 1:
        nav_row = []
        if page > 0:
            nav_row.append(types.InlineKeyboardButton(text="◀️", callback_data=f"admin_users_page:{page-1}"))
        nav_row.append(types.InlineKeyboardButton(text=f"{page+1}/{total_pages}", callback_data="ignore"))
        if page < total_pages-1:
            nav_row.append(types.InlineKeyboardButton(text="▶️", callback_data=f"admin_users_page:{page+1}"))
        builder.row(*nav_row)

    builder.row(types.InlineKeyboardButton(text="🔙 رجوع", callback_data="admin_user_management"))

    # if is_callback:
    #     await message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    # else:
    #     await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    if is_callback:
        await message.delete()
    await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        
@router.callback_query(F.data.startswith("admin_users_page:"))
async def admin_users_page(callback: types.CallbackQuery):
    page = int(callback.data.split(":")[1])
    await show_users_page(callback, bot=callback.bot, page=int(page))
    await callback.answer()

async def generate_full_users_text(bot) -> str:
    """Generate a text report of all users with live usernames."""
    users = await db.fetch("SELECT id, chat_id, full_name, balance, created_at FROM users ORDER BY created_at DESC")
    lines = [f"إجمالي المستخدمين: {len(users)}\n", "="*50 + "\n"]
    for u in users:
        try:
            chat = await bot.get_chat(u['chat_id'])
            username = f"@{chat.username}" if chat.username else "—"
        except:
            username = "—"
        created = u['created_at'].strftime('%Y-%m-%d %H:%M') if u['created_at'] else "—"
        ref_count = await get_referral_count(u['id'])
        lines.append(
            f"ID: {u['chat_id']} | {username}\n"
            f"الاسم: {u['full_name']}\n"
            f"الرصيد: {u['balance']} ل.س\n"
            f"تاريخ الانضمام: {created}\n"
            f"عدد المدعوين: {ref_count}\n"
            + "-"*40 + "\n"
        )
    return "\n".join(lines)


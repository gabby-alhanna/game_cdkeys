import os
import html
from aiogram import Router, types, F
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from database_methods import get_or_create_user, is_system_ready
from reply_buttons import get_all_buttons, build_reply_keyboard
from .settings_handler import show_settings_menu
from .referral_handler import process_referral
from database import db
from decimal import Decimal

router = Router()
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID"))
    
def escape_html(text):
    return html.escape(str(text) if text is not None else "")

async def show_main_menu(
    message: types.Message,
    state: FSMContext = None,
    set_reply_keyboard: bool = False,
    user_id: int = None,
    user_name: str = None
):
    if state:
        await state.clear()
    
    if user_id is None:
        user_id = message.from_user.id
        user_name = message.from_user.full_name
    
    user = await get_or_create_user(user_id, user_name)
    ready, config = await is_system_ready()
    
    escaped_username = escape_html(user['full_name'])
    builder = InlineKeyboardBuilder()
    
    pending = await db.fetchrow("""
        SELECT id FROM balance_requests
        WHERE user_id = (SELECT id FROM users WHERE chat_id = $1)
        AND status = 'pending'
    """, user_id)
    
    # Only show welcome message on explicit start (Main or /start)
    if set_reply_keyboard:
        main_button = await db.fetchrow("SELECT image_file_id, description FROM reply_buttons WHERE button_key = 'main'")
        if main_button:
            is_admin = (user_id == ADMIN_CHAT_ID)
            reply_kb = await build_reply_keyboard(is_admin) if set_reply_keyboard else None
            
            welcome_text = main_button['description'] or "مرحباً بك في البوت!"
            if main_button['image_file_id']:
                await message.answer_photo(
                    photo=main_button['image_file_id'],
                    caption=welcome_text,
                    reply_markup=reply_kb,
                    parse_mode="HTML"
                )
            else:
                await message.answer(welcome_text, parse_mode="HTML", reply_markup=reply_kb)
    
    if user_id == 'ADMIN_CHAT_ID':
        text = (
            f"👤 <b>معرف المشرف:</b> <code>{escape_html(user_id)}</code>\n"
            f"⚡ <b>إدارة النظام</b>"
        )
        builder.row(types.InlineKeyboardButton(text="عرض طلبات الشحن", callback_data="admin_requests"))
        builder.row(types.InlineKeyboardButton(text="عرض الألعاب", callback_data="admin_games"))
        builder.row(types.InlineKeyboardButton(text="عرض المشتريات", callback_data="admin_purchases"))
        builder.row(types.InlineKeyboardButton(text="إدارة المستخدمين", callback_data="admin_user_management"))
        builder.row(types.InlineKeyboardButton(text="تعديل المعلومات", callback_data="admin_edit"))
    else:
        if not ready:
            builder.row(types.InlineKeyboardButton(
                text="⚠️ حالة النظام (اضغط للتفاصيل)",
                callback_data="system_not_ready"
            ))
            builder.row(types.InlineKeyboardButton(text="تصفح الألعاب", callback_data="view_games"))
            builder.row(types.InlineKeyboardButton(text="سجل العمليات", callback_data="view_history"))
            await message.answer(
                "مرحباً! النظام قيد التحديث حالياً. يرجى المحاولة لاحقاً.",
                reply_markup=builder.as_markup(),
                parse_mode="HTML"
            )
            return
        else:
            text = (
                f"👤 <b>المعرف:</b> <code>{escape_html(user['chat_id'])}</code>\n"
                f"🏷 <b>المستخدم:</b> {escaped_username}\n"
                f"💰 <b>الرصيد:</b> {escape_html(user['balance'])} ل.س"
            )
            if pending:
                builder.row(types.InlineKeyboardButton(text="⏳ طلب معلق", callback_data="view_pending_request"))
            else:
                builder.row(types.InlineKeyboardButton(text="شحن الرصيد", callback_data="charge_balance"))
            
            builder.row(types.InlineKeyboardButton(text="تصفح الألعاب", callback_data="view_games"))
            builder.row(types.InlineKeyboardButton(text="سجل العمليات", callback_data="view_history"))
            builder.row(types.InlineKeyboardButton(text="🎁 الإحالات", callback_data="referral_menu"))

    await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")


# 1. Global Start Command
@router.message(CommandStart(), F.chat.type == "private")
async def cmd_start(message: types.Message, state: FSMContext):
    args = message.text.split()
    if len(args) > 1:
        code = args[1]
        await process_referral(message.from_user.id, code, message.bot)
    await show_main_menu(message, state, set_reply_keyboard=True)


@router.message(F.text, F.chat.type == "private")
async def handle_reply_buttons(message: types.Message, state: FSMContext):

    # 2. Handle special button texts
    buttons = await get_all_buttons()
    button_map = {b['display_text']: b for b in buttons}
    if message.text in button_map:
        btn = button_map[message.text]
        key = btn['button_key']
        if key == 'main':
            await show_main_menu(message, state, set_reply_keyboard=True)
        elif key == 'help':
            await state.clear()
            text = btn['description'] or "ℹ️ لم يتم تعيين نص المساعدة."
            if btn['image_file_id']:
                await message.answer_photo(photo=btn['image_file_id'], caption=text, parse_mode="HTML")
            else:
                await message.answer(text, parse_mode="HTML")
        elif key == 'about':
            await state.clear()
            text = btn['description'] or "ℹ️ لم يتم تعيين نص المعلومات."
            if btn['image_file_id']:
                await message.answer_photo(photo=btn['image_file_id'], caption=text, parse_mode="HTML")
            else:
                await message.answer(text, parse_mode="HTML")
        return

    # 3. Handle Settings button
    if message.text == "⚙️ الإعدادات" and message.from_user.id == ADMIN_CHAT_ID:
        await show_settings_menu(message, state)
        return

    # 4. If there is an active FSM state, skip this handler so FSM handlers can process it
    current_state = await state.get_state()
    if current_state is not None:
        return

    # 5. No active state and not a button – fallback
    await message.answer("عذراً، لم أفهم ما قلته. الرجاء استخدام الأزرار أدناه.")
    await show_main_menu(
        message,
        state,
        set_reply_keyboard=False,
        user_id=message.from_user.id,
        user_name=message.from_user.full_name
    )
# --- Callbacks remain the same ---

@router.callback_query(F.data == "system_not_ready")
async def system_not_ready_popup(callback: types.CallbackQuery):
    await callback.answer("🛠 النظام قيد التحديث حالياً. يرجى المحاولة لاحقاً.", show_alert=True)

@router.callback_query(F.data == "view_pending_request")
async def view_pending_request(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    req = await db.fetchrow("""
        SELECT br.id, br.transfer_code, br.description, br.created_at
        FROM balance_requests br
        JOIN users u ON u.id = br.user_id
        WHERE u.chat_id = $1 AND br.status = 'pending'
    """, user_id)
    if not req:
        await callback.answer("لا يوجد طلب معلق.", show_alert=True)
        return
    
    text = (
        f"⏳ <b>طلب شحن معلق</b>\n\n"
        f"🆔 رقم الطلب: <code>{req['id']}</code>\n"
        f"🔑 رمز التحويل: <code>{escape_html(req['transfer_code'])}</code>\n"
        f"📝 الوصف:\n{escape_html(req['description'] or '—')}\n"
        f"🕐 تاريخ الإنشاء: {req['created_at'].strftime('%Y-%m-%d %H:%M')}"
    )
    kb = InlineKeyboardBuilder()
    kb.row(
        types.InlineKeyboardButton(text="❌ حذف الطلب", callback_data=f"delete_pending_request:{req['id']}"),
        types.InlineKeyboardButton(text="🔙 رجوع", callback_data="back_to_main")
    )
    await callback.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.startswith("delete_pending_request:"))
async def delete_pending_request(callback: types.CallbackQuery, state: FSMContext):
    req_id = callback.data.split(":")[1]
    user_id = callback.from_user.id
    req = await db.fetchrow(
        "SELECT id FROM balance_requests WHERE id=$1 AND user_id=(SELECT id FROM users WHERE chat_id=$2) AND status='pending'",
        req_id, user_id
    )
    if not req:
        await callback.answer("الطلب غير موجود أو تمت معالجته بالفعل.", show_alert=True)
        return
    
    await db.execute("DELETE FROM balance_requests WHERE id=$1", req_id)
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="🔙 العودة إلى الرئيسية", callback_data="back_to_main"))
    await callback.message.edit_text("✅ تم حذف طلبك المعلق.", reply_markup=kb.as_markup())
    await callback.answer()

@router.callback_query(F.data == "back_to_main")
async def back_to_main(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await show_main_menu(
        callback.message,
        state,
        set_reply_keyboard=False,
        user_id=callback.from_user.id,
        user_name=callback.from_user.full_name
    )
    await callback.answer()
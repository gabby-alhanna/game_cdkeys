from aiogram import Router, types, F
import html
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from reply_buttons import get_button, update_button, get_all_buttons
from .common_handlers import get_cancel_button
from .hint_tracker import reset_keyboard_hint, _shown_keyboard_hint
from static_lists import SPECIAL_BUTTONS, load_special_buttons
from .request_handler import method_display
import os
from database import db

router = Router()
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID"))

class EditPayment(StatesGroup):
    waiting_method = State()
    waiting_code = State()
    waiting_qr = State()

class EditButton(StatesGroup):
    waiting_display_text = State()
    waiting_image = State()
    waiting_description = State()

def escape_html(text):
    return html.escape(str(text) if text is not None else "")


async def show_settings_menu(message: types.Message, state: FSMContext = None):
    """Main admin settings menu."""
    if state:
        await state.clear()
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🔘 تعديل الأزرار", callback_data="admin_edit_buttons"))
    builder.row(types.InlineKeyboardButton(text="🎁 إعدادات الإحالة", callback_data="admin_referral_settings"))
    builder.row(types.InlineKeyboardButton(text="🔙 رجوع", callback_data="settings_back"))
    await message.answer(
        "⚙️ **الإعدادات**\nاختر القسم الذي تريد تعديله:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )

@router.callback_query(F.data == "admin_edit_buttons")
async def admin_edit_buttons(callback: types.CallbackQuery):
    """Show list of reply buttons to edit."""
    buttons = await get_all_buttons()
    if not buttons:
        await callback.message.edit_text("لا توجد أزرار.")
        return
    builder = InlineKeyboardBuilder()
    for btn in buttons:
        builder.row(types.InlineKeyboardButton(
            text=f"✏️ {btn['display_text']}",
            callback_data=f"reply-buttons-edit_{btn['button_key']}"
        ))
    builder.row(types.InlineKeyboardButton(text="🔙 رجوع", callback_data="settings_main"))
    await callback.message.edit_text(
        "📋 **اختر الزر الذي تريد تعديله:**",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data == "settings_main")
async def settings_main(callback: types.CallbackQuery, state: FSMContext):
    """Return to main settings menu."""
    await show_settings_menu(callback.message, state)
    await callback.message.delete()
    await callback.answer()

@router.callback_query(F.data.startswith("reply-buttons-edit_"))
async def start_edit(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_CHAT_ID:
        await callback.answer("غير مصرح لك.", show_alert=True)
        return
    key = callback.data.split("_")[1]
    await state.update_data(button_key=key)
    await state.set_state(EditButton.waiting_display_text)
    builder = get_cancel_button()
    await callback.message.answer(
        f"✏️ أدخل **النص الجديد** للزر (الزر الحالي: {key}):",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()

@router.message(EditButton.waiting_display_text)
async def get_display_text(message: types.Message, state: FSMContext):
    await state.update_data(display_text=message.text)
    await state.set_state(EditButton.waiting_image)
    builder = get_cancel_button()
    await message.answer(
        "🖼 أرسل **صورة** للزر (أو أرسل '.' للتخطي):",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )

@router.message(EditButton.waiting_image, F.photo, F.text.not_in(SPECIAL_BUTTONS))
async def get_image(message: types.Message, state: FSMContext):
    file_id = message.photo[-1].file_id
    await state.update_data(image_file_id=file_id)
    await state.set_state(EditButton.waiting_description)
    builder = get_cancel_button()
    await message.answer(
        "📝 أرسل **وصفاً** للزر (أو أرسل '.' للتخطي):",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )

@router.message(EditButton.waiting_image, F.text == ".", F.text.not_in(SPECIAL_BUTTONS)) 
async def skip_image(message: types.Message, state: FSMContext):
    await state.update_data(image_file_id=None)
    await state.set_state(EditButton.waiting_description)
    builder = get_cancel_button()
    await message.answer(
        "📝 أرسل **وصفاً** للزر (أو أرسل '.' للتخطي):",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )

@router.message(EditButton.waiting_description, F.text.not_in(SPECIAL_BUTTONS))
async def get_description(message: types.Message, state: FSMContext):
    desc = message.text if message.text != '.' else None
    data = await state.get_data()
    button_key = data['button_key']
    display_text = data['display_text']
    image_file_id = data.get('image_file_id')
    await update_button(button_key, display_text=display_text, image_file_id=image_file_id, description=desc)
    reset_keyboard_hint()
    await state.clear()
    await message.answer(f"✅ تم تحديث الزر **{button_key}** بنجاح!", parse_mode="HTML")
    await load_special_buttons()
    await show_settings_menu(message)

@router.callback_query(F.data == "settings_back")
async def settings_back(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    # العودة إلى القائمة الرئيسية
    from .commands_handler import show_main_menu
    await show_main_menu(
        callback.message,
        user_id=ADMIN_CHAT_ID,
        user_name="Admin",
        set_reply_keyboard=False
    )
    await callback.answer()
    await callback.message.delete()

async def get_payment_info(method: str):
    row = await db.fetchrow("SELECT * FROM system_settings WHERE id=1")
    if not row:
        return None, None
    if method == "sham":
        return row.get('superadmin_shamcash_code'), row.get('superadmin_qr_file_id')
    elif method == "syriatel":
        return row.get('syriatel_code'), row.get('syriatel_qr_file_id')
    elif method == "mtn":
        return row.get('mtn_code'), row.get('mtn_qr_file_id')
    return None, None

@router.callback_query(F.data == "admin_edit")
async def admin_edit_menu(callback: types.CallbackQuery, state: FSMContext):
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="💰 شام كاش", callback_data="edit_pay:sham"))
    builder.row(types.InlineKeyboardButton(text="📱 سيريتيل كاش", callback_data="edit_pay:syriatel"))
    builder.row(types.InlineKeyboardButton(text="📱 إم تي إن كاش", callback_data="edit_pay:mtn"))
    builder.row(types.InlineKeyboardButton(text="🔙 تراجع", callback_data="settings_back"))
    await callback.message.edit_text(
        "⚙️ **تعديل معلومات الدفع**\nاختر الطريقة التي تريد تعديلها:",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

@router.callback_query(F.data.startswith("edit_pay:"))
async def edit_payment_start(callback: types.CallbackQuery, state: FSMContext):
    method = callback.data.split(":")[1]
    await state.update_data(method=method)
    current_code, current_qr = await get_payment_info(method)

    # إرسال المعلومات الحالية
    if current_qr:
        caption = f"🔑 **الرمز الحالي:** <code>{escape_html(current_code or 'غير محدد')}</code>\n\n📤 أرسل الرمز الجديد أو أرسل '.' للإبقاء على القديم."
        await callback.message.answer_photo(
            photo=current_qr,
            caption=caption,
            parse_mode="HTML"
        )
    else:
        text = f"🔑 **الرمز الحالي:** {escape_html(current_code or 'غير محدد')}\n\n📤 أرسل الرمز الجديد أو أرسل '.' للإبقاء على القديم."
        await callback.message.answer(text, parse_mode="HTML")

    await state.set_state(EditPayment.waiting_code)
    builder = get_cancel_button()
    await callback.message.answer(
        "✏️ الرمز الجديد:",
        reply_markup=builder.as_markup()
    )
    await callback.message.delete()
    await callback.answer()

@router.message(EditPayment.waiting_code, F.text.not_in(SPECIAL_BUTTONS))
async def edit_payment_code(message: types.Message, state: FSMContext):
    # تحقق مما إذا كانت الرسالة نصية
    if message.text is None:
        await message.answer("❌ الرجاء إرسال نص (الرمز الجديد) أو '.' للإبقاء على القديم.")
        return
    text = message.text.strip()
    if text == '.':
        await state.update_data(keep_code=True)
    else:
        await state.update_data(new_code=text, keep_code=False)
    await state.set_state(EditPayment.waiting_qr)
    builder = get_cancel_button()
    await message.answer(
        "🖼 الآن قم برفع **صورة رمز QR** الجديدة (أو أرسل '.' للإبقاء على القديمة):",
        reply_markup=builder.as_markup()
    )

@router.message(EditPayment.waiting_code, F.text.not_in(SPECIAL_BUTTONS))
async def edit_payment_code_non_text(message: types.Message):
    await message.answer("❌ الرجاء إرسال نص (الرمز الجديد) أو '.' للإبقاء على القديم.")

@router.message(EditPayment.waiting_qr, F.photo)
async def edit_payment_qr(message: types.Message, state: FSMContext):
    file_id = message.photo[-1].file_id
    await state.update_data(new_qr=file_id, keep_qr=False)
    await finalize_payment_update(message, state)

@router.message(EditPayment.waiting_qr, F.text == ".")
async def edit_payment_qr_skip(message: types.Message, state: FSMContext):
    await state.update_data(keep_qr=True)
    await finalize_payment_update(message, state)

@router.message(EditPayment.waiting_qr)
async def edit_payment_qr_non_text(message: types.Message):
    await message.answer("❌ الرجاء إرسال صورة أو أرسل '.' للإبقاء على القديمة.")

async def finalize_payment_update(message: types.Message, state: FSMContext):
    data = await state.get_data()
    method = data['method']

    if method == "sham":
        code_col = "superadmin_shamcash_code"
        qr_col = "superadmin_qr_file_id"
    elif method == "syriatel":
        code_col = "syriatel_code"
        qr_col = "syriatel_qr_file_id"
    elif method == "mtn":
        code_col = "mtn_code"
        qr_col = "mtn_qr_file_id"
    else:
        await message.answer("❌ طريقة دفع غير معروفة.")
        await state.clear()
        return

    sets = []
    args = []

    if not data.get('keep_code', False) and 'new_code' in data:
        sets.append(f"{code_col} = ${len(args)+1}")
        args.append(data['new_code'])
    if not data.get('keep_qr', False) and 'new_qr' in data:
        sets.append(f"{qr_col} = ${len(args)+1}")
        args.append(data['new_qr'])

    if sets:
        query = f"UPDATE system_settings SET {', '.join(sets)} WHERE id=1"
        await db.execute(query, *args)
        await message.answer(f"✅ تم تحديث طريقة {method_display(method)} بنجاح.")
    else:
        await message.answer("لم يتم إجراء أي تغييرات.")

    await state.clear()
    # العودة إلى قائمة تعديل الدفع
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🔙 العودة إلى تعديل الدفع", callback_data="admin_edit"))
    await message.answer("اختر طريقة أخرى أو عد للقائمة الرئيسية.", reply_markup=builder.as_markup())
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from reply_buttons import get_button, update_button, get_all_buttons
from .common_handlers import get_cancel_button
from .hint_tracker import reset_keyboard_hint, _shown_keyboard_hint
from static_lists import SPECIAL_BUTTONS, load_special_buttons

import os

router = Router()
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID"))

class EditButton(StatesGroup):
    waiting_display_text = State()
    waiting_image = State()
    waiting_description = State()

async def show_settings_menu(message: types.Message, state: FSMContext = None):
    if state:
        await state.clear()
    builder = InlineKeyboardBuilder()
    buttons = await get_all_buttons()
    for btn in buttons:
        builder.row(types.InlineKeyboardButton(
            text=f"تعديل {btn['display_text']}",
            callback_data=f"reply-buttons-edit_{btn['button_key']}"
        ))
    builder.row(types.InlineKeyboardButton(text="🔙 رجوع", callback_data="settings_back"))
    await message.answer("⚙️ **الإعدادات** – اختر زراً لتعديله:", reply_markup=builder.as_markup(), parse_mode="HTML")

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

@router.message(EditButton.waiting_image, F.photo)
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

@router.message(EditButton.waiting_image, F.text == ".") 
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
    await show_settings_menu(message)

@router.callback_query(F.data == "settings_back")
async def settings_back(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.delete()
    # العودة إلى القائمة الرئيسية
    from .commands_handler import show_main_menu
    await show_main_menu(
        callback.message,
        user_id=ADMIN_CHAT_ID,
        user_name="Admin",
        set_reply_keyboard=False
    )
    await callback.answer()
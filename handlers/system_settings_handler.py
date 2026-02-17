from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from static_lists import SPECIAL_BUTTONS
from .common_handlers import get_cancel_button

router = Router()

class AdminEdit(StatesGroup):
    waiting_code = State()
    waiting_qr = State()

@router.callback_query(F.data == "admin_edit")
async def start_edit(callback: types.CallbackQuery, state: FSMContext):
    builder = get_cancel_button()  # الحصول على builder جديد مع زر إلغاء
    await state.set_state(AdminEdit.waiting_code)
    await callback.message.answer(
        "📝 أرسل **رمز ShamCash** الجديد:",
        reply_markup=builder.as_markup()
    )
    await callback.message.delete()
    await callback.answer()

@router.message(AdminEdit.waiting_code, F.text.not_in(SPECIAL_BUTTONS))
async def get_code(message: types.Message, state: FSMContext):
    await state.update_data(code=message.text)
    await state.set_state(AdminEdit.waiting_qr)
    builder = get_cancel_button()
    await message.answer(
        "🖼 الآن قم برفع **صورة رمز QR**:",
        reply_markup=builder.as_markup()
    )

@router.message(AdminEdit.waiting_qr, F.photo)
async def get_qr(message: types.Message, state: FSMContext):
    data = await state.get_data()
    file_id = message.photo[-1].file_id
    # تحديث قاعدة البيانات
    from database import db
    await db.pool.execute(
        "UPDATE system_settings SET superadmin_shamcash_code=$1, superadmin_qr_file_id=$2 WHERE id=1",
        data['code'], file_id
    )
    await state.clear()
    await message.answer("✅ تم تحديث النظام بنجاح.")
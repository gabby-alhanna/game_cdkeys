from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest

router = Router()

@router.callback_query(F.data == "cancel_action")
async def cancel_handler(callback: types.CallbackQuery, state: FSMContext):
    """إجراء إلغاء شامل – يمسح الحالة، ويحذف الرسالة الأصلية، ويرسل إشعار الإلغاء."""
    await state.clear()
    try:
        # حذف الرسالة التي تحتوي على زر الإلغاء (صورة أو نص)
        await callback.message.delete()
    except TelegramBadRequest:
        # إذا فشل الحذف (مثلاً الرسالة قديمة جداً)، نرسل رسالة الإلغاء على أي حال
        pass

    # إرسال رسالة جديدة لتأكيد الإلغاء
    await callback.message.answer("❌ تم الإلغاء.")
    await callback.answer()  # إخفاء تحميل الزر

def get_cancel_button() -> InlineKeyboardBuilder:
    """تُعيد builder يحتوي على زر إلغاء واحد."""
    builder = InlineKeyboardBuilder()
    builder.add(types.InlineKeyboardButton(text="❌ إلغاء", callback_data="cancel_action"))
    return builder

@router.callback_query(F.data == "ignore")
async def handle_ignore_callback(callback: types.CallbackQuery):
    """
    معالج للأزرار التي لا تتطلب استجابة.
    هذا يمنع ظهور علامة التحميل (الخادم لا يستجيب) عند المستخدم.
    """
    await callback.answer()
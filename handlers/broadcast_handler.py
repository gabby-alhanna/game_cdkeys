from aiogram import Router, types, F
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from database import db
from .common_handlers import get_cancel_button
import os
import logging
import asyncio

router = Router()
ADMIN_ID = int(os.getenv("ADMIN_CHAT_ID"))

class Broadcast(StatesGroup):
    waiting_text = State()
    waiting_media = State()
    waiting_confirmation = State()

@router.message(Command("broadcast"), F.chat.type == "private")
async def cmd_broadcast(message: types.Message, state: FSMContext):
    """بدء عملية البث (للمشرف فقط)."""
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ لست مخولاً لاستخدام هذا الأمر.")
        return

    await state.set_state(Broadcast.waiting_text)
    builder = get_cancel_button()
    await message.answer(
        "📝 الرجاء إدخال **النص** الذي تريد بثه.\n"
        "يمكنك أيضًا إرسال صورة أو فيديو بعد هذه الخطوة.",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )

@router.message(Broadcast.waiting_text, F.text)
async def broadcast_get_text(message: types.Message, state: FSMContext):
    await state.update_data(text=message.html_text)  # تخزين النص بصيغة HTML
    await state.set_state(Broadcast.waiting_media)
    builder = get_cancel_button()
    await message.answer(
        "🖼 الآن أرسل **صورة** أو **فيديو** (اختياري)، أو أرسل '.' لتخطي الوسائط.",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )

@router.message(Broadcast.waiting_media, F.photo)
async def broadcast_get_photo(message: types.Message, state: FSMContext):
    file_id = message.photo[-1].file_id
    caption = message.caption or ""  # تعليق اختياري للوسائط
    await state.update_data(media_type='photo', media_file_id=file_id, media_caption=caption)
    await show_confirmation(message, state)

@router.message(Broadcast.waiting_media, F.video)
async def broadcast_get_video(message: types.Message, state: FSMContext):
    file_id = message.video.file_id
    caption = message.caption or ""
    await state.update_data(media_type='video', media_file_id=file_id, media_caption=caption)
    await show_confirmation(message, state)

@router.message(Broadcast.waiting_media, F.text == ".")
async def broadcast_skip_media(message: types.Message, state: FSMContext):
    await state.update_data(media_type=None)
    await show_confirmation(message, state)

async def show_confirmation(message: types.Message, state: FSMContext):
    data = await state.get_data()
    text = data.get('text', '')
    media_type = data.get('media_type')
    media_caption = data.get('media_caption', '')

    preview = "📨 **معاينة البث**\n\n"
    preview += f"النص: {text}\n"
    if media_type:
        preview += f"الوسائط: {media_type} (تعليق: {media_caption or 'بدون'})"
    else:
        preview += "الوسائط: لا يوجد"

    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="✅ إرسال", callback_data="broadcast_confirm"),
        types.InlineKeyboardButton(text="❌ إلغاء", callback_data="broadcast_cancel")
    )
    await message.answer(preview, reply_markup=builder.as_markup(), parse_mode="HTML")
    await state.set_state(Broadcast.waiting_confirmation)

@router.callback_query(Broadcast.waiting_confirmation, F.data == "broadcast_confirm")
async def broadcast_confirm(callback: types.CallbackQuery, state: FSMContext, bot):
    data = await state.get_data()
    text = data.get('text', '')
    media_type = data.get('media_type')
    media_file_id = data.get('media_file_id')
    media_caption = data.get('media_caption', '')

    # جلب جميع المستخدمين
    users = await db.fetch("SELECT chat_id FROM users")
    if not users:
        await callback.message.edit_text("لا يوجد مستخدمون في قاعدة البيانات.")
        await state.clear()
        return

    await callback.message.edit_text("📤 جاري بدء البث... قد يستغرق هذا بعض الوقت.")
    await callback.answer()

    success = 0
    failed = 0
    for user in users:
        try:
            if media_type == 'photo':
                await bot.send_photo(
                    chat_id=user['chat_id'],
                    photo=media_file_id,
                    caption=f"{media_caption}\n\n{text}" if media_caption else text,
                    parse_mode="HTML"
                )
            elif media_type == 'video':
                await bot.send_video(
                    chat_id=user['chat_id'],
                    video=media_file_id,
                    caption=f"{media_caption}\n\n{text}" if media_caption else text,
                    parse_mode="HTML"
                )
            else:
                await bot.send_message(chat_id=user['chat_id'], text=text, parse_mode="HTML")
            success += 1
        except Exception as e:
            logging.error(f"فشل الإرسال إلى {user['chat_id']}: {e}")
            failed += 1
        # تأخير بسيط لتجنب حدود السرعة
        await asyncio.sleep(0.05)

    await callback.message.answer(f"✅ تم البث.\nنجاح: {success}\nفشل: {failed}")
    await state.clear()

@router.callback_query(Broadcast.waiting_confirmation, F.data == "broadcast_cancel")
async def broadcast_cancel(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ تم إلغاء البث.")
    await callback.answer()
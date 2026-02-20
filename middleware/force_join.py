import os
import logging
from aiogram import Bot, BaseMiddleware
from aiogram.types import Update

CHANNEL_USERNAME = "@ArshAlShahn"
CHANNEL_ID = "@ArshAlShahn"  # or your numeric string

class ForceJoinMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: Update, data: dict):
        # Extract user ID
        user_id = None
        if event.message:
            user_id = event.message.from_user.id
        elif event.callback_query:
            user_id = event.callback_query.from_user.id
        else:
            return await handler(event, data)

        # Safety: if CHANNEL_ID is not set, log and allow
        if CHANNEL_ID is None:
            logging.error("ForceJoinMiddleware: CHANNEL_ID is None! Allowing user.")
            return await handler(event, data)

        bot: Bot = data['bot']

        try:
            member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
            if member.status in ("member", "administrator", "creator"):
                return await handler(event, data)
            else:
                # User is not a member – block
                text = (
                    f"⚠️ للوصول إلى البوت، يجب أن تكون عضواً في القناة أولاً:\n"
                    f"{CHANNEL_USERNAME}\n\n"
                    f"بعد الاشتراك، أرسل /start مرة أخرى."
                )
                from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="📢 اشترك في القناة", url=f"https://t.me/{CHANNEL_USERNAME[1:]}")]
                ])
                if event.message:
                    await event.message.answer(text, reply_markup=keyboard)
                elif event.callback_query:
                    await event.callback_query.message.answer(text, reply_markup=keyboard)
                    await event.callback_query.answer()
                return
        except Exception as e:
            # If bot lacks admin rights, we cannot verify – log and allow to avoid breaking
            if "member list is inaccessible" in str(e):
                logging.warning(f"Bot lacks admin rights in channel {CHANNEL_ID}. Allowing user {user_id}.")
                return await handler(event, data)
            else:
                # Other errors (like network) – log and allow (better than crashing)
                logging.error(f"Force join check failed for user {user_id}: {e}")
                return await handler(event, data)
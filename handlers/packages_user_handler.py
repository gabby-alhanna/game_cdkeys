from aiogram import Router, types, F
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest
from game_utils import get_packages, count_packages, get_game
import html
import logging

router = Router()

def escape_html(text):
    return html.escape(str(text) if text is not None else "")

async def show_packages_page(target, game_id: str, page: int):
    """
    عرض تفاصيل اللعبة وحزمها. target يمكن أن يكون CallbackQuery أو Message.
    """
    if isinstance(target, types.CallbackQuery):
        message = target.message
        is_callback = True
    else:
        message = target
        is_callback = False

    game = await get_game(game_id)
    if not game:
        await message.answer("اللعبة غير موجودة.")
        return

    packages = await get_packages(game_id, page)
    total = await count_packages(game_id)
    total_pages = (total + 3 - 1) // 3

    # بناء التسمية التوضيحية
    caption_lines = [f"📦 <b>{escape_html(game['name'])} – الحزم</b>"]
    if game.get('description'):
        caption_lines.append(f"📝 {escape_html(game['description'])}")
    caption_lines.append("")

    if not packages:
        caption_lines.append("لا توجد حزم متاحة.")
    else:
        for p in packages:
            caption_lines.append(f"• {escape_html(p['name'])} – {p['price']} ل.س")

    caption = "\n".join(caption_lines)

    builder = InlineKeyboardBuilder()
    for p in packages:
        builder.row(
            types.InlineKeyboardButton(text=f"{p['name']} – {p['price']} ل.س", callback_data=f"buy_package:{p['id']}")
        )
    if total_pages > 1:
        nav_row = []
        if page > 0:
            nav_row.append(types.InlineKeyboardButton(text="◀️", callback_data=f"user_packages_page:{game_id}:{page-1}"))
        nav_row.append(types.InlineKeyboardButton(text=f"{page+1}/{total_pages}", callback_data="ignore"))
        if page < total_pages-1:
            nav_row.append(types.InlineKeyboardButton(text="▶️", callback_data=f"user_packages_page:{game_id}:{page+1}"))
        builder.row(*nav_row)
    builder.row(types.InlineKeyboardButton(text="🔙 العودة إلى الألعاب", callback_data="view_games"))

    # محاولة إرسال الصورة إن وجدت
    if game.get('image_file_id'):
        try:
            if is_callback:
                # First, send the photo as a new message
                await message.answer_photo(
                    photo=game['image_file_id'],
                    caption=caption,
                    reply_markup=builder.as_markup(),
                    parse_mode="HTML"
                )
                # If successful, delete the original message
                await message.delete()
            else:
                await message.answer_photo(
                    photo=game['image_file_id'],
                    caption=caption,
                    reply_markup=builder.as_markup(),
                    parse_mode="HTML"
                )
        except TelegramBadRequest as e:
            logging.warning(f"فشل إرسال صورة اللعبة {game_id}: {e}")
            # Photo failed – fallback to text
            if is_callback:
                # Original message still exists, edit it
                await message.edit_text(caption, reply_markup=builder.as_markup(), parse_mode="HTML")
            else:
                await message.answer(caption, reply_markup=builder.as_markup(), parse_mode="HTML")
    else:
        # No image
        if is_callback:
            await message.edit_text(caption, reply_markup=builder.as_markup(), parse_mode="HTML")
        else:
            await message.answer(caption, reply_markup=builder.as_markup(), parse_mode="HTML")

@router.callback_query(F.data.startswith("user_packages_page:"))
async def user_packages_page(callback: types.CallbackQuery):
    _, game_id, page = callback.data.split(":")
    await show_packages_page(callback, game_id, int(page))
    await callback.answer()
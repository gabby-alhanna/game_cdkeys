from aiogram import Router, types, F
from aiogram.utils.keyboard import InlineKeyboardBuilder
from game_utils import get_games, count_games
import html

router = Router()

def escape_html(text):
    return html.escape(str(text) if text is not None else "")

async def show_games_page(target, page: int = 0):
    """
    عرض قائمة الألعاب. target يمكن أن يكون CallbackQuery أو Message.
    """
    if isinstance(target, types.CallbackQuery):
        message = target.message
        is_callback = True
    else:
        message = target
        is_callback = False

    games = await get_games(page, only_active=True)
    total = await count_games(only_active=True)
    total_pages = (total + 3 - 1) // 3

    if not games:
        if is_callback:
            await target.answer("لا توجد ألعاب متاحة حالياً.", show_alert=True)
            return
        else:
            builder = InlineKeyboardBuilder()
            builder.row(types.InlineKeyboardButton(text="🔙 القائمة الرئيسية", callback_data="user_back"))
            await target.delete()
            await target.answer("لا توجد ألعاب متاحة حالياً.", show_alert=True, reply_markup=builder.as_markup())
            return

    else:
        text = "🎮 **الألعاب المتاحة**\n\n"
        builder = InlineKeyboardBuilder()
        for g in games:
            builder.row(types.InlineKeyboardButton(text=g['name'], callback_data=f"user_game:{g['id']}"))
        if total_pages > 1:
            nav_row = []
            if page > 0:
                nav_row.append(types.InlineKeyboardButton(text="◀️", callback_data=f"user_games_page:{page-1}"))
            nav_row.append(types.InlineKeyboardButton(text=f"{page+1}/{total_pages}", callback_data="ignore"))
            if page < total_pages-1:
                nav_row.append(types.InlineKeyboardButton(text="▶️", callback_data=f"user_games_page:{page+1}"))
            builder.row(*nav_row)
        builder.row(types.InlineKeyboardButton(text="🔙 القائمة الرئيسية", callback_data="user_back"))

    if is_callback:
        # إذا كانت الرسالة الحالية تحتوي على صورة، احذف وأرسل جديدة
        if message.photo:
            await message.delete()
            if builder:
                await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")
            else:
                await message.answer(text, parse_mode="HTML")
        else:
            # رسالة نصية – تعديل
            if builder:
                await message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
            else:
                await message.edit_text(text, parse_mode="HTML")
    else:
        # رسالة جديدة
        if builder:
            await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        else:
            await message.answer(text, parse_mode="HTML")

@router.callback_query(F.data == "view_games")
async def user_view_games(callback: types.CallbackQuery):
    # لا تحذف الرسالة المحفزة – سنقوم بتعديلها
    await show_games_page(callback, page=0)
    await callback.answer()

@router.callback_query(F.data.startswith("user_games_page:"))
async def user_games_page(callback: types.CallbackQuery):
    page = int(callback.data.split(":")[1])
    await show_games_page(callback, page)
    await callback.answer()

@router.callback_query(F.data.startswith("user_game:"))
async def user_game_selected(callback: types.CallbackQuery):
    game_id = callback.data.split(":")[1]
    # لا تحذف رسالة قائمة الألعاب – سيتم تعديلها أو استبدالها
    from handlers.packages_user_handler import show_packages_page
    await show_packages_page(callback, game_id, page=0)
    await callback.answer()

@router.callback_query(F.data == "user_back")
async def user_back(callback: types.CallbackQuery):
    # احذف الرسالة الحالية واعرض القائمة الرئيسية كرسالة جديدة
    await callback.message.delete()
    from handlers.commands_handler import show_main_menu
    await show_main_menu(
        callback.message,
        user_id=callback.from_user.id,
        user_name=callback.from_user.full_name,
        set_reply_keyboard=False
    )
    await callback.answer()
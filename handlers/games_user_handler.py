from aiogram import Router, types, F
from aiogram.utils.keyboard import InlineKeyboardBuilder
from game_utils import get_games, count_games
import html

router = Router()

def escape_html(text):
    return html.escape(str(text) if text is not None else "")

async def show_games_page(target, page: int = 0):
    """
    عرض قائمة الألعاب للمستخدم بتنسيق 4x2.
    تستخدم منطق العرض المرن (حتى 12 لعبة في صفحة واحدة).
    """
    if isinstance(target, types.CallbackQuery):
        message = target.message
        is_callback = True
    else:
        message = target
        is_callback = False

    # جلب العدد الإجمالي للألعاب النشطة فقط
    total_count = await count_games(only_active=True)
    
    # الإعدادات المثالية للتنسيق
    MAX_SINGLE_PAGE = 12 
    DEFAULT_PAGE_SIZE = 8

    # تحديد ما إذا كنا سنعرض صفحة واحدة أم نستخدم التقسيم
    if total_count <= MAX_SINGLE_PAGE:
        games = await get_games(0, only_active=True, limit=total_count)
        total_pages = 1
        current_page = 0
    else:
        games = await get_games(page, only_active=True, limit=DEFAULT_PAGE_SIZE)
        total_pages = (total_count + DEFAULT_PAGE_SIZE - 1) // DEFAULT_PAGE_SIZE
        current_page = page

    # التعامل مع حالة عدم وجود ألعاب
    if not games:
        text = "❌ لا توجد ألعاب متاحة حالياً."
        builder = InlineKeyboardBuilder()
        builder.row(types.InlineKeyboardButton(text="🔙 القائمة الرئيسية", callback_data="user_back"))
        
        if is_callback:
            await target.answer(text, show_alert=True)
            return
        else:
            await message.answer(text, reply_markup=builder.as_markup())
            return

    # بناء الواجهة للألعاب
    text = "🎮 **الألعاب المتاحة**\n\nاختر اللعبة التي تود استعراضها:"
    builder = InlineKeyboardBuilder()

    # إضافة الألعاب (تنسيق عمودين)
    for g in games:
        builder.add(types.InlineKeyboardButton(
            text=g['name'], 
            callback_data=f"user_game:{g['id']}")
        )
    
    # تطبيق التنسيق 2 في كل صف
    builder.adjust(2)

    # إضافة أزرار التنقل (Pagination) إذا لزم الأمر
    if total_pages > 1:
        nav_buttons = []
        if current_page > 0:
            nav_buttons.append(types.InlineKeyboardButton(text="◀️", callback_data=f"user_games_page:{current_page-1}"))
        else:
            nav_buttons.append(types.InlineKeyboardButton(text=" ", callback_data="ignore"))
            
        nav_buttons.append(types.InlineKeyboardButton(text=f"{current_page+1}/{total_pages}", callback_data="ignore"))
        
        if current_page < total_pages - 1:
            nav_buttons.append(types.InlineKeyboardButton(text="▶️", callback_data=f"user_games_page:{current_page+1}"))
        else:
            nav_buttons.append(types.InlineKeyboardButton(text=" ", callback_data="ignore"))
            
        builder.row(*nav_buttons)

    # زر الرجوع الدائم
    builder.row(types.InlineKeyboardButton(text="🔙 القائمة الرئيسية", callback_data="user_back"))

    # منطق الإرسال / التعديل
    reply_markup = builder.as_markup()
    
    if is_callback:
        # إذا كانت الرسالة الحالية تحتوي على صورة (مثل واجهة اللعبة السابقة)
        if message.photo:
            await message.delete()
            await message.answer(text, reply_markup=reply_markup, parse_mode="Markdown")
        else:
            try:
                await message.edit_text(text, reply_markup=reply_markup, parse_mode="Markdown")
            except Exception:
                # لتجنب خطأ edit_text إذا لم يتغير المحتوى
                pass
    else:
        await message.answer(text, reply_markup=reply_markup, parse_mode="Markdown")
    
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
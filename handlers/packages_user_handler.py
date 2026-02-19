from aiogram import Router, types, F
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest
from game_utils import get_packages, count_packages, get_game
import html
import logging

router = Router()

def escape_html(text):
    return html.escape(str(text) if text is not None else "")

async def show_packages_page(target, game_id: str, page: int = 0):
    """
    عرض حزم اللعبة بتنسيق شبكة (2 column grid) مع شرح العروض في الكابشن.
    يتم عرض شرح الحزم التابعة للصفحة الحالية فقط.
    """
    if isinstance(target, types.CallbackQuery):
        message = target.message
        is_callback = True
    else:
        message = target
        is_callback = False

    game = await get_game(game_id)
    if not game:
        await message.answer("⚠️ اللعبة غير موجودة.")
        return

    # جلب إحصائيات الحزم
    total_count = await count_packages(game_id)
    
    # إعدادات التوزيع (8 حزم لكل صفحة كحد أقصى، أو 12 إذا كان العدد الكلي بسيطاً)
    MAX_SINGLE_PAGE = 12
    DEFAULT_PAGE_SIZE = 8

    if total_count <= MAX_SINGLE_PAGE:
        packages = await get_packages(game_id, 0, limit=total_count)
        total_pages = 1
        current_page = 0
    else:
        packages = await get_packages(game_id, page, limit=DEFAULT_PAGE_SIZE)
        total_pages = (total_count + DEFAULT_PAGE_SIZE - 1) // DEFAULT_PAGE_SIZE
        current_page = page
    # --- بناء نص الرسالة (Caption) بتنسيق متوافق مع اللغة العربية ---
    caption_lines = [
        f"🎮 <b>{escape_html(game['name'])}</b>",
        f"<i>{escape_html(game.get('description', 'استعرض أفضل العروض المتاحة'))}</i>",
        "────────────────"
    ]
    
    caption_lines.append("📦 <b>قائمة العروض المتاحة:</b>\n")
    
    if not packages:
        caption_lines.append("<i>لا توجد حزم متاحة حالياً.</i>")
    else:
        # عرض الحزم للصفحة الحالية فقط
        for i, p in enumerate(packages, 1):
            # استخدام ترتيب (الرقم - اسم الحزمة - السعر) بشكل يمنع تداخل الأقواس
            item_text = f"{i} - <b>{escape_html(p['name'])}</b>"
            price_text = f"💳 السعر: <code>{p['price']}</code> ل.س"
            
            caption_lines.append(item_text)
            caption_lines.append(price_text)
            caption_lines.append("") # سطر فارغ للفصل بين العروض

    caption_lines.append("👇 <b>اختر الحزمة المطلوبة من الأسفل:</b>")
    
    caption = "\n".join(caption_lines)

    # --- بناء الأزرار (Keyboard) ---
    builder = InlineKeyboardBuilder()
    
    # إضافة الأزرار (توزيع 2 في كل صف كما طلبت 2-1، 4-3...)
    for p in packages:
        builder.add(types.InlineKeyboardButton(
            text=f"{p['name']} | {p['price']}", 
            callback_data=f"buy_package:{p['id']}"
        ))

    builder.adjust(2) # التنسيق الشبكي

    # أزرار التنقل (Pagination)
    if total_pages > 1:
        nav_buttons = []
        # زر السابق
        if current_page > 0:
            nav_buttons.append(types.InlineKeyboardButton(text="◀️", callback_data=f"user_packages_page:{game_id}:{current_page-1}"))
        else:
            nav_buttons.append(types.InlineKeyboardButton(text=" ", callback_data="ignore"))

        # مؤشر الصفحة
        nav_buttons.append(types.InlineKeyboardButton(text=f"{current_page+1}/{total_pages}", callback_data="ignore"))

        # زر التالي
        if current_page < total_pages - 1:
            nav_buttons.append(types.InlineKeyboardButton(text="▶️", callback_data=f"user_packages_page:{game_id}:{current_page+1}"))
        else:
            nav_buttons.append(types.InlineKeyboardButton(text=" ", callback_data="ignore"))
        
        builder.row(*nav_buttons)

    # أزرار التحكم
    builder.row(types.InlineKeyboardButton(text="🔙 العودة لقائمة الألعاب", callback_data="view_games"))

    reply_markup = builder.as_markup()
    image_id = game.get('image_file_id')

    # --- منطق الإرسال الذكي ---
    try:
        if image_id:
            if is_callback:
                # حذف الرسالة السابقة لإرسال الصورة الجديدة (لأن تليجرام لا يحول النص لصورة بالـ edit)
                await message.delete()
            
            await message.answer_photo(
                photo=image_id,
                caption=caption,
                reply_markup=reply_markup,
                parse_mode="HTML"
            )
        else:
            # معالجة الرسائل النصية فقط
            if is_callback:
                if message.photo: 
                    await message.delete()
                    await message.answer(caption, reply_markup=reply_markup, parse_mode="HTML")
                else:
                    await message.edit_text(caption, reply_markup=reply_markup, parse_mode="HTML")
            else:
                await message.answer(caption, reply_markup=reply_markup, parse_mode="HTML")
                
    except Exception as e:
        logging.error(f"Error: {e}")
        await message.answer(caption, reply_markup=reply_markup, parse_mode="HTML")

@router.callback_query(F.data.startswith("user_packages_page:"))
async def user_packages_page(callback: types.CallbackQuery):
    _, game_id, page = callback.data.split(":")
    await show_packages_page(callback, game_id, int(page))
    await callback.answer()
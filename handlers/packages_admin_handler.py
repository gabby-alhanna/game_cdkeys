from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from .common_handlers import get_cancel_button
from game_utils import get_packages, count_packages, get_game
from database import db
from static_lists import SPECIAL_BUTTONS
import os
import html
import logging

router = Router()
ADMIN_ID = int(os.getenv("ADMIN_CHAT_ID"))

PAGE_SIZE = 3

def escape_html(text):
    return html.escape(str(text) if text is not None else "")

class PackageCreate(StatesGroup):
    waiting_game_id = State()
    waiting_name = State()
    waiting_price = State()

class PackageEdit(StatesGroup):
    waiting_package_id = State()
    waiting_name = State()
    waiting_price = State()

async def show_game_details_with_packages(target, game_id: str, page: int = 0):
    """عرض تفاصيل اللعبة + قائمة الحزم مع أزرار الإدارة بتنسيق متوافق مع RTL."""
    if isinstance(target, types.CallbackQuery):
        message = target.message
        is_callback = True
    else:
        message = target
        is_callback = False

    game = await get_game(game_id)
    if not game:
        await message.answer("⚠️ اللعبة غير موجودة في قاعدة البيانات.")
        return

    # استخدام نفس المنطق المرن (8-12) لضمان تناسق العرض
    total_count = await count_packages(game_id)
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

    # --- بناء الـ Caption بنفس أسلوب واجهة المستخدم (التصميم الموحد) ---
    caption_lines = [
        f"⚙️ <b>لوحة إدارة: {escape_html(game['name'])}</b>",
        f"<i>{escape_html(game.get('description', 'لا يوجد وصف متاح'))}</i>",
        "────────────────"
    ]
    
    caption_lines.append("📦 <b>الحزم المضافة حالياً:</b>\n")

    if not packages:
        caption_lines.append("<i>لا توجد حزم مضافة لهذه اللعبة.</i>")
    else:
        for i, p in enumerate(packages, 1):
            # تنسيق يمنع تداخل الأقواس (اسم الحزمة ثم السعر في سطر مستقل)
            item_text = f"{i} - <b>{escape_html(p['name'])}</b>"
            price_text = f"💰 السعر الحالي: <code>{p['price']}</code> ل.س"
            
            caption_lines.append(item_text)
            caption_lines.append(price_text)
            caption_lines.append("") # فواصل بصرية

    caption_lines.append("🛠 <b>خيارات التحكم:</b>")
    full_text = "\n".join(caption_lines)

    # --- بناء لوحة التحكم (Keyboard) ---
    builder = InlineKeyboardBuilder()
    
    # 1. أزرار التحكم باللعبة الأساسية
    builder.row(
        types.InlineKeyboardButton(text="✏️ تعديل اسم/وصف", callback_data=f"ge:{game_id}"),
        types.InlineKeyboardButton(text="❌ حذف اللعبة", callback_data=f"gd:{game_id}")
    )

    # 2. أزرار إدارة الحزم (تنسيق صفوف للإدارة لتسهيل الضغط)
    for p in packages:
        builder.row(
            types.InlineKeyboardButton(text=f"📦 {p['name']}", callback_data=f"pv:{p['id']}"),
            types.InlineKeyboardButton(text="✏️", callback_data=f"pe:{p['id']}"),
            types.InlineKeyboardButton(text="🗑", callback_data=f"pd:{p['id']}")
        )

    # 3. أزرار التنقل (Pagination)
    if total_pages > 1:
        nav_buttons = []
        if current_page > 0:
            nav_buttons.append(types.InlineKeyboardButton(text="◀️", callback_data=f"pp:{game_id}:{current_page-1}"))
        else:
            nav_buttons.append(types.InlineKeyboardButton(text=" ", callback_data="ignore"))

        nav_buttons.append(types.InlineKeyboardButton(text=f"{current_page+1}/{total_pages}", callback_data="ignore"))

        if current_page < total_pages - 1:
            nav_buttons.append(types.InlineKeyboardButton(text="▶️", callback_data=f"pp:{game_id}:{current_page+1}"))
        else:
            nav_buttons.append(types.InlineKeyboardButton(text=" ", callback_data="ignore"))
        
        builder.row(*nav_buttons)

    # 4. أزرار الإجراءات الإضافية
    builder.row(types.InlineKeyboardButton(text="➕ إضافة حزمة جديدة", callback_data=f"pa:{game_id}"))
    builder.row(types.InlineKeyboardButton(text="🔙 العودة لقائمة الألعاب", callback_data="admin_games_page:0"))

    reply_markup = builder.as_markup()

    # --- معالجة الإرسال (صورة أو نص) ---
    image_id = game.get('image_file_id')
    try:
        if image_id:
            if is_callback:
                await message.delete() # حذف القديم لضمان تحديث الصورة والكابشن
            
            await message.answer_photo(
                photo=image_id,
                caption=full_text,
                reply_markup=reply_markup,
                parse_mode="HTML"
            )
        else:
            if is_callback:
                if message.photo:
                    await message.delete()
                    await message.answer(full_text, reply_markup=reply_markup, parse_mode="HTML")
                else:
                    await message.edit_text(full_text, reply_markup=reply_markup, parse_mode="HTML")
            else:
                await message.answer(full_text, reply_markup=reply_markup, parse_mode="HTML")
                
    except Exception as e:
        logging.error(f"Error in Admin View: {e}")
        await message.answer(full_text, reply_markup=reply_markup, parse_mode="HTML")

@router.callback_query(F.data.startswith("pp:"))
async def packages_page(callback: types.CallbackQuery):
    _, game_id, page = callback.data.split(":")
    await show_game_details_with_packages(callback, game_id, int(page))
    await callback.answer()

# ------------------ إضافة حزمة ------------------
@router.callback_query(F.data.startswith("pa:"))
async def add_package_start(callback: types.CallbackQuery, state: FSMContext):
    game_id = callback.data.split(":")[1]
    await state.update_data(game_id=game_id)
    await state.set_state(PackageCreate.waiting_name)
    builder = get_cancel_button()
    await callback.message.answer("✏️ أدخل **اسم الحزمة**:", reply_markup=builder.as_markup())
    await callback.answer()
    
@router.message(PackageCreate.waiting_name, F.text.not_in(SPECIAL_BUTTONS))
async def add_package_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(PackageCreate.waiting_price)
    builder = get_cancel_button()
    await message.answer("💰 أدخل **السعر** (بالليرة السورية):", reply_markup=builder.as_markup())

@router.message(PackageCreate.waiting_price, F.text.not_in(SPECIAL_BUTTONS))
async def add_package_price(message: types.Message, state: FSMContext):
    try:
        price = float(message.text)
    except ValueError:
        await message.answer("❌ الرجاء إدخال رقم صحيح.")
        return
    data = await state.get_data()
    await db.execute(
        "INSERT INTO game_packages (game_id, name, price) VALUES ($1, $2, $3)",
        data['game_id'], data['name'], price
    )
    await message.answer("✅ تمت إضافة الحزمة!")
    await state.clear()
    # العودة إلى تفاصيل اللعبة
    await show_game_details_with_packages(message, data['game_id'], 0)

# ------------------ عرض الحزمة (اختياري) ------------------
@router.callback_query(F.data.startswith("pv:"))
async def view_package(callback: types.CallbackQuery):
    package_id = callback.data.split(":")[1]
    pkg = await db.fetchrow("SELECT * FROM game_packages WHERE id = $1", package_id)
    if not pkg:
        await callback.answer("الحزمة غير موجودة", show_alert=True)
        return
    text = f"📦 **{pkg['name']}**\nالسعر: {pkg['price']} ل.س"
    await callback.message.answer(text)
    await callback.answer()

# ------------------ تعديل حزمة ------------------
@router.callback_query(F.data.startswith("pe:"))
async def edit_package_start(callback: types.CallbackQuery, state: FSMContext):
    package_id = callback.data.split(":")[1]
    pkg = await db.fetchrow("SELECT * FROM game_packages WHERE id = $1", package_id)
    if not pkg:
        await callback.message.edit_text("الحزمة غير موجودة.")
        return
    await state.update_data(package_id=package_id, game_id=pkg['game_id'])
    await state.set_state(PackageEdit.waiting_name)
    builder = get_cancel_button()
    await callback.message.answer(
        f"✏️ الاسم الحالي: **{pkg['name']}**\nأدخل الاسم الجديد (أو أرسل '.' للإبقاء):",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

@router.message(PackageEdit.waiting_name, F.text.not_in(SPECIAL_BUTTONS))
async def edit_package_name(message: types.Message, state: FSMContext):
    text = message.text
    if text != '.':
        await state.update_data(new_name=text)
    await state.set_state(PackageEdit.waiting_price)
    builder = get_cancel_button()
    await message.answer("💰 أدخل السعر الجديد (أو أرسل '.' للإبقاء):", reply_markup=builder.as_markup())

@router.message(PackageEdit.waiting_price, F.text.not_in(SPECIAL_BUTTONS))
async def edit_package_price(message: types.Message, state: FSMContext):
    text = message.text
    data = await state.get_data()
    updates = []
    args = []
    if 'new_name' in data:
        updates.append(f"name = ${len(args)+1}")
        args.append(data['new_name'])
    if text != '.':
        try:
            price = float(text)
            updates.append(f"price = ${len(args)+1}")
            args.append(price)
        except ValueError:
            await message.answer("❌ سعر غير صالح. الرجاء إدخال رقم أو '.' للإبقاء.")
            return
    if updates:
        args.append(data['package_id'])
        await db.execute(f"UPDATE game_packages SET {', '.join(updates)} WHERE id = ${len(args)}", *args)
        await message.answer("✅ تم تحديث الحزمة!")
    else:
        await message.answer("لم يتم إجراء أي تغييرات.")
    await state.clear()
    # العودة إلى تفاصيل اللعبة
    await show_game_details_with_packages(message, data['game_id'], 0)

# ------------------ حذف حزمة ------------------
@router.callback_query(F.data.startswith("pd:"))
async def delete_package_confirm(callback: types.CallbackQuery):
    package_id = callback.data.split(":")[1]
    pkg = await db.fetchrow("SELECT * FROM game_packages WHERE id = $1", package_id)
    if not pkg:
        await callback.message.edit_text("الحزمة غير موجودة.")
        await callback.answer()
        return

    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="✅ نعم", callback_data=f"pd_yes:{package_id}"),
        types.InlineKeyboardButton(text="❌ لا", callback_data=f"admin_game_view:{pkg['game_id']}")
    )
    text = f"حذف الحزمة **{pkg['name']}**؟"
    # إزالة الصورة بحذف رسالة الصورة وإرسال رسالة نصية جديدة
    if callback.message.photo:
        await callback.message.delete()
        await callback.message.answer(text, reply_markup=builder.as_markup())
    else:
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()

@router.callback_query(F.data.startswith("pd_yes:"))
async def delete_package_execute(callback: types.CallbackQuery):
    package_id = callback.data.split(":")[1]
    pkg = await db.fetchrow("SELECT game_id FROM game_packages WHERE id = $1", package_id)
    if pkg:
        await db.execute("DELETE FROM game_packages WHERE id = $1", package_id)
        # حذف رسالة التأكيد (قد لا تزال تحتوي على صورة)
        await callback.message.delete()
        # العودة إلى تفاصيل اللعبة (إرسال رسالة جديدة)
        await show_game_details_with_packages(callback.message, pkg['game_id'], 0)
    else:
        if callback.message.photo:
            await callback.message.delete()
            await callback.message.answer("الحزمة محذوفة بالفعل.")
        else:
            await callback.message.edit_text("الحزمة محذوفة بالفعل.")
    await callback.answer()
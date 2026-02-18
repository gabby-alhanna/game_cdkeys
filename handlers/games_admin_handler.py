from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from .common_handlers import get_cancel_button
from game_utils import get_games, count_games, get_game, pagination_keyboard, GAME_PAGE_SIZE
from database import db
from static_lists import SPECIAL_BUTTONS
import os

router = Router()
ADMIN_ID = int(os.getenv("ADMIN_CHAT_ID"))

class GameCreate(StatesGroup):
    waiting_name = State()
    waiting_image = State()
    waiting_description = State()

class GameEdit(StatesGroup):
    waiting_game_id = State()
    waiting_name = State()
    waiting_image = State()
    waiting_description = State()

@router.callback_query(F.data == "admin_games")
async def admin_games_start(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await show_games_page(callback, page=0)

async def show_games_page(target, page: int):
    if isinstance(target, types.CallbackQuery):
        message = target.message
        is_callback = True
    else:
        message = target
        is_callback = False

    total_count = await count_games(only_active=False)
    
    # الإعدادات الخاصة بك
    MAX_SINGLE_PAGE = 12 
    DEFAULT_PAGE_SIZE = 8 # تم تعديلها لـ 8 لتناسب 4x2 كما طلبت

    if total_count <= MAX_SINGLE_PAGE:
        # نمرر limit=total_count لجلب كل الألعاب في صفحة واحدة
        games = await get_games(0, only_active=False, limit=total_count)
        total_pages = 1
        current_page = 0
    else:
        games = await get_games(page, only_active=False, limit=DEFAULT_PAGE_SIZE)
        total_pages = (total_count + DEFAULT_PAGE_SIZE - 1) // DEFAULT_PAGE_SIZE
        current_page = page

    text = "🎮 **إدارة الألعاب**"
    builder = InlineKeyboardBuilder()

    for g in games:
        builder.add(types.InlineKeyboardButton(
            text=g['name'], 
            callback_data=f"admin_game_view:{g['id']}")
        )
    
    builder.adjust(2) 

    if total_pages > 1:
        nav_buttons = []
        # زر السابق
        if current_page > 0:
            nav_buttons.append(types.InlineKeyboardButton(text="◀️", callback_data=f"admin_games_page:{current_page-1}"))
        else:
            nav_buttons.append(types.InlineKeyboardButton(text=" ", callback_data="ignore"))
        
        nav_buttons.append(types.InlineKeyboardButton(text=f"{current_page+1}/{total_pages}", callback_data="ignore"))
        
        # زر التالي
        if current_page < total_pages - 1:
            nav_buttons.append(types.InlineKeyboardButton(text="▶️", callback_data=f"admin_games_page:{current_page+1}"))
        else:
            nav_buttons.append(types.InlineKeyboardButton(text=" ", callback_data="ignore"))
        
        builder.row(*nav_buttons)

    builder.row(types.InlineKeyboardButton(text="➕ إضافة لعبة جديدة", callback_data="admin_game_add"))
    builder.row(types.InlineKeyboardButton(text="🔙 القائمة الرئيسية", callback_data="admin_back"))

    reply_markup = builder.as_markup()
    
    if is_callback:
        if message.photo:
            await message.delete()
            await message.answer(text, reply_markup=reply_markup)
        else:
            await message.edit_text(text, reply_markup=reply_markup)
    else:
        await message.answer(text, reply_markup=reply_markup)


@router.callback_query(F.data.startswith("admin_games_page:"))
async def games_page(callback: types.CallbackQuery):
    page = int(callback.data.split(":")[1])
    await show_games_page(callback, page)
    await callback.answer()

# تُستدعى عندما ينقر المشرف على اسم لعبة لعرض تفاصيلها
@router.callback_query(F.data.startswith("admin_game_view:"))
async def admin_game_view(callback: types.CallbackQuery):
    game_id = callback.data.split(":")[1]
    # استيراد هنا لتجنب الاستيراد الدائري
    from handlers.packages_admin_handler import show_game_details_with_packages
    await show_game_details_with_packages(callback, game_id, page=0)
    await callback.answer()

# ------------------ إضافة لعبة ------------------
@router.callback_query(F.data == "admin_game_add")
async def add_game_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(GameCreate.waiting_name)
    builder = get_cancel_button()
    await callback.message.edit_text("✏️ أدخل **اسم اللعبة**:", reply_markup=builder.as_markup())
    await callback.answer()

@router.message(GameCreate.waiting_name, F.text.not_in(SPECIAL_BUTTONS))
async def add_game_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(GameCreate.waiting_image)
    builder = get_cancel_button()
    await message.answer("🖼 أرسل **صورة** للعبة (أو أرسل '.' للتخطي):", reply_markup=builder.as_markup())

@router.message(GameCreate.waiting_image, F.photo, F.text.not_in(SPECIAL_BUTTONS))
async def add_game_image(message: types.Message, state: FSMContext):
    file_id = message.photo[-1].file_id
    await state.update_data(image_file_id=file_id)
    await state.set_state(GameCreate.waiting_description)
    builder = get_cancel_button()
    await message.answer("📝 أرسل **وصفاً** للعبة (أو أرسل '.' للتخطي):", reply_markup=builder.as_markup())

@router.message(GameCreate.waiting_image, F.text == ".", F.text.not_in(SPECIAL_BUTTONS))
async def add_game_skip_image(message: types.Message, state: FSMContext):
    await state.update_data(image_file_id=None)
    await state.set_state(GameCreate.waiting_description)
    builder = get_cancel_button()
    await message.answer("📝 أرسل **وصفاً** للعبة (أو أرسل '.' للتخطي):", reply_markup=builder.as_markup())

@router.message(GameCreate.waiting_description, F.text.not_in(SPECIAL_BUTTONS))
async def add_game_description(message: types.Message, state: FSMContext):
    desc = message.text if message.text != '.' else None
    data = await state.get_data()
    try:
        await db.execute(
            "INSERT INTO games (name, image_file_id, description) VALUES ($1, $2, $3)",
            data['name'], data.get('image_file_id'), desc
        )
        await message.answer(f"✅ تمت إضافة اللعبة **{data['name']}**!")
    except Exception as e:
        await message.answer(f"❌ خطأ: {e}")
    await state.clear()
    await show_games_page(message, 0)

# ------------------ تعديل لعبة (من صفحة التفاصيل) ------------------
@router.callback_query(F.data.startswith("ge:"))
async def edit_game_from_detail(callback: types.CallbackQuery, state: FSMContext):
    game_id = callback.data.split(":")[1]
    game = await get_game(game_id)
    if not game:
        await callback.message.edit_text("اللعبة غير موجودة.")
        return
    await state.update_data(game_id=game_id, from_detail=True)
    await state.set_state(GameEdit.waiting_name)
    builder = get_cancel_button()
    if callback.message.photo:
        await callback.message.edit_caption(
            caption=f"✏️ الاسم الحالي: **{game['name']}**\nأدخل الاسم الجديد (أو أرسل '.' للإبقاء):",
            reply_markup=builder.as_markup()
        )
    else:
        await callback.message.edit_text(
            f"✏️ الاسم الحالي: **{game['name']}**\nأدخل الاسم الجديد (أو أرسل '.' للإبقاء):",
            reply_markup=builder.as_markup()
        )
    await callback.answer()

@router.message(GameEdit.waiting_name, F.text.not_in(SPECIAL_BUTTONS))
async def edit_game_name(message: types.Message, state: FSMContext):
    text = message.text
    data = await state.get_data()
    if text == '.':
        # الإبقاء على الاسم القديم
        pass
    else:
        await state.update_data(new_name=text)
    await state.set_state(GameEdit.waiting_image)
    builder = get_cancel_button()
    await message.answer("🖼 أرسل الصورة الجديدة (أو أرسل '.' للإبقاء):", reply_markup=builder.as_markup())

@router.message(GameEdit.waiting_image, F.photo, F.text.not_in(SPECIAL_BUTTONS))
async def edit_game_image(message: types.Message, state: FSMContext):
    file_id = message.photo[-1].file_id
    await state.update_data(new_image=file_id)
    await state.set_state(GameEdit.waiting_description)
    builder = get_cancel_button()
    await message.answer("📝 أرسل الوصف الجديد (أو أرسل '.' للإبقاء):", reply_markup=builder.as_markup())

@router.message(GameEdit.waiting_image, F.text == ".", F.text.not_in(SPECIAL_BUTTONS))
async def edit_game_skip_image(message: types.Message, state: FSMContext):
    await state.update_data(new_image=None)
    await state.set_state(GameEdit.waiting_description)
    builder = get_cancel_button()
    await message.answer("📝 أرسل الوصف الجديد (أو أرسل '.' للإبقاء):", reply_markup=builder.as_markup())

@router.message(GameEdit.waiting_description, F.text.not_in(SPECIAL_BUTTONS))
async def edit_game_description(message: types.Message, state: FSMContext):
    desc = message.text if message.text != '.' else None
    data = await state.get_data()
    game_id = data['game_id']
    updates = []
    args = []
    if 'new_name' in data:
        updates.append(f"name = ${len(args)+1}")
        args.append(data['new_name'])
    if 'new_image' in data:
        updates.append(f"image_file_id = ${len(args)+1}")
        args.append(data['new_image'])
    if desc is not None:
        updates.append(f"description = ${len(args)+1}")
        args.append(desc)
    if updates:
        args.append(game_id)
        await db.execute(f"UPDATE games SET {', '.join(updates)} WHERE id = ${len(args)}", *args)
        await message.answer("✅ تم تحديث اللعبة!")
    else:
        await message.answer("لم يتم إجراء أي تغييرات.")
    await state.clear()
    # العودة إلى تفاصيل اللعبة إذا أتينا منها، وإلا إلى قائمة الألعاب
    if data.get('from_detail'):
        from handlers.packages_admin_handler import show_game_details_with_packages
        await show_game_details_with_packages(message, game_id, 0)
    else:
        await show_games_page(message, 0)

# ------------------ حذف لعبة (من صفحة التفاصيل) ------------------
@router.callback_query(F.data.startswith("gd:"))
async def delete_game_from_detail(callback: types.CallbackQuery):
    game_id = callback.data.split(":")[1]
    game = await get_game(game_id)
    if not game:
        await callback.message.edit_text("اللعبة غير موجودة.")
        return
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="✅ نعم", callback_data=f"gd_yes:{game_id}"),
        types.InlineKeyboardButton(text="❌ لا", callback_data=f"admin_game_view:{game_id}")
    )
    if callback.message.photo:
        await callback.message.edit_caption(
            caption=f"هل أنت متأكد من حذف **{game['name']}**؟ سيتم حذف جميع حزمها أيضاً.",
            reply_markup=builder.as_markup()
        )
    else:
        await callback.message.edit_text(
            f"هل أنت متأكد من حذف **{game['name']}**؟ سيتم حذف جميع حزمها أيضاً.",
            reply_markup=builder.as_markup()
        )
    await callback.answer()

@router.callback_query(F.data.startswith("gd_yes:"))
async def delete_game_execute(callback: types.CallbackQuery):
    game_id = callback.data.split(":")[1]
    game = await get_game(game_id)
    if game:
        await db.execute("DELETE FROM games WHERE id = $1", game_id)
        # حذف رسالة التأكيد
        await callback.message.delete()
        # العودة إلى قائمة الألعاب (إرسال رسالة جديدة)
        await show_games_page(callback.message, 0)
    else:
        if callback.message.photo:
            await callback.message.delete()
            await callback.message.answer("اللعبة محذوفة بالفعل.")
        else:
            await callback.message.edit_text("اللعبة محذوفة بالفعل.")
    await callback.answer()

# ------------------ رجوع ------------------
@router.callback_query(F.data == "admin_back")
async def admin_back(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    from .commands_handler import show_main_menu
    await show_main_menu(
        callback.message,
        user_id=callback.from_user.id,
        user_name=callback.from_user.full_name,
        set_reply_keyboard=False
    )

    await callback.message.delete()
    await callback.answer()
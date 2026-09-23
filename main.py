import asyncio
import logging
import sqlite3
import sys
from os import getenv

from aiogram import Bot, Dispatcher, F, html
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode, ChatMemberStatus
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message, 
    ReplyKeyboardMarkup, 
    KeyboardButton, 
    ReplyKeyboardRemove,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# --- SOZLAMALAR ---
TOKEN = getenv("BOT_TOKEN", "8561467455:AAEnHUoxH3UAPHHITJv1vW-At-CI2GjBa0Q")
ADMIN_ID = int(getenv("ADMIN_ID", "8923173548")) 

dp = Dispatcher()

# --- FSM (ADMIN PANEL UCHUN HOLATLAR) ---
class AddAnimeState(StatesGroup):
    waiting_for_code = State()
    waiting_for_title = State()
    waiting_for_video = State()

class ChannelState(StatesGroup):
    waiting_for_channel = State()

# --- MA'LUMOTLAR BAZASI (SQLITE) ---
def init_db():
    """Baza va jadvallarni yaratadi."""
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    
    # Animelar jadvali
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS animes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE,
            title TEXT,
            file_id TEXT
        )
    """)
    
    # Foydalanuvchilar jadvali
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            full_name TEXT
        )
    """)

    # Sozlamalar jadvali (Majburiy obuna uchun)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    
    conn.commit()
    conn.close()

def add_user(user_id: int, full_name: str):
    """Yangi foydalanuvchini bazaga saqlaydi."""
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id, full_name) VALUES (?, ?)", (user_id, full_name))
    conn.commit()
    conn.close()

def add_anime(code: str, title: str, file_id: str) -> bool:
    """Yangi animeni bazaga qo'shadi."""
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO animes (code, title, file_id) VALUES (?, ?, ?)", (code, title, file_id))
        conn.commit()
        res = True
    except sqlite3.IntegrityError:
        res = False
    conn.close()
    return res

def get_anime_by_code(code: str):
    """Kodu bo'yicha animeni qidiradi."""
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT title, file_id FROM animes WHERE code = ?", (code,))
    result = cursor.fetchone()
    conn.close()
    return result

def get_stats():
    """Foydalanuvchilar va animelar sonini qaytaradi."""
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    users_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM animes")
    anime_count = cursor.fetchone()[0]
    conn.close()
    return users_count, anime_count

def set_setting(key: str, value: str):
    """Sozlamani bazaga saqlaydi."""
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()

def get_setting(key: str):
    """Sozlamani bazadan oladi."""
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

# --- MAJBURIY OBUNANI TEKSHIRISH FUNKSIYASI ---
async def check_subscription(bot: Bot, user_id: int) -> bool:
    channel = get_setting("required_channel")
    if not channel:
        return True  # Agar kanal sozlanmagan bo'lsa, obuna majburiy emas
    try:
        member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
        if member.status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]:
            return True
        return False
    except Exception as e:
        logging.error(f"Obuna tekshirishda xatolik: {e}")
        return True  # Bot kanalda admin bo'lmasa, xatolik berib qolmasligi uchun

def get_sub_keyboard(channel: str):
    channel_link = channel.replace("@", "https://t.me/") if channel.startswith("@") else channel
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📢 Kanalga obuna bo'lish", url=channel_link)],
            [InlineKeyboardButton(text="✅ Obunani tekshirish", callback_data="check_sub")]
        ]
    )
    return keyboard

# --- TUGMALAR (KEYBOARDS) ---
main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🔍 Anime Izlash")],
        [KeyboardButton(text="👑 VIP Animelar"), KeyboardButton(text="💎 VIP Obuna")],
        [KeyboardButton(text="⚙️ Kabinet"), KeyboardButton(text="▶️ Shorts")],
        [KeyboardButton(text="📑 Qo'llanma"), KeyboardButton(text="📢 Reklama")]
    ],
    resize_keyboard=True
)

admin_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ Anime Qo'shish")],
        [KeyboardButton(text="⚙️ Majburiy obuna sozlamalari")],
        [KeyboardButton(text="📊 Statistika")],
        [KeyboardButton(text="🔙 Asosiy Menyu")]
    ],
    resize_keyboard=True
)

channel_setting_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ Kanal ulash / O'zgartirish")],
        [KeyboardButton(text="❌ Obunani o'chirish")],
        [KeyboardButton(text="⬅️ Admin Menyu")]
    ],
    resize_keyboard=True
)

# --- XABAR ISHLOGICHLARI (HANDLERS) ---

@dp.message(CommandStart())
async def command_start_handler(message: Message, bot: Bot) -> None:
    add_user(message.from_user.id, message.from_user.full_name)
    
    is_subbed = await check_subscription(bot, message.from_user.id)
    if not is_subbed:
        channel = get_setting("required_channel")
        await message.answer(
            "⚠️ Botdan foydalanish uchun quyidagi kanalimizga obuna bo'lishingiz shart:",
            reply_markup=get_sub_keyboard(channel)
        )
        return

    await message.answer(
        f"Assalomu alaykum, {html.bold(message.from_user.full_name)}!\n\n"
        f"AniOlam botiga xush kelibsiz! Anime kodini yuboring yoki menyudan foydalaning:",
        reply_markup=main_keyboard
    )

@dp.callback_query(F.data == "check_sub")
async def check_sub_callback(callback: CallbackQuery, bot: Bot):
    is_subbed = await check_subscription(bot, callback.from_user.id)
    if is_subbed:
        await callback.message.delete()
        await callback.message.answer(
            f"✅ Obuna tasdiqlandi! Hush kelibsiz, {html.bold(callback.from_user.full_name)}!",
            reply_markup=main_keyboard
        )
    else:
        await callback.answer("❌ Siz hali kanalga obuna bo'lmadingiz!", show_alert=True)

# --- ADMIN PANEL ---

@dp.message(Command("admin"))
async def admin_panel(message: Message):
    if message.from_user.id == ADMIN_ID:
        await message.answer("🛠 Admin panelga xush kelibsiz!", reply_markup=admin_keyboard)
    else:
        await message.answer("❌ Siz admin emassiz!")

@dp.message(F.text == "🔙 Asosiy Menyu")
async def back_to_main(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Asosiy menyuga qaytdingiz:", reply_markup=main_keyboard)

@dp.message(F.text == "⬅️ Admin Menyu")
async def back_to_admin(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Admin menyuga qaytdingiz:", reply_markup=admin_keyboard)

@dp.message(F.text == "📊 Statistika")
async def stats_handler(message: Message):
    if message.from_user.id == ADMIN_ID:
        users, animes = get_stats()
        channel = get_setting("required_channel") or "Ulanmagan"
        await message.answer(
            f"📊 **Bot Statistikasi:**\n\n"
            f"👤 Foydalanuvchilar: {users} ta\n"
            f"🎬 Animelar: {animes} ta\n"
            f"📢 Majburiy kanal: {channel}"
        )

# --- MAJBURIY OBUNA SOZLAMALARI ---

@dp.message(F.text == "⚙️ Majburiy obuna sozlamalari")
async def sub_settings_handler(message: Message):
    if message.from_user.id == ADMIN_ID:
        channel = get_setting("required_channel")
        status = f"Hozirgi kanal: {channel}" if channel else "Hozircha majburiy obuna kanali o'rnatilmagan."
        await message.answer(
            f"⚙️ **Majburiy obuna sozlamalari**\n\n{status}\n\n"
            f"⚠️ *Eslatma: Bot ko'rsatilgan kanalda ADMIN bo'lishi shart!*",
            reply_markup=channel_setting_keyboard,
            parse_mode=ParseMode.MARKDOWN
        )

@dp.message(F.text == "➕ Kanal ulash / O'zgartirish")
async def add_channel_start(message: Message, state: FSMContext):
    if message.from_user.id == ADMIN_ID:
        await state.set_state(ChannelState.waiting_for_channel)
        await message.answer(
            "📢 Kanal username-ini kiriting (masalan: `@kanalim_uz`):\n\n"
            "⚠️ Bot ushbu kanalda **administrator** huquqiga ega ekanligiga ishonch hosil qiling!",
            reply_markup=ReplyKeyboardRemove()
        )

@dp.message(ChannelState.waiting_for_channel)
async def process_channel_input(message: Message, state: FSMContext):
    channel = message.text.strip()
    if not channel.startswith("@"):
        await message.answer("❌ Kanal username-i `@` belgisi bilan boshlanishi kerak (masalan: `@my_channel`). Qayta kiriting:")
        return
    
    set_setting("required_channel", channel)
    await state.clear()
    await message.answer(f"✅ Majburiy obuna kanali `{channel}` ga muvaffaqiyatli o'zgartirildi!", reply_markup=channel_setting_keyboard, parse_mode=ParseMode.MARKDOWN)

@dp.message(F.text == "❌ Obunani o'chirish")
async def remove_channel_handler(message: Message):
    if message.from_user.id == ADMIN_ID:
        set_setting("required_channel", "")
        await message.answer("✅ Majburiy obuna kanali o'chirib tashlandi!", reply_markup=channel_setting_keyboard)

# --- ANIME QO'SHISH (FSM JARYONI) ---

@dp.message(F.text == "➕ Anime Qo'shish")
async def start_add_anime(message: Message, state: FSMContext):
    if message.from_user.id == ADMIN_ID:
        await state.set_state(AddAnimeState.waiting_for_code)
        await message.answer("Yangi anime uchun **KOD** kiriting (masalan: `101`):", reply_markup=ReplyKeyboardRemove())

@dp.message(AddAnimeState.waiting_for_code)
async def process_code(message: Message, state: FSMContext):
    await state.update_data(code=message.text.strip())
    await state.set_state(AddAnimeState.waiting_for_title)
    await message.answer("Anime **NOMINI** kiriting:")

@dp.message(AddAnimeState.waiting_for_title)
async def process_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text.strip())
    await state.set_state(AddAnimeState.waiting_for_video)
    await message.answer("Anime **VIDEO FAYLINI** yuboring:")

@dp.message(AddAnimeState.waiting_for_video, F.video)
async def process_video(message: Message, state: FSMContext):
    data = await state.get_data()
    file_id = message.video.file_id
    
    success = add_anime(data['code'], data['title'], file_id)
    if success:
        await message.answer(f"✅ Anime muvaffaqiyatli saqlandi!\n\n🔑 Kod: {data['code']}\n🎬 Nomi: {data['title']}", reply_markup=admin_keyboard)
    else:
        await message.answer("❌ Xatolik: Bu kod bilan anime allaqachon mavjud!", reply_markup=admin_keyboard)
    
    await state.clear()

# --- MENYU TUGMALARI ---

@dp.message(F.text == "🔍 Anime Izlash")
async def anime_search_handler(message: Message, bot: Bot) -> None:
    if not await check_subscription(bot, message.from_user.id):
        channel = get_setting("required_channel")
        await message.answer("⚠️ Botdan foydalanish uchun kanalga obuna bo'ling:", reply_markup=get_sub_keyboard(channel))
        return
    await message.answer("🔎 Anime kodini kiriting:")

@dp.message(F.text == "👑 VIP Animelar")
async def vip_anime_handler(message: Message) -> None:
    await message.answer("✨ VIP Animelar bo'limi tez orada ishga tushadi.")

@dp.message(F.text == "💎 VIP Obuna")
async def vip_sub_handler(message: Message) -> None:
    await message.answer("💳 VIP obuna xarid qilish uchun adminga murojaat qiling.")

@dp.message(F.text == "⚙️ Kabinet")
async def cabinet_handler(message: Message) -> None:
    await message.answer(f"👤 **Kabinet:**\n\nID: `{message.from_user.id}`\nIsm: {message.from_user.full_name}")

@dp.message(F.text == "▶️ Shorts")
async def shorts_handler(message: Message) -> None:
    await message.answer("🎬 Qisqa videolar bo'limi.")

@dp.message(F.text == "📑 Qo'llanma")
async def guide_handler(message: Message) -> None:
    await message.answer("📖 Botdan foydalanish uchun anime kodini yuborishingiz kifoya.")

@dp.message(F.text == "📢 Reklama")
async def ad_handler(message: Message) -> None:
    await message.answer("📢 Reklama berish uchun admin bilan bog'laning.")

# --- KOD BO'YICHA ANIME QIDIRUV ---

@dp.message()
async def search_anime_handler(message: Message, bot: Bot) -> None:
    if not await check_subscription(bot, message.from_user.id):
        channel = get_setting("required_channel")
        await message.answer("⚠️ Botdan foydalanish uchun kanalga obuna bo'ling:", reply_markup=get_sub_keyboard(channel))
        return

    code = message.text.strip()
    anime = get_anime_by_code(code)
    
    if anime:
        title, file_id = anime
        if file_id:
            await message.answer_video(video=file_id, caption=f"🎬 <b>{title}</b>")
        else:
            await message.answer(f"🎬 <b>{title}</b>")
    else:
        await message.answer("❌ **Afsuski, hech narsa topilmadi.**")

# --- BOTNI ISHGA TUSHRISH ---

async def main() -> None:
    init_db()  # Bazani ishga tushirish
    bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    
    # Eskirgan va mojaroli so'rovlarni tozalash
    await bot.delete_webhook(drop_pending_updates=True)
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())
    
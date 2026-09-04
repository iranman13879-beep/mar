from aiogram import Router, F, Bot
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery

import database as db
import keyboards as kb
from config import ADMIN_IDS

router = Router(name="admin")
# فقط ادمین‌ها به این روتر دسترسی دارن
router.message.filter(F.from_user.id.in_(ADMIN_IDS))
router.callback_query.filter(F.from_user.id.in_(ADMIN_IDS))


SETTING_LABELS = {
    "start_coins": "سکه شروع کاربر جدید",
    "daily_bonus": "جایزه روزانه",
    "solo_entry_fee": "هزینه ورود بازی تکی",
    "solo_win_reward": "جایزه برد بازی تکی",
    "pvp_default_stake": "شرط پیش‌فرض بازی دو نفره",
}


class AdminStates(StatesGroup):
    waiting_coins_target = State()
    waiting_coins_amount = State()
    waiting_ban_target = State()
    waiting_broadcast = State()
    waiting_setting_value = State()


async def _resolve_user(text: str) -> dict | None:
    text = text.strip()
    if text.startswith("@"):
        return await db.find_user_by_username(text)
    if text.isdigit():
        return await db.get_user(int(text))
    return None


@router.message(Command("admin"))
async def cmd_admin(message: Message):
    await message.answer("🛠 <b>پنل مدیریت</b>", reply_markup=kb.admin_menu())


@router.callback_query(F.data == "adm:open")
async def cb_admin_open(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("🛠 <b>پنل مدیریت</b>", reply_markup=kb.admin_menu())
    await callback.answer()


@router.callback_query(F.data == "adm:cancel")
async def cb_admin_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("🛠 <b>پنل مدیریت</b>", reply_markup=kb.admin_menu())
    await callback.answer("لغو شد.")


# ---------------- stats ----------------

@router.callback_query(F.data == "adm:stats")
async def cb_admin_stats(callback: CallbackQuery):
    s = await db.stats_summary()
    text = (
        "📊 <b>آمار کلی ربات</b>\n\n"
        f"👥 تعداد کاربران: <b>{s['total_users']}</b>\n"
        f"🚫 کاربران مسدود: <b>{s['banned_count']}</b>\n"
        f"💰 مجموع سکه‌های در گردش: <b>{s['total_coins']}</b>\n"
        f"🎮 مجموع بازی‌های ثبت‌شده: <b>{s['total_games']}</b>\n"
        f"🎲 مجموع دورهای بازی‌شده: <b>{s['total_games_played']}</b>"
    )
    await callback.message.edit_text(text, reply_markup=kb.admin_menu())
    await callback.answer()


# ---------------- coin management ----------------

@router.callback_query(F.data == "adm:coins")
async def cb_admin_coins(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_coins_target)
    await callback.message.edit_text(
        "👤 آیدی عددی یا یوزرنیم (@username) کاربر مورد نظر رو بفرست:",
        reply_markup=kb.cancel_fsm_keyboard(),
    )
    await callback.answer()


@router.message(StateFilter(AdminStates.waiting_coins_target))
async def admin_coins_target(message: Message, state: FSMContext):
    user = await _resolve_user(message.text)
    if not user:
        await message.answer("❗️ کاربر پیدا نشد. دوباره امتحان کن (آیدی عددی یا @username):")
        return
    await state.update_data(target_id=user["user_id"])
    name = ("@" + user["username"]) if user["username"] else user["first_name"]
    await state.set_state(AdminStates.waiting_coins_amount)
    await message.answer(
        f"👤 کاربر: {name}\n💰 موجودی فعلی: {user['coins']}\n\n"
        "مقدار سکه رو بفرست (برای کم کردن، عدد منفی بفرست، مثلا -50):",
        reply_markup=kb.cancel_fsm_keyboard(),
    )


@router.message(StateFilter(AdminStates.waiting_coins_amount))
async def admin_coins_amount(message: Message, state: FSMContext):
    text = message.text.strip()
    try:
        amount = int(text)
    except ValueError:
        await message.answer("❗️ یه عدد صحیح بفرست (مثلا 100 یا -50):")
        return
    data = await state.get_data()
    target_id = data["target_id"]
    await db.add_coins(target_id, amount)
    user = await db.get_user(target_id)
    await state.clear()
    await message.answer(
        f"✅ انجام شد. موجودی جدید کاربر: <b>{user['coins']}</b> سکه",
        reply_markup=kb.admin_menu(),
    )


# ---------------- ban / unban ----------------

@router.callback_query(F.data == "adm:ban")
async def cb_admin_ban(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_ban_target)
    await callback.message.edit_text(
        "👤 آیدی عددی یا یوزرنیم کاربری که می‌خوای وضعیت مسدودیتش رو تغییر بدی رو بفرست:",
        reply_markup=kb.cancel_fsm_keyboard(),
    )
    await callback.answer()


@router.message(StateFilter(AdminStates.waiting_ban_target))
async def admin_ban_target(message: Message, state: FSMContext):
    user = await _resolve_user(message.text)
    if not user:
        await message.answer("❗️ کاربر پیدا نشد. دوباره امتحان کن:")
        return
    new_status = not bool(user["is_banned"])
    await db.set_ban(user["user_id"], new_status)
    await state.clear()
    name = ("@" + user["username"]) if user["username"] else user["first_name"]
    status_text = "مسدود شد 🚫" if new_status else "رفع مسدودیت شد ✅"
    await message.answer(f"کاربر {name} {status_text}.", reply_markup=kb.admin_menu())


# ---------------- broadcast ----------------

@router.callback_query(F.data == "adm:broadcast")
async def cb_admin_broadcast(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_broadcast)
    await callback.message.edit_text(
        "📢 پیامی که می‌خوای برای همه کاربران ارسال بشه رو بفرست:",
        reply_markup=kb.cancel_fsm_keyboard(),
    )
    await callback.answer()


@router.message(StateFilter(AdminStates.waiting_broadcast))
async def admin_broadcast_text(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    user_ids = await db.all_user_ids()
    sent, failed = 0, 0
    status_msg = await message.answer(f"⏳ در حال ارسال به {len(user_ids)} کاربر...")
    for uid in user_ids:
        try:
            await bot.copy_message(uid, message.chat.id, message.message_id)
            sent += 1
        except Exception:
            failed += 1
    await status_msg.edit_text(
        f"✅ ارسال شد به {sent} کاربر.\n❌ ناموفق: {failed}",
    )
    await message.answer("🛠 پنل مدیریت", reply_markup=kb.admin_menu())


# ---------------- settings ----------------

@router.callback_query(F.data == "adm:settings")
async def cb_admin_settings(callback: CallbackQuery):
    settings = await db.get_all_settings()
    lines = ["⚙️ <b>تنظیمات اقتصاد بازی</b>\n"]
    for key, label in SETTING_LABELS.items():
        lines.append(f"• {label}: <b>{settings.get(key, 0)}</b>")
    lines.append("\nبرای تغییر، یکی از دکمه‌های زیر رو بزن:")
    await callback.message.edit_text("\n".join(lines), reply_markup=kb.admin_settings_keyboard())
    await callback.answer()


@router.callback_query(F.data.startswith("adm:set:"))
async def cb_admin_set_setting(callback: CallbackQuery, state: FSMContext):
    key = callback.data.split(":")[2]
    if key not in SETTING_LABELS:
        await callback.answer()
        return
    current = await db.get_setting(key)
    await state.set_state(AdminStates.waiting_setting_value)
    await state.update_data(setting_key=key)
    await callback.message.edit_text(
        f"⚙️ {SETTING_LABELS[key]}\nمقدار فعلی: <b>{current}</b>\n\n"
        "عدد جدید رو بفرست:",
        reply_markup=kb.cancel_fsm_keyboard(),
    )
    await callback.answer()


@router.message(StateFilter(AdminStates.waiting_setting_value))
async def admin_setting_value(message: Message, state: FSMContext):
    text = message.text.strip()
    if not text.isdigit() or int(text) < 0:
        await message.answer("❗️ یه عدد صحیح و غیرمنفی بفرست:")
        return
    data = await state.get_data()
    key = data["setting_key"]
    await db.set_setting(key, int(text))
    await state.clear()
    await message.answer(
        f"✅ {SETTING_LABELS[key]} به {text} تغییر کرد.", reply_markup=kb.admin_menu()
    )

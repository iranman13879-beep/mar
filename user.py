import time

from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery

import database as db
import keyboards as kb
from config import ADMIN_IDS

router = Router(name="user")

DAY_SECONDS = 24 * 60 * 60

WELCOME = (
    "🐍🪜 به ربات <b>مار و پله</b> خوش اومدی!\n\n"
    "می‌تونی به‌صورت تکی بازی کنی و سکه جمع کنی، یا یک لابی چندنفره بسازی. "
    "دوستانت از داخل گروه وارد لابی می‌شن و خود بازی داخل ربات انجام می‌شه.\n\n"
    "از منوی زیر شروع کن 👇"
)

HELP_TEXT = (
    "📖 <b>راهنمای بازی</b>\n\n"
    "🎲 هر نوبت یه تاس (۱ تا ۶) می‌ندازی و مهره‌ت جلو می‌ره.\n"
    "🪜 اگه به پایین نردبان برسی، می‌پری بالا.\n"
    "🐍 اگه به سر مار برسی، میفتی پایین!\n"
    "🏁 هرکی اول به خونه ۱۰۰ برسه برنده‌ست.\n\n"
    "🎮 <b>بازی تکی:</b> با هزینه ورود کوچیک بازی می‌کنی و اگه به خونه ۱۰۰ برسی جایزه می‌گیری.\n"
    "⚔️ <b>بازی چندنفره:</b> یک لابی ۲ یا ۴ نفره بساز، لینک «پیوستن به لابی» را "
    "در گروه بفرست و بازیکنان وارد شوند. بازی بعد از تکمیل لابی داخل ربات ادامه پیدا می‌کند.\n"
    "🎁 <b>جایزه روزانه:</b> هر ۲۴ ساعت یک‌بار می‌تونی جایزه رایگان بگیری."
)


def _display_name(user) -> str:
    if user.get("username"):
        return "@" + user["username"]
    return user.get("first_name") or "بازیکن"


@router.message(CommandStart())
async def cmd_start(message: Message):
    user = await db.get_or_create_user(
        message.from_user.id, message.from_user.username, message.from_user.first_name
    )
    is_admin = message.from_user.id in ADMIN_IDS
    await message.answer(WELCOME, reply_markup=kb.main_menu(is_admin))


@router.message(Command("menu"))
async def cmd_menu(message: Message):
    is_admin = message.from_user.id in ADMIN_IDS
    await message.answer("منوی اصلی 👇", reply_markup=kb.main_menu(is_admin))


@router.callback_query(F.data == "menu:main")
async def cb_main_menu(callback: CallbackQuery):
    is_admin = callback.from_user.id in ADMIN_IDS
    await callback.message.edit_text("منوی اصلی 👇", reply_markup=kb.main_menu(is_admin))
    await callback.answer()


@router.callback_query(F.data == "menu:help")
async def cb_help(callback: CallbackQuery):
    await callback.message.edit_text(HELP_TEXT, reply_markup=kb.back_to_menu())
    await callback.answer()


@router.callback_query(F.data == "menu:profile")
async def cb_profile(callback: CallbackQuery):
    user = await db.get_or_create_user(
        callback.from_user.id, callback.from_user.username, callback.from_user.first_name
    )
    text = (
        f"👤 <b>پروفایل شما</b>\n\n"
        f"💰 سکه: <b>{user['coins']}</b>\n"
        f"🏆 برد‌ها: <b>{user['wins']}</b>\n"
        f"🎮 تعداد بازی‌ها: <b>{user['games_played']}</b>"
    )
    await callback.message.edit_text(text, reply_markup=kb.back_to_menu())
    await callback.answer()


@router.callback_query(F.data == "menu:daily")
async def cb_daily(callback: CallbackQuery):
    user = await db.get_or_create_user(
        callback.from_user.id, callback.from_user.username, callback.from_user.first_name
    )
    now = time.time()
    remaining = DAY_SECONDS - (now - user["last_daily"])
    if remaining > 0:
        hours = int(remaining // 3600)
        minutes = int((remaining % 3600) // 60)
        await callback.answer(
            f"⏳ جایزه بعدی تا {hours} ساعت و {minutes} دقیقه‌ی دیگه.", show_alert=True
        )
        return
    bonus = await db.get_setting("daily_bonus")
    await db.add_coins(callback.from_user.id, bonus)
    await db.set_last_daily(callback.from_user.id, now)
    await callback.answer(f"🎁 تبریک! {bonus} سکه جایزه گرفتی.", show_alert=True)
    user = await db.get_user(callback.from_user.id)
    text = (
        f"🎁 جایزه‌ت رو گرفتی!\n\n💰 موجودی فعلی: <b>{user['coins']}</b> سکه\n\n"
        "فردا دوباره سر بزن 😉"
    )
    await callback.message.edit_text(text, reply_markup=kb.back_to_menu())


@router.callback_query(F.data == "menu:leaderboard")
async def cb_leaderboard(callback: CallbackQuery):
    top = await db.top_players(10)
    if not top:
        text = "هنوز هیچ بازیکنی ثبت نشده."
    else:
        lines = ["🏆 <b>برترین بازیکنان</b>\n"]
        medals = ["🥇", "🥈", "🥉"]
        for i, p in enumerate(top):
            medal = medals[i] if i < 3 else f"{i + 1}."
            name = ("@" + p["username"]) if p["username"] else (p["first_name"] or "بازیکن")
            lines.append(f"{medal} {name} — 💰 {p['coins']} | 🏆 {p['wins']}")
        text = "\n".join(lines)
    await callback.message.edit_text(text, reply_markup=kb.back_to_menu())
    await callback.answer()


@router.callback_query(F.data == "noop")
async def cb_noop(callback: CallbackQuery):
    await callback.answer()

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_menu(is_admin: bool = False) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🎮 بازی تکی", callback_data="menu:solo")
    b.button(text="⚔️ چالش با دوست", callback_data="menu:pvp")
    b.button(text="💰 موجودی من", callback_data="menu:profile")
    b.button(text="🏆 برترین‌ها", callback_data="menu:leaderboard")
    b.button(text="🎁 جایزه روزانه", callback_data="menu:daily")
    b.button(text="ℹ️ راهنما", callback_data="menu:help")
    if is_admin:
        b.button(text="🛠 پنل مدیریت", callback_data="adm:open")
    b.adjust(2, 2, 2, 1)
    return b.as_markup()


def back_to_menu() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🔙 بازگشت به منو", callback_data="menu:main")
    return b.as_markup()


def solo_roll_keyboard(game_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🎲 تاس بنداز", callback_data=f"solo:roll:{game_id}")
    b.button(text="❌ لغو بازی", callback_data=f"solo:cancel:{game_id}")
    b.adjust(1)
    return b.as_markup()


def solo_finished_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🔁 بازی دوباره", callback_data="menu:solo")
    b.button(text="🔙 بازگشت به منو", callback_data="menu:main")
    b.adjust(1)
    return b.as_markup()


def pvp_invite_keyboard(game_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✅ قبول می‌کنم", callback_data=f"pvp:accept:{game_id}")
    b.button(text="❌ رد می‌کنم", callback_data=f"pvp:decline:{game_id}")
    b.adjust(2)
    return b.as_markup()


def pvp_roll_keyboard(game_id: int, can_roll: bool = True) -> InlineKeyboardMarkup:
    # این پیام بین هر دو بازیکن مشترکه، پس متن دکمه خنثی‌ه؛ نوبت واقعی توی
    # کپشن بالای عکس مشخصه و سمت سرور هم موقع کلیک چک می‌شه.
    b = InlineKeyboardBuilder()
    b.button(text="🎲 تاس بنداز", callback_data=f"pvp:roll:{game_id}")
    b.adjust(1)
    return b.as_markup()


def pvp_finished_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="⚔️ چالش جدید", callback_data="menu:pvp")
    b.button(text="🔙 بازگشت به منو", callback_data="menu:main")
    b.adjust(1)
    return b.as_markup()


def admin_menu() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="📊 آمار کلی", callback_data="adm:stats")
    b.button(text="💰 مدیریت سکه کاربر", callback_data="adm:coins")
    b.button(text="🚫 مسدود/رفع مسدودیت", callback_data="adm:ban")
    b.button(text="📢 پیام همگانی", callback_data="adm:broadcast")
    b.button(text="⚙️ تنظیمات اقتصاد بازی", callback_data="adm:settings")
    b.button(text="🔙 بازگشت", callback_data="menu:main")
    b.adjust(2, 2, 1, 1)
    return b.as_markup()


def admin_settings_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="سکه شروع", callback_data="adm:set:start_coins")
    b.button(text="جایزه روزانه", callback_data="adm:set:daily_bonus")
    b.button(text="هزینه بازی تکی", callback_data="adm:set:solo_entry_fee")
    b.button(text="جایزه بازی تکی", callback_data="adm:set:solo_win_reward")
    b.button(text="شرط پیش‌فرض دو نفره", callback_data="adm:set:pvp_default_stake")
    b.button(text="🔙 بازگشت", callback_data="adm:open")
    b.adjust(1)
    return b.as_markup()


def cancel_fsm_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="❌ انصراف", callback_data="adm:cancel")
    return b.as_markup()

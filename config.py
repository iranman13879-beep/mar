import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")

_admin_ids_raw = os.getenv("ADMIN_IDS", "7287316708")
ADMIN_IDS = {int(x.strip()) for x in _admin_ids_raw.split(",") if x.strip()}

DB_PATH = os.getenv("DB_PATH", "snake_bot.db")

# --- تنظیمات پیش‌فرض اقتصاد بازی (این‌ها از پنل ادمین هم قابل تغییرند) ---
DEFAULT_SETTINGS = {
    "start_coins": "200",      # سکه اولیه هر کاربر جدید
    "daily_bonus": "50",       # جایزه روزانه
    "solo_entry_fee": "10",    # هزینه ورود بازی تکی
    "solo_win_reward": "80",   # جایزه رسیدن به خانه ۱۰۰ در بازی تکی
    "pvp_default_stake": "30", # شرط پیش‌فرض بازی دو نفره
}

BOARD_SIZE = 10  # 10x10 = 100 خانه
CELL_PX = 76
MARGIN_PX = 30
HEADER_PX = 90

# خانه‌های مار (خانه بزرگ -> خانه کوچک)
SNAKES = {
    16: 6,
    46: 25,
    49: 11,
    62: 19,
    64: 60,
    74: 53,
    89: 68,
    92: 88,
    95: 75,
    99: 80,
}

# خانه‌های نردبان (خانه کوچک -> خانه بزرگ)
LADDERS = {
    2: 38,
    7: 14,
    8: 31,
    15: 26,
    21: 42,
    28: 84,
    36: 44,
    51: 67,
    71: 91,
    78: 98,
}

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN
from database import init_db
from handlers import user, game, admin

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN تنظیم نشده! متغیر محیطی BOT_TOKEN رو با توکن ربات‌فادر پر کن."
        )

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())

    # ترتیب مهمه: ادمین اول (فیلتر داخلی خودش داره)، بعد بازی، بعد کاربر عادی
    dp.include_router(admin.router)
    dp.include_router(game.router)
    dp.include_router(user.router)

    await init_db()
    logger.info("دیتابیس آماده شد. ربات در حال اجراست...")

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

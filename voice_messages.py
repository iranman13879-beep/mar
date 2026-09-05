"""
تولید پیام صوتی خودکار (متن به گفتار) برای لحظات برد/باخت بازی.
از gTTS استفاده می‌شود (رایگان، بدون نیاز به API Key) — فقط نیاز به اینترنت دارد.
"""

import io
import random
import logging

logger = logging.getLogger(__name__)

# اگر gTTS نصب نباشد یا خطا بدهد، کل ربات نباید کرش کند؛
# صدا صرفاً یک ویژگی جانبی است.
try:
    from gtts import gTTS
    GTTS_AVAILABLE = True
except ImportError:
    GTTS_AVAILABLE = False
    logger.warning("gTTS نصب نیست؛ پیام صوتی غیرفعال می‌ماند.")


WIN_PHRASES = [
    "برد بزرگ! {name} امروز مار و پله رو به زانو در آورد! تبریک قهرمان!",
    "وای وای وای! {name} به خونه صد رسید و صاحب سکه‌ها شد! دمت گرم!",
    "{name} امشب حسابی شانس آورد و برد خودشو گرفت! هوراااا!",
    "توجه توجه! یک برندهٔ جدید داریم، اسمش {name} هست! تبریک میگم رفیق!",
    "{name} مثل بلدرچین از رو نردبون‌ها پرید و برنده شد! دمت گرم داداش!",
    "بازی تموم شد، {name} با افتخار جام رو بالا برد! آفرین!",
]

LOSE_PHRASES = [
    "نگران نباش {name}، این بار حریف شانس آورد. دفعه بعد نوبت توئه!",
    "{name} امروز مار خیلی گشنه بود! دفعه بعد بهتر می‌شی، ادامه بده!",
    "باختن هم بخشی از بازیه {name}، سرتو بالا بگیر و دوباره امتحان کن!",
    "{name} این دور نشد، ولی رفیق، شانس بعدی حتماً برای توئه!",
]


def _synthesize(text: str) -> bytes | None:
    """متن فارسی را به بایت‌های صوتی MP3 تبدیل می‌کند. در صورت خطا None برمی‌گرداند."""
    if not GTTS_AVAILABLE:
        return None
    try:
        tts = gTTS(text=text, lang="fa")
        buf = io.BytesIO()
        tts.write_to_fp(buf)
        return buf.getvalue()
    except Exception as e:
        logger.warning(f"تولید صدا ناموفق بود: {e}")
        return None


def win_voice_bytes(name: str) -> bytes | None:
    phrase = random.choice(WIN_PHRASES).format(name=name)
    return _synthesize(phrase)


def lose_voice_bytes(name: str) -> bytes | None:
    phrase = random.choice(LOSE_PHRASES).format(name=name)
    return _synthesize(phrase)

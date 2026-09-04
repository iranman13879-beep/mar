from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    Message,
    BufferedInputFile,
    InputMediaPhoto,
)

import database as db
import keyboards as kb
from board_image import render_board
from game_logic import roll_dice, apply_move

router = Router(name="game")


# ============================================================
#                         HELPERS
# ============================================================

def _name_of(user_row: dict | None, fallback_id: int) -> str:
    if not user_row:
        return str(fallback_id)

    if user_row.get("username"):
        return "@" + user_row["username"]

    return user_row.get("first_name") or str(fallback_id)


async def _bot_username(bot: Bot) -> str:
    me = await bot.get_me()
    return me.username or ""


def _players_from_game(game: dict) -> list[int]:
    players = []

    max_players = int(game.get("max_players") or 2)

    for i in range(1, max_players + 1):
        uid = game.get(f"player{i}_id")
        if uid:
            players.append(uid)

    return players


async def _lobby_text(game: dict) -> str:
    players = _players_from_game(game)

    lines = [
        "🐍🪜 <b>لابی مار و پله</b>",
        "",
        f"👥 ظرفیت: <b>{game['max_players']} نفر</b>",
        f"💰 شرط: <b>{game['stake']} سکه</b> برای هر نفر",
        "",
        f"👤 بازیکنان: <b>{len(players)}/{game['max_players']}</b>",
    ]

    for i, uid in enumerate(players, 1):
        user = await db.get_user(uid)
        lines.append(
            f"  {i}. {_name_of(user, uid)}"
        )

    if len(players) < game["max_players"]:
        lines.append("")
        lines.append("⏳ منتظر بازیکن‌های دیگر...")
        lines.append("")
        lines.append("👇 برای ورود روی «پیوستن به لابی» بزنید.")
    else:
        lines.append("")
        lines.append("🔥 <b>لابی تکمیل شد!</b>")
        lines.append("")
        lines.append(
            "🎮 همه بازیکنان روی «ادامه بازی در ربات» بزنند."
        )

    return "\n".join(lines)


def _render_game_board(game: dict):
    """
    رندر تخته برای 2 یا 4 بازیکن.

    اگر board_image.py نسخه جدید 4 بازیکنه باشد،
    p3/p4 هم ارسال می‌شوند.
    """

    max_players = int(game.get("max_players") or 2)

    positions = [
        game.get("player1_pos", 0),
        game.get("player2_pos", 0),
        game.get("player3_pos", 0),
        game.get("player4_pos", 0),
    ]

    labels = []

    for i in range(1, max_players + 1):
        uid = game.get(f"player{i}_id")

        if uid:
            # این تابع sync است، پس اسم موقت می‌گذاریم.
            # اسم واقعی قبل از رندر در caller آماده می‌شود.
            labels.append(str(i))
        else:
            labels.append(f"P{i}")

    try:
        return render_board(
            p1_pos=positions[0],
            p2_pos=positions[1] if max_players >= 2 else None,
            p3_pos=positions[2] if max_players >= 3 else None,
            p4_pos=positions[3] if max_players >= 4 else None,
            p1_label=labels[0],
            p2_label=labels[1],
            p3_label=labels[2],
            p4_label=labels[3],
        )
    except TypeError:
        # سازگاری با board_image.py قدیمی
        return render_board(
            p1_pos=positions[0],
            p2_pos=positions[1] if max_players >= 2 else None,
            p1_label=labels[0],
            p2_label=labels[1],
        )


async def _render_game_board_with_names(game: dict, names: list[str]):
    max_players = int(game.get("max_players") or 2)

    positions = [
        game.get("player1_pos", 0),
        game.get("player2_pos", 0),
        game.get("player3_pos", 0),
        game.get("player4_pos", 0),
    ]

    try:
        return render_board(
            p1_pos=positions[0],
            p2_pos=positions[1] if max_players >= 2 else None,
            p3_pos=positions[2] if max_players >= 3 else None,
            p4_pos=positions[3] if max_players >= 4 else None,
            p1_label=names[0] if len(names) > 0 else "P1",
            p2_label=names[1] if len(names) > 1 else "P2",
            p3_label=names[2] if len(names) > 2 else "P3",
            p4_label=names[3] if len(names) > 3 else "P4",
        )
    except TypeError:
        return render_board(
            p1_pos=positions[0],
            p2_pos=positions[1] if max_players >= 2 else None,
            p1_label=names[0] if len(names) > 0 else "P1",
            p2_label=names[1] if len(names) > 1 else "P2",
        )


# ============================================================
#                         SOLO GAME
# ============================================================

@router.callback_query(F.data == "menu:solo")
async def cb_start_solo(callback: CallbackQuery, bot: Bot):

    user = await db.get_or_create_user(
        callback.from_user.id,
        callback.from_user.username,
        callback.from_user.first_name,
    )

    if user["is_banned"]:
        await callback.answer(
            "⛔️ شما مسدود شده‌اید.",
            show_alert=True,
        )
        return

    fee = await db.get_setting("solo_entry_fee")

    if user["coins"] < fee:
        await callback.answer(
            f"💸 سکه کافی نداری!\nبرای شروع {fee} سکه لازمه.",
            show_alert=True,
        )
        return

    await db.add_coins(
        callback.from_user.id,
        -fee,
    )

    game_id = await db.create_game(
        "solo",
        callback.message.chat.id,
        callback.from_user.id,
        None,
        fee,
    )

    img = render_board(
        p1_pos=0,
        p1_label=_name_of(
            user,
            callback.from_user.id,
        ),
    )

    caption = (
        "🎮 <b>بازی تکی شروع شد!</b>\n\n"
        f"💰 هزینه ورود: {fee} سکه\n"
        "📍 موقعیت: خانه 0\n\n"
        "🎲 دکمه را بزن تا تاس بیندازی."
    )

    try:
        await callback.message.delete()
    except Exception:
        pass

    sent = await bot.send_photo(
        callback.message.chat.id,
        BufferedInputFile(
            img,
            filename="board.png",
        ),
        caption=caption,
        reply_markup=kb.solo_roll_keyboard(game_id),
    )

    await db.update_game_message(
        game_id,
        sent.message_id,
    )

    await callback.answer()


@router.callback_query(F.data.startswith("solo:roll:"))
async def cb_solo_roll(
    callback: CallbackQuery,
    bot: Bot,
):

    game_id = int(
        callback.data.split(":")[2]
    )

    game = await db.get_game(game_id)

    if not game or game["status"] != "active":
        await callback.answer(
            "این بازی دیگه فعال نیست.",
            show_alert=True,
        )
        return

    if callback.from_user.id != game["player1_id"]:
        await callback.answer(
            "این بازیِ تو نیست 😅",
            show_alert=True,
        )
        return

    dice = roll_dice()

    result = apply_move(
        game["player1_pos"],
        dice,
    )

    await db.update_game_position(
        game_id,
        1,
        result["final_to"],
    )

    user = await db.get_user(
        callback.from_user.id
    )

    name = _name_of(
        user,
        callback.from_user.id,
    )

    event_text = ""

    if result["event"] == "overshoot":
        event_text = (
            "🚫 عدد بزرگه، از خونه ۱۰۰ رد می‌شی!"
        )

    elif result["event"] == "snake":
        event_text = (
            f"🐍 وای نه! مار قورتت داد و رفتی "
            f"خونه {result['final_to']}."
        )

    elif result["event"] == "ladder":
        event_text = (
            f"🪜 چه شانسی! از نردبان رفتی بالا "
            f"تا خونه {result['final_to']}."
        )

    if result["won"]:

        reward = await db.get_setting(
            "solo_win_reward"
        )

        await db.add_coins(
            callback.from_user.id,
            reward,
        )

        await db.increment_stats(
            callback.from_user.id,
            won=True,
        )

        await db.finish_game(
            game_id,
            winner_id=callback.from_user.id,
        )

        img = render_board(
            p1_pos=100,
            p1_label=name,
        )

        caption = (
            f"🎉 <b>تبریک {name}!</b>\n\n"
            f"🎲 تاس: {dice}\n"
            "🏁 به خانه ۱۰۰ رسیدی و برنده شدی!\n"
            f"💰 جایزه: +{reward} سکه"
        )

        await bot.edit_message_media(
            media=InputMediaPhoto(
                media=BufferedInputFile(
                    img,
                    filename="board.png",
                ),
                caption=caption,
                parse_mode="HTML",
            ),
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
            reply_markup=kb.solo_finished_keyboard(),
        )

        await callback.answer("🏆 بردی!")
        return

    img = render_board(
        p1_pos=result["final_to"],
        p1_label=name,
    )

    caption_lines = [
        f"🎮 <b>بازی تکی</b> — {name}",
        f"🎲 تاس: {dice}",
    ]

    if event_text:
        caption_lines.append(event_text)

    caption_lines.append(
        f"📍 موقعیت فعلی: خانه {result['final_to']}"
    )

    caption = "\n".join(caption_lines)

    await bot.edit_message_media(
        media=InputMediaPhoto(
            media=BufferedInputFile(
                img,
                filename="board.png",
            ),
            caption=caption,
            parse_mode="HTML",
        ),
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        reply_markup=kb.solo_roll_keyboard(game_id),
    )

    await callback.answer()


@router.callback_query(F.data.startswith("solo:cancel:"))
async def cb_solo_cancel(callback: CallbackQuery):

    game_id = int(
        callback.data.split(":")[2]
    )

    game = await db.get_game(game_id)

    if not game or game["status"] != "active":
        await callback.answer()
        return

    if callback.from_user.id != game["player1_id"]:
        await callback.answer(
            "این بازیِ تو نیست 😅",
            show_alert=True,
        )
        return

    await db.finish_game(
        game_id,
        winner_id=None,
        status="cancelled",
    )

    await callback.message.edit_caption(
        caption="❌ بازی لغو شد.",
        reply_markup=kb.solo_finished_keyboard(),
    )

    await callback.answer()


# ============================================================
#                     MULTIPLAYER MENU
# ============================================================

@router.callback_query(F.data == "menu:pvp")
async def cb_pvp_intro(
    callback: CallbackQuery,
):

    default_stake = await db.get_setting(
        "pvp_default_stake"
    )

    text = (
        "⚔️ <b>بازی چندنفره مار و پله</b>\n\n"
        f"💰 شرط پیش‌فرض: <b>{default_stake} سکه</b> برای هر نفر\n\n"
        "😎 دیگه لازم نیست آیدی کسی رو وارد کنی!\n\n"
        "🏠 یک لابی بساز و دکمه «پیوستن به لابی» "
        "رو در گروه قرار بده.\n\n"
        "👥 بازیکن‌ها از همان دکمه وارد لابی می‌شوند.\n\n"
        "🔥 امکان بازی ۲ نفره و ۴ نفره وجود دارد."
    )

    await callback.message.edit_text(
        text,
        reply_markup=kb.pvp_mode_keyboard(),
    )

    await callback.answer()


# ============================================================
#                    CREATE LOBBY
# ============================================================

@router.callback_query(F.data.startswith("pvp:create:"))
async def cb_create_lobby(
    callback: CallbackQuery,
    bot: Bot,
):

    try:
        max_players = int(
            callback.data.split(":")[2]
        )
    except Exception:
        await callback.answer(
            "❌ ظرفیت لابی نامعتبر است.",
            show_alert=True,
        )
        return

    if max_players not in (2, 4):
        await callback.answer(
            "❌ فقط لابی ۲ نفره یا ۴ نفره مجاز است.",
            show_alert=True,
        )
        return

    user = await db.get_or_create_user(
        callback.from_user.id,
        callback.from_user.username,
        callback.from_user.first_name,
    )

    if user["is_banned"]:
        await callback.answer(
            "⛔️ شما مسدود شده‌اید.",
            show_alert=True,
        )
        return

    stake = await db.get_setting(
        "pvp_default_stake"
    )

    if user["coins"] < stake:
        await callback.answer(
            f"💸 برای ورود به لابی حداقل {stake} سکه لازم داری.",
            show_alert=True,
        )
        return

    game_id = await db.create_game(
        "pvp",
        callback.message.chat.id,
        callback.from_user.id,
        None,
        stake,
        max_players=max_players,
    )

    await db.set_game_status(
        game_id,
        "pending",
    )

    game = await db.get_game(game_id)

    username = await _bot_username(bot)

    text = await _lobby_text(game)

    markup = kb.pvp_lobby_keyboard(
        game_id,
        username,
        max_players,
    )

    try:
        await callback.message.edit_text(
            text,
            reply_markup=markup,
        )

        await db.update_game_message(
            game_id,
            callback.message.message_id,
        )

    except Exception:

        sent = await callback.message.answer(
            text,
            reply_markup=markup,
        )

        await db.update_game_message(
            game_id,
            sent.message_id,
        )

    await callback.answer(
        "✅ لابی ساخته شد!"
    )


# ============================================================
#                     JOIN LOBBY
# ============================================================

@router.callback_query(F.data.startswith("lobby:join:"))
async def cb_join_lobby(
    callback: CallbackQuery,
    bot: Bot,
):

    # پاسخ سریع به Telegram تا دکمه حالت loading نداشته باشد
    await callback.answer(
        "⏳ در حال ورود به لابی..."
    )

    try:
        game_id = int(
            callback.data.split(":")[2]
        )
    except Exception:

        await callback.answer(
            "❌ شناسه لابی نامعتبر است.",
            show_alert=True,
        )
        return

    game = await db.get_game(game_id)

    if not game:
        await callback.answer(
            "❌ این لابی پیدا نشد.",
            show_alert=True,
        )
        return

    if game["status"] != "pending":
        await callback.answer(
            "❌ این لابی دیگر فعال نیست.",
            show_alert=True,
        )
        return

    user = await db.get_or_create_user(
        callback.from_user.id,
        callback.from_user.username,
        callback.from_user.first_name,
    )

    if user["is_banned"]:
        await callback.answer(
            "⛔️ شما مسدود شده‌اید.",
            show_alert=True,
        )
        return

    # بررسی موجودی
    if user["coins"] < game["stake"]:
        await callback.answer(
            f"💸 برای ورود به این لابی {game['stake']} سکه لازم داری.",
            show_alert=True,
        )
        return

    # اضافه کردن کاربر به اولین جای خالی
    ok, reason = await db.add_player_to_lobby(
        game_id,
        callback.from_user.id,
    )

    if not ok:

        if reason == "full":
            msg = "❌ لابی پر شده است."

        elif reason == "closed":
            msg = "❌ این لابی دیگر فعال نیست."

        elif reason == "not_found":
            msg = "❌ لابی پیدا نشد."

        else:
            msg = "❌ ورود به لابی ناموفق بود."

        await callback.answer(
            msg,
            show_alert=True,
        )
        return

    # دریافت نسخه جدید بازی
    game = await db.get_game(game_id)

    players = _players_from_game(game)

    # اگر لابی کامل شد
    if len(players) >= game["max_players"]:

        # دوباره موجودی همه را بررسی می‌کنیم
        balances_ok = True

        for uid in players:

            u = await db.get_user(uid)

            if not u or u["coins"] < game["stake"]:
                balances_ok = False
                break

        if not balances_ok:

            await callback.answer(
                "❌ یکی از بازیکنان سکه کافی ندارد.",
                show_alert=True,
            )

        else:

            # کم کردن شرط همه
            for uid in players:
                await db.add_coins(
                    uid,
                    -game["stake"],
                )

            # شروع بازی
            await db.set_game_status(
                game_id,
                "active",
            )

            await db.set_turn(
                game_id,
                1,
            )

    game = await db.get_game(game_id)

    # متن جدید لابی
    text = await _lobby_text(game)

    username = await _bot_username(bot)

    markup = kb.pvp_lobby_keyboard(
        game_id,
        username,
        game["max_players"],
    )

    # ========================================================
    # لابی هنوز کامل نشده
    # ========================================================

    if game["status"] == "pending":

        try:
            await bot.edit_message_text(
                text,
                chat_id=game["chat_id"],
                message_id=game["message_id"],
                reply_markup=markup,
            )

        except Exception:
            pass

        await callback.answer(
            "✅ وارد لابی شدی!",
            show_alert=True,
        )

        return

    # ========================================================
    # لابی کامل شده
    # ========================================================

    text += (
        "\n\n"
        "🔥 <b>بازی آماده است!</b>\n\n"
        "🎮 برای ورود به بازی خصوصی، "
        "روی دکمه «ادامه بازی در ربات» بزن."
    )

    try:

        await bot.edit_message_text(
            text,
            chat_id=game["chat_id"],
            message_id=game["message_id"],
            reply_markup=markup,
        )

    except Exception:
        pass

    await callback.answer(
        "🔥 لابی تکمیل شد! وارد ربات شو.",
        show_alert=True,
    )


# ============================================================
#                      CANCEL LOBBY
# ============================================================

@router.callback_query(F.data.startswith("lobby:cancel:"))
async def cb_cancel_lobby(
    callback: CallbackQuery,
):

    try:
        game_id = int(
            callback.data.split(":")[2]
        )
    except Exception:
        await callback.answer()
        return

    game = await db.get_game(game_id)

    if not game:
        await callback.answer()
        return

    if game["status"] != "pending":
        await callback.answer(
            "این لابی دیگر فعال نیست.",
            show_alert=True,
        )
        return

    if callback.from_user.id != game["player1_id"]:
        await callback.answer(
            "فقط سازنده لابی می‌تواند آن را لغو کند.",
            show_alert=True,
        )
        return

    await db.finish_game(
        game_id,
        winner_id=None,
        status="cancelled",
    )

    try:
        await callback.message.edit_text(
            "❌ <b>لابی لغو شد.</b>",
        )
    except Exception:
        pass

    await callback.answer(
        "لابی لغو شد."
    )


# ============================================================
#                 OPEN GAME INSIDE BOT
# ============================================================

async def _send_private_game_view(
    bot: Bot,
    game: dict,
    user_id: int,
):

    slot = await db.get_player_slot(
        game,
        user_id,
    )

    if not slot:
        await bot.send_message(
            user_id,
            "❌ تو در این بازی نیستی.",
        )
        return False

    # هنوز کامل نشده
    if game["status"] == "pending":

        await bot.send_message(
            user_id,
            "⏳ <b>لابی هنوز کامل نشده.</b>\n\n"
            "وقتی تعداد بازیکنان کامل شود، "
            "بازی آماده خواهد شد.",
        )

        return True

    if game["status"] != "active":

        await bot.send_message(
            user_id,
            "❌ این بازی دیگر فعال نیست.",
        )

        return True

    players = _players_from_game(game)

    names = []

    for uid in players:

        u = await db.get_user(uid)

        names.append(
            _name_of(u, uid)
        )

    img = await _render_game_board_with_names(
        game,
        names,
    )

    turn = int(
        game.get("turn") or 1
    )

    turn_name = (
        names[turn - 1]
        if 0 < turn <= len(names)
        else "بازیکن"
    )

    my_position = game.get(
        f"player{slot}_pos",
        0,
    )

    caption = (
        f"🐍🪜 <b>مار و پله {game['max_players']} نفره</b>\n\n"
        f"💰 شرط هر نفر: {game['stake']} سکه\n"
        f"🎯 نوبت: <b>{turn_name}</b>\n"
        f"📍 موقعیت تو: خانه {my_position}"
    )

    sent = await bot.send_photo(
        user_id,
        BufferedInputFile(
            img,
            filename="board.png",
        ),
        caption=caption,
        reply_markup=kb.private_game_keyboard(
            game["game_id"]
        ),
    )

    await db.update_player_message(
        game["game_id"],
        slot,
        sent.message_id,
    )

    return True


# ============================================================
#                  /start game_ID
# ============================================================

@router.message(F.text.startswith("/start game_"))
async def cmd_game_start(
    message: Message,
    bot: Bot,
):

    parts = (
        message.text or ""
    ).split(
        maxsplit=1
    )

    if len(parts) < 2:
        return

    payload = parts[1]

    if not payload.startswith("game_"):
        return

    try:
        game_id = int(
            payload[5:]
        )
    except ValueError:

        await message.answer(
            "❌ لینک بازی نامعتبر است."
        )
        return

    game = await db.get_game(
        game_id
    )

    if not game:

        await message.answer(
            "❌ این بازی پیدا نشد."
        )
        return

    user_id = message.from_user.id

    if user_id not in _players_from_game(game):

        await message.answer(
            "❌ این لینک برای بازیکنان این لابی است."
        )
        return

    await db.get_or_create_user(
        user_id,
        message.from_user.username,
        message.from_user.first_name,
    )

    await _send_private_game_view(
        bot,
        game,
        user_id,
    )


# ============================================================
#                       PVP ROLL
# ============================================================

@router.callback_query(F.data.startswith("pvp:roll:"))
async def cb_pvp_roll(
    callback: CallbackQuery,
    bot: Bot,
):

    try:
        game_id = int(
            callback.data.split(":")[2]
        )
    except Exception:

        await callback.answer(
            "❌ بازی نامعتبر است.",
            show_alert=True,
        )
        return

    game = await db.get_game(
        game_id
    )

    if not game or game["status"] != "active":

        await callback.answer(
            "این بازی دیگه فعال نیست.",
            show_alert=True,
        )
        return

    slot = await db.get_player_slot(
        game,
        callback.from_user.id,
    )

    if not slot:

        await callback.answer(
            "❌ این بازی برای تو نیست.",
            show_alert=True,
        )
        return

    if game["turn"] != slot:

        await callback.answer(
            "⏳ هنوز نوبت تو نیست!",
            show_alert=True,
        )
        return

    players = _players_from_game(
        game
    )

    names = []

    for uid in players:

        u = await db.get_user(uid)

        names.append(
            _name_of(u, uid)
        )

    current_player_id = game[
        f"player{slot}_id"
    ]

    current_position = game[
        f"player{slot}_pos"
    ]

    dice = roll_dice()

    result = apply_move(
        current_position,
        dice,
    )

    await db.update_game_position(
        game_id,
        slot,
        result["final_to"],
    )

    # ========================================================
    # WIN
    # ========================================================

    if result["won"]:

        pot = (
            game["stake"]
            * game["max_players"]
        )

        await db.add_coins(
            current_player_id,
            pot,
        )

        await db.increment_stats(
            current_player_id,
            won=True,
        )

        for uid in players:

            if uid != current_player_id:

                await db.increment_stats(
                    uid,
                    won=False,
                )

        await db.finish_game(
            game_id,
            winner_id=current_player_id,
        )

        game = await db.get_game(
            game_id
        )

        img = await _render_game_board_with_names(
            game,
            names,
        )

        winner_name = names[
            slot - 1
        ]

        caption = (
            f"🏆 <b>{winner_name} برنده شد!</b>\n\n"
            f"🎲 تاس: {dice}\n"
            f"💰 جایزه: {pot} سکه"
        )

        for i, uid in enumerate(
            players,
            1,
        ):

            message_id = game.get(
                f"player{i}_message_id"
            )

            if not message_id:
                continue

            try:

                await bot.edit_message_media(
                    media=InputMediaPhoto(
                        media=BufferedInputFile(
                            img,
                            filename="board.png",
                        ),
                        caption=caption,
                        parse_mode="HTML",
                    ),
                    chat_id=uid,
                    message_id=message_id,
                    reply_markup=kb.pvp_finished_keyboard(),
                )

            except Exception:
                pass

        await callback.answer(
            "🏆 برنده شدی!"
        )

        return

    # ========================================================
    # NEXT TURN
    # ========================================================

    max_players = int(
        game["max_players"]
    )

    next_turn = (
        slot % max_players
    ) + 1

    await db.set_turn(
        game_id,
        next_turn,
    )

    game = await db.get_game(
        game_id
    )

    event_text = ""

    if result["event"] == "overshoot":

        event_text = (
            "🚫 از خانه ۱۰۰ رد شد؛ "
            "حرکت انجام نشد."
        )

    elif result["event"] == "snake":

        event_text = (
            f"🐍 مار! رفتی خانه "
            f"{result['final_to']}."
        )

    elif result["event"] == "ladder":

        event_text = (
            f"🪜 نردبان! رفتی خانه "
            f"{result['final_to']}."
        )

    img = await _render_game_board_with_names(
        game,
        names,
    )

    next_player_name = names[
        next_turn - 1
    ]

    caption = (
        f"🐍🪜 <b>مار و پله {max_players} نفره</b>\n\n"
        f"🎲 {names[slot - 1]} انداخت: <b>{dice}</b>\n"
        f"{event_text}\n\n"
        f"🎯 نوبت: <b>{next_player_name}</b>"
    )

    for i, uid in enumerate(
        players,
        1,
    ):

        message_id = game.get(
            f"player{i}_message_id"
        )

        if not message_id:
            continue

        try:

            await bot.edit_message_media(
                media=InputMediaPhoto(
                    media=BufferedInputFile(
                        img,
                        filename="board.png",
                    ),
                    caption=caption,
                    parse_mode="HTML",
                ),
                chat_id=uid,
                message_id=message_id,
                reply_markup=kb.private_game_keyboard(
                    game_id
                ),
            )

        except Exception:
            pass

    await callback.answer()


# ============================================================
#                        LEAVE GAME
# ============================================================

@router.callback_query(F.data.startswith("pvp:leave:"))
async def cb_pvp_leave(
    callback: CallbackQuery,
    bot: Bot,
):

    try:
        game_id = int(
            callback.data.split(":")[2]
        )
    except Exception:

        await callback.answer()
        return

    game = await db.get_game(
        game_id
    )

    if not game or game["status"] != "active":

        await callback.answer()
        return

    slot = await db.get_player_slot(
        game,
        callback.from_user.id,
    )

    if not slot:

        await callback.answer(
            "تو در این بازی نیستی.",
            show_alert=True,
        )
        return

    players = _players_from_game(
        game
    )

    await db.finish_game(
        game_id,
        winner_id=None,
        status="cancelled",
    )

    for uid in players:

        if uid == callback.from_user.id:
            continue

        try:

            await bot.send_message(
                uid,
                "❌ بازی به دلیل خروج یکی از بازیکنان لغو شد.",
            )

        except Exception:
            pass

    try:

        await callback.message.edit_caption(
            caption="❌ از بازی خارج شدی؛ بازی لغو شد.",
            reply_markup=kb.pvp_finished_keyboard(),
        )

    except Exception:
        pass

    await callback.answer(
        "از بازی خارج شدی."
    )

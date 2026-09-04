import logging

from aiogram import Router, F, Bot
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

logger = logging.getLogger(__name__)


# ============================================================
# HELPERS
# ============================================================

def _name_of(user: dict | None, user_id: int) -> str:
    if not user:
        return str(user_id)

    username = user.get("username")

    if username:
        return "@" + username

    first_name = user.get("first_name")

    if first_name:
        return first_name

    return str(user_id)


async def _bot_username(bot: Bot) -> str:
    me = await bot.get_me()
    return me.username or ""


def _players_from_game(game: dict) -> list[int]:
    max_players = int(game.get("max_players") or 2)

    players = []

    for i in range(1, max_players + 1):
        user_id = game.get(f"player{i}_id")

        if user_id:
            players.append(user_id)

    return players


async def _get_player_names(game: dict) -> list[str]:
    names = []

    max_players = int(game.get("max_players") or 2)

    for i in range(1, max_players + 1):

        user_id = game.get(f"player{i}_id")

        if not user_id:
            names.append(f"P{i}")
            continue

        user = await db.get_user(user_id)

        names.append(
            _name_of(user, user_id)
        )

    return names


def _render_board(game: dict, names: list[str] | None = None):

    max_players = int(game.get("max_players") or 2)

    positions = [
        game.get("player1_pos", 0),
        game.get("player2_pos", 0),
        game.get("player3_pos", 0),
        game.get("player4_pos", 0),
    ]

    if names is None:
        names = ["P1", "P2", "P3", "P4"]

    while len(names) < 4:
        names.append(f"P{len(names) + 1}")

    return render_board(
        p1_pos=positions[0],

        p2_pos=(
            positions[1]
            if max_players >= 2
            else None
        ),

        p3_pos=(
            positions[2]
            if max_players >= 3
            else None
        ),

        p4_pos=(
            positions[3]
            if max_players >= 4
            else None
        ),

        p1_label=names[0],
        p2_label=names[1],
        p3_label=names[2],
        p4_label=names[3],
    )


async def _lobby_text(game: dict) -> str:

    max_players = int(
        game.get("max_players") or 2
    )

    players = _players_from_game(game)

    lines = [
        "🎮 <b>لابی مار و پله</b>",
        "",
        f"👥 ظرفیت: <b>{max_players} نفر</b>",
        f"💰 شرط هر نفر: <b>{game['stake']} سکه</b>",
        "",
        f"👤 بازیکنان: <b>{len(players)}/{max_players}</b>",
        "",
    ]

    for index, user_id in enumerate(players, 1):

        user = await db.get_user(user_id)

        name = _name_of(
            user,
            user_id
        )

        lines.append(
            f"🎲 بازیکن {index}: {name}"
        )

    if len(players) < max_players:

        lines.extend(
            [
                "",
                "⏳ <b>منتظر بازیکنان دیگر...</b>",
                "",
                "👥 هرکس می‌تواند با زدن",
                "«پیوستن به لابی» وارد شود.",
            ]
        )

    else:

        lines.extend(
            [
                "",
                "🔥 <b>لابی کامل شد!</b>",
                "",
                "🎮 برای ورود به بازی روی",
                "«ادامه بازی در ربات» بزنید.",
            ]
        )

    return "\n".join(lines)


# ============================================================
# SOLO GAME
# ============================================================

@router.callback_query(F.data == "menu:solo")
async def cb_start_solo(
    callback: CallbackQuery,
    bot: Bot,
):

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

    fee = await db.get_setting(
        "solo_entry_fee"
    )

    if user["coins"] < fee:

        await callback.answer(
            f"💸 سکه کافی نداری!\n"
            f"برای شروع {fee} سکه لازمه.",
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

    await db.set_game_status(
        game_id,
        "active",
    )

    name = _name_of(
        user,
        callback.from_user.id,
    )

    img = render_board(
        p1_pos=0,
        p1_label=name,
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
        reply_markup=kb.solo_roll_keyboard(
            game_id
        ),
    )

    await db.update_game_message(
        game_id,
        sent.message_id,
    )

    await callback.answer()


@router.callback_query(
    F.data.startswith("solo:roll:")
)
async def cb_solo_roll(
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
            "❌ این بازی دیگر فعال نیست.",
            show_alert=True,
        )

        return

    if callback.from_user.id != game["player1_id"]:

        await callback.answer(
            "❌ این بازی برای تو نیست.",
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

    if result["event"] == "overshoot":

        event_text = (
            "🚫 از خانه ۱۰۰ رد می‌شدی؛ "
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

    else:

        event_text = ""

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
            "🏁 به خانه ۱۰۰ رسیدی!\n"
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

        await callback.answer(
            "🏆 بردی!"
        )

        return

    game = await db.get_game(
        game_id
    )

    img = render_board(
        p1_pos=game["player1_pos"],
        p1_label=name,
    )

    caption = (
        f"🎮 <b>بازی تکی</b>\n\n"
        f"🎲 تاس: {dice}\n"
        f"{event_text}\n"
        f"📍 خانه فعلی: {game['player1_pos']}"
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
        reply_markup=kb.solo_roll_keyboard(
            game_id
        ),
    )

    await callback.answer()


@router.callback_query(
    F.data.startswith("solo:cancel:")
)
async def cb_solo_cancel(
    callback: CallbackQuery,
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

    if callback.from_user.id != game["player1_id"]:

        await callback.answer(
            "❌ این بازی برای تو نیست.",
            show_alert=True,
        )

        return

    await db.finish_game(
        game_id,
        winner_id=None,
        status="cancelled",
    )

    try:

        await callback.message.edit_caption(
            caption="❌ بازی لغو شد.",
            reply_markup=kb.solo_finished_keyboard(),
        )

    except Exception:
        pass

    await callback.answer(
        "بازی لغو شد."
    )


# ============================================================
# PVP MENU
# ============================================================

@router.callback_query(
    F.data == "menu:pvp"
)
async def cb_pvp_intro(
    callback: CallbackQuery,
):

    stake = await db.get_setting(
        "pvp_default_stake"
    )

    text = (
        "⚔️ <b>مار و پله چندنفره</b>\n\n"
        f"💰 شرط هر نفر: <b>{stake} سکه</b>\n\n"
        "🔥 بدون نیاز به وارد کردن آیدی!\n\n"
        "👥 لابی ۲ نفره یا ۴ نفره بساز.\n"
        "👤 بقیه بازیکنان روی «پیوستن به لابی» بزنند.\n"
        "🎮 بعد از تکمیل لابی، بازی داخل ربات ادامه پیدا می‌کند."
    )

    await callback.message.edit_text(
        text,
        reply_markup=kb.pvp_mode_keyboard(),
    )

    await callback.answer()


# ============================================================
# CREATE LOBBY
# ============================================================

@router.callback_query(
    F.data.startswith("pvp:create:")
)
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
            f"💸 برای ساخت این لابی "
            f"{stake} سکه لازم داری.",
            show_alert=True,
        )

        return

    # --------------------------------------------------------
    # ساخت لابی
    # --------------------------------------------------------

    game_id = await db.create_game(
        "pvp",
        callback.message.chat.id,
        callback.from_user.id,
        None,
        stake,
        max_players=max_players,
    )

    # حتماً pending
    await db.set_game_status(
        game_id,
        "pending",
    )

    game = await db.get_game(
        game_id
    )

    username = await _bot_username(
        bot
    )

    text = await _lobby_text(
        game
    )

    keyboard = kb.pvp_lobby_keyboard(
        game_id,
        username,
        max_players,
    )

    try:

        await callback.message.edit_text(
            text,
            reply_markup=keyboard,
        )

        await db.update_game_message(
            game_id,
            callback.message.message_id,
        )

    except Exception as e:

        logger.exception(
            "Could not edit lobby message"
        )

        sent = await callback.message.answer(
            text,
            reply_markup=keyboard,
        )

        await db.update_game_message(
            game_id,
            sent.message_id,
        )

    await callback.answer(
        "🔥 لابی ساخته شد!"
    )


# ============================================================
# JOIN LOBBY
# ============================================================

@router.callback_query(
    F.data.startswith("lobby:join:")
)
async def cb_join_lobby(
    callback: CallbackQuery,
    bot: Bot,
):

    # --------------------------------------------------------
    # استخراج ID
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # دریافت لابی
    # --------------------------------------------------------

    game = await db.get_game(
        game_id
    )

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

    # --------------------------------------------------------
    # ثبت کاربر
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # آیا کاربر قبلاً داخل لابی است؟
    # --------------------------------------------------------

    players_before = _players_from_game(
        game
    )

    if callback.from_user.id in players_before:

        await callback.answer(
            "✅ تو قبلاً داخل این لابی هستی.",
            show_alert=True,
        )

        return

    # --------------------------------------------------------
    # بررسی سکه
    # --------------------------------------------------------

    if user["coins"] < game["stake"]:

        await callback.answer(
            f"💸 برای ورود به این لابی "
            f"{game['stake']} سکه لازم داری.",
            show_alert=True,
        )

        return

    # --------------------------------------------------------
    # اضافه کردن بازیکن
    # --------------------------------------------------------

    ok, reason = await db.add_player_to_lobby(
        game_id,
        callback.from_user.id,
    )

    if not ok:

        if reason == "full":
            message = "❌ لابی پر شده است."

        elif reason == "closed":
            message = "❌ این لابی بسته شده است."

        elif reason == "not_found":
            message = "❌ لابی پیدا نشد."

        else:
            message = "❌ ورود به لابی ناموفق بود."

        await callback.answer(
            message,
            show_alert=True,
        )

        return

    # --------------------------------------------------------
    # دریافت وضعیت جدید
    # --------------------------------------------------------

    game = await db.get_game(
        game_id
    )

    players = _players_from_game(
        game
    )

    max_players = int(
        game["max_players"]
    )

    # --------------------------------------------------------
    # اگر لابی کامل شده
    # --------------------------------------------------------

    if len(players) >= max_players:

        # بررسی موجودی همه
        balance_ok = True

        for player_id in players:

            player = await db.get_user(
                player_id
            )

            if not player:

                balance_ok = False
                break

            if player["coins"] < game["stake"]:

                balance_ok = False
                break

        if not balance_ok:

            await callback.answer(
                "❌ یکی از بازیکنان سکه کافی ندارد.",
                show_alert=True,
            )

            return

        # ----------------------------------------------------
        # دریافت شرط از همه
        # ----------------------------------------------------

        for player_id in players:

            await db.add_coins(
                player_id,
                -game["stake"],
            )

        # ----------------------------------------------------
        # شروع بازی
        # ----------------------------------------------------

        await db.set_turn(
            game_id,
            1,
        )

        await db.set_game_status(
            game_id,
            "active",
        )

        game = await db.get_game(
            game_id
        )

    # --------------------------------------------------------
    # آپدیت پیام لابی
    # --------------------------------------------------------

    text = await _lobby_text(
        game
    )

    username = await _bot_username(
        bot
    )

    keyboard = kb.pvp_lobby_keyboard(
        game_id,
        username,
        max_players,
    )

    try:

        await bot.edit_message_text(
            text,
            chat_id=game["chat_id"],
            message_id=game["message_id"],
            reply_markup=keyboard,
        )

    except Exception as e:

        logger.warning(
            "Could not update lobby message: %s",
            e,
        )

    # --------------------------------------------------------
    # نتیجه
    # --------------------------------------------------------

    if game["status"] == "active":

        await callback.answer(
            "🔥 لابی کامل شد! حالا «ادامه بازی در ربات» را بزن.",
            show_alert=True,
        )

    else:

        await callback.answer(
            "✅ با موفقیت وارد لابی شدی!",
            show_alert=True,
        )


# ============================================================
# CANCEL LOBBY
# ============================================================

@router.callback_query(
    F.data.startswith("lobby:cancel:")
)
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

    game = await db.get_game(
        game_id
    )

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
            "❌ فقط سازنده لابی می‌تواند آن را لغو کند.",
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
            "❌ <b>لابی لغو شد.</b>"
        )

    except Exception:
        pass

    await callback.answer(
        "لابی لغو شد."
    )


# ============================================================
# OPEN GAME IN PRIVATE BOT
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
            "❌ تو بازیکن این لابی نیستی."
        )

        return False

    # --------------------------------------------------------
    # هنوز کامل نشده
    # --------------------------------------------------------

    if game["status"] == "pending":

        players = _players_from_game(
            game
        )

        await bot.send_message(
            user_id,
            (
                "⏳ <b>لابی هنوز کامل نشده.</b>\n\n"
                f"👥 بازیکنان: "
                f"{len(players)}/{game['max_players']}\n\n"
                "وقتی ظرفیت کامل شود، "
                "بازی آماده خواهد شد."
            )
        )

        return True

    # --------------------------------------------------------
    # بازی فعال نیست
    # --------------------------------------------------------

    if game["status"] != "active":

        await bot.send_message(
            user_id,
            "❌ این بازی دیگر فعال نیست."
        )

        return True

    # --------------------------------------------------------
    # بازیکنان
    # --------------------------------------------------------

    players = _players_from_game(
        game
    )

    names = await _get_player_names(
        game
    )

    # --------------------------------------------------------
    # تصویر
    # --------------------------------------------------------

    img = _render_board(
        game,
        names,
    )

    turn = int(
        game.get("turn") or 1
    )

    if 1 <= turn <= len(names):

        turn_name = names[
            turn - 1
        ]

    else:

        turn_name = "بازیکن"

    my_position = game.get(
        f"player{slot}_pos",
        0,
    )

    caption = (
        f"🐍🪜 <b>مار و پله "
        f"{game['max_players']} نفره</b>\n\n"
        f"👥 بازیکنان: "
        f"{len(players)}/{game['max_players']}\n"
        f"💰 شرط هر نفر: "
        f"{game['stake']} سکه\n\n"
        f"🎯 نوبت: <b>{turn_name}</b>\n"
        f"📍 موقعیت تو: "
        f"خانه {my_position}"
    )

    # --------------------------------------------------------
    # ارسال بازی
    # --------------------------------------------------------

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
# TELEGRAM /start game_ID
# ============================================================

@router.message(
    F.text.startswith("/start game_")
)
async def cmd_game_start(
    message: Message,
    bot: Bot,
):

    text = message.text or ""

    parts = text.split(
        maxsplit=1
    )

    if len(parts) < 2:

        return

    payload = parts[1].strip()

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

    players = _players_from_game(
        game
    )

    if user_id not in players:

        await message.answer(
            "❌ این لینک برای بازیکنان همین لابی است."
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
# PVP ROLL
# ============================================================

@router.callback_query(
    F.data.startswith("pvp:roll:")
)
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
            "❌ این بازی دیگر فعال نیست.",
            show_alert=True,
        )

        return

    slot = await db.get_player_slot(
        game,
        callback.from_user.id,
    )

    if not slot:

        await callback.answer(
            "❌ تو در این بازی نیستی.",
            show_alert=True,
        )

        return

    if int(game["turn"]) != slot:

        await callback.answer(
            "⏳ هنوز نوبت تو نیست!",
            show_alert=True,
        )

        return

    players = _players_from_game(
        game
    )

    names = await _get_player_names(
        game
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

    # --------------------------------------------------------
    # WIN
    # --------------------------------------------------------

    if result["won"]:

        pot = (
            game["stake"]
            * game["max_players"]
        )

        await db.add_coins(
            current_player_id,
            pot,
        )

        for player_id in players:

            await db.increment_stats(
                player_id,
                won=(
                    player_id ==
                    current_player_id
                ),
            )

        await db.finish_game(
            game_id,
            winner_id=current_player_id,
            status="finished",
        )

        game = await db.get_game(
            game_id
        )

        img = _render_board(
            game,
            names,
        )

        winner_name = names[
            slot - 1
        ]

        caption = (
            f"🏆 <b>{winner_name} برنده شد!</b>\n\n"
            f"🎲 تاس: {dice}\n"
            f"🏁 به خانه ۱۰۰ رسید!\n"
            f"💰 جایزه: {pot} سکه"
        )

        for index, player_id in enumerate(
            players,
            1,
        ):

            message_id = game.get(
                f"player{index}_message_id"
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
                    chat_id=player_id,
                    message_id=message_id,
                    reply_markup=kb.pvp_finished_keyboard(),
                )

            except Exception as e:

                logger.warning(
                    "Could not update winner message: %s",
                    e,
                )

        await callback.answer(
            "🏆 بردی!"
        )

        return

    # --------------------------------------------------------
    # EVENT
    # --------------------------------------------------------

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

    else:

        event_text = ""

    # --------------------------------------------------------
    # NEXT TURN
    # --------------------------------------------------------

    max_players = int(
        game["max_players"]
    )

    next_turn = (
        (slot % max_players) + 1
    )

    await db.set_turn(
        game_id,
        next_turn,
    )

    game = await db.get_game(
        game_id
    )

    img = _render_board(
        game,
        names,
    )

    next_player_name = names[
        next_turn - 1
    ]

    current_name = names[
        slot - 1
    ]

    caption = (
        f"⚔️ <b>مار و پله "
        f"{max_players} نفره</b>\n\n"
        f"🎲 {current_name} "
        f"تاس انداخت: <b>{dice}</b>\n"
        f"{event_text}\n\n"
        f"🎯 نوبت: "
        f"<b>{next_player_name}</b>"
    )

    # --------------------------------------------------------
    # بروزرسانی همه بازیکنان
    # --------------------------------------------------------

    for index, player_id in enumerate(
        players,
        1,
    ):

        message_id = game.get(
            f"player{index}_message_id"
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
                chat_id=player_id,
                message_id=message_id,
                reply_markup=kb.private_game_keyboard(
                    game_id
                ),
            )

        except Exception as e:

            logger.warning(
                "Could not update player %s: %s",
                player_id,
                e,
            )

    await callback.answer()


# ============================================================
# LEAVE PVP
# ============================================================

@router.callback_query(
    F.data.startswith("pvp:leave:")
)
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

    for player_id in players:

        if player_id == callback.from_user.id:
            continue

        try:

            await bot.send_message(
                player_id,
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

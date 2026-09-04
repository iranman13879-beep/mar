from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message, BufferedInputFile, InputMediaPhoto

import database as db
import keyboards as kb
from board_image import render_board
from game_logic import roll_dice, apply_move

router = Router(name="game")


def _name_of(user_row: dict | None, fallback_id: int) -> str:
    if not user_row:
        return str(fallback_id)
    if user_row.get("username"):
        return "@" + user_row["username"]
    return user_row.get("first_name") or str(fallback_id)


# ============================================================
#                      SOLO GAME
# ============================================================

@router.callback_query(F.data == "menu:solo")
async def cb_start_solo(callback: CallbackQuery, bot: Bot):
    user = await db.get_or_create_user(
        callback.from_user.id, callback.from_user.username, callback.from_user.first_name
    )
    if user["is_banned"]:
        await callback.answer("⛔️ شما مسدود شده‌اید.", show_alert=True)
        return

    fee = await db.get_setting("solo_entry_fee")
    if user["coins"] < fee:
        await callback.answer(
            f"💸 سکه کافی نداری! برای شروع {fee} سکه لازمه.", show_alert=True
        )
        return

    await db.add_coins(callback.from_user.id, -fee)
    game_id = await db.create_game("solo", callback.message.chat.id,
                                    callback.from_user.id, None, fee)

    img = render_board(p1_pos=0, p1_label=_name_of(user, callback.from_user.id))
    caption = (
        f"🎮 <b>بازی تکی شروع شد!</b>\n"
        f"هزینه ورود: {fee} سکه\n"
        f"موقعیت: خانه 0\n\n"
        f"🎲 دکمه رو بزن تا تاس بندازی."
    )
    try:
        await callback.message.delete()
    except Exception:
        pass
    sent = await bot.send_photo(
        callback.message.chat.id,
        BufferedInputFile(img, filename="board.png"),
        caption=caption,
        reply_markup=kb.solo_roll_keyboard(game_id),
    )
    await db.update_game_message(game_id, sent.message_id)
    await callback.answer()


@router.callback_query(F.data.startswith("solo:roll:"))
async def cb_solo_roll(callback: CallbackQuery, bot: Bot):
    game_id = int(callback.data.split(":")[2])
    game = await db.get_game(game_id)
    if not game or game["status"] != "active":
        await callback.answer("این بازی دیگه فعال نیست.", show_alert=True)
        return
    if callback.from_user.id != game["player1_id"]:
        await callback.answer("این بازیِ تو نیست 😅", show_alert=True)
        return

    dice = roll_dice()
    result = apply_move(game["player1_pos"], dice)
    await db.update_game_position(game_id, 1, result["final_to"])

    user = await db.get_user(callback.from_user.id)
    name = _name_of(user, callback.from_user.id)

    event_text = ""
    if result["event"] == "overshoot":
        event_text = "🚫 عدد بزرگه، از خونه ۱۰۰ رد می‌شی! دوباره تلاش کن."
    elif result["event"] == "snake":
        event_text = f"🐍 وای نه! مار قورتت داد و رفتی خونه {result['final_to']}."
    elif result["event"] == "ladder":
        event_text = f"🪜 چه شانسی! از نردبان رفتی بالا تا خونه {result['final_to']}."

    if result["won"]:
        reward = await db.get_setting("solo_win_reward")
        await db.add_coins(callback.from_user.id, reward)
        await db.increment_stats(callback.from_user.id, won=True)
        await db.finish_game(game_id, winner_id=callback.from_user.id)

        img = render_board(p1_pos=100, p1_label=name)
        caption = (
            f"🎉 <b>تبریک {name}!</b>\n"
            f"🎲 تاس: {dice}\n"
            f"🏁 به خونه ۱۰۰ رسیدی و برنده شدی!\n"
            f"💰 جایزه: +{reward} سکه"
        )
        await bot.edit_message_media(
            media=InputMediaPhoto(media=BufferedInputFile(img, filename="board.png"),
                                   caption=caption, parse_mode="HTML"),
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
            reply_markup=kb.solo_finished_keyboard(),
        )
        await callback.answer("🏆 بردی!")
        return

    img = render_board(p1_pos=result["final_to"], p1_label=name)
    caption_lines = [f"🎮 <b>بازی تکی</b> — {name}", f"🎲 تاس: {dice}"]
    if event_text:
        caption_lines.append(event_text)
    caption_lines.append(f"📍 موقعیت فعلی: خانه {result['final_to']}")
    caption = "\n".join(caption_lines)
    await bot.edit_message_media(
        media=InputMediaPhoto(media=BufferedInputFile(img, filename="board.png"),
                               caption=caption, parse_mode="HTML"),
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        reply_markup=kb.solo_roll_keyboard(game_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("solo:cancel:"))
async def cb_solo_cancel(callback: CallbackQuery):
    game_id = int(callback.data.split(":")[2])
    game = await db.get_game(game_id)
    if not game or game["status"] != "active":
        await callback.answer()
        return
    if callback.from_user.id != game["player1_id"]:
        await callback.answer("این بازیِ تو نیست 😅", show_alert=True)
        return
    await db.finish_game(game_id, winner_id=None, status="cancelled")
    await callback.message.edit_caption(
        caption="❌ بازی لغو شد. (هزینه ورودی برگردونده نمی‌شه)",
        reply_markup=kb.solo_finished_keyboard(),
    )
    await callback.answer()


# ============================================================
#                    MULTIPLAYER MATCHMAKING
# ============================================================

def _players_from_game(game: dict) -> list[int]:
    return [game[f"player{i}_id"] for i in range(1, game["max_players"] + 1)
            if game.get(f"player{i}_id")]


async def _send_private_game_view(bot: Bot, game: dict, user_id: int):
    slot = await db.get_player_slot(game, user_id)
    if not slot:
        return False

    if game["status"] != "active":
        await bot.send_message(user_id, "❌ این بازی دیگر فعال نیست.")
        return True

    players = _players_from_game(game)
    names = []
    for i in range(1, game["max_players"] + 1):
        u = await db.get_user(game[f"player{i}_id"])
        names.append(_name_of(u, game[f"player{i}_id"]))

    positions = [game[f"player{i}_pos"] for i in range(1, game["max_players"] + 1)]
    img = render_board(
        p1_pos=positions[0],
        p2_pos=positions[1] if len(positions) > 1 else None,
        p3_pos=positions[2] if len(positions) > 2 else None,
        p4_pos=positions[3] if len(positions) > 3 else None,
        p1_label=names[0],
        p2_label=names[1] if len(names) > 1 else "P2",
        p3_label=names[2] if len(names) > 2 else "P3",
        p4_label=names[3] if len(names) > 3 else "P4",
    )
    turn_name = names[game["turn"] - 1]
    caption = (
        f"⚔️ <b>مار و پله {game['max_players']} نفره</b>\n"
        f"💰 شرط هر نفر: {game['stake']} سکه\n\n"
        f"🎯 نوبت: <b>{turn_name}</b>\n"
        f"📍 موقعیت تو: خانه {game[f'player{slot}_pos']}"
    )
    sent = await bot.send_photo(
        user_id,
        BufferedInputFile(img, filename="board.png"),
        caption=caption,
        reply_markup=kb.private_game_keyboard(game["game_id"]),
    )
    await db.update_player_message(game["game_id"], slot, sent.message_id)
    return True


@router.callback_query(F.data == "menu:pvp")
async def cb_pvp_intro(callback: CallbackQuery):
    default_stake = await db.get_setting("pvp_default_stake")
    text = (
        "⚔️ <b>بازی چندنفره مار و پله</b>\n\n"
        "🎯 اول مشخص کن چند نفره بازی کنی، بعد «جستجو» شروع می‌شود.\n"
        "بات به‌صورت خودکار بازیکن‌های منتظر را پیدا می‌کند و بازی را داخل چت خصوصی بات شروع می‌کند.\n\n"
        f"💰 شرط هر نفر: <b>{default_stake} سکه</b>\n"
        "🎲 حالت‌ها: ۲، ۳ یا ۴ نفره\n\n"
        "🔥 لازم نیست آیدی کسی را وارد کنی یا لابی بسازی!"
    )
    await callback.message.edit_text(text, reply_markup=kb.pvp_mode_keyboard())
    await callback.answer()


@router.callback_query(F.data.startswith("pvp:search:"))
async def cb_matchmaking_search(callback: CallbackQuery, bot: Bot):
    try:
        max_players = int(callback.data.split(":")[2])
    except (ValueError, IndexError):
        await callback.answer("تعداد بازیکنان نامعتبر است.", show_alert=True)
        return

    if max_players not in (2, 3, 4):
        await callback.answer("تعداد بازیکنان نامعتبر است.", show_alert=True)
        return

    user = await db.get_or_create_user(
        callback.from_user.id, callback.from_user.username, callback.from_user.first_name
    )
    if user["is_banned"]:
        await callback.answer("⛔️ شما مسدود شده‌اید.", show_alert=True)
        return

    stake = await db.get_setting("pvp_default_stake")
    if user["coins"] < stake:
        await callback.answer(f"💸 برای بازی حداقل {stake} سکه لازم داری.", show_alert=True)
        return

    status, game_id, players = await db.matchmaking_join(
        callback.from_user.id, max_players, stake
    )

    if status == "waiting":
        count = await db.matchmaking_count(max_players, stake)
        text = (
            "🔎 <b>جستجوی حریف شروع شد!</b>\n\n"
            f"👥 حالت: <b>{max_players} نفره</b>\n"
            f"💰 شرط: <b>{stake} سکه</b>\n\n"
            f"⏳ بازیکنان آماده: <b>{count}/{max_players}</b>\n"
            "منتظر بازیکن‌های دیگر هستیم...\n\n"
            "وقتی ظرفیت کامل شود، بازی خودکار داخل بات شروع می‌شود. 🎮"
        )
        try:
            await callback.message.edit_text(text, reply_markup=kb.matchmaking_wait_keyboard())
        except Exception:
            await callback.message.answer(text, reply_markup=kb.matchmaking_wait_keyboard())
        await callback.answer("🔎 در حال پیدا کردن حریف...")
        return

    game = await db.get_game(game_id)
    if not game:
        await callback.answer("❌ بازی ساخته نشد؛ دوباره تلاش کن.", show_alert=True)
        return

    # همه بازیکنان بلافاصله به چت خصوصی بات هدایت می‌شوند و صفحه بازی را می‌گیرند.
    for uid in players:
        try:
            await bot.send_message(uid, "🔥 <b>حریف پیدا شد!</b> بازی شما آماده است؛ تاس بندازید!", parse_mode="HTML")
            await _send_private_game_view(bot, game, uid)
        except Exception:
            # اگر کاربر قبلاً بات را استارت نکرده باشد، پیام تلگرام ممکن است خطا بدهد.
            pass

    await callback.message.edit_text(
        "🎉 <b>حریف پیدا شد!</b>\n\n"
        f"⚔️ بازی {max_players} نفره ساخته شد.\n"
        "🎮 بازی داخل چت خصوصی بات برایت باز شد.\n\n"
        "اگر صفحه بازی را نمی‌بینی، بات را باز کن و دوباره /start بزن.",
        reply_markup=kb.back_to_menu(),
    )
    await callback.answer("🎉 حریف پیدا شد!", show_alert=False)


@router.callback_query(F.data == "match:cancel")
async def cb_matchmaking_cancel(callback: CallbackQuery):
    removed = await db.matchmaking_cancel(callback.from_user.id)
    if removed:
        await callback.message.edit_text("❌ جستجوی حریف لغو شد.", reply_markup=kb.back_to_menu())
        await callback.answer("جستجو لغو شد.")
    else:
        await callback.answer("جستجوی فعالی نداری.", show_alert=True)


async def _send_private_game_view(bot: Bot, game: dict, user_id: int):
    slot = await db.get_player_slot(game, user_id)
    if not slot:
        return False

    players = _players_from_game(game)
    if game["status"] == "pending":
        await bot.send_message(
            user_id,
            "⏳ هنوز لابی کامل نشده.\nوقتی ظرفیت تکمیل شود، از همین‌جا وارد بازی می‌شوی.",
        )
        return True

    if game["status"] != "active":
        await bot.send_message(user_id, "❌ این بازی دیگر فعال نیست.")
        return True

    names = []
    for i in range(1, game["max_players"] + 1):
        u = await db.get_user(game[f"player{i}_id"])
        names.append(_name_of(u, game[f"player{i}_id"]))

    positions = [game[f"player{i}_pos"] for i in range(1, game["max_players"] + 1)]
    img = render_board(
        p1_pos=positions[0],
        p2_pos=positions[1] if len(positions) > 1 else None,
        p3_pos=positions[2] if len(positions) > 2 else None,
        p4_pos=positions[3] if len(positions) > 3 else None,
        p1_label=names[0],
        p2_label=names[1] if len(names) > 1 else "P2",
        p3_label=names[2] if len(names) > 2 else "P3",
        p4_label=names[3] if len(names) > 3 else "P4",
    )
    turn_name = names[game["turn"] - 1]
    caption = (
        f"⚔️ <b>مار و پله {game['max_players']} نفره</b>\n"
        f"💰 شرط هر نفر: {game['stake']} سکه\n\n"
        f"🎯 نوبت: <b>{turn_name}</b>\n"
        f"📍 موقعیت تو: خانه {game[f'player{slot}_pos']}"
    )
    sent = await bot.send_photo(
        user_id,
        BufferedInputFile(img, filename="board.png"),
        caption=caption,
        reply_markup=kb.private_game_keyboard(game["game_id"]),
    )
    await db.update_player_message(game["game_id"], slot, sent.message_id)
    return True


@router.callback_query(F.data.startswith("pvp:roll:"))
async def cb_pvp_roll(callback: CallbackQuery, bot: Bot):
    game_id = int(callback.data.split(":")[2])
    game = await db.get_game(game_id)
    if not game or game["status"] != "active":
        await callback.answer("این بازی دیگه فعال نیست.", show_alert=True)
        return

    slot = await db.get_player_slot(game, callback.from_user.id)
    if not slot:
        await callback.answer("این بازی برای تو نیست.", show_alert=True)
        return
    if game["turn"] != slot:
        await callback.answer("صبر کن، هنوز نوبت تو نیست! ⏳", show_alert=True)
        return

    current_player_id = game[f"player{slot}_id"]
    players = _players_from_game(game)
    player_data = [await db.get_user(uid) for uid in players]
    names = [_name_of(u, uid) for u, uid in zip(player_data, players)]

    dice = roll_dice()
    current_pos = game[f"player{slot}_pos"]
    result = apply_move(current_pos, dice)
    await db.update_game_position(game_id, slot, result["final_to"])

    if result["won"]:
        pot = game["stake"] * game["max_players"]
        await db.add_coins(current_player_id, pot)
        await db.increment_stats(current_player_id, won=True)
        for uid in players:
            if uid != current_player_id:
                await db.increment_stats(uid, won=False)
        await db.finish_game(game_id, winner_id=current_player_id)

        game = await db.get_game(game_id)
        positions = [game[f"player{i}_pos"] for i in range(1, game["max_players"] + 1)]
        img = render_board(
            p1_pos=positions[0],
            p2_pos=positions[1] if len(positions) > 1 else None,
            p3_pos=positions[2] if len(positions) > 2 else None,
            p4_pos=positions[3] if len(positions) > 3 else None,
            p1_label=names[0],
            p2_label=names[1] if len(names) > 1 else "P2",
            p3_label=names[2] if len(names) > 2 else "P3",
            p4_label=names[3] if len(names) > 3 else "P4",
        )
        caption = f"🏆 <b>{names[slot-1]} برنده شد!</b>\n🎲 تاس: {dice}\n💰 جایزه: {pot} سکه"
        for i, uid in enumerate(players, 1):
            mid = game.get(f"player{i}_message_id")
            if mid:
                try:
                    await bot.edit_message_media(
                        media=InputMediaPhoto(
                            media=BufferedInputFile(img, filename="board.png"),
                            caption=caption, parse_mode="HTML"
                        ),
                        chat_id=uid, message_id=mid,
                        reply_markup=kb.pvp_finished_keyboard(),
                    )
                except Exception:
                    pass
        await callback.answer("🏆 بردی!")
        return

    next_turn = (slot % game["max_players"]) + 1
    await db.set_turn(game_id, next_turn)
    game = await db.get_game(game_id)

    event_text = ""
    if result["event"] == "overshoot":
        event_text = "🚫 از ۱۰۰ رد شد؛ حرکت انجام نشد."
    elif result["event"] == "snake":
        event_text = f"🐍 مار! رفتی خانه {result['final_to']}."
    elif result["event"] == "ladder":
        event_text = f"🪜 نردبان! رفتی خانه {result['final_to']}."

    positions = [game[f"player{i}_pos"] for i in range(1, game["max_players"] + 1)]
    img = render_board(
        p1_pos=positions[0],
        p2_pos=positions[1] if len(positions) > 1 else None,
        p3_pos=positions[2] if len(positions) > 2 else None,
        p4_pos=positions[3] if len(positions) > 3 else None,
        p1_label=names[0],
        p2_label=names[1] if len(names) > 1 else "P2",
        p3_label=names[2] if len(names) > 2 else "P3",
        p4_label=names[3] if len(names) > 3 else "P4",
    )
    caption = (
        f"⚔️ <b>مار و پله {game['max_players']} نفره</b>\n"
        f"🎲 {names[slot-1]} انداخت: <b>{dice}</b>\n"
        f"{event_text}\n"
        f"🎯 نوبت: <b>{names[next_turn-1]}</b>"
    )

    for i, uid in enumerate(players, 1):
        mid = game.get(f"player{i}_message_id")
        if not mid:
            continue
        try:
            await bot.edit_message_media(
                media=InputMediaPhoto(
                    media=BufferedInputFile(img, filename="board.png"),
                    caption=caption, parse_mode="HTML"
                ),
                chat_id=uid, message_id=mid,
                reply_markup=kb.private_game_keyboard(game_id),
            )
        except Exception:
            pass
    await callback.answer()


@router.callback_query(F.data.startswith("pvp:leave:"))
async def cb_pvp_leave(callback: CallbackQuery, bot: Bot):
    game_id = int(callback.data.split(":")[2])
    game = await db.get_game(game_id)
    if not game or game["status"] != "active":
        await callback.answer()
        return
    slot = await db.get_player_slot(game, callback.from_user.id)
    if not slot:
        await callback.answer("تو در این بازی نیستی.", show_alert=True)
        return

    await db.finish_game(game_id, winner_id=None, status="cancelled")
    players = _players_from_game(game)
    for uid in players:
        if uid == callback.from_user.id:
            continue
        try:
            await bot.send_message(uid, "❌ بازی به دلیل خروج یکی از بازیکنان لغو شد.")
        except Exception:
            pass
    await callback.message.edit_caption(
        caption="❌ از بازی خارج شدی؛ بازی لغو شد.",
        reply_markup=kb.solo_finished_keyboard(),
    )
    await callback.answer()


# این handler از /start game_ID استفاده می‌کند و بعد از ورود به ربات، بازی را
# در چت خصوصی کاربر نمایش می‌دهد. handler معمول /start در handlers/user.py
# برای /start بدون payload باقی می‌ماند.
@router.message(F.text.startswith("/start game_"))
async def cmd_game_start(message: Message, bot: Bot):
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].startswith("game_"):
        return  # اجازه بده handler عمومی /start پاسخ بدهد.

    try:
        game_id = int(parts[1][5:])
    except ValueError:
        await message.answer("❌ لینک بازی نامعتبر است.")
        return

    game = await db.get_game(game_id)
    if not game:
        await message.answer("❌ این بازی پیدا نشد.")
        return

    uid = message.from_user.id
    if uid not in _players_from_game(game):
        await message.answer("❌ این لینک برای بازیکنان این لابی است.")
        return

    await db.get_or_create_user(uid, message.from_user.username, message.from_user.first_name)
    await _send_private_game_view(bot, game, uid)

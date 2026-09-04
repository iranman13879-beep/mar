from aiogram import Router, F, Bot
from aiogram.filters import Command
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
#                      PVP GAME
# ============================================================

@router.callback_query(F.data == "menu:pvp")
async def cb_pvp_intro(callback: CallbackQuery):
    default_stake = await db.get_setting("pvp_default_stake")
    text = (
        "⚔️ <b>چالش با دوست</b>\n\n"
        "برای دعوت یه دوست به بازی، روی یکی از پیام‌های اون توی همین چت "
        "(گروه یا خصوصی) ریپلای کن و این دستور رو بفرست:\n\n"
        f"<code>/pvp {default_stake}</code>\n\n"
        "عدد جلوی دستور، مقدار سکه‌ای‌ه که هر دو نفر شرط می‌بندید "
        "(می‌تونی خالی بذاری تا مقدار پیش‌فرض استفاده بشه).\n\n"
        "همچنین می‌تونی به‌جای ریپلای، یوزرنیم دوستت رو بنویسی:\n"
        f"<code>/pvp @username {default_stake}</code>"
    )
    await callback.message.edit_text(text, reply_markup=kb.back_to_menu())
    await callback.answer()


@router.message(Command("pvp"))
async def cmd_pvp(message: Message, bot: Bot):
    challenger = await db.get_or_create_user(
        message.from_user.id, message.from_user.username, message.from_user.first_name
    )
    if challenger["is_banned"]:
        await message.reply("⛔️ شما مسدود شده‌اید.")
        return

    args = message.text.split()[1:]
    opponent_id = None
    opponent_username = None
    opponent_first_name = None
    stake_arg = None

    if message.reply_to_message and message.reply_to_message.from_user:
        opp = message.reply_to_message.from_user
        if opp.is_bot:
            await message.reply("نمی‌تونی ربات رو به چالش دعوت کنی 😅")
            return
        opponent_id = opp.id
        opponent_username = opp.username
        opponent_first_name = opp.first_name
        if args:
            stake_arg = args[0]
    elif args and args[0].startswith("@"):
        found = await db.find_user_by_username(args[0])
        if not found:
            await message.reply(
                "❗️ اون کاربر هنوز ربات رو استارت نکرده. اول باید یه بار به ربات پیام بده."
            )
            return
        opponent_id = found["user_id"]
        opponent_username = found["username"]
        opponent_first_name = found["first_name"]
        if len(args) > 1:
            stake_arg = args[1]
    else:
        await message.reply(
            "❗️ روی پیام دوستت ریپلای کن و /pvp بزن، یا از فرمت "
            "<code>/pvp @username مبلغ</code> استفاده کن."
        )
        return

    if opponent_id == message.from_user.id:
        await message.reply("نمی‌تونی خودت رو به چالش دعوت کنی 😄")
        return

    default_stake = await db.get_setting("pvp_default_stake")
    if stake_arg:
        if not stake_arg.isdigit() or int(stake_arg) <= 0:
            await message.reply("مبلغ شرط باید یه عدد مثبت باشه.")
            return
        stake = int(stake_arg)
    else:
        stake = default_stake

    if challenger["coins"] < stake:
        await message.reply(f"💸 سکه کافی نداری! برای این شرط {stake} سکه لازمه.")
        return

    await db.get_or_create_user(opponent_id, opponent_username, opponent_first_name)

    game_id = await db.create_game(
        "pvp", message.chat.id, message.from_user.id, opponent_id, stake
    )
    await db.finish_game(game_id, winner_id=None, status="pending")
    # finish_game فقط برای تغییر status استفاده شده، بازی هنوز واقعا تموم نشده

    challenger_name = _name_of(challenger, message.from_user.id)
    opponent_name = "@" + opponent_username if opponent_username else (opponent_first_name or str(opponent_id))

    text = (
        f"⚔️ <b>دعوت به چالش!</b>\n\n"
        f"{challenger_name} از {opponent_name} دعوت کرد تا با {stake} سکه شرط، "
        f"مار و پله بازی کنن.\n\n"
        f"{opponent_name} قبول می‌کنی؟"
    )
    sent = await message.answer(text, reply_markup=kb.pvp_invite_keyboard(game_id))
    await db.update_game_message(game_id, sent.message_id)


@router.callback_query(F.data.startswith("pvp:accept:"))
async def cb_pvp_accept(callback: CallbackQuery, bot: Bot):
    game_id = int(callback.data.split(":")[2])
    game = await db.get_game(game_id)
    if not game or game["status"] != "pending":
        await callback.answer("این دعوت دیگه معتبر نیست.", show_alert=True)
        return
    if callback.from_user.id != game["player2_id"]:
        await callback.answer("این دعوت برای تو نیست 😅", show_alert=True)
        return

    p1 = await db.get_user(game["player1_id"])
    p2 = await db.get_user(game["player2_id"])
    stake = game["stake"]

    if p1["coins"] < stake:
        await db.finish_game(game_id, winner_id=None, status="cancelled")
        await callback.message.edit_text("❌ دعوت‌کننده دیگه سکه کافی نداره. بازی لغو شد.")
        await callback.answer()
        return
    if p2["coins"] < stake:
        await callback.answer(f"💸 تو هم باید حداقل {stake} سکه داشته باشی!", show_alert=True)
        return

    await db.add_coins(p1["user_id"], -stake)
    await db.add_coins(p2["user_id"], -stake)
    await db.finish_game(game_id, winner_id=None, status="active")
    await db.set_turn(game_id, 1)

    p1_name = _name_of(p1, p1["user_id"])
    p2_name = _name_of(p2, p2["user_id"])

    img = render_board(p1_pos=0, p2_pos=0, p1_label=p1_name, p2_label=p2_name)
    caption = (
        f"⚔️ <b>{p1_name}</b> 🆚 <b>{p2_name}</b>\n"
        f"💰 شرط: {stake} سکه هر نفر (برنده کل {stake * 2} رو می‌بره)\n\n"
        f"نوبت: {p1_name} 🎲"
    )
    try:
        await callback.message.delete()
    except Exception:
        pass
    sent = await bot.send_photo(
        callback.message.chat.id,
        BufferedInputFile(img, filename="board.png"),
        caption=caption,
        reply_markup=kb.pvp_roll_keyboard(game_id, can_roll=True),
    )
    await db.update_game_message(game_id, sent.message_id)
    await callback.answer("✅ بازی شروع شد!")


@router.callback_query(F.data.startswith("pvp:decline:"))
async def cb_pvp_decline(callback: CallbackQuery):
    game_id = int(callback.data.split(":")[2])
    game = await db.get_game(game_id)
    if not game or game["status"] != "pending":
        await callback.answer()
        return
    if callback.from_user.id != game["player2_id"]:
        await callback.answer("این دعوت برای تو نیست 😅", show_alert=True)
        return
    await db.finish_game(game_id, winner_id=None, status="cancelled")
    await callback.message.edit_text("❌ دعوت رد شد.")
    await callback.answer()


@router.callback_query(F.data.startswith("pvp:roll:"))
async def cb_pvp_roll(callback: CallbackQuery, bot: Bot):
    game_id = int(callback.data.split(":")[2])
    game = await db.get_game(game_id)
    if not game or game["status"] != "active":
        await callback.answer("این بازی دیگه فعال نیست.", show_alert=True)
        return

    is_p1_turn = game["turn"] == 1
    current_player_id = game["player1_id"] if is_p1_turn else game["player2_id"]
    if callback.from_user.id != current_player_id:
        await callback.answer("صبر کن، نوبت توئه نیست! ⏳", show_alert=True)
        return

    p1 = await db.get_user(game["player1_id"])
    p2 = await db.get_user(game["player2_id"])
    p1_name = _name_of(p1, game["player1_id"])
    p2_name = _name_of(p2, game["player2_id"])

    dice = roll_dice()
    current_pos = game["player1_pos"] if is_p1_turn else game["player2_pos"]
    result = apply_move(current_pos, dice)
    await db.update_game_position(game_id, 1 if is_p1_turn else 2, result["final_to"])

    mover_name = p1_name if is_p1_turn else p2_name

    event_text = ""
    if result["event"] == "overshoot":
        event_text = f"🚫 {mover_name} عدد بزرگ آورد و از ۱۰۰ رد شد، نوبت می‌ره به نفر بعد."
    elif result["event"] == "snake":
        event_text = f"🐍 {mover_name} به مار خورد و افتاد خونه {result['final_to']}."
    elif result["event"] == "ladder":
        event_text = f"🪜 {mover_name} از نردبان رفت بالا تا خونه {result['final_to']}."

    p1_pos = result["final_to"] if is_p1_turn else game["player1_pos"]
    p2_pos = result["final_to"] if not is_p1_turn else game["player2_pos"]

    if result["won"]:
        pot = game["stake"] * 2
        winner_id = current_player_id
        loser_id = game["player2_id"] if is_p1_turn else game["player1_id"]
        await db.add_coins(winner_id, pot)
        await db.increment_stats(winner_id, won=True)
        await db.increment_stats(loser_id, won=False)
        await db.finish_game(game_id, winner_id=winner_id)

        img = render_board(p1_pos=p1_pos, p2_pos=p2_pos, p1_label=p1_name, p2_label=p2_name)
        caption = (
            f"🎉 <b>{mover_name} برنده شد!</b>\n"
            f"🎲 تاس: {dice}\n"
            f"💰 {pot} سکه رو برد!"
        )
        await bot.edit_message_media(
            media=InputMediaPhoto(media=BufferedInputFile(img, filename="board.png"),
                                   caption=caption, parse_mode="HTML"),
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
            reply_markup=kb.pvp_finished_keyboard(),
        )
        await callback.answer("🏆 بردی!")
        return

    next_turn = 2 if is_p1_turn else 1
    await db.set_turn(game_id, next_turn)
    next_player_name = p2_name if next_turn == 2 else p1_name

    img = render_board(p1_pos=p1_pos, p2_pos=p2_pos, p1_label=p1_name, p2_label=p2_name)
    caption_lines = [f"⚔️ <b>{p1_name}</b> 🆚 <b>{p2_name}</b>", f"🎲 {mover_name} انداخت: {dice}"]
    if event_text:
        caption_lines.append(event_text)
    caption_lines.append(f"\nنوبت: {next_player_name} 🎲")
    caption = "\n".join(caption_lines)

    next_player_id = game["player2_id"] if next_turn == 2 else game["player1_id"]
    await bot.edit_message_media(
        media=InputMediaPhoto(media=BufferedInputFile(img, filename="board.png"),
                               caption=caption, parse_mode="HTML"),
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        reply_markup=kb.pvp_roll_keyboard(game_id, can_roll=True),
    )
    await callback.answer()

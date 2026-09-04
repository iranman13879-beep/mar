import time
import aiosqlite

from config import DB_PATH, DEFAULT_SETTINGS

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    coins INTEGER NOT NULL DEFAULT 0,
    wins INTEGER NOT NULL DEFAULT 0,
    games_played INTEGER NOT NULL DEFAULT 0,
    is_banned INTEGER NOT NULL DEFAULT 0,
    last_daily REAL NOT NULL DEFAULT 0,
    created_at REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS games (
    game_id INTEGER PRIMARY KEY AUTOINCREMENT,
    game_type TEXT NOT NULL,          -- 'solo' or 'pvp'
    chat_id INTEGER NOT NULL,
    message_id INTEGER,
    player1_id INTEGER NOT NULL,
    player2_id INTEGER,
    player3_id INTEGER,
    player4_id INTEGER,
    player1_pos INTEGER NOT NULL DEFAULT 0,
    player2_pos INTEGER NOT NULL DEFAULT 0,
    player3_pos INTEGER NOT NULL DEFAULT 0,
    player4_pos INTEGER NOT NULL DEFAULT 0,
    max_players INTEGER NOT NULL DEFAULT 2,
    player1_message_id INTEGER,
    player2_message_id INTEGER,
    player3_message_id INTEGER,
    player4_message_id INTEGER,
    turn INTEGER NOT NULL DEFAULT 1,
    stake INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active', -- active/finished/cancelled
    winner_id INTEGER,
    created_at REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS matchmaking_queue (
    user_id INTEGER PRIMARY KEY,
    max_players INTEGER NOT NULL,
    stake INTEGER NOT NULL DEFAULT 0,
    joined_at REAL NOT NULL DEFAULT 0
);
"""


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(_SCHEMA)
        # Migration for older installations.
        cur = await db.execute("PRAGMA table_info(games)")
        columns = {row[1] for row in await cur.fetchall()}
        for col, definition in [
            ("player3_id", "INTEGER"),
            ("player4_id", "INTEGER"),
            ("player3_pos", "INTEGER NOT NULL DEFAULT 0"),
            ("player4_pos", "INTEGER NOT NULL DEFAULT 0"),
            ("max_players", "INTEGER NOT NULL DEFAULT 2"),
            ("player1_message_id", "INTEGER"),
            ("player2_message_id", "INTEGER"),
            ("player3_message_id", "INTEGER"),
            ("player4_message_id", "INTEGER"),
        ]:
            if col not in columns:
                await db.execute(f"ALTER TABLE games ADD COLUMN {col} {definition}")
        # Repair status values from older/broken builds.
        # Solo games must be active immediately after creation; PVP lobbies are pending
        # until their capacity is reached. Do not resurrect finished/cancelled games.
        await db.execute(
            "UPDATE games SET status = 'active' WHERE game_type = 'solo' AND (status IS NULL OR status = '')"
        )
        await db.execute(
            "UPDATE games SET status = 'pending' WHERE game_type = 'pvp' AND (status IS NULL OR status = '')"
        )
        for k, v in DEFAULT_SETTINGS.items():
            await db.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v)
            )
        await db.commit()


# ---------------- settings ----------------

async def get_setting(key: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = await cur.fetchone()
        if row is None:
            return int(DEFAULT_SETTINGS.get(key, 0))
        return int(row[0])


async def set_setting(key: str, value: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, str(value)),
        )
        await db.commit()


async def get_all_settings() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT key, value FROM settings")
        rows = await cur.fetchall()
        return {k: int(v) for k, v in rows}


# ---------------- users ----------------

async def get_or_create_user(user_id: int, username: str, first_name: str) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        if row is None:
            start_coins = await get_setting("start_coins")
            await db.execute(
                "INSERT INTO users (user_id, username, first_name, coins, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (user_id, username or "", first_name or "", start_coins, time.time()),
            )
            await db.commit()
            cur = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            row = await cur.fetchone()
        else:
            # keep username/first_name fresh
            await db.execute(
                "UPDATE users SET username = ?, first_name = ? WHERE user_id = ?",
                (username or "", first_name or "", user_id),
            )
            await db.commit()
        return _user_row_to_dict(row)


async def get_user(user_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        return _user_row_to_dict(row) if row else None


def _user_row_to_dict(row) -> dict:
    keys = [
        "user_id", "username", "first_name", "coins", "wins",
        "games_played", "is_banned", "last_daily", "created_at",
    ]
    return dict(zip(keys, row))


async def add_coins(user_id: int, amount: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET coins = coins + ? WHERE user_id = ?", (amount, user_id)
        )
        await db.commit()


async def set_coins(user_id: int, amount: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET coins = ? WHERE user_id = ?", (amount, user_id)
        )
        await db.commit()


async def increment_stats(user_id: int, won: bool):
    async with aiosqlite.connect(DB_PATH) as db:
        if won:
            await db.execute(
                "UPDATE users SET games_played = games_played + 1, wins = wins + 1 "
                "WHERE user_id = ?", (user_id,)
            )
        else:
            await db.execute(
                "UPDATE users SET games_played = games_played + 1 WHERE user_id = ?",
                (user_id,),
            )
        await db.commit()


async def set_last_daily(user_id: int, ts: float):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET last_daily = ? WHERE user_id = ?", (ts, user_id)
        )
        await db.commit()


async def set_ban(user_id: int, banned: bool):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET is_banned = ? WHERE user_id = ?",
            (1 if banned else 0, user_id),
        )
        await db.commit()


async def find_user_by_username(username: str) -> dict | None:
    username = username.lstrip("@")
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT * FROM users WHERE username = ? COLLATE NOCASE", (username,)
        )
        row = await cur.fetchone()
        return _user_row_to_dict(row) if row else None


async def top_players(limit: int = 10) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT user_id, username, first_name, coins, wins FROM users "
            "ORDER BY coins DESC LIMIT ?", (limit,)
        )
        rows = await cur.fetchall()
        return [
            {"user_id": r[0], "username": r[1], "first_name": r[2], "coins": r[3], "wins": r[4]}
            for r in rows
        ]


async def all_user_ids() -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT user_id FROM users")
        rows = await cur.fetchall()
        return [r[0] for r in rows]


async def stats_summary() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT COUNT(*), COALESCE(SUM(coins),0), COALESCE(SUM(games_played),0) FROM users")
        total_users, total_coins, total_games_played = await cur.fetchone()
        cur = await db.execute("SELECT COUNT(*) FROM users WHERE is_banned = 1")
        (banned_count,) = await cur.fetchone()
        cur = await db.execute("SELECT COUNT(*) FROM games")
        (total_games,) = await cur.fetchone()
        return {
            "total_users": total_users,
            "total_coins": total_coins,
            "total_games_played": total_games_played,
            "banned_count": banned_count,
            "total_games": total_games,
        }


# ---------------- games ----------------

async def create_game(game_type: str, chat_id: int, player1_id: int,
                       player2_id: int | None, stake: int,
                       max_players: int = 2,
                       player3_id: int | None = None,
                       player4_id: int | None = None) -> int:
    max_players = 4 if max_players == 4 else 2
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO games (game_type, chat_id, player1_id, player2_id, player3_id, player4_id, "
            "stake, max_players, status, turn, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (game_type, chat_id, player1_id, player2_id, player3_id, player4_id,
             stake, max_players, "pending" if game_type == "pvp" else "active", 1, time.time()),
        )
        await db.commit()
        return cur.lastrowid


async def add_player_to_lobby(game_id: int, user_id: int) -> tuple[bool, str]:
    """Atomically add a user to the next free slot. Returns (success, reason)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")
        cur = await db.execute("SELECT game_id, game_type, chat_id, message_id, player1_id, player2_id, player3_id, player4_id, player1_pos, player2_pos, player3_pos, player4_pos, max_players, player1_message_id, player2_message_id, player3_message_id, player4_message_id, turn, stake, status, winner_id, created_at FROM games WHERE game_id = ?", (game_id,))
        row = await cur.fetchone()
        if not row:
            await db.rollback()
            return False, "not_found"
        game = _game_row_to_dict(row)
        if game["status"] != "pending":
            await db.rollback()
            return False, "closed"
        players = [game["player1_id"], game["player2_id"], game["player3_id"], game["player4_id"]]
        if user_id in [p for p in players if p]:
            await db.rollback()
            return True, "already"
        if len([p for p in players if p]) >= game["max_players"]:
            await db.rollback()
            return False, "full"
        slot = next(i for i, p in enumerate(players, 1) if p is None)
        col = f"player{slot}_id"
        await db.execute(f"UPDATE games SET {col} = ? WHERE game_id = ?", (user_id, game_id))
        await db.commit()
        return True, "joined"


async def lobby_players(game_id: int) -> list[int]:
    game = await get_game(game_id)
    if not game:
        return []
    return [p for p in [game["player1_id"], game["player2_id"], game["player3_id"], game["player4_id"]] if p]


async def get_game(game_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT game_id, game_type, chat_id, message_id, player1_id, player2_id, player3_id, player4_id, player1_pos, player2_pos, player3_pos, player4_pos, max_players, player1_message_id, player2_message_id, player3_message_id, player4_message_id, turn, stake, status, winner_id, created_at FROM games WHERE game_id = ?", (game_id,))
        row = await cur.fetchone()
        return _game_row_to_dict(row) if row else None


def _game_row_to_dict(row) -> dict:
    keys = [
        "game_id", "game_type", "chat_id", "message_id", "player1_id", "player2_id",
        "player3_id", "player4_id", "player1_pos", "player2_pos", "player3_pos",
        "player4_pos", "max_players", "player1_message_id", "player2_message_id",
        "player3_message_id", "player4_message_id", "turn", "stake", "status", "winner_id", "created_at",
    ]
    # Backward-compatible guard for databases created by very old versions.
    return dict(zip(keys, row))


async def update_game_message(game_id: int, message_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE games SET message_id = ? WHERE game_id = ?", (message_id, game_id)
        )
        await db.commit()


async def update_game_position(game_id: int, player_slot: int, new_pos: int):
    if player_slot not in (1, 2, 3, 4):
        raise ValueError("invalid player slot")
    col = f"player{player_slot}_pos"
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f"UPDATE games SET {col} = ? WHERE game_id = ?", (new_pos, game_id)
        )
        await db.commit()


async def update_player_message(game_id: int, player_slot: int, message_id: int):
    if player_slot not in (1, 2, 3, 4):
        raise ValueError("invalid player slot")
    col = f"player{player_slot}_message_id"
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE games SET {col} = ? WHERE game_id = ?", (message_id, game_id))
        await db.commit()


async def get_player_slot(game: dict, user_id: int) -> int | None:
    for slot in range(1, game["max_players"] + 1):
        if game.get(f"player{slot}_id") == user_id:
            return slot
    return None


async def set_turn(game_id: int, turn: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE games SET turn = ? WHERE game_id = ?", (turn, game_id))
        await db.commit()


async def finish_game(game_id: int, winner_id: int | None, status: str = "finished"):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE games SET status = ?, winner_id = ? WHERE game_id = ?",
            (status, winner_id, game_id),
        )
        await db.commit()


async def set_game_status(game_id: int, status: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE games SET status = ? WHERE game_id = ?", (status, game_id))
        await db.commit()


# ---------------- matchmaking ----------------

async def matchmaking_join(user_id: int, max_players: int, stake: int) -> tuple[str, int | None, list[int]]:
    """Join a random matchmaking queue. Returns (status, game_id, players).
    status is 'waiting' or 'matched'. Matching and stake deduction happen atomically.
    """
    if max_players not in (2, 3, 4):
        raise ValueError("max_players must be 2, 3 or 4")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")
        # A user can only be in one matchmaking queue at a time.
        await db.execute("DELETE FROM matchmaking_queue WHERE user_id = ?", (user_id,))

        cur = await db.execute(
            "SELECT q.user_id FROM matchmaking_queue q "
            "JOIN users u ON u.user_id = q.user_id "
            "WHERE q.max_players = ? AND q.stake = ? AND u.is_banned = 0 "
            "ORDER BY q.joined_at ASC",
            (max_players, stake),
        )
        candidates = [r[0] for r in await cur.fetchall() if r[0] != user_id]

        # Drop users who no longer have enough coins.
        valid = []
        for uid in candidates:
            cur = await db.execute("SELECT coins FROM users WHERE user_id = ?", (uid,))
            row = await cur.fetchone()
            if row and row[0] >= stake:
                valid.append(uid)
            else:
                await db.execute("DELETE FROM matchmaking_queue WHERE user_id = ?", (uid,))
            if len(valid) >= max_players - 1:
                break

        if len(valid) < max_players - 1:
            await db.execute(
                "INSERT INTO matchmaking_queue (user_id, max_players, stake, joined_at) VALUES (?, ?, ?, ?)",
                (user_id, max_players, stake, time.time()),
            )
            await db.commit()
            return "waiting", None, [user_id] + valid

        players = valid[:max_players - 1] + [user_id]
        # Verify every player's balance while the write lock is held.
        for uid in players:
            cur = await db.execute("SELECT coins FROM users WHERE user_id = ?", (uid,))
            row = await cur.fetchone()
            if not row or row[0] < stake:
                # Put the current user back in the queue; the stale candidate will be removed.
                await db.execute("DELETE FROM matchmaking_queue WHERE user_id = ?", (uid,))
                await db.execute(
                    "INSERT OR REPLACE INTO matchmaking_queue (user_id, max_players, stake, joined_at) VALUES (?, ?, ?, ?)",
                    (user_id, max_players, stake, time.time()),
                )
                await db.commit()
                return "waiting", None, [user_id]

        for uid in players:
            await db.execute("UPDATE users SET coins = coins - ? WHERE user_id = ?", (stake, uid))
            await db.execute("DELETE FROM matchmaking_queue WHERE user_id = ?", (uid,))

        placeholders = [None, None, None, None]
        for i, uid in enumerate(players):
            placeholders[i] = uid
        cur = await db.execute(
            "INSERT INTO games (game_type, chat_id, player1_id, player2_id, player3_id, player4_id, "
            "stake, max_players, status, turn, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("pvp", 0, placeholders[0], placeholders[1], placeholders[2], placeholders[3],
             stake, max_players, "active", 1, time.time()),
        )
        game_id = cur.lastrowid
        await db.commit()
        return "matched", game_id, players


async def matchmaking_cancel(user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("DELETE FROM matchmaking_queue WHERE user_id = ?", (user_id,))
        await db.commit()
        return cur.rowcount > 0


async def matchmaking_get(user_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT user_id, max_players, stake, joined_at FROM matchmaking_queue WHERE user_id = ?",
            (user_id,),
        )
        row = await cur.fetchone()
        if not row:
            return None
        return {"user_id": row[0], "max_players": row[1], "stake": row[2], "joined_at": row[3]}


async def matchmaking_count(max_players: int, stake: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT COUNT(*) FROM matchmaking_queue WHERE max_players = ? AND stake = ?",
            (max_players, stake),
        )
        (count,) = await cur.fetchone()
        return count

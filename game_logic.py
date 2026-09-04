import random
from config import SNAKES, LADDERS


def roll_dice() -> int:
    return random.randint(1, 6)


def apply_move(current_pos: int, dice: int) -> dict:
    """
    محاسبه خانه‌ی جدید بازیکن بعد از تاس انداختن.
    برمی‌گردونه: {'from', 'raw_to', 'final_to', 'event': None|'snake'|'ladder', 'won': bool}
    """
    raw_to = current_pos + dice

    if raw_to > 100:
        # اگه از خونه ۱۰۰ رد بشه، حرکت باطله و تاس بعدی رو باید بندازه
        return {
            "from": current_pos,
            "raw_to": current_pos,
            "final_to": current_pos,
            "event": "overshoot",
            "won": False,
        }

    final_to = raw_to
    event = None

    if raw_to in SNAKES:
        final_to = SNAKES[raw_to]
        event = "snake"
    elif raw_to in LADDERS:
        final_to = LADDERS[raw_to]
        event = "ladder"

    return {
        "from": current_pos,
        "raw_to": raw_to,
        "final_to": final_to,
        "event": event,
        "won": final_to == 100,
    }

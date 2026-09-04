import io
import math
from PIL import Image, ImageDraw, ImageFont, ImageFilter

from config import SNAKES, LADDERS, CELL_PX, MARGIN_PX, HEADER_PX

FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_PATH_REGULAR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

BOARD_N = 10

# --- پالت رنگی ---
BG_TOP = (30, 20, 60)
BG_BOTTOM = (70, 30, 90)
CELL_LIGHT = (255, 244, 214)
CELL_DARK = (255, 214, 153)
CELL_BORDER = (120, 70, 30)
LADDER_COLOR = (60, 160, 90)
LADDER_RUNG = (255, 255, 255)
SNAKE_COLOR = (220, 60, 70)
TEXT_COLOR = (90, 55, 20)
P1_COLOR = (52, 120, 246)
P2_COLOR = (235, 64, 92)
GOLD = (255, 205, 60)


def _font(size, bold=True):
    try:
        return ImageFont.truetype(FONT_PATH if bold else FONT_PATH_REGULAR, size)
    except Exception:
        return ImageFont.load_default()


def cell_to_xy(cell: int):
    """تبدیل شماره خانه (۱ تا ۱۰۰) به مختصات پیکسل مرکز خانه."""
    idx = cell - 1
    row = idx // BOARD_N          # 0 = پایین‌ترین ردیف
    col = idx % BOARD_N
    if row % 2 == 1:
        col = BOARD_N - 1 - col
    x = MARGIN_PX + col * CELL_PX + CELL_PX // 2
    y = HEADER_PX + MARGIN_PX + (BOARD_N - 1 - row) * CELL_PX + CELL_PX // 2
    return x, y


def _vertical_gradient(size, top_color, bottom_color):
    w, h = size
    base = Image.new("RGB", (w, h), top_color)
    top = Image.new("RGB", (w, h), top_color)
    bottom = Image.new("RGB", (w, h), bottom_color)
    mask = Image.new("L", (w, h))
    mask_data = []
    for y in range(h):
        mask_data.extend([int(255 * (y / h))] * w)
    mask.putdata(mask_data)
    base = Image.composite(bottom, top, mask)
    return base


def _draw_snake(draw: ImageDraw.ImageDraw, start_xy, end_xy):
    x1, y1 = start_xy
    x2, y2 = end_xy
    steps = 24
    points = []
    dx = x2 - x1
    dy = y2 - y1
    length = math.hypot(dx, dy)
    perp = (-dy / length, dx / length) if length else (0, 0)
    amplitude = min(18, CELL_PX * 0.35)
    for i in range(steps + 1):
        t = i / steps
        bx = x1 + dx * t
        by = y1 + dy * t
        wave = math.sin(t * math.pi * 3) * amplitude * (1 - t * 0.15)
        points.append((bx + perp[0] * wave, by + perp[1] * wave))
    draw.line(points, fill=SNAKE_COLOR, width=9, joint="curve")
    # سر مار
    draw.ellipse(
        [x1 - 11, y1 - 11, x1 + 11, y1 + 11], fill=SNAKE_COLOR, outline=(120, 20, 25), width=2
    )
    # چشم‌ها
    draw.ellipse([x1 - 4, y1 - 4, x1 - 1, y1 - 1], fill="white")
    draw.ellipse([x1 + 1, y1 - 4, x1 + 4, y1 - 1], fill="white")
    # دم
    draw.ellipse([x2 - 5, y2 - 5, x2 + 5, y2 + 5], fill=SNAKE_COLOR)


def _draw_ladder(draw: ImageDraw.ImageDraw, start_xy, end_xy):
    x1, y1 = start_xy
    x2, y2 = end_xy
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy) or 1
    perp = (-dy / length, dx / length)
    offset = 9
    rail1_start = (x1 + perp[0] * offset, y1 + perp[1] * offset)
    rail1_end = (x2 + perp[0] * offset, y2 + perp[1] * offset)
    rail2_start = (x1 - perp[0] * offset, y1 - perp[1] * offset)
    rail2_end = (x2 - perp[0] * offset, y2 - perp[1] * offset)
    draw.line([rail1_start, rail1_end], fill=LADDER_COLOR, width=6)
    draw.line([rail2_start, rail2_end], fill=LADDER_COLOR, width=6)
    rungs = max(3, int(length // 26))
    for i in range(rungs + 1):
        t = i / rungs
        rx1 = rail1_start[0] + (rail1_end[0] - rail1_start[0]) * t
        ry1 = rail1_start[1] + (rail1_end[1] - rail1_start[1]) * t
        rx2 = rail2_start[0] + (rail2_end[0] - rail2_start[0]) * t
        ry2 = rail2_start[1] + (rail2_end[1] - rail2_start[1]) * t
        draw.line([(rx1, ry1), (rx2, ry2)], fill=LADDER_RUNG, width=4)


def render_board(p1_pos: int = 0, p2_pos: int | None = None,
                  p1_label: str = "P1", p2_label: str = "P2",
                  p3_pos: int | None = None, p4_pos: int | None = None,
                  p3_label: str = "P3", p4_label: str = "P4") -> bytes:
    board_px = CELL_PX * BOARD_N
    width = board_px + MARGIN_PX * 2
    height = board_px + MARGIN_PX * 2 + HEADER_PX

    img = _vertical_gradient((width, height), BG_TOP, BG_BOTTOM)
    draw = ImageDraw.Draw(img)

    # --- هدر ---
    # توجه: فونت DejaVu حروف فارسی رو پشتیبانی نمی‌کنه (به‌صورت باکس نمایش داده می‌شه)
    # به همین خاطر عنوان داخل تصویر انگلیسی/ایموجی‌ه؛ متن‌های فارسی همه در پیام‌های
    # تلگرام فرستاده می‌شن که خودِ اپ تلگرام رندرشون می‌کنه و مشکلی ندارن.
    title_font = _font(30)
    draw.text((width / 2, HEADER_PX / 2 - 6), "SNAKE  &  LADDER", font=title_font,
               fill=GOLD, anchor="mm")

    # --- زمینه‌ی تخته با سایه و حاشیه گرد ---
    board_top = HEADER_PX + MARGIN_PX - 10
    rounded = Image.new("RGBA", (board_px + 20, board_px + 20), (0, 0, 0, 0))
    rd = ImageDraw.Draw(rounded)
    rd.rounded_rectangle([0, 0, board_px + 19, board_px + 19], radius=18,
                          fill=(255, 255, 255, 255))
    img.paste(rounded, (MARGIN_PX - 10, board_top), rounded)
    draw = ImageDraw.Draw(img)

    num_font = _font(15)

    # --- خانه‌ها ---
    for cell in range(1, 101):
        idx = cell - 1
        row = idx // BOARD_N
        col = idx % BOARD_N
        if row % 2 == 1:
            col = BOARD_N - 1 - col
        x0 = MARGIN_PX + col * CELL_PX
        y0 = HEADER_PX + MARGIN_PX + (BOARD_N - 1 - row) * CELL_PX
        x1 = x0 + CELL_PX
        y1 = y0 + CELL_PX
        color = CELL_LIGHT if (row + col) % 2 == 0 else CELL_DARK
        draw.rectangle([x0, y0, x1, y1], fill=color, outline=CELL_BORDER, width=1)
        draw.text((x0 + 6, y0 + 4), str(cell), font=num_font, fill=TEXT_COLOR)

    # --- مارها ---
    for start, end in SNAKES.items():
        _draw_snake(draw, cell_to_xy(start), cell_to_xy(end))

    # --- نردبان‌ها ---
    for start, end in LADDERS.items():
        _draw_ladder(draw, cell_to_xy(start), cell_to_xy(end))

    # --- مهره‌های بازیکن‌ها ---
    token_colors = [P1_COLOR, P2_COLOR, (60, 190, 120), (175, 85, 220)]
    positions = [p1_pos, p2_pos, p3_pos, p4_pos]
    labels = ["1", "2", "3", "4"]
    names = [p1_label, p2_label, p3_label, p4_label]

    active = [(i, pos) for i, pos in enumerate(positions) if pos is not None]
    offsets = {
        1: [0],
        2: [-10, 10],
        3: [-13, 0, 13],
        4: [-14, -5, 5, 14],
    }.get(len(active), [0])

    def draw_token(pos, color, label, side_offset):
        if pos is None or pos <= 0:
            return
        x, y = cell_to_xy(pos)
        x += side_offset
        r = 15
        draw.ellipse([x - r, y - r, x + r, y + r], fill=color, outline="white", width=3)
        f = _font(13)
        draw.text((x, y), label, font=f, fill="white", anchor="mm")

    for offset, (i, pos) in zip(offsets, active):
        draw_token(pos, token_colors[i], labels[i], offset)

    # --- راهنما ---
    legend_font = _font(14, bold=False)
    ly = height - 6
    x = MARGIN_PX
    for i, pos in active:
        draw.ellipse([x, ly - 16, x + 14, ly - 2], fill=token_colors[i])
        label = names[i][:14]
        draw.text((x + 20, ly - 16), label, font=legend_font, fill="white")
        x += 190

    buf = io.BytesIO()
    img = img.convert("RGB")
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.getvalue()

"""ArchSchool Visual Card & Chart Renderer.

Generates sleek, dark-themed visual cards inspired directly by the ArchSchool mobile app UI:
- True pitch-black surfaces (#060608 / #0E0F14)
- Cyber corner ticks (<Corners />)
- Mono labels with double slashes (// ARCHSCHOOL, // MY STREAK, // LEADERBOARD, // ACTIVITY)
- Role badges (OWNER, ADMIN, MEMBER)
- Procedural vector flames, glowing medals, progress bars, and authentic 7-day activity bar charts.
- Zero raw emoji glyphs to prevent PIL missing-glyph boxes / tofu.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import arabic_reshaper
from bidi.algorithm import get_display
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from .. import models
from ..analytics import compute_user_stats
from . import school_knowledge

# Assets paths
CURRENT_DIR = Path(__file__).resolve().parent
ASSETS_DIR = CURRENT_DIR.parent / "assets"
FONTS_DIR = ASSETS_DIR / "fonts"
CACHE_DIR = ASSETS_DIR / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

FONT_BOLD_PATH = str(FONTS_DIR / "Vazirmatn-Bold.ttf")
FONT_MEDIUM_PATH = str(FONTS_DIR / "Vazirmatn-Medium.ttf")

# ---------------------------------------------------------------------------
# Visual Palette - 1:1 Mirror of ArchSchool Mobile Design Tokens
# ---------------------------------------------------------------------------
C_BG = (6, 6, 8)                   # #060608 True Ink surface
C_PANEL = (14, 15, 20)             # #0E0F14 Card surface (mobile .panel)
C_PANEL_ELEVATED = (22, 24, 32)    # #161820 Elevated stat tile
C_LINE = (38, 41, 52)              # rgba(255,255,255,0.08)
C_LINE_STRONG = (65, 72, 92)       # rgba(255,255,255,0.18)
C_CORNERS = (75, 82, 102)          # rgba(255,255,255,0.20) Corner brackets

C_TEXT = (250, 250, 250)           # #FAFAFA Primary text
C_TEXT_SOFT = (212, 212, 216)      # #D4D4D8 Subtitle
C_MUTED = (161, 161, 170)          # #A1A1AA Secondary
C_FAINT = (124, 124, 134)          # #7C7C86 Faint / labels

C_FLAME = (251, 146, 60)           # #FB923C Streak hero flame
C_FLAME_BG = (45, 25, 12)          # Soft glowing orange
C_GOLD = (251, 191, 36)            # #FBBF24 Top 1 medal / gold
C_GOLD_BG = (42, 33, 10)           # Soft gold glow
C_SILVER = (212, 212, 216)         # #D4D4D8 Top 2 medal / silver
C_SILVER_BG = (30, 32, 40)         # Soft silver glow
C_BRONZE = (201, 132, 85)          # #C98455 Top 3 medal / bronze
C_BRONZE_BG = (38, 26, 18)         # Soft bronze glow

C_SUCCESS = (52, 211, 153)         # #34D399 Success / Completed
C_SUCCESS_BG = (12, 38, 28)        # Soft emerald glow
C_SKY = (125, 211, 252)            # #7DD3FC Sky blue
C_SKY_BG = (14, 34, 48)            # Soft sky glow
C_DANGER = (248, 113, 113)         # #F87171 Urgent / Danger
C_DANGER_BG = (45, 18, 18)         # Soft red glow
C_PURPLE = (192, 132, 252)         # #C084FC Purple accent


def fa(text: str) -> str:
    """Reshape and reorder Persian/Arabic text for correct RTL rendering."""
    if not text:
        return ""
    try:
        # Strip raw emoji characters that break RTL shaping or produce tofu
        cleaned = "".join(ch for ch in str(text) if ord(ch) < 0x1F000 and ord(ch) not in (0x23F0, 0x23F3, 0x2705, 0x274C, 0x26A0, 0x26BD))
        reshaped = arabic_reshaper.reshape(cleaned.strip())
        return get_display(reshaped)
    except Exception:
        return str(text)


def _load_font(path: str, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    if os.path.exists(path):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    return ImageFont.load_default()


def _get_fonts() -> Dict[str, Any]:
    return {
        "hero_num": _load_font(FONT_BOLD_PATH, 50),
        "stat_val": _load_font(FONT_BOLD_PATH, 32),
        "stat_val_sm": _load_font(FONT_BOLD_PATH, 22),
        "title": _load_font(FONT_BOLD_PATH, 21),
        "subtitle": _load_font(FONT_MEDIUM_PATH, 15),
        "body_bold": _load_font(FONT_BOLD_PATH, 15),
        "body": _load_font(FONT_MEDIUM_PATH, 14),
        "mono": _load_font(FONT_BOLD_PATH, 11),
        "badge": _load_font(FONT_BOLD_PATH, 12),
        "tag": _load_font(FONT_MEDIUM_PATH, 11),
        "small": _load_font(FONT_MEDIUM_PATH, 12),
    }


def _truncate_text(draw: ImageDraw.ImageDraw, text: str, font: Any, max_width: int) -> str:
    """Truncate Persian text cleanly with ellipsis if wider than max_width."""
    if not text:
        return ""
    if draw.textlength(fa(text), font=font) <= max_width:
        return text
    cur = text
    while cur and draw.textlength(fa(cur + "…"), font=font) > max_width:
        cur = cur[:-1]
    return cur + "…"


def _draw_corners(draw: ImageDraw.ImageDraw, box: Tuple[int, int, int, int], tone: Tuple[int, int, int] = C_CORNERS) -> None:
    """Draws 4 high-tech cyber L-brackets matching <Corners /> in the mobile app."""
    x1, y1, x2, y2 = box
    arm = 7
    inset = 8
    # Top-Left
    draw.line([(x1 + inset, y1 + inset), (x1 + inset + arm, y1 + inset)], fill=tone, width=1)
    draw.line([(x1 + inset, y1 + inset), (x1 + inset, y1 + inset + arm)], fill=tone, width=1)
    # Top-Right
    draw.line([(x2 - inset, y1 + inset), (x2 - inset - arm, y1 + inset)], fill=tone, width=1)
    draw.line([(x2 - inset, y1 + inset), (x2 - inset, y1 + inset + arm)], fill=tone, width=1)
    # Bottom-Left
    draw.line([(x1 + inset, y2 - inset), (x1 + inset + arm, y2 - inset)], fill=tone, width=1)
    draw.line([(x1 + inset, y2 - inset), (x1 + inset, y2 - inset - arm)], fill=tone, width=1)
    # Bottom-Right
    draw.line([(x2 - inset, y2 - inset), (x2 - inset - arm, y2 - inset)], fill=tone, width=1)
    draw.line([(x2 - inset, y2 - inset), (x2 - inset, y2 - inset - arm)], fill=tone, width=1)


def _draw_panel(
    draw: ImageDraw.ImageDraw,
    box: Tuple[int, int, int, int],
    radius: int = 16,
    fill: Tuple[int, int, int] = C_PANEL,
    outline: Tuple[int, int, int] = C_LINE,
    corners: bool = True,
    corner_tone: Tuple[int, int, int] = C_CORNERS,
) -> None:
    """Draws a rounded dark panel with optional cyber corners."""
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=1)
    if corners:
        _draw_corners(draw, box, corner_tone)


def _draw_vector_flame(draw: ImageDraw.ImageDraw, cx: int, cy: int, size: int = 36) -> None:
    """Draw a vibrant cyber flame with outer orange and inner golden core without emojis."""
    draw.ellipse((cx - size - 8, cy - size - 8, cx + size + 8, cy + size + 8), fill=C_FLAME_BG)
    s = size / 24.0
    outer_pts = [
        (cx, cy - int(24 * s)),
        (cx + int(10 * s), cy - int(8 * s)),
        (cx + int(16 * s), cy + int(6 * s)),
        (cx + int(14 * s), cy + int(18 * s)),
        (cx + int(6 * s), cy + int(24 * s)),
        (cx - int(6 * s), cy + int(24 * s)),
        (cx - int(14 * s), cy + int(18 * s)),
        (cx - int(16 * s), cy + int(6 * s)),
        (cx - int(10 * s), cy - int(8 * s)),
    ]
    draw.polygon(outer_pts, fill=C_FLAME)
    inner_pts = [
        (cx, cy - int(10 * s)),
        (cx + int(6 * s), cy + int(2 * s)),
        (cx + int(4 * s), cy + int(16 * s)),
        (cx - int(4 * s), cy + int(16 * s)),
        (cx - int(6 * s), cy + int(2 * s)),
    ]
    draw.polygon(inner_pts, fill=C_GOLD)


def _draw_medal_badge(draw: ImageDraw.ImageDraw, cx: int, cy: int, rank: int, col: Tuple[int, int, int], bg: Tuple[int, int, int], font: Any) -> None:
    """Draws a crisp geometric medallion with #1, #2, #3 inside."""
    r = 22
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=bg, outline=col, width=2)
    txt = f"#{rank}"
    tw = draw.textlength(txt, font=font)
    draw.text((cx - tw // 2, cy - 8), txt, font=font, fill=col)


def _draw_mobile_header(
    draw: ImageDraw.ImageDraw,
    title: str,
    mono_label: str,
    user: Optional[models.User] = None,
    width: int = 960,
) -> None:
    """Draws the top bar matching ArchSchool mobile app header."""
    fonts = _get_fonts()

    # 1. Top Right Pill: // ARCHSCHOOL with Green Pulse Dot
    pill_box = (width - 240, 24, width - 32, 54)
    draw.rounded_rectangle(pill_box, radius=15, fill=(18, 20, 28), outline=C_LINE, width=1)
    draw.ellipse((width - 52, 36, width - 44, 44), fill=C_SUCCESS)
    draw.text((width - 224, 33), "// ARCHSCHOOL", font=fonts["mono"], fill=C_TEXT_SOFT)

    # 2. Top Center: Date Pill
    now_fa = school_knowledge.format_iran_datetime(datetime.utcnow())
    date_pill_box = (width // 2 - 130, 24, width // 2 + 130, 54)
    draw.rounded_rectangle(date_pill_box, radius=15, fill=(14, 16, 22), outline=C_LINE, width=1)
    date_str = fa(f"امروز: {now_fa}")
    d_w = draw.textlength(date_str, font=fonts["tag"])
    draw.text((width // 2 - d_w // 2, 33), date_str, font=fonts["tag"], fill=C_MUTED)

    # 3. Top Left: User Badge & Role
    if user:
        u_box = (32, 24, 250, 54)
        draw.rounded_rectangle(u_box, radius=15, fill=(18, 20, 28), outline=C_LINE, width=1)
        draw.ellipse((42, 30, 66, 50), fill=(40, 44, 60), outline=C_LINE_STRONG, width=1)
        initial = (user.username[:1] if user.username else "U").upper()
        draw.text((50, 31), initial, font=fonts["badge"], fill=C_TEXT)

        u_name = user.username or "کاربر"
        draw.text((76, 33), u_name[:12], font=fonts["mono"], fill=C_TEXT)

        role = getattr(user, "role", "member") or "member"
        is_owner = models.is_owner(user)
        badge_txt = "OWNER" if is_owner else ("ADMIN" if user.is_admin or role == "admin" else "MEMBER")
        b_col = C_GOLD if is_owner else (C_TEXT_SOFT if badge_txt == "ADMIN" else C_FAINT)
        draw.text((188, 33), f"[{badge_txt}]", font=fonts["mono"], fill=b_col)
    else:
        u_box = (32, 24, 180, 54)
        draw.rounded_rectangle(u_box, radius=15, fill=(18, 20, 28), outline=C_LINE, width=1)
        draw.text((46, 33), "// GUEST USER", font=fonts["mono"], fill=C_FAINT)

    # 4. Main Title & Mono Label
    draw.text((36, 76), mono_label, font=fonts["mono"], fill=C_FLAME)
    title_fa = fa(title)
    draw.text((width - 32 - draw.textlength(title_fa, font=fonts["title"]), 72), title_fa, font=fonts["title"], fill=C_TEXT)

    # 5. Header divider
    draw.line([(32, 114), (width - 32, 114)], fill=C_LINE, width=1)


def _draw_progress_bar(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    w: int,
    h: int,
    pct: float,
    fill_col: Tuple[int, int, int],
    bg_col: Tuple[int, int, int] = (24, 27, 36),
) -> None:
    """Draws a smooth rounded progress bar matching mobile app tracks."""
    draw.rounded_rectangle((x, y, x + w, y + h), radius=h // 2, fill=bg_col)
    clamped_pct = min(100.0, max(0.0, pct))
    fill_w = int(w * (clamped_pct / 100.0))
    if fill_w > h:
        draw.rounded_rectangle((x, y, x + fill_w, y + h), radius=h // 2, fill=fill_col)


def _draw_weekly_activity_bars(
    draw: ImageDraw.ImageDraw,
    box: Tuple[int, int, int, int],
    activity_counts: List[int],
    today_index: int,
    fonts: Dict[str, Any],
) -> None:
    """Draws a sleek 7-day bar chart showing daily activity matching mobile app charts."""
    x1, y1, x2, y2 = box
    draw.rounded_rectangle(box, radius=14, fill=C_PANEL_ELEVATED, outline=C_LINE, width=1)

    chart_title = fa("نمودار فعالیت ۷ روز اخیر (شنبه تا جمعه)")
    draw.text((x2 - 16 - draw.textlength(chart_title, font=fonts["tag"]), y1 + 12), chart_title, font=fonts["tag"], fill=C_MUTED)
    draw.text((x1 + 16, y1 + 12), "// ACTIVITY METRICS", font=fonts["mono"], fill=C_FAINT)

    days_labels = ["ش", "ی", "د", "س", "چ", "پ", "ج"]
    chart_h = y2 - y1 - 60
    col_w = (x2 - x1 - 32) // 7
    max_count = max(activity_counts + [4])

    for i, (day_lbl, count) in enumerate(zip(days_labels, activity_counts)):
        bx = x1 + 16 + i * col_w + 8
        bw = col_w - 16
        is_today = (i == today_index)
        bar_fill = C_FLAME if is_today else (C_SUCCESS if count > 0 else (36, 40, 52))

        # Vertical Track
        track_y1 = y1 + 42
        track_y2 = y2 - 28
        draw.rounded_rectangle((bx, track_y1, bx + bw, track_y2), radius=6, fill=(16, 18, 24))

        # Filled bar from bottom
        bar_h = int((count / max_count) * (chart_h - 10))
        if bar_h > 0 or count > 0:
            actual_h = max(bar_h, 8)
            by1 = track_y2 - actual_h
            draw.rounded_rectangle((bx, by1, bx + bw, track_y2), radius=6, fill=bar_fill)

        # Count on top if > 0
        if count > 0:
            cnt_str = str(count)
            cw = draw.textlength(cnt_str, font=fonts["tag"])
            draw.text((bx + (bw - cw) // 2, track_y2 - max(bar_h, 8) - 16), cnt_str, font=fonts["tag"], fill=C_TEXT)

        # Day label at bottom
        dl_fa = fa(day_lbl)
        dw = draw.textlength(dl_fa, font=fonts["mono"])
        col_lbl = C_FLAME if is_today else (C_TEXT_SOFT if count > 0 else C_FAINT)
        draw.text((bx + (bw - dw) // 2, y2 - 22), dl_fa, font=fonts["mono"], fill=col_lbl)


# ---------------------------------------------------------------------------
# 1. Progress & Activity Card (کارنامه تحصیلی، استریک و نمودار فعالیت)
# ---------------------------------------------------------------------------
def render_progress_card(db: Session, user: Optional[models.User]) -> Tuple[str, str, Dict[str, Any]]:
    width, height = 960, 560
    img = Image.new("RGB", (width, height), color=C_BG)
    draw = ImageDraw.Draw(img)
    fonts = _get_fonts()

    u_name = user.username if user else "دانش‌آموز"
    _draw_mobile_header(
        draw,
        title=f"کارنامه تحصیلی و نمودار استریک ({u_name})",
        mono_label="// MY STREAK & ACTIVITY CHART",
        user=user,
        width=width,
    )

    # Data queries
    total_assignments = db.query(models.Assignment).filter(
        models.Assignment.deleted_at.is_(None),
        models.Assignment.is_reminder_only.is_(False),
    ).count()

    completed_count = 0
    streak = 0
    activity_counts = [0] * 7

    if user:
        completed_count = db.query(models.AssignmentCompletion).filter(
            models.AssignmentCompletion.user_id == user.id
        ).count()
        stats = compute_user_stats(db, user.id)
        if stats:
            streak = int(stats.get("current_streak", 0))

        # Query weekly activity counts for the 7 days (Saturday to Friday)
        now_iran = school_knowledge.get_iran_now()
        cur_py_wday = now_iran.weekday()
        # Saturday is index 0 in Iran week
        cur_iran_wday = (cur_py_wday + 2) % 7
        sat_date = now_iran.date() - timedelta(days=cur_iran_wday)

        for d_idx in range(7):
            day_target = sat_date + timedelta(days=d_idx)
            act_row = db.query(models.DailyActivity).filter(
                models.DailyActivity.user_id == user.id,
                models.DailyActivity.activity_date == day_target,
            ).first()
            if act_row and act_row.completions:
                activity_counts[d_idx] = act_row.completions
    else:
        now_iran = school_knowledge.get_iran_now()
        cur_iran_wday = (now_iran.weekday() + 2) % 7

    pct = round((completed_count / total_assignments * 100), 1) if total_assignments > 0 else 100.0
    pending_count = max(0, total_assignments - completed_count)

    # --- LEFT SIDE: Streak Hero Panel ---
    hero_box = (32, 134, 460, 526)
    _draw_panel(draw, hero_box, radius=18, fill=C_PANEL, outline=C_LINE, corners=True, corner_tone=C_CORNERS)

    # Procedural Vector Flame (NO tofu emojis)
    _draw_vector_flame(draw, cx=104, cy=208, size=32)

    # Hero Mono Label
    draw.text((164, 154), "// MY STREAK", font=fonts["mono"], fill=C_FAINT)
    # Status Badge
    draw.rounded_rectangle((hero_box[2] - 130, 148, hero_box[2] - 20, 176), radius=10, fill=C_SUCCESS_BG, outline=C_SUCCESS, width=1)
    tag_fa = fa("ثبت فعال [OK]")
    draw.text((hero_box[2] - 120, 153), tag_fa, font=fonts["tag"], fill=C_SUCCESS)

    # Big Streak Number + "روز متوالی"
    streak_s = str(streak)
    draw.text((164, 178), streak_s, font=fonts["hero_num"], fill=C_FLAME)
    num_w = draw.textlength(streak_s, font=fonts["hero_num"])
    lbl_fa = fa("روز متوالی")
    draw.text((164 + int(num_w) + 14, 212), lbl_fa, font=fonts["body_bold"], fill=C_TEXT_SOFT)

    # Subtitle
    sub_txt = "استریکت را حفظ کردی — همین‌طور پرقدرت ادامه بده" if streak > 0 else "امروز می‌تواند شروع یک استریک آتشین جدید باشد"
    sub_fa = fa(sub_txt)
    draw.text((hero_box[2] - 24 - draw.textlength(sub_fa, font=fonts["small"]), 270), sub_fa, font=fonts["small"], fill=C_MUTED)

    # Inner Progress Bar
    draw.text((hero_box[2] - 24 - draw.textlength(fa("نرخ تکمیل کل تکالیف"), font=fonts["tag"]), 310), fa("نرخ تکمیل کل تکالیف"), font=fonts["tag"], fill=C_FAINT)
    pct_str = f"{pct}%"
    pct_col = C_SUCCESS if pct >= 75 else (C_GOLD if pct >= 50 else C_DANGER)
    draw.text((54, 306), pct_str, font=fonts["stat_val_sm"], fill=pct_col)
    _draw_progress_bar(draw, 54, 340, hero_box[2] - hero_box[0] - 44, 12, pct, pct_col)

    # 7-Day Activity Bar Chart inside Hero Bottom
    chart_box = (50, 372, hero_box[2] - 20, 508)
    _draw_weekly_activity_bars(draw, chart_box, activity_counts, cur_iran_wday, fonts)

    # --- RIGHT SIDE: 3 Clean Summary Stat Cards ---
    stat_cards = [
        ("// COMPLETED", str(completed_count), "تکالیف تحویل داده شده", "انجام‌شده و تیک‌خورده در اپلیکیشن", C_SUCCESS, C_SUCCESS_BG),
        ("// PENDING", str(pending_count), "تکالیف در انتظار انجام", "نیاز به بررسی و تحویل قبل از موعد", C_GOLD if pending_count else C_MUTED, C_GOLD_BG if pending_count else C_PANEL),
        ("// TOTAL TASKS", str(total_assignments), "کل تکالیف ثبت‌شده", "تکالیف ترم جاری برای این کلاس", C_SKY, C_SKY_BG),
    ]

    card_h = 118
    for idx, (m_lbl, val, title_fa, hint_fa, tone_col, tone_bg) in enumerate(stat_cards):
        sy = 134 + idx * (card_h + 16)
        c_box = (484, sy, width - 32, sy + card_h)
        _draw_panel(draw, c_box, radius=16, fill=C_PANEL, outline=C_LINE, corners=True, corner_tone=C_CORNERS)

        # Mono Label
        draw.text((504, sy + 16), m_lbl, font=fonts["mono"], fill=C_FAINT)
        # Big Stat Value on Left
        draw.text((504, sy + 44), val, font=fonts["stat_val"], fill=tone_col)

        # Persian Title & Hint on Right
        t_fa = fa(title_fa)
        draw.text((c_box[2] - 24 - draw.textlength(t_fa, font=fonts["body_bold"]), sy + 28), t_fa, font=fonts["body_bold"], fill=C_TEXT)

        h_fa = fa(hint_fa)
        draw.text((c_box[2] - 24 - draw.textlength(h_fa, font=fonts["tag"]), sy + 64), h_fa, font=fonts["tag"], fill=C_MUTED)

    out_file = str(CACHE_DIR / f"card_progress_{user.id if user else 0}.png")
    img.save(out_file, "PNG", optimize=True)
    summary_data = {
        "user": u_name,
        "completion_percentage": pct,
        "current_streak": streak,
        "completed": completed_count,
        "pending": pending_count,
        "total": total_assignments,
        "weekly_activity": activity_counts,
    }
    return out_file, f"کارنامه و نمودار پیشرفت ({u_name})", summary_data


# ---------------------------------------------------------------------------
# 2. Leaderboard Podium Card (سکوی قهرمانی و رتبه‌بندی کلاس)
# ---------------------------------------------------------------------------
def render_leaderboard_card(db: Session) -> Tuple[str, str, Dict[str, Any]]:
    width, height = 960, 560
    img = Image.new("RGB", (width, height), color=C_BG)
    draw = ImageDraw.Draw(img)
    fonts = _get_fonts()

    _draw_mobile_header(
        draw,
        title="سکوی برترین‌های لیدربورد کلاس",
        mono_label="// BI-WEEKLY LEADERBOARD",
        user=None,
        width=width,
    )

    from .telegram_bot import build_leaderboard
    entries, _ = build_leaderboard(db)

    # Top Reset Countdown Banner
    banner_box = (32, 126, width - 32, 174)
    _draw_panel(draw, banner_box, radius=12, fill=C_PANEL, outline=C_LINE, corners=False)
    draw.text((48, 142), "// BI-WEEKLY RESET", font=fonts["mono"], fill=C_FLAME)
    draw.text((width // 2 - 80, 140), fa("ریست دوره‌ای امتیازات:"), font=fonts["tag"], fill=C_MUTED)
    draw.text((width // 2 + 60, 138), "08d : 14h : 22m", font=fonts["mono"], fill=C_TEXT)
    draw.text((width - 240, 140), fa("سیزن رقابت دوهفته‌ای"), font=fonts["tag"], fill=C_GOLD)

    # Podium Ranks Config (1st, 2nd, 3rd)
    podium_configs = [
        {"rank": 1, "label": "رتبه اول کلاس", "col": C_GOLD, "bg": C_GOLD_BG, "x": 352, "w": 256, "h": 224},
        {"rank": 2, "label": "رتبه دوم کلاس", "col": C_SILVER, "bg": C_SILVER_BG, "x": 32, "w": 296, "h": 208},
        {"rank": 3, "label": "رتبه سوم کلاس", "col": C_BRONZE, "bg": C_BRONZE_BG, "x": 632, "w": 296, "h": 208},
    ]

    for p in podium_configs:
        idx = p["rank"] - 1
        px, pw, ph = p["x"], p["w"], p["h"]
        py = 192 if p["rank"] == 1 else 208
        p_box = (px, py, px + pw, py + ph)
        border_col = p["col"] if p["rank"] == 1 else C_LINE
        _draw_panel(draw, p_box, radius=16, fill=C_PANEL, outline=border_col, corners=True, corner_tone=p["col"])

        # Medallion Icon on top
        _draw_medal_badge(draw, px + pw // 2, py + 34, p["rank"], p["col"], p["bg"], fonts["badge"])

        # Medal Header Title
        m_fa = fa(p["label"])
        draw.text((px + pw // 2 - draw.textlength(m_fa, font=fonts["tag"]) // 2, py + 62), m_fa, font=fonts["tag"], fill=p["col"])

        if idx < len(entries):
            e = entries[idx]
            u_name = e["user"].username or "دانش‌آموز"
            pct = round(e.get("completion_percentage", 0), 1)
            streak = e.get("current_streak", 0)

            # Username
            u_fa = fa(u_name)
            draw.text((px + pw // 2 - draw.textlength(u_fa, font=fonts["title"]) // 2, py + 92), u_fa, font=fonts["title"], fill=C_TEXT)

            # Percentage & Progress Bar
            pct_s = f"{pct}%"
            draw.text((px + pw // 2 - draw.textlength(pct_s, font=fonts["stat_val_sm"]) // 2, py + 128), pct_s, font=fonts["stat_val_sm"], fill=p["col"])
            _draw_progress_bar(draw, px + 24, py + 162, pw - 48, 8, pct, p["col"])

            # Streak Text
            st_fa = fa(f"استریک: {streak} روز")
            draw.text((px + pw // 2 - draw.textlength(st_fa, font=fonts["tag"]) // 2, py + 180), st_fa, font=fonts["tag"], fill=C_MUTED)
        else:
            empty_fa = fa("جایگاه خالی در سیزن")
            draw.text((px + pw // 2 - draw.textlength(empty_fa, font=fonts["small"]) // 2, py + 110), empty_fa, font=fonts["small"], fill=C_FAINT)

    # Bottom Row: Ranks 4 to 6
    bot_box = (32, 440, width - 32, 526)
    _draw_panel(draw, bot_box, radius=14, fill=C_PANEL, outline=C_LINE, corners=True, corner_tone=C_CORNERS)
    draw.text((48, 452), "// OTHER RANKS", font=fonts["mono"], fill=C_FAINT)

    if len(entries) > 3:
        step_w = (width - 96) // 3
        for j, e in enumerate(entries[3:6]):
            rx = 48 + j * step_w
            u_str = e["user"].username
            pct_num = round(e.get("completion_percentage", 0))
            st_num = e.get("current_streak", 0)
            rk_str = fa(f"رتبه {j+4}: {u_str} ({pct_num}% - استریک: {st_num})")
            draw.text((rx, 480), rk_str, font=fonts["body"], fill=C_TEXT_SOFT)
    else:
        inf_fa = fa("سایر دانش‌آموزان به زودی با تکمیل تکالیف به جدول لیدربورد اضافه می‌شوند")
        draw.text((width // 2 - draw.textlength(inf_fa, font=fonts["small"]) // 2, 474), inf_fa, font=fonts["small"], fill=C_MUTED)

    out_file = str(CACHE_DIR / "card_leaderboard.png")
    img.save(out_file, "PNG", optimize=True)
    summary_data = {
        "top1": entries[0]["user"].username if len(entries) > 0 else "هیچ‌کس",
        "top1_pct": round(entries[0].get("completion_percentage", 0), 1) if len(entries) > 0 else 0,
        "total_ranked": len(entries),
    }
    return out_file, "جدول لیدربورد کلاس", summary_data


# ---------------------------------------------------------------------------
# 3. Weekly Schedule Card (برنامه درسی و زنگ‌های مدرسه)
# ---------------------------------------------------------------------------
def render_schedule_card(db: Session, target_day: Optional[str] = None) -> Tuple[str, str, Dict[str, Any]]:
    width, height = 960, 550
    img = Image.new("RGB", (width, height), color=C_BG)
    draw = ImageDraw.Draw(img)
    fonts = _get_fonts()

    current_status = school_knowledge.get_current_school_status()
    if target_day and ("فردا" in target_day or any(k in target_day for k in ("شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنج‌شنبه", "جمعه"))):
        _, _, day_label, d_key = school_knowledge.resolve_target_day_bounds(target_day)
        day_sched = school_knowledge.WEEKLY_SCHEDULE.get(d_key, {})
        periods = day_sched.get("periods", [])
        day_name = day_label
        b_stat = "برنامه انتخابی روز"
    else:
        day_name = current_status.get("day_name", "امروز")
        sched = current_status.get("schedule", {})
        periods = sched.get("periods", [])
        b_stat = current_status.get("bell_status", "خارج از ساعات کلاسی")

    _draw_mobile_header(
        draw,
        title=f"برنامه درسی و زنگ‌های مدرسه ({day_name})",
        mono_label="// CLASS TIMETABLE",
        user=None,
        width=width,
    )

    # Active Bell Status Pill
    b_pill_box = (32, 126, width - 32, 172)
    _draw_panel(draw, b_pill_box, radius=12, fill=C_PANEL, outline=C_LINE, corners=False)
    draw.text((48, 140), "// CURRENT BELL", font=fonts["mono"], fill=C_FLAME)
    draw.text((width - 32 - draw.textlength(fa(f"وضعیت زنگ: {b_stat}"), font=fonts["small"]) - 16, 138), fa(f"وضعیت زنگ: {b_stat}"), font=fonts["small"], fill=C_TEXT)

    if not periods:
        empty_box = (32, 190, width - 32, 516)
        _draw_panel(draw, empty_box, radius=16, fill=C_PANEL, outline=C_LINE, corners=True, corner_tone=C_CORNERS)
        no_fa = fa(f"برای {day_name} کلاسی برگزار نمی‌شود و تعطیل است")
        draw.text((width // 2 - draw.textlength(no_fa, font=fonts["title"]) // 2, 310), no_fa, font=fonts["title"], fill=C_SKY)
        sub_fa = fa("فرصت عالی برای جبران تکالیف عقب‌افتاده و استراحت!")
        draw.text((width // 2 - draw.textlength(sub_fa, font=fonts["small"]) // 2, 350), sub_fa, font=fonts["small"], fill=C_MUTED)
    else:
        card_w = (width - 64 - (len(periods) - 1) * 16) // len(periods)
        for idx, p in enumerate(periods):
            px = 32 + idx * (card_w + 16)
            is_active = (idx + 1) == current_status.get("active_period") if not target_day else False
            border_c = C_GOLD if is_active else C_LINE
            p_box = (px, 190, px + card_w, 516)
            _draw_panel(draw, p_box, radius=16, fill=C_PANEL, outline=border_c, corners=True, corner_tone=border_c)

            # Period tag
            p_lbl = fa(f"زنگ {idx+1}")
            p_col = C_GOLD if is_active else C_TEXT_SOFT
            draw.text((px + card_w // 2 - draw.textlength(p_lbl, font=fonts["body_bold"]) // 2, 212), p_lbl, font=fonts["body_bold"], fill=p_col)

            # Time tag
            time_str = f"{p.get('start', '')} - {p.get('end', '')}"
            draw.text((px + card_w // 2 - draw.textlength(time_str, font=fonts["mono"]) // 2, 246), time_str, font=fonts["mono"], fill=C_FAINT)

            # Subject Badge placeholder
            draw.rounded_rectangle((px + card_w // 2 - 28, 280, px + card_w // 2 + 28, 328), radius=12, fill=C_PANEL_ELEVATED, outline=C_LINE, width=1)
            b_txt = f"P{idx+1}"
            draw.text((px + card_w // 2 - draw.textlength(b_txt, font=fonts["badge"]) // 2, 296), b_txt, font=fonts["badge"], fill=C_GOLD if is_active else C_SKY)

            # Subject Name
            s_name = fa(p.get("subject_name", ""))
            draw.text((px + card_w // 2 - draw.textlength(s_name, font=fonts["title"]) // 2, 348), s_name, font=fonts["title"], fill=C_TEXT)

            # Teacher Name
            t_name = fa(f"استاد {p.get('teacher', '')}")
            draw.text((px + card_w // 2 - draw.textlength(t_name, font=fonts["small"]) // 2, 394), t_name, font=fonts["small"], fill=C_SKY)

            # Status pill
            if is_active:
                act_fa = fa("[زنگ جاری]")
                draw.rounded_rectangle((px + 20, 444, px + card_w - 20, 484), radius=10, fill=C_GOLD_BG, outline=C_GOLD, width=1)
                draw.text((px + card_w // 2 - draw.textlength(act_fa, font=fonts["badge"]) // 2, 454), act_fa, font=fonts["badge"], fill=C_GOLD)
            else:
                ok_fa = fa("ساعات تحصیلی")
                draw.text((px + card_w // 2 - draw.textlength(ok_fa, font=fonts["tag"]) // 2, 458), ok_fa, font=fonts["tag"], fill=C_FAINT)

    out_file = str(CACHE_DIR / "card_schedule.png")
    img.save(out_file, "PNG", optimize=True)
    summary_data = {
        "day": day_name,
        "bell_status": b_stat,
        "period_count": len(periods),
    }
    return out_file, f"برنامه درسی ({day_name})", summary_data


# ---------------------------------------------------------------------------
# 4. Active Assignments Card (کارت تکالیف فعال و اولویت‌دار)
# ---------------------------------------------------------------------------
def render_assignments_card(
    db: Session,
    user: Optional[models.User] = None,
    target_day: Optional[str] = None,
) -> Tuple[str, str, Dict[str, Any]]:
    width, height = 960, 550
    img = Image.new("RGB", (width, height), color=C_BG)
    draw = ImageDraw.Draw(img)
    fonts = _get_fonts()

    now = datetime.utcnow()

    if target_day:
        start_utc, end_utc, day_label, day_key = school_knowledge.resolve_target_day_bounds(target_day)
        card_title = f"تکالیف {day_label}"
        mono_label = f"// ASSIGNMENTS: {day_key.upper()}"
        summary_pill_text = f"تکالیف {day_label}"

        day_sched = school_knowledge.WEEKLY_SCHEDULE.get(day_key, {})
        day_subjs = [p["subject_id"] for p in day_sched.get("periods", []) if p.get("subject_id")]

        tasks = (
            db.query(models.Assignment)
            .filter(
                models.Assignment.deleted_at.is_(None),
                models.Assignment.is_reminder_only.is_(False),
                or_(
                    and_(
                        models.Assignment.due_date.isnot(None),
                        models.Assignment.due_date >= start_utc,
                        models.Assignment.due_date <= end_utc,
                    ),
                    and_(
                        models.Assignment.due_date.is_(None),
                        or_(
                            models.Assignment.subject_id.in_(day_subjs),
                            models.Assignment.course.in_(day_subjs),
                        ),
                    ),
                ),
            )
            .order_by(models.Assignment.due_date.asc().nulls_last())
            .limit(4)
            .all()
        )
    else:
        card_title = "تکالیف فعال و دارای مهلت تحویل"
        mono_label = "// ACTIVE ASSIGNMENTS"
        day_label = "روزهای جاری"
        summary_pill_text = "تکالیف اولویت‌دار کلاسی"

        all_candidates = (
            db.query(models.Assignment)
            .filter(
                models.Assignment.deleted_at.is_(None),
                models.Assignment.is_reminder_only.is_(False),
            )
            .order_by(models.Assignment.due_date.asc().nulls_last())
            .all()
        )
        # Strictly exclude overdue tasks from active list
        tasks = [
            t for t in all_candidates
            if not school_knowledge.is_assignment_overdue(t.due_date, t.subject_id)
        ][:4]

    _draw_mobile_header(
        draw,
        title=card_title,
        mono_label=mono_label,
        user=user,
        width=width,
    )

    # Top summary pill
    t_box = (32, 126, width - 32, 168)
    _draw_panel(draw, t_box, radius=12, fill=C_PANEL, outline=C_LINE, corners=False)
    draw.text((48, 138), "// QUEUE STATUS", font=fonts["mono"], fill=C_FLAME)
    draw.text((width - 32 - draw.textlength(fa(f"تعداد {len(tasks)} {summary_pill_text}"), font=fonts["small"]) - 16, 136), fa(f"تعداد {len(tasks)} {summary_pill_text}"), font=fonts["small"], fill=C_TEXT)

    if not tasks:
        empty_box = (32, 184, width - 32, 516)
        _draw_panel(draw, empty_box, radius=16, fill=C_PANEL, outline=C_LINE, corners=True, corner_tone=C_CORNERS)
        no_fa = fa(f"برای {day_label} هیچ تکلیفی ثبت نشده است")
        draw.text((width // 2 - draw.textlength(no_fa, font=fonts["title"]) // 2, 320), no_fa, font=fonts["title"], fill=C_SUCCESS)
        sub_fa = fa("تمامی موارد انجام شده یا تکلیفی برای این موعد در سیستم وجود ندارد.")
        draw.text((width // 2 - draw.textlength(sub_fa, font=fonts["small"]) // 2, 360), sub_fa, font=fonts["small"], fill=C_MUTED)
    else:
        row_h = 76
        for idx, t in enumerate(tasks):
            ty = 184 + idx * (row_h + 10)
            row_box = (32, ty, width - 32, ty + row_h)
            _draw_panel(draw, row_box, radius=14, fill=C_PANEL, outline=C_LINE, corners=True, corner_tone=C_CORNERS)

            # Checkbox circle on right
            cb_x = width - 68
            cb_y = ty + row_h // 2
            draw.ellipse((cb_x - 12, cb_y - 12, cb_x + 12, cb_y + 12), fill=C_PANEL_ELEVATED, outline=C_LINE_STRONG, width=1)

            # Subject Pill on Right
            subj_title = t.course or t.subject_id or "عمومی"
            s_fa = fa(subj_title)
            s_w = draw.textlength(s_fa, font=fonts["tag"])
            pill_w = max(int(s_w) + 24, 70)
            pill_x1 = cb_x - 24 - pill_w
            pill_x2 = cb_x - 24
            draw.rounded_rectangle((pill_x1, ty + 22, pill_x2, ty + 54), radius=8, fill=C_SKY_BG, outline=C_SKY, width=1)
            draw.text((pill_x1 + (pill_w - s_w) // 2, ty + 28), s_fa, font=fonts["tag"], fill=C_SKY)

            # Due Date / Status chip on Left
            if t.due_date:
                hours_left = (t.due_date - now).total_seconds() / 3600.0
                if school_knowledge.is_assignment_overdue(t.due_date, t.subject_id):
                    time_lbl = fa("[منقضی شده]")
                    t_col = C_DANGER
                elif hours_left <= 6:
                    time_lbl = fa(f"[فوری: {int(max(1, hours_left))} ساعت]")
                    t_col = C_DANGER
                elif hours_left <= 24:
                    time_lbl = fa("[کمتر از ۱ روز]")
                    t_col = C_GOLD
                else:
                    time_lbl = fa(f"[{int(hours_left // 24)} روز دیگر]")
                    t_col = C_SUCCESS
            else:
                time_lbl = fa("[بدون ددلاین]")
                t_col = C_MUTED

            draw.text((54, ty + 28), time_lbl, font=fonts["small"], fill=t_col)
            time_w = draw.textlength(time_lbl, font=fonts["small"])

            # Safely truncate assignment title so it NEVER overlaps with due badge or subject pill
            max_title_w = pill_x1 - 54 - int(time_w) - 40
            safe_title = _truncate_text(draw, t.title, fonts["body_bold"], max_title_w)
            t_fa = fa(safe_title)
            draw.text((pill_x1 - 20 - draw.textlength(t_fa, font=fonts["body_bold"]), ty + 26), t_fa, font=fonts["body_bold"], fill=C_TEXT)

    cache_key = f"card_assignments_{target_day or 'default'}.png".replace(" ", "_")
    out_file = str(CACHE_DIR / cache_key)
    img.save(out_file, "PNG", optimize=True)
    summary_data = {
        "active_count": len(tasks),
        "target_day": day_label,
        "nearest_task": tasks[0].title if tasks else "بدون تکلیف",
    }
    return out_file, f"{card_title}", summary_data


# ---------------------------------------------------------------------------
# Master Dispatcher
# ---------------------------------------------------------------------------
def generate_card(
    db: Session,
    card_type: str,
    user: Optional[models.User] = None,
    subject: Optional[str] = None,
    target_day: Optional[str] = None,
) -> Tuple[str, str, Dict[str, Any]]:
    """Generates the requested visual card and returns (file_path, card_title, data_summary)."""
    ctype = (card_type or "progress").lower().strip()
    if ctype in ("leaderboard", "ranks", "لیدربورد", "رتبه", "سکوی"):
        return render_leaderboard_card(db)
    elif ctype in ("schedule", "timetable", "برنامه", "زنگ"):
        return render_schedule_card(db, target_day=target_day)
    elif ctype in ("assignments", "tasks", "مشق", "تکالیف"):
        return render_assignments_card(db, user, target_day=target_day)
    else:
        # progress / chart / default
        return render_progress_card(db, user)

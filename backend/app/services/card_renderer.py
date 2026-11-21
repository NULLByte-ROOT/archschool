"""ArchSchool Visual Card & Chart Renderer.

Generates sleek, dark-themed visual cards (matching ArchSchool mobile app aesthetic)
for progress charts, leaderboard podium, active assignments, and weekly schedule.
These cards are sent by the Telegram AI Bot to users/groups with interactive refresh buttons.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import arabic_reshaper
from bidi.algorithm import get_display
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import or_, select
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

# Palette matching ArchSchool App Theme
C_BG = (11, 15, 23)           # #0B0F17 deep space background
C_CARD = (18, 24, 38)         # #121826 sleek card surface
C_CARD_HOVER = (26, 34, 52)   # #1A2234
C_BORDER = (35, 45, 66)       # #232D42 subtle border
C_BORDER_LIGHT = (55, 68, 98) # #374462
C_TEXT_WHITE = (248, 250, 252)# #F8FAFC
C_TEXT_MUTED = (148, 163, 184)# #94A3B8
C_TEXT_FAINT = (100, 116, 139)# #64748B
C_AMBER = (245, 158, 11)      # #F59E0B primary accent
C_EMERALD = (16, 185, 129)    # #10B981 success / completed
C_ROSE = (244, 63, 94)        # #F43F5E urgent / missing
C_SKY = (56, 189, 248)        # #38BDF8 info / course
C_PURPLE = (168, 85, 247)     # #A855F7 bonus / streak


def fa(text: str) -> str:
    """Reshape and reorder Persian/Arabic text for correct RTL Pillow rendering."""
    if not text:
        return ""
    try:
        reshaped = arabic_reshaper.reshape(str(text))
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
        "title": _load_font(FONT_BOLD_PATH, 24),
        "subtitle": _load_font(FONT_MEDIUM_PATH, 16),
        "stat_val": _load_font(FONT_BOLD_PATH, 36),
        "stat_val_sm": _load_font(FONT_BOLD_PATH, 26),
        "stat_lbl": _load_font(FONT_MEDIUM_PATH, 14),
        "body": _load_font(FONT_MEDIUM_PATH, 15),
        "body_bold": _load_font(FONT_BOLD_PATH, 16),
        "badge": _load_font(FONT_BOLD_PATH, 13),
        "tag": _load_font(FONT_MEDIUM_PATH, 12),
        "small": _load_font(FONT_MEDIUM_PATH, 13),
    }


def _draw_header(draw: ImageDraw.ImageDraw, title: str, subtitle: str, width: int) -> None:
    fonts = _get_fonts()
    # ArchSchool pill logo
    draw.rounded_rectangle((32, 28, 180, 56), radius=14, fill=(245, 158, 11, 35), outline=C_AMBER, width=1)
    tag_str = fa("ARCHSCHOOL · سامانه")
    draw.text((44, 34), tag_str, font=fonts["badge"], fill=C_AMBER)

    # Date / Live Stamp on top right
    now_fa = school_knowledge.format_iran_datetime(datetime.utcnow())
    date_str = fa(f"به‌روزرسانی: {now_fa}")
    draw.text((width - 32 - draw.textlength(date_str, font=fonts["tag"]), 35), date_str, font=fonts["tag"], fill=C_TEXT_FAINT)

    # Main Title & Subtitle
    title_str = fa(title)
    draw.text((width - 32 - draw.textlength(title_str, font=fonts["title"]), 68), title_str, font=fonts["title"], fill=C_TEXT_WHITE)

    sub_str = fa(subtitle)
    draw.text((width - 32 - draw.textlength(sub_str, font=fonts["subtitle"]), 104), sub_str, font=fonts["subtitle"], fill=C_TEXT_MUTED)

    # Divider
    draw.line((32, 132, width - 32, 132), fill=C_BORDER, width=1)


# ---------------------------------------------------------------------------
# 1. Progress Card (کارنامه و نمودار پیشرفت تحصیلی دانش‌آموز)
# ---------------------------------------------------------------------------
def render_progress_card(db: Session, user: Optional[models.User]) -> str:
    width, height = 860, 480
    img = Image.new("RGB", (width, height), color=C_BG)
    draw = ImageDraw.Draw(img)
    fonts = _get_fonts()

    u_name = user.username if user else "دانش‌آموز"
    _draw_header(
        draw,
        title=f"کارنامه تحصیلی و وضعیت پیشرفت ({u_name})",
        subtitle="بررسی لحظه‌ای تکالیف انجام‌شده، نرخ تکمیل و استریک کلاسی",
        width=width,
    )

    # Gather data
    total_assignments = db.query(models.Assignment).filter(
        models.Assignment.deleted_at.is_(None),
        models.Assignment.is_reminder_only.is_(False),
    ).count()

    completed_count = 0
    streak = 0
    if user:
        completed_count = db.query(models.AssignmentCompletion).filter(
            models.AssignmentCompletion.user_id == user.id
        ).count()
        stats = compute_user_stats(db, user.id)
        if stats:
            streak = int(stats.get("current_streak", 0))

    pct = round((completed_count / total_assignments * 100), 1) if total_assignments > 0 else 100.0
    pending_count = max(0, total_assignments - completed_count)

    # Big Progress Card on Left/Center
    draw.rounded_rectangle((32, 152, 420, 436), radius=20, fill=C_CARD, outline=C_BORDER, width=1)

    pct_title = fa("نرخ تکمیل کل تکالیف")
    draw.text((226 - draw.textlength(pct_title, font=fonts["body_bold"]) // 2, 174), pct_title, font=fonts["body_bold"], fill=C_TEXT_WHITE)

    pct_num = f"{pct}%"
    pct_color = C_EMERALD if pct >= 75 else (C_AMBER if pct >= 50 else C_ROSE)
    draw.text((226 - draw.textlength(pct_num, font=fonts["stat_val"]) // 2, 210), pct_num, font=fonts["stat_val"], fill=pct_color)

    # Progress bar
    bar_x, bar_y, bar_w, bar_h = 60, 276, 332, 22
    draw.rounded_rectangle((bar_x, bar_y, bar_x + bar_w, bar_y + bar_h), radius=11, fill=(26, 34, 52))
    fill_w = int(bar_w * (min(100.0, max(0.0, pct)) / 100.0))
    if fill_w > 12:
        draw.rounded_rectangle((bar_x, bar_y, bar_x + fill_w, bar_y + bar_h), radius=11, fill=pct_color)

    # Status assessment
    if pct >= 85:
        tone_msg = fa("وضعیت: عالی و پیشتاز کلاس 🌟")
        tone_c = C_EMERALD
    elif pct >= 60:
        tone_msg = fa("وضعیت: خوب و منظم در تحویل تکالیف 👍")
        tone_c = C_SKY
    else:
        tone_msg = fa("وضعیت: نیازمند پیگیری و جبران تکالیف ⚠️")
        tone_c = C_ROSE
    draw.text((226 - draw.textlength(tone_msg, font=fonts["small"]) // 2, 320), tone_msg, font=fonts["small"], fill=tone_c)

    # Streak badge
    streak_badge = fa(f"🔥 استریک آتشین: {streak} روز مداوم")
    draw.rounded_rectangle((70, 364, 382, 408), radius=12, fill=(245, 158, 11, 25), outline=C_AMBER, width=1)
    draw.text((226 - draw.textlength(streak_badge, font=fonts["badge"]) // 2, 376), streak_badge, font=fonts["badge"], fill=C_AMBER)

    # 3 Stat Cards on Right Side
    stats = [
        ("تکالیف تحویل داده شده", f"{completed_count}", C_EMERALD, "انجام شده و تیک‌خورده ✅"),
        ("تکالیف در انتظار انجام", f"{pending_count}", C_AMBER if pending_count else C_TEXT_MUTED, "باقی‌مانده در سامانه ⏳"),
        ("کل تکالیف ترم جاری", f"{total_assignments}", C_SKY, "ثبت‌شده برای کلاس 📚"),
    ]

    for idx, (lbl, val, col, sub) in enumerate(stats):
        sy = 152 + idx * 98
        draw.rounded_rectangle((440, sy, width - 32, sy + 84), radius=18, fill=C_CARD, outline=C_BORDER, width=1)
        # Value
        draw.text((464, sy + 18), val, font=fonts["stat_val_sm"], fill=col)
        # Label
        lbl_fa = fa(lbl)
        draw.text((width - 56 - draw.textlength(lbl_fa, font=fonts["body_bold"]), sy + 18), lbl_fa, font=fonts["body_bold"], fill=C_TEXT_WHITE)
        # Sub
        sub_fa = fa(sub)
        draw.text((width - 56 - draw.textlength(sub_fa, font=fonts["tag"]), sy + 48), sub_fa, font=fonts["tag"], fill=C_TEXT_MUTED)

    out_file = str(CACHE_DIR / f"card_progress_{user.id if user else 0}.png")
    img.save(out_file, "PNG", optimize=True)
    return out_file


# ---------------------------------------------------------------------------
# 2. Leaderboard Podium Card (جدول سکوی قهرمانی و رتبه‌بندی کلاس)
# ---------------------------------------------------------------------------
def render_leaderboard_card(db: Session) -> str:
    width, height = 860, 520
    img = Image.new("RGB", (width, height), color=C_BG)
    draw = ImageDraw.Draw(img)
    fonts = _get_fonts()

    _draw_header(
        draw,
        title="سکوی برترین‌های لیدربورد کلاس",
        subtitle="رقابت دوهفته‌ای دانش‌آموزان بر اساس درصد موفقیت و استریک",
        width=width,
    )

    from .telegram_bot import build_leaderboard
    entries, _ = build_leaderboard(db)

    podium_colors = [
        (250, 204, 21),  # Gold #FACC15
        (226, 232, 240),  # Silver #E2E8F0
        (249, 115, 22),   # Bronze #F97316
    ]
    podium_labels = ["🥇 رتبه اول", "🥈 رتبه دوم", "🥉 رتبه سوم"]

    # Top 3 Podium Cards
    for idx in range(3):
        col = podium_colors[idx]
        px = 32 + idx * 266
        draw.rounded_rectangle((px, 152, px + 250, 360), radius=20, fill=C_CARD, outline=col if idx == 0 else C_BORDER, width=2 if idx == 0 else 1)

        # Crown / Medal header
        med_fa = fa(podium_labels[idx])
        draw.text((px + 125 - draw.textlength(med_fa, font=fonts["badge"]) // 2, 172), med_fa, font=fonts["badge"], fill=col)

        if idx < len(entries):
            e = entries[idx]
            u_name = e["user"].username
            pct = round(e.get("completion_percentage", 0), 1)
            streak = e.get("current_streak", 0)

            # Name
            u_fa = fa(u_name)
            draw.text((px + 125 - draw.textlength(u_fa, font=fonts["body_bold"]) // 2, 206), u_fa, font=fonts["body_bold"], fill=C_TEXT_WHITE)

            # Pct
            pct_s = f"{pct}%"
            draw.text((px + 125 - draw.textlength(pct_s, font=fonts["stat_val_sm"]) // 2, 242), pct_s, font=fonts["stat_val_sm"], fill=col)

            # Streak
            st_fa = fa(f"🔥 استریک: {streak} روز")
            draw.text((px + 125 - draw.textlength(st_fa, font=fonts["small"]) // 2, 290), st_fa, font=fonts["small"], fill=C_TEXT_MUTED)

            comp_s = fa(f"تکمیل: {e.get('completed_count', 0)} تکلیف")
            draw.text((px + 125 - draw.textlength(comp_s, font=fonts["tag"]) // 2, 320), comp_s, font=fonts["tag"], fill=C_TEXT_FAINT)
        else:
            empty_fa = fa("جایگاه خالی")
            draw.text((px + 125 - draw.textlength(empty_fa, font=fonts["small"]) // 2, 240), empty_fa, font=fonts["small"], fill=C_TEXT_FAINT)

    # Ranks 4 to 6 row at the bottom
    draw.rounded_rectangle((32, 380, width - 32, 484), radius=16, fill=C_CARD, outline=C_BORDER, width=1)
    if len(entries) > 3:
        for j, e in enumerate(entries[3:6]):
            rx = 54 + j * 260
            rk_str = fa(f"#{j+4} {e['user'].username} ({round(e.get('completion_percentage', 0))}% · 🔥{e.get('current_streak', 0)}d)")
            draw.text((rx, 420), rk_str, font=fonts["small"], fill=C_TEXT_MUTED)
    else:
        inf_fa = fa("سایر دانش‌آموزان به زودی با تکمیل تکالیف به جدول اضافه می‌شوند 🚀")
        draw.text((width // 2 - draw.textlength(inf_fa, font=fonts["small"]) // 2, 422), inf_fa, font=fonts["small"], fill=C_TEXT_FAINT)

    out_file = str(CACHE_DIR / "card_leaderboard.png")
    img.save(out_file, "PNG", optimize=True)
    return out_file


# ---------------------------------------------------------------------------
# 3. Weekly Schedule Card (چارت برنامه هفتگی و زنگ‌ها)
# ---------------------------------------------------------------------------
def render_schedule_card(db: Session, target_day: Optional[str] = None) -> str:
    width, height = 860, 520
    img = Image.new("RGB", (width, height), color=C_BG)
    draw = ImageDraw.Draw(img)
    fonts = _get_fonts()

    current_status = school_knowledge.get_current_school_status()
    day_name = current_status.get("day_name", "امروز")
    sched = current_status.get("schedule", {})
    periods = sched.get("periods", [])

    _draw_header(
        draw,
        title=f"برنامه درسی و زنگ‌های مدرسه ({day_name})",
        subtitle=f"زنگ جاری: {current_status.get('bell_status', 'خارج از ساعات مدرسه')}",
        width=width,
    )

    if not periods:
        # Weekend or holiday
        draw.rounded_rectangle((32, 160, width - 32, 460), radius=20, fill=C_CARD, outline=C_BORDER, width=1)
        msg_fa = fa("امروز کلاس درسی برگزار نمی‌شود و تعطیل است 🏖️")
        draw.text((width // 2 - draw.textlength(msg_fa, font=fonts["body_bold"]) // 2, 280), msg_fa, font=fonts["body_bold"], fill=C_SKY)
        sub_fa = fa("فرصت مناسب برای جبران تکالیف و استراحت!")
        draw.text((width // 2 - draw.textlength(sub_fa, font=fonts["small"]) // 2, 320), sub_fa, font=fonts["small"], fill=C_TEXT_MUTED)
    else:
        card_w = (width - 64 - (len(periods) - 1) * 20) // len(periods)
        for idx, p in enumerate(periods):
            px = 32 + idx * (card_w + 20)
            is_active = (idx + 1) == current_status.get("active_period")
            border_c = C_AMBER if is_active else C_BORDER

            draw.rounded_rectangle((px, 160, px + card_w, 460), radius=18, fill=C_CARD, outline=border_c, width=2 if is_active else 1)

            # Period tag
            p_lbl = fa(f"زنگ {idx+1}")
            p_col = C_AMBER if is_active else C_TEXT_MUTED
            draw.text((px + card_w // 2 - draw.textlength(p_lbl, font=fonts["badge"]) // 2, 185), p_lbl, font=fonts["badge"], fill=p_col)

            # Time tag
            time_str = f"{p.get('start', '')} - {p.get('end', '')}"
            draw.text((px + card_w // 2 - draw.textlength(time_str, font=fonts["tag"]) // 2, 215), time_str, font=fonts["tag"], fill=C_TEXT_FAINT)

            # Subject Name
            s_name = fa(p.get("subject_name", ""))
            draw.text((px + card_w // 2 - draw.textlength(s_name, font=fonts["body_bold"]) // 2, 270), s_name, font=fonts["body_bold"], fill=C_TEXT_WHITE)

            # Teacher
            t_name = fa(f"استاد {p.get('teacher', '')}")
            draw.text((px + card_w // 2 - draw.textlength(t_name, font=fonts["small"]) // 2, 310), t_name, font=fonts["small"], fill=C_SKY)

            # Active status badge
            if is_active:
                act_fa = fa("🔴 زنگ جاری")
                draw.rounded_rectangle((px + 20, 390, px + card_w - 20, 428), radius=10, fill=(245, 158, 11, 30), outline=C_AMBER, width=1)
                draw.text((px + card_w // 2 - draw.textlength(act_fa, font=fonts["badge"]) // 2, 400), act_fa, font=fonts["badge"], fill=C_AMBER)
            else:
                ok_fa = fa("ساعات تحصیلی")
                draw.text((px + card_w // 2 - draw.textlength(ok_fa, font=fonts["tag"]) // 2, 404), ok_fa, font=fonts["tag"], fill=C_TEXT_FAINT)

    out_file = str(CACHE_DIR / "card_schedule.png")
    img.save(out_file, "PNG", optimize=True)
    return out_file


# ---------------------------------------------------------------------------
# 4. Active Assignments Card (کارت تکالیف فعال و دارای مهلت)
# ---------------------------------------------------------------------------
def render_assignments_card(db: Session, user: Optional[models.User] = None) -> str:
    width, height = 860, 520
    img = Image.new("RGB", (width, height), color=C_BG)
    draw = ImageDraw.Draw(img)
    fonts = _get_fonts()

    _draw_header(
        draw,
        title="تکالیف فعال و جاری کلاس",
        subtitle="فهرست تکالیف تحویل نشده با ددلاین و سطح فوریت",
        width=width,
    )

    now = datetime.utcnow()
    tasks = (
        db.query(models.Assignment)
        .filter(
            models.Assignment.deleted_at.is_(None),
            or_(
                models.Assignment.due_date.is_(None),
                models.Assignment.due_date >= now,
            ),
        )
        .order_by(models.Assignment.due_date.asc().nulls_last())
        .limit(4)
        .all()
    )

    if not tasks:
        draw.rounded_rectangle((32, 160, width - 32, 460), radius=20, fill=C_CARD, outline=C_BORDER, width=1)
        no_fa = fa("در حال حاضر هیچ تکلیف فعالی با مهلت باز وجود ندارد 🎉")
        draw.text((width // 2 - draw.textlength(no_fa, font=fonts["body_bold"]) // 2, 290), no_fa, font=fonts["body_bold"], fill=C_EMERALD)
    else:
        for idx, t in enumerate(tasks):
            ty = 152 + idx * 78
            draw.rounded_rectangle((32, ty, width - 32, ty + 68), radius=14, fill=C_CARD, outline=C_BORDER, width=1)

            # Subject Pill
            subj_title = t.course or t.subject_id or "عمومی"
            s_fa = fa(subj_title)
            draw.rounded_rectangle((width - 170, ty + 18, width - 48, ty + 50), radius=8, fill=(56, 189, 248, 25), outline=C_SKY, width=1)
            draw.text((width - 109 - draw.textlength(s_fa, font=fonts["tag"]) // 2, ty + 24), s_fa, font=fonts["tag"], fill=C_SKY)

            # Title
            t_fa = fa(t.title)
            draw.text((width - 190 - draw.textlength(t_fa, font=fonts["body_bold"]), ty + 23), t_fa, font=fonts["body_bold"], fill=C_TEXT_WHITE)

            # Deadline / Relative time
            if t.due_date:
                hours_left = (t.due_date - now).total_seconds() / 3600.0
                if hours_left <= 6:
                    time_lbl = fa(f"🚨 فقط {int(max(1, hours_left))} ساعت مانده")
                    t_col = C_ROSE
                elif hours_left <= 24:
                    time_lbl = fa(f"⚠️ کمتر از ۱ روز مانده")
                    t_col = C_AMBER
                else:
                    time_lbl = fa(f"📅 مهلت: {int(hours_left // 24)} روز دیگر")
                    t_col = C_EMERALD
            else:
                time_lbl = fa("بدون ددلاین خاص")
                t_col = C_TEXT_MUTED

            draw.text((52, ty + 24), time_lbl, font=fonts["small"], fill=t_col)

    out_file = str(CACHE_DIR / "card_assignments.png")
    img.save(out_file, "PNG", optimize=True)
    return out_file


# ---------------------------------------------------------------------------
# Master Card Dispatcher
# ---------------------------------------------------------------------------
def generate_card(
    db: Session,
    card_type: str,
    user: Optional[models.User] = None,
    subject: Optional[str] = None,
) -> Tuple[str, str]:
    """Generates the requested visual card and returns (file_path, card_title)."""
    ctype = (card_type or "progress").lower().strip()
    if ctype in ("leaderboard", "ranks", "لیدربورد", "رتبه"):
        return render_leaderboard_card(db), "جدول لیدربورد کلاس 🏆"
    elif ctype in ("schedule", "timetable", "برنامه", "زنگ"):
        return render_schedule_card(db, subject), "برنامه هفتگی و زنگ‌ها 📚"
    elif ctype in ("assignments", "tasks", "مشق", "تکالیف"):
        return render_assignments_card(db, user), "لیست تکالیف فعال 📝"
    else:
        return render_progress_card(db, user), "کارنامه پیشرفت تحصیلی 📊"

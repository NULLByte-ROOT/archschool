import pytest
from datetime import datetime, timedelta
from app import models
from app.services import ai_agent, telegram_bot


def test_telegram_link_token_lifecycle(db_session):
    # 1. Create a dummy user
    user = models.User(
        username="test_student",
        code="TEST01",
        role=models.ROLE_MEMBER,
    )
    db_session.add(user)
    db_session.commit()

    # 2. Generate link token
    token = telegram_bot.generate_user_link_token(db_session, user)
    assert token.startswith("arch_")
    assert user.telegram_link_token == token
    assert user.telegram_id is None

    # 3. Link with telegram id
    tg_id = 987654321
    tg_user = "test_tg_user"
    linked = telegram_bot.link_telegram_user(db_session, tg_id, tg_user, token)
    assert linked is not None
    assert linked.id == user.id
    assert linked.telegram_id == tg_id
    assert linked.telegram_username == tg_user
    assert linked.telegram_link_token is None  # Used token is cleared

    # 4. Unlink
    telegram_bot.unlink_telegram_user(db_session, user)
    assert user.telegram_id is None
    assert user.telegram_username is None


def test_bot_settings(db_session):
    telegram_bot.set_bot_setting(db_session, "telegram_bot_token", "123456:ABC-DEF")
    telegram_bot.set_bot_setting(db_session, "ai_api_key", "sk-or-v1-TestKey")
    telegram_bot.set_bot_setting(db_session, "ai_provider", "openrouter")
    telegram_bot.set_bot_setting(db_session, "ai_base_url", "https://openrouter.ai/api/v1")
    telegram_bot.set_bot_setting(db_session, "ai_model", "x-ai/grok-2")
    telegram_bot.set_bot_setting(db_session, "telegram_group_id", "-100123456789")

    settings = telegram_bot.get_all_bot_settings(db_session)
    assert settings["bot_token"] == "123456:ABC-DEF"
    assert settings["ai_api_key"] == "sk-or-v1-TestKey"
    assert settings["ai_provider"] == "openrouter"
    assert settings["ai_base_url"] == "https://openrouter.ai/api/v1"
    assert settings["ai_model"] == "x-ai/grok-2"
    assert settings["group_id"] == "-100123456789"
    assert settings["has_token"] is True
    assert settings["has_ai"] is True

    # Test Groq defaults
    groq_base, groq_model = telegram_bot.get_provider_defaults("groq")
    assert groq_base == "https://api.groq.com/openai/v1"
    assert groq_model == "openai/gpt-oss-120b"

    # Test Gemini defaults
    gemini_base, gemini_model = telegram_bot.get_provider_defaults("gemini")
    assert gemini_base == "https://generativelanguage.googleapis.com/v1beta/openai/"
    assert gemini_model == "gemini-3.1-flash-lite"


def test_universal_ai_tools_execution(db_session):
    admin = models.User(
        username="admin_user",
        code="ADMIN01",
        is_admin=True,
        role=models.ROLE_ADMIN,
    )
    student = models.User(
        username="student_user",
        code="STUDENT01",
        role=models.ROLE_MEMBER,
    )
    db_session.add_all([admin, student])
    db_session.commit()

    # 1. Student cannot add assignment
    res = ai_agent.execute_tool(
        "add_assignment",
        {"title": "تمرین تستی", "due_date": "2026-12-01"},
        db_session,
        student,
    )
    assert res["success"] is False
    assert "عدم دسترسی" in res["error"]

    # 2. Admin can add assignment
    res_admin = ai_agent.execute_tool(
        "add_assignment",
        {"title": "تمرین مجاز ادمین", "due_date": "2026-12-01", "subject": "هندسه"},
        db_session,
        admin,
    )
    assert res_admin["success"] is True

    # 3. get_class_assignments (active only)
    assignments = ai_agent.execute_tool("get_class_assignments", {}, db_session, student)
    assert assignments["success"] is True
    assert len(assignments["assignments"]) >= 1

    # 3b. Add an expired assignment and verify it is filtered out
    ai_agent.execute_tool(
        "add_assignment",
        {"title": "تکلیف منقضی شده پارسال", "due_date": "2025-01-01", "subject": "تاریخ"},
        db_session,
        admin,
    )
    active_assignments = ai_agent.execute_tool("get_class_assignments", {}, db_session, student)
    titles = [a["title"] for a in active_assignments["assignments"]]
    assert "تکلیف منقضی شده پارسال" not in titles

    # 4. get_my_status
    status = ai_agent.execute_tool("get_my_status", {}, db_session, student)
    assert status["success"] is True
    assert status["username"] == "student_user"
    pending_titles = [p["title"] for p in status["pending_assignments"]]
    assert "تکلیف منقضی شده پارسال" not in pending_titles


def test_format_telegram_html():
    # 1. Bold with double asterisks
    raw = "**عنوان تکلیف:**\n* مورد اول\n- مورد دوم\n`کد 123`\nفرمول 3 < 5 و a > b"
    formatted = telegram_bot.format_telegram_html(raw)

    # Must convert **bold** to <b>bold</b>
    assert "<b>عنوان تکلیف:</b>" in formatted
    # Must convert * and - bullets to 🔹
    assert "🔹 مورد اول" in formatted
    assert "🔹 مورد دوم" in formatted
    # Must convert `code` to <code>code</code>
    assert "<code>کد 123</code>" in formatted
    # Must escape raw < and > so Telegram HTML doesn't fail
    assert "&lt;" in formatted and "&gt;" in formatted
    # No stray asterisks
    assert "*" not in formatted


def test_school_knowledge(db_session):
    from app.services import school_knowledge

    # 1. Subject resolution
    math_subj = school_knowledge.resolve_subject("ریاضی")
    assert math_subj is not None
    assert math_subj["id"] == "math"
    assert math_subj["teacher"] == "یوسفی"

    web_subj = school_knowledge.resolve_subject("طراحی وب")
    assert web_subj is not None
    assert web_subj["teacher"] == "محمدی‌فر"

    # 2. Schedule lookup
    sat_schedule = school_knowledge.WEEKLY_SCHEDULE["sat"]
    assert sat_schedule["day_fa"] == "شنبه"
    assert len(sat_schedule["periods"]) == 4

    # 3. Tool execution with day filter
    res = ai_agent.execute_tool("get_school_schedule", {"day": "شنبه"}, db_session, None)
    assert res["success"] is True
    assert res["day"] == "شنبه"
    assert len(res["periods"]) == 4


def test_telegram_chat_history_memory(db_session):
    chat_id = 99887766

    # 1. Initially empty
    assert telegram_bot.is_recent_conversation(db_session, chat_id) is False
    assert telegram_bot.get_chat_history(db_session, chat_id) == []

    # 2. Save user message and bot response
    telegram_bot.save_chat_history(db_session, chat_id, role="user", content="سلام")
    telegram_bot.save_chat_history(db_session, chat_id, role="assistant", content="درود! چطور می‌تونم کمکت کنم؟")

    # 3. Check memory
    assert telegram_bot.is_recent_conversation(db_session, chat_id, max_idle_minutes=10) is True
    history = telegram_bot.get_chat_history(db_session, chat_id, limit=5)
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[0]["content"] == "سلام"
    assert history[1]["role"] == "assistant"


def test_toggle_assignment_completion_smart_fallback(db_session):
    student = models.User(username="learner", code="LEARN1", role=models.ROLE_MEMBER)
    admin = models.User(username="teacher", code="TEACH1", is_admin=True, role=models.ROLE_ADMIN)
    db_session.add_all([student, admin])
    db_session.commit()

    # Create active assignment
    a1 = models.Assignment(
        title="تمرین شیمی فصل ۲",
        subject_id="chemistry",
        category="شیمی",
        course="شیمی",
        owner_id=admin.id,
        creator_id=admin.id,
    )
    db_session.add(a1)
    db_session.commit()

    # 1. Student says "تکلیف شیمی رو تیک بزنم" -> stop words stripped, matches chemistry
    res = ai_agent.execute_tool(
        "toggle_assignment_completion",
        {"action": "complete", "scope": "single", "assignment_query": "تکلیف شیمی رو تیک بزنم"},
        db_session,
        student,
    )
    assert res["success"] is True
    assert "تمرین شیمی فصل ۲" in res["modified_titles"]

    # 2. Check it is completed in database
    comp = db_session.query(models.AssignmentCompletion).filter_by(user_id=student.id, assignment_id=a1.id).first()
    assert comp is not None

    # 3. Untick it
    res_un = ai_agent.execute_tool(
        "toggle_assignment_completion",
        {"action": "uncomplete", "scope": "single", "assignment_query": "تکلیف شیمی"},
        db_session,
        student,
    )
    assert res_un["success"] is True
    assert "تمرین شیمی فصل ۲" in res_un["modified_titles"]
    comp_after = db_session.query(models.AssignmentCompletion).filter_by(user_id=student.id, assignment_id=a1.id).first()
    assert comp_after is None

    # 4. Generic query without subject -> smart fallback finds active assignment
    res_generic = ai_agent.execute_tool(
        "toggle_assignment_completion",
        {"action": "complete", "scope": "single", "assignment_query": "یک تکلیفی رو تیک بزنم"},
        db_session,
        student,
    )
    assert res_generic["success"] is True
    assert len(res_generic["modified_titles"]) == 1


@pytest.mark.asyncio
async def test_interactive_task_wizard_and_callbacks(db_session, monkeypatch):
    from app.services import telegram_task_wizard

    admin = models.User(username="headmaster", code="HEAD01", is_admin=True, role=models.ROLE_OWNER)
    db_session.add(admin)
    db_session.commit()

    # Stub telegram HTTP methods so no actual requests are sent to api.telegram.org
    async def async_stub(*args, **kwargs):
        return True

    monkeypatch.setattr(telegram_bot, "edit_telegram_message", async_stub)
    monkeypatch.setattr(telegram_bot, "answer_callback_query", async_stub)

    # 1. Test build steps
    kb1 = telegram_task_wizard.build_step1_keyboard()
    assert "inline_keyboard" in kb1
    assert any("تکلیف نوشتنی" in btn["text"] for row in kb1["inline_keyboard"] for btn in row)

    kb2 = telegram_task_wizard.build_step2_keyboard("written")
    assert any("طراحی وب" in btn["text"] for row in kb2["inline_keyboard"] for btn in row)

    text3, kb3 = telegram_task_wizard.build_step3_keyboard("written", "math")
    assert "تکلیف نوشتنی ریاضی" in text3
    assert any("پیشنهادی درس" in btn["text"] for row in kb3["inline_keyboard"] for btn in row)

    # 2. Test saving via callback
    res = await telegram_task_wizard.handle_wizard_callback(
        db=db_session,
        user=admin,
        data="wiz:save:written:math:none",
        chat_id=12345,
        message_id=6789,
        query_id="q1",
        token="fake_token",
    )
    assert res is True

    # 3. Verify created in database with auto-title
    created = db_session.query(models.Assignment).filter_by(title="تکلیف نوشتنی ریاضی").first()
    assert created is not None
    assert created.course == "ریاضی"
    assert created.subject_id == "math"
    assert created.subtype == "written"
    assert created.creator_id == admin.id


def test_reminder_only_assignment_and_deduplication(db_session):
    from app.routers.telegram import _is_duplicate_update, _mark_update_completed

    # 1. Test update deduplication
    up_id = 999888777
    assert _is_duplicate_update(up_id) is False  # first time
    assert _is_duplicate_update(up_id) is True   # duplicate while in-flight
    _mark_update_completed(up_id)
    assert _is_duplicate_update(up_id) is True   # duplicate after completed

    # 2. Test reminder-only assignment creation and anti-tick protection
    admin = models.User(username="headmaster2", code="HEAD02", is_admin=True, role=models.ROLE_OWNER)
    student = models.User(username="learner2", code="LEARN02", role=models.ROLE_MEMBER)
    db_session.add_all([admin, student])
    db_session.commit()

    res_add = ai_agent.execute_tool(
        "add_assignment",
        {"title": "یادآوری آزمون جامع", "due_date": "2026-12-01", "is_reminder_only": True},
        db_session,
        admin,
    )
    assert res_add["success"] is True
    a_id = res_add["assignment_id"]

    reminder_task = db_session.query(models.Assignment).get(a_id)
    assert reminder_task is not None
    assert reminder_task.is_reminder_only is True

    # 3. Student tries to tick reminder-only assignment -> blocked!
    res_tick = ai_agent.execute_tool(
        "toggle_assignment_completion",
        {"action": "complete", "assignment_query": "یادآوری آزمون جامع"},
        db_session,
        student,
    )
    assert res_tick["success"] is False
    assert "یادآوری" in res_tick["error"]


def test_owner_exempt_from_anti_cheat_rate_limit(db_session):
    from datetime import datetime, timedelta
    from fastapi import HTTPException
    from app.routers.assignments import _toggle_completion

    owner = models.User(username="the_owner", code="OWNER99", role=models.ROLE_OWNER, is_admin=True)
    student = models.User(username="the_student", code="STUDENT99", role=models.ROLE_MEMBER)
    assignment = models.Assignment(
        title="تکلیف فوری تست",
        due_date=datetime.utcnow() + timedelta(days=2),
        created_at=datetime.utcnow(),
    )
    db_session.add_all([owner, student, assignment])
    db_session.commit()

    # 1. Student attempting immediate completion is blocked by anti-cheat delay
    with pytest.raises(HTTPException) as exc_info:
        _toggle_completion(db_session, assignment, student)
    assert exc_info.value.status_code == 400
    assert "تقلب" in exc_info.value.detail

    # 2. Owner attempting immediate and repeated toggles is NEVER blocked (no delay, no rate limit)
    for _ in range(10):
        _toggle_completion(db_session, assignment, owner)
        db_session.commit()

    # Verify owner completion state exists
    is_completed = (
        db_session.query(models.AssignmentCompletion)
        .filter(
            models.AssignmentCompletion.user_id == owner.id,
            models.AssignmentCompletion.assignment_id == assignment.id,
        )
        .first()
    )
    # Since toggled 10 times (even count), it toggled back to undone without any error or lock!
    assert is_completed is None


def test_dynamic_prompt_management_and_reset(db_session):
    from app.services import telegram_bot, ai_agent
    from app.prompts import default_prompts

    # 1. Fetch initial settings (should contain defaults)
    settings = telegram_bot.get_all_bot_settings(db_session)
    assert settings["ai_system_prompt"] == default_prompts.DEFAULT_SYSTEM_PROMPT
    assert settings["ai_temperature"] == default_prompts.DEFAULT_TEMPERATURE

    # 2. Update prompt dynamically
    custom_prompt = "تو یک دستیار کاملاً رسمی و آکادمیک هستی."
    telegram_bot.set_bot_setting(db_session, "ai_system_prompt", custom_prompt)
    telegram_bot.set_bot_setting(db_session, "ai_temperature", "0.4")
    ai_agent.invalidate_prompt_cache()

    cfg = ai_agent.get_ai_prompts_and_config(db_session)
    assert cfg["system_prompt"] == custom_prompt
    assert cfg["temperature"] == 0.4

    # 3. Reset back to defaults
    reset_settings = telegram_bot.reset_bot_prompts(db_session)
    ai_agent.invalidate_prompt_cache()
    assert reset_settings["ai_system_prompt"] == default_prompts.DEFAULT_SYSTEM_PROMPT
    assert reset_settings["ai_system_prompt"] == ""
    assert reset_settings["ai_temperature"] == default_prompts.DEFAULT_TEMPERATURE


def test_open_add_homework_wizard_tool_permissions(db_session):
    from app.services import ai_agent

    admin = models.User(username="head_admin", code="HEAD11", is_admin=True, role=models.ROLE_ADMIN)
    student = models.User(username="regular_student", code="STU11", is_admin=False, role=models.ROLE_MEMBER)
    db_session.add_all([admin, student])
    db_session.commit()

    # 1. Unauthenticated user
    res_unauth = ai_agent.execute_tool("open_add_homework_wizard", {}, db_session, None)
    assert res_unauth["success"] is False
    assert res_unauth["action"] == "auth_required"

    # 2. Regular student (not admin) -> permission denied
    res_stu = ai_agent.execute_tool("open_add_homework_wizard", {}, db_session, student)
    assert res_stu["success"] is False
    assert res_stu["action"] == "permission_denied"

    # 3. Admin user -> open_wizard success
    res_admin = ai_agent.execute_tool("open_add_homework_wizard", {}, db_session, admin)
    assert res_admin["success"] is True
    assert res_admin["action"] == "open_wizard"


def test_owner_only_bot_settings_permission(client, db_session):
    from app.security import create_access_token

    # Create admin user and owner user
    admin_u = models.User(username="regular_admin_test", code="ADM_TEST1", is_admin=True, role=models.ROLE_ADMIN)
    owner_u = models.User(username="the_owner_test", code="OWN_TEST1", is_admin=True, role=models.ROLE_OWNER)
    db_session.add_all([admin_u, owner_u])
    db_session.commit()

    admin_token = create_access_token({"sub": str(admin_u.id)})
    owner_token = create_access_token({"sub": str(owner_u.id)})

    # Admin should receive 403 Forbidden: Owner only
    resp_admin = client.get("/api/v1/telegram/settings", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp_admin.status_code == 403
    assert "Owner only" in resp_admin.text

    # Owner should receive 200 OK
    resp_owner = client.get("/api/v1/telegram/settings", headers={"Authorization": f"Bearer {owner_token}"})
    assert resp_owner.status_code == 200


def test_owner_diagnostic_report_and_error_recording(db_session):
    from app.services import telegram_bot

    owner = models.User(username="boss", code="BOSS1", is_admin=True, role=models.ROLE_OWNER, telegram_id=987654321)
    db_session.add(owner)
    db_session.commit()

    # Simulate an error
    try:
        raise ValueError("تست خطای سرور برای پیوی اونر")
    except Exception as exc:
        err_entry = telegram_bot.record_system_error(exc, endpoint="POST /api/v1/test", user_info="boss (ID: 1)")
        assert err_entry["error_type"] == "ValueError"
        assert "تست خطای سرور" in err_entry["error_msg"]

    # Build owner report
    report = telegram_bot.build_owner_detailed_report(db_session)
    assert "گزارش جامع وضعیت سرور" in report
    assert "CPU" in report
    assert "RAM" in report
    assert "ValueError" in report


def test_render_visual_card_tool(db_session):
    from app.services import ai_agent, card_renderer
    import os

    student = models.User(username="ali", code="ALI01", role=models.ROLE_MEMBER)
    db_session.add(student)
    db_session.commit()

    # Progress card
    res = ai_agent.execute_tool("render_visual_card", {"card_type": "progress"}, db_session, student)
    assert res["success"] is True
    assert res["card_type"] == "progress"
    assert os.path.exists(res["image_path"])

    # Leaderboard card
    res_lb = ai_agent.execute_tool("render_visual_card", {"card_type": "leaderboard"}, db_session, student)
    assert res_lb["success"] is True
    assert os.path.exists(res_lb["image_path"])


def test_is_private_telegram_chat():
    from app.services.telegram_bot import is_private_telegram_chat

    assert is_private_telegram_chat(12345678) is True
    assert is_private_telegram_chat("12345678") is True
    assert is_private_telegram_chat(-100123456789) is False
    assert is_private_telegram_chat("-100123456789") is False
    assert is_private_telegram_chat(0) is False
    assert is_private_telegram_chat(None) is False
    assert is_private_telegram_chat("not_a_number") is False


@pytest.mark.asyncio
async def test_mirror_pv_to_owner(db_session, monkeypatch):
    from app.services import telegram_bot

    owner = models.User(username="owner_boss", code="OWN99", role=models.ROLE_OWNER, telegram_id=999000, is_active=True)
    student = models.User(username="mamad", code="MAM01", role=models.ROLE_MEMBER, telegram_id=111222, telegram_username="mamad_tg", is_active=True)
    db_session.add_all([owner, student])
    db_session.commit()

    telegram_bot.set_bot_setting(db_session, "telegram_bot_token", "fake_token_123")
    telegram_bot.set_bot_setting(db_session, "owner_telegram_chat_id", "999000")

    sent_messages = []

    async def fake_send_message(token, chat_id, text, **kwargs):
        sent_messages.append({"chat_id": chat_id, "text": text, **kwargs})
        return True

    monkeypatch.setattr(telegram_bot, "send_telegram_message", fake_send_message)

    # 1. Mirror inbound message from student to owner
    res = await telegram_bot.mirror_pv_to_owner(
        telegram_id=111222,
        telegram_username="mamad_tg",
        text="سلام تکلیف ریاضی فردا چی بود؟",
        direction="inbound",
        db=db_session,
    )
    assert res is True
    assert len(sent_messages) == 1
    msg1 = sent_messages[0]
    assert msg1["chat_id"] == 999000
    assert "پیام دریافتی از کاربر در پیوی" in msg1["text"]
    assert "mamad" in msg1["text"]
    assert "111222" in msg1["text"]
    assert "@mamad_tg" in msg1["text"]
    assert "سلام تکلیف ریاضی فردا چی بود؟" in msg1["text"]

    # 2. Mirror outbound reply to student
    sent_messages.clear()
    res2 = await telegram_bot.mirror_pv_to_owner(
        telegram_id=111222,
        text="تکلیف ریاضی صفحه ۴۵ تمرین ۳ است.",
        direction="outbound",
        db=db_session,
    )
    assert res2 is True
    assert len(sent_messages) == 1
    msg2 = sent_messages[0]
    assert msg2["chat_id"] == 999000
    assert "پاسخ ارسالی ربات به کاربر در پیوی" in msg2["text"]
    assert "111222" in msg2["text"]
    assert "تکلیف ریاضی صفحه ۴۵ تمرین ۳ است." in msg2["text"]

    # 3. Mirror action (button tap)
    sent_messages.clear()
    res3 = await telegram_bot.mirror_pv_to_owner(
        telegram_id=111222,
        text="🔘 کلیک روی دکمه: تیک تکلیف ۱۲",
        direction="action",
        db=db_session,
    )
    assert res3 is True
    assert len(sent_messages) == 1
    assert "عملیات کاربر در پیوی" in sent_messages[0]["text"]

    # 4. Never mirror owner's own chats to owner
    sent_messages.clear()
    res_owner = await telegram_bot.mirror_pv_to_owner(
        telegram_id=999000,
        text="دستور مدیریت",
        direction="inbound",
        db=db_session,
    )
    assert res_owner is False
    assert len(sent_messages) == 0

    # 5. Never mirror group chats
    res_group = await telegram_bot.mirror_pv_to_owner(
        telegram_id=-100123456,
        text="پیام گروه",
        direction="inbound",
        db=db_session,
    )
    assert res_group is False
    assert len(sent_messages) == 0


def test_check_who_completed_assignment(db_session):
    from app.services import ai_agent

    # 1. Create users
    u1 = models.User(username="ali_comp", code="ALI_C1", role=models.ROLE_MEMBER, is_active=True)
    u2 = models.User(username="reza_comp", code="REZ_C1", role=models.ROLE_MEMBER, is_active=True)
    u3 = models.User(username="sara_comp", code="SAR_C1", role=models.ROLE_MEMBER, is_active=True)
    db_session.add_all([u1, u2, u3])
    db_session.commit()

    # 2. Create an assignment
    asgn = models.Assignment(
        title="تمرین هندسه تحلیلی",
        course="ریاضی",
        subject_id="math",
        due_date=datetime.utcnow() + timedelta(days=2),
    )
    db_session.add(asgn)
    db_session.commit()

    # 3. u1 and u2 mark it completed; u3 has not
    c1 = models.AssignmentCompletion(user_id=u1.id, assignment_id=asgn.id)
    c2 = models.AssignmentCompletion(user_id=u2.id, assignment_id=asgn.id)
    db_session.add_all([c1, c2])
    db_session.commit()

    # 4. Check completions with natural language query
    data = ai_agent.execute_check_assignment_completions(db_session, "کیا هندسه تحلیلی رو انجام دادن")
    assert data["success"] is True
    assert data["assignment_id"] == asgn.id
    assert data["completed_count"] == 2
    assert "ali_comp" in data["completed_students"]
    assert "reza_comp" in data["completed_students"]
    assert "sara_comp" in data["pending_students"]

    # 5. Test HTML formatter
    html_msg = ai_agent.format_assignment_completions_html(data)
    assert "گزارش وضعیت انجام تکلیف کلاسی" in html_msg
    assert "تمرین هندسه تحلیلی" in html_msg
    assert "ali_comp" in html_msg
    assert "sara_comp" in html_msg
    assert "تیک زده و انجام داده‌اند (2 نفر)" in html_msg


def test_live_context_strictly_excludes_overdue_and_segregates_realtime(db_session):
    from app.services import ai_agent

    user = models.User(username="sepehr_live", code="SEP_L1", role=models.ROLE_MEMBER, is_active=True)
    db_session.add(user)
    db_session.commit()

    # Task 1: Overdue task (past due date)
    overdue_task = models.Assignment(
        title="تکلیف قدیمی شیمی",
        course="شیمی",
        due_date=datetime.utcnow() - timedelta(days=3),
    )
    # Task 2: Active task
    active_task = models.Assignment(
        title="پروژه طراحی وب",
        course="طراحی وب",
        due_date=datetime.utcnow() + timedelta(days=2),
    )
    db_session.add_all([overdue_task, active_task])
    db_session.commit()

    # Before user ticks the active task
    ctx1 = ai_agent.build_live_school_context(db_session, current_user=user)
    # Overdue task MUST NOT be in live context!
    assert "تکلیف قدیمی شیمی" not in ctx1
    # Active task MUST be present under pending
    assert "پروژه طراحی وب" in ctx1
    assert "تکالیف جاری باقی‌مانده" in ctx1

    # Now user completes the active task
    comp = models.AssignmentCompletion(user_id=user.id, assignment_id=active_task.id)
    db_session.add(comp)
    db_session.commit()

    # Next call must instantly reflect the update in real-time memory!
    ctx2 = ai_agent.build_live_school_context(db_session, current_user=user)
    assert "تکلیف قدیمی شیمی" not in ctx2
    assert "تکالیف جاری انجام‌شده کاربر" in ctx2
    assert "پروژه طراحی وب" in ctx2







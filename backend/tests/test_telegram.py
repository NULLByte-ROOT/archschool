import pytest
from app import models
from app.services import gemini_agent, telegram_bot


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
    telegram_bot.set_bot_setting(db_session, "gemini_api_key", "AIzaSyTestKey")
    telegram_bot.set_bot_setting(db_session, "telegram_group_id", "-100123456789")

    settings = telegram_bot.get_all_bot_settings(db_session)
    assert settings["bot_token"] == "123456:ABC-DEF"
    assert settings["gemini_api_key"] == "AIzaSyTestKey"
    assert settings["group_id"] == "-100123456789"
    assert settings["has_token"] is True
    assert settings["has_gemini"] is True


def test_gemini_tools_execution(db_session):
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
    res = gemini_agent.execute_tool(
        "add_assignment",
        {"title": "تمرین تستی", "due_date": "2026-12-01"},
        db_session,
        student,
    )
    assert res["success"] is False
    assert "عدم دسترسی" in res["error"]

    # 2. Admin can add assignment
    res_admin = gemini_agent.execute_tool(
        "add_assignment",
        {"title": "تمرین مجاز ادمین", "due_date": "2026-12-01", "subject": "هندسه"},
        db_session,
        admin,
    )
    assert res_admin["success"] is True

    # 3. get_class_assignments
    assignments = gemini_agent.execute_tool("get_class_assignments", {}, db_session, student)
    assert assignments["success"] is True
    assert len(assignments["assignments"]) >= 1

    # 4. get_my_status
    status = gemini_agent.execute_tool("get_my_status", {}, db_session, student)
    assert status["success"] is True
    assert status["username"] == "student_user"

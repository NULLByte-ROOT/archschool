from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from typing import List

from datetime import datetime

from .. import chat, models, push, schemas
from ..config import settings
from ..database import get_db
from ..dependencies import get_current_admin, get_current_owner, get_current_user
from ..security import (
    generate_code,
    is_valid_access_code,
    normalize_access_code,
    normalize_username,
)
from ..storage import delete_upload

router = APIRouter()


@router.get("/team", response_model=List[schemas.PublicUserOut])
def team(
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
):
    return (
        db.query(models.User)
        .filter(models.User.is_active.is_(True))
        .order_by(models.User.username.asc())
        .all()
    )


@router.patch("/me", response_model=schemas.UserOut)
def update_me(
    data: schemas.UserSelfUpdate,
    db: Session = Depends(get_db),
    current: models.User = Depends(get_current_user),
):
    updates = data.model_dump(exclude_unset=True)
    if "avatar_url" in updates:
        chat.validate_file_url(updates["avatar_url"])
    if "bio" in updates:
        updates["bio"] = (updates["bio"] or "").strip()
    for key, value in updates.items():
        setattr(current, key, value)
    db.commit()
    db.refresh(current)
    return current


@router.delete("/me/avatar", response_model=schemas.UserOut)
def delete_my_avatar(
    db: Session = Depends(get_db),
    current: models.User = Depends(get_current_user),
):
    previous = current.avatar_url
    current.avatar_url = None
    db.commit()
    db.refresh(current)
    if previous:
        delete_upload(previous)
    return current


# ---------------------------------------------------------------------------
#  Mobile push tokens
# ---------------------------------------------------------------------------
PUSH_TOKEN_HINT = "توکن اعلان نامعتبر است"
VALID_DEVICE_TYPES = ("android", "ios", "web", "unknown")


def _valid_push_token(token: str) -> bool:
    """Expo tokens look like ``ExponentPushToken[xxxxxxxx]``.

    The backend only talks to Expo's push service, so tokens from another
    provider would never deliver and are rejected at registration time.
    """
    value = (token or "").strip()
    return bool(
        value.startswith(("ExponentPushToken[", "ExpoPushToken["))
        and value.endswith("]")
        and len(value) <= 255
    )


@router.post("/push-token", response_model=schemas.PushTokenOut)
def register_push_token(
    data: schemas.PushTokenCreate,
    db: Session = Depends(get_db),
    current: models.User = Depends(get_current_user),
):
    """Register (or re-own) the token of this device.

    A token is unique: signing into another account on the same phone moves the
    token instead of leaving a duplicate that would notify the previous user.
    """
    token = (data.token or "").strip()
    if not _valid_push_token(token):
        raise HTTPException(status_code=400, detail=PUSH_TOKEN_HINT)

    device_type = (data.device_type or "unknown").strip().lower()
    if device_type not in VALID_DEVICE_TYPES:
        device_type = "unknown"

    existing = (
        db.query(models.PushToken)
        .filter(models.PushToken.token == token)
        .first()
    )
    if existing is not None:
        existing.user_id = current.id
        existing.device_type = device_type
        existing.updated_at = datetime.utcnow()
        row = existing
    else:
        row = models.PushToken(
            user_id=current.id, token=token, device_type=device_type
        )
        db.add(row)

    try:
        db.commit()
    except IntegrityError:
        # Two installs registered the same token at once: keep the winner and
        # make this request idempotent instead of returning a 500.
        db.rollback()
        row = (
            db.query(models.PushToken)
            .filter(models.PushToken.token == token)
            .first()
        )
        if row is None:
            raise HTTPException(status_code=500, detail="ثبت اعلان ناموفق بود")
        row.user_id = current.id
        row.device_type = device_type
        row.updated_at = datetime.utcnow()
        db.commit()

    db.refresh(row)
    return row


@router.delete("/push-token", status_code=204)
def unregister_push_token(
    token: str | None = Query(None, max_length=255),
    data: schemas.PushTokenDelete | None = Body(None),
    db: Session = Depends(get_db),
    current: models.User = Depends(get_current_user),
):
    """Remove a token on logout, or when the OS rotates it.

    Scoped to the caller so one account can never unregister another account's
    device. Accepts the token as a query parameter or a JSON body.
    """
    value = (token or (data.token if data else "") or "").strip()
    if not value:
        raise HTTPException(status_code=400, detail=PUSH_TOKEN_HINT)

    db.query(models.PushToken).filter(
        models.PushToken.token == value,
        models.PushToken.user_id == current.id,
    ).delete(synchronize_session=False)
    db.commit()
    return None


def _token_preview(token: str) -> str:
    """Short, log-safe rendering of a push token (it is a send credential)."""
    value = (token or "").strip()
    if len(value) <= 30:
        return value
    return f"{value[:24]}…{value[-4:]}"


@router.get("/push-token", response_model=schemas.PushDiagnosticsOut)
def push_token_diagnostics(
    db: Session = Depends(get_db),
    current: models.User = Depends(get_current_user),
):
    """Self-scoped push diagnostics: does this account have a deliverable token?

    `token_count == 0` after a successful login means the phone never registered
    — on Android that is almost always a build without Firebase credentials
    (`getExpoPushTokenAsync` throws before any request), or a denied
    notification permission.
    """
    rows = (
        db.query(models.PushToken)
        .filter(models.PushToken.user_id == current.id)
        .order_by(models.PushToken.updated_at.desc())
        .all()
    )
    return schemas.PushDiagnosticsOut(
        user_id=current.id,
        username=current.username,
        push_enabled=settings.PUSH_NOTIFICATIONS_ENABLED,
        access_token_configured=bool((settings.EXPO_ACCESS_TOKEN or "").strip()),
        token_count=len(rows),
        tokens=[
            schemas.PushTokenDiagnosticOut(
                id=row.id,
                device_type=row.device_type,
                token_preview=_token_preview(row.token),
                notify_chat=row.notify_chat,
                notify_assignments=row.notify_assignments,
                notify_deadlines=row.notify_deadlines,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row in rows
        ],
    )


@router.post("/push-token/test", response_model=schemas.PushTestOut)
async def send_test_push(
    data: schemas.PushTestIn | None = Body(None),
    db: Session = Depends(get_db),
    current: models.User = Depends(get_current_user),
):
    """Send one notification to the caller's own devices and return Expo tickets.

    This is the shortest path from «nothing arrives» to a cause:

    * `DeviceNotRegistered` — the app was uninstalled or the token was revoked;
    * `InvalidCredentials` / `MismatchSenderId` — the FCM V1 service account in
      EAS does not match the app's package;
    * `http_error` with 401 — the Expo project requires an access token
      (`EXPO_ACCESS_TOKEN` is empty);
    * `ok` with an `id` — Expo accepted it, so the miss is on the device
      (channel, battery optimisation, or notifications disabled in Settings).

    Self-scoped on purpose: no user can probe another account's device.
    """
    payload = data or schemas.PushTestIn()

    query = db.query(models.PushToken).filter(
        models.PushToken.user_id == current.id
    )
    if payload.token:
        query = query.filter(models.PushToken.token == payload.token.strip())
    tokens = [row.token for row in query.all()]

    if not tokens:
        raise HTTPException(
            status_code=404,
            detail="برای این حساب توکن اعلانی ثبت نشده است",
        )
    if not settings.PUSH_NOTIFICATIONS_ENABLED:
        raise HTTPException(
            status_code=409,
            detail="ارسال اعلان در سرور غیرفعال است (PUSH_NOTIFICATIONS_ENABLED=false)",
        )

    report = await push.send_push_report(
        tokens,
        payload.title,
        payload.body,
        {"type": "test"},
        channel_id="default",
    )

    return schemas.PushTestOut(
        sent=len(tokens),
        results=[
            schemas.PushTestTicketOut(
                token_preview=_token_preview(str(item.get("token") or "")),
                status=str(item.get("status") or "unknown"),
                error=item.get("error"),
                message=item.get("message"),
                http_status=item.get("http_status"),
            )
            for item in report
        ],
    )


@router.get(
    "/push-token/preferences", response_model=schemas.NotificationPreferencesOut
)
def get_notification_preferences(
    db: Session = Depends(get_db),
    current: models.User = Depends(get_current_user),
):
    """Current per-device switches (defaults to everything on).

    When the account has more than one registered device, the most recently
    updated token wins — the Settings page then reflects what the user last
    chose on this phone.
    """
    row = (
        db.query(models.PushToken)
        .filter(models.PushToken.user_id == current.id)
        .order_by(models.PushToken.updated_at.desc())
        .first()
    )
    if row is None:
        return schemas.NotificationPreferencesOut()
    return schemas.NotificationPreferencesOut(
        chat=bool(row.notify_chat),
        assignments=bool(row.notify_assignments),
        deadlines=bool(row.notify_deadlines),
    )


@router.patch(
    "/push-token/preferences", response_model=schemas.NotificationPreferencesOut
)
def update_notification_preferences(
    data: schemas.NotificationPreferencesIn,
    db: Session = Depends(get_db),
    current: models.User = Depends(get_current_user),
):
    """Save the mobile Settings toggles for one device (or all of them)."""
    query = db.query(models.PushToken).filter(
        models.PushToken.user_id == current.id
    )
    if data.token:
        query = query.filter(models.PushToken.token == data.token.strip())
    rows = query.all()
    for row in rows:
        row.notify_chat = data.chat
        row.notify_assignments = data.assignments
        row.notify_deadlines = data.deadlines
        row.updated_at = datetime.utcnow()
    db.commit()
    return schemas.NotificationPreferencesOut(
        chat=data.chat, assignments=data.assignments, deadlines=data.deadlines
    )


@router.get("/{user_id}/profile", response_model=schemas.UserProfileOut)
def user_profile(
    user_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
):
    user = (
        db.query(models.User)
        .filter(models.User.id == user_id, models.User.is_active.is_(True))
        .first()
    )
    if not user:
        raise HTTPException(status_code=404, detail="کاربر پیدا نشد")
    return user


@router.get("/", response_model=List[schemas.UserOut])
def list_users(
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_admin),
):
    return db.query(models.User).order_by(models.User.created_at.desc()).all()


@router.post("/", response_model=schemas.UserOut, status_code=201)
def create_user(
    data: schemas.UserCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin),
):
    username = normalize_username(data.username)
    exists = (
        db.query(models.User)
        .filter(func.lower(models.User.username) == username.lower())
        .first()
    )
    if exists:
        raise HTTPException(status_code=400, detail="این نام کاربری قبلاً گرفته شده")

    code = normalize_access_code(data.code) if data.code else generate_code()
    if not is_valid_access_code(code):
        raise HTTPException(
            status_code=400,
            detail="کد دسترسی باید دقیقاً ۶ کاراکتر و فقط شامل اعداد و حروف انگلیسی بزرگ باشد",
        )
    code_taken = (
        db.query(models.User)
        .filter(func.upper(models.User.code) == code)
        .first()
    )
    if code_taken:
        raise HTTPException(status_code=400, detail="این کد دسترسی قبلاً استفاده شده است")

    role = data.role or (models.ROLE_ADMIN if data.is_admin else models.ROLE_MEMBER)
    if role not in models.VALID_ROLES:
        raise HTTPException(status_code=400, detail="نقش نامعتبر است")

    # Only an owner may mint another owner; admins manage member/friend/admin.
    if role == models.ROLE_OWNER and not models.is_owner(current_user):
        raise HTTPException(
            status_code=403, detail="فقط Owner می‌تواند نقش Owner بسازد"
        )

    user = models.User(
        username=username,
        code=code,
        is_admin=role in (models.ROLE_ADMIN, models.ROLE_OWNER),
        role=role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.patch("/{user_id}", response_model=schemas.UserOut)
def update_user(
    user_id: int,
    data: schemas.UserUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    updates = data.model_dump(exclude_unset=True)

    # Role guardrails: admins manage member/admin; the owner role can only be
    # granted or revoked by an owner. An admin can also never touch the owner
    # account itself (demote/deactivate is owner business).
    if "role" in updates and updates["role"] not in models.VALID_ROLES:
        raise HTTPException(status_code=400, detail="نقش نامعتبر است")
    if models.is_owner(user) and not models.is_owner(current_user):
        if "role" in updates and updates["role"] != models.ROLE_OWNER:
            raise HTTPException(
                status_code=403, detail="فقط Owner می‌تواند حساب Owner را تغییر دهد"
            )
    if "role" in updates and updates["role"] == models.ROLE_OWNER:
        if not models.is_owner(current_user):
            raise HTTPException(
                status_code=403, detail="فقط Owner می‌تواند نقش Owner بسازد"
            )
    if updates.get("username"):
        updates["username"] = normalize_username(updates["username"])
    if "code" in updates and updates["code"] is not None:
        # کد دسترسی فقط از مسیر Owner قابل تغییر است
        if not models.is_owner(current_user):
            raise HTTPException(
                status_code=403,
                detail="فقط Owner می‌تواند کد دسترسی را تغییر دهد",
            )
        updates["code"] = normalize_access_code(updates["code"])
        if not is_valid_access_code(updates["code"]):
            raise HTTPException(
                status_code=400,
                detail="کد دسترسی باید دقیقاً ۶ کاراکتر و فقط شامل اعداد و حروف انگلیسی بزرگ باشد",
            )
        code_taken = (
            db.query(models.User)
            .filter(
                func.upper(models.User.code) == updates["code"],
                models.User.id != user.id,
            )
            .first()
        )
        if code_taken:
            raise HTTPException(
                status_code=400, detail="این کد دسترسی قبلاً استفاده شده است"
            )
    else:
        updates.pop("code", None)

    for key, value in updates.items():
        setattr(user, key, value)

    # Keep the legacy `is_admin` flag and the RBAC `role` in sync so both the
    # old admin-only checks and the new role checks agree. Owner keeps its
    # role even if only `is_admin` is patched.
    if "role" in updates:
        user.is_admin = user.role in (models.ROLE_ADMIN, models.ROLE_OWNER)
    elif "is_admin" in updates and not models.is_owner(user):
        user.role = models.ROLE_ADMIN if user.is_admin else models.ROLE_MEMBER

    db.commit()
    db.refresh(user)
    return user


@router.patch("/{user_id}/code", response_model=schemas.UserOut)
def change_user_code(
    user_id: int,
    data: schemas.UserCodeUpdate,
    db: Session = Depends(get_db),
    current: models.User = Depends(get_current_owner),
):
    """Change any user's 6-character access code. Owner-only by design."""
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    code = normalize_access_code(data.code)
    if not is_valid_access_code(code):
        raise HTTPException(
            status_code=400,
            detail="کد دسترسی باید دقیقاً ۶ کاراکتر و فقط شامل اعداد و حروف انگلیسی بزرگ باشد",
        )
    code_taken = (
        db.query(models.User)
        .filter(func.upper(models.User.code) == code, models.User.id != user.id)
        .first()
    )
    if code_taken:
        raise HTTPException(status_code=400, detail="این کد دسترسی قبلاً استفاده شده است")

    # Respect the environment: the .env is the source of truth for the Owner's
    # own account and a later boot re-applies that value.
    if models.is_owner(user):
        owner_env_code = ""
        try:
            from ..config import settings

            owner_env_code = normalize_access_code(settings.OWNER_ACCESS_CODE or "")
        except Exception:  # pragma: no cover - normalize never raises
            owner_env_code = ""
        if models.is_owner(current) and current.id == user.id and owner_env_code:
            raise HTTPException(
                status_code=403,
                detail="کد حساب Owner از backend/.env کنترل می‌شود؛ از منوی سرور تغییر دهید",
            )

    user.code = code
    db.commit()
    db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=204)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current: models.User = Depends(get_current_admin),
):
    if user_id == current.id:
        raise HTTPException(status_code=400, detail="خودت رو نمی‌تونی حذف کنی")
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if models.is_owner(user) and not models.is_owner(current):
        raise HTTPException(
            status_code=403, detail="فقط Owner می‌تواند حساب Owner را حذف کند"
        )
    db.delete(user)
    db.commit()
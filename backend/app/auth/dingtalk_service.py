from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.auth.dingtalk import DingTalkAuthError, dingtalk_client
from app.models import Company, User


def _dingtalk_user_id(profile: Dict[str, Any]) -> str:
    """Stable DingTalk user identifier from the contact profile."""
    for key in ("unionId", "unionid", "openId", "openid", "userid", "userId"):
        value = profile.get(key)
        if value:
            return str(value).strip()
    return ""


def _profile_email(profile: Dict[str, Any]) -> Optional[str]:
    email = (profile.get("email") or profile.get("orgEmail") or "").strip().lower()
    return email or None


def _profile_display_name(
    profile: Dict[str, Any],
    *,
    email: Optional[str],
    dingtalk_id: str,
) -> str:
    for key in ("nick", "name", "realName"):
        value = profile.get(key)
        if value:
            return str(value).strip()
    if email:
        return email.split("@", 1)[0]
    return f"DingTalk User {dingtalk_id[:8]}"


def _store_dingtalk_session(user: User, token_data: Dict[str, Any], corp_id: Optional[str]) -> None:
    expire_in = int(token_data.get("expireIn") or token_data.get("expiresIn") or 7200)
    resolved_corp_id = corp_id or token_data.get("corpId") or token_data.get("corp_id")
    preferences = dict(user.preferences or {})
    preferences["dingtalk"] = {
        "access_token": token_data.get("accessToken") or token_data.get("access_token"),
        "refresh_token": token_data.get("refreshToken") or token_data.get("refresh_token"),
        "expires_at": (datetime.utcnow() + timedelta(seconds=expire_in)).isoformat(),
        "corp_id": resolved_corp_id,
        "updated_at": datetime.utcnow().isoformat(),
    }
    user.preferences = preferences


def get_or_create_company(db: Session, corp_id: str, company_name: Optional[str] = None) -> Company:
    company = db.query(Company).filter(Company.dingtalk_corp_id == corp_id).first()
    if company:
        if company_name and company.name.startswith("DingTalk Corp"):
            company.name = company_name
        return company

    company = Company(
        name=company_name or f"DingTalk Corp {corp_id[:8]}",
        dingtalk_corp_id=corp_id,
    )
    db.add(company)
    db.flush()
    return company


def find_or_create_user_from_dingtalk(
    db: Session,
    *,
    corp_id: str,
    profile: Dict[str, Any],
    token_data: Dict[str, Any],
) -> User:
    """
    Link an existing user by DingTalk ID or email, or create a new ``hr_viewer``.

    DingTalk corp ID is stored on the company record and in ``user.preferences['dingtalk']``.
    """
    dingtalk_id = _dingtalk_user_id(profile)
    if not dingtalk_id:
        raise DingTalkAuthError(
            "DingTalk profile did not include openId/unionId. "
            "Ensure OAuth scope includes 'openid' and the app has contact read permission.",
            status_code=400,
        )

    company = get_or_create_company(db, corp_id, profile.get("corpName"))
    email = _profile_email(profile)
    display_name = _profile_display_name(profile, email=email, dingtalk_id=dingtalk_id)

    user_by_dingtalk = (
        db.query(User)
        .filter(User.company_id == company.id, User.dingtalk_user_id == dingtalk_id)
        .first()
    )
    user_by_email = db.query(User).filter(User.email == email).first() if email else None

    if user_by_dingtalk and user_by_email and user_by_dingtalk.id != user_by_email.id:
        raise DingTalkAuthError(
            "This DingTalk account and email belong to different users. Contact an administrator.",
            status_code=409,
        )

    user = user_by_dingtalk or user_by_email

    if user:
        if user.dingtalk_user_id and user.dingtalk_user_id != dingtalk_id:
            raise DingTalkAuthError(
                "This email is already linked to a different DingTalk account.",
                status_code=409,
            )
        user.company_id = company.id
        user.dingtalk_user_id = dingtalk_id
        user.name = display_name
        if email and not user.email:
            existing_email_owner = (
                db.query(User)
                .filter(User.email == email, User.id != user.id)
                .first()
            )
            if existing_email_owner:
                raise DingTalkAuthError(
                    "This email is already used by another account.",
                    status_code=409,
                )
            user.email = email
    else:
        if email:
            existing_email_owner = db.query(User).filter(User.email == email).first()
            if existing_email_owner:
                raise DingTalkAuthError(
                    "This email is already registered. Sign in with email/password to link DingTalk.",
                    status_code=409,
                )

        user = User(
            company_id=company.id,
            dingtalk_user_id=dingtalk_id,
            name=display_name,
            email=email,
            role="hr_viewer",
            is_active=True,
        )
        db.add(user)

    _store_dingtalk_session(user, token_data, corp_id)
    db.flush()
    return user


def refresh_stored_dingtalk_token(db: Session, user: User) -> Optional[str]:
    dingtalk_prefs = (user.preferences or {}).get("dingtalk", {})
    access_token = dingtalk_prefs.get("access_token")
    expires_at = dingtalk_prefs.get("expires_at")
    refresh_token = dingtalk_prefs.get("refresh_token")

    if access_token and expires_at:
        try:
            if datetime.fromisoformat(expires_at) > datetime.utcnow() + timedelta(minutes=1):
                return access_token
        except ValueError:
            pass

    if not refresh_token:
        return None

    if not dingtalk_client.is_configured():
        return None

    try:
        token_data = dingtalk_client.refresh_user_access_token(refresh_token)
    except DingTalkAuthError:
        return None

    _store_dingtalk_session(user, token_data, dingtalk_prefs.get("corp_id"))
    db.commit()
    return token_data.get("accessToken") or token_data.get("access_token")

from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.auth.dingtalk import DingTalkAuthError, dingtalk_client
from app.models import Company, User


def _dingtalk_user_id(profile: Dict[str, Any]) -> str:
    return (
        profile.get("unionId")
        or profile.get("openId")
        or profile.get("userid")
        or profile.get("userId")
        or profile.get("nick")
    )


def _store_dingtalk_session(user: User, token_data: Dict[str, Any], corp_id: Optional[str]) -> None:
    expire_in = int(token_data.get("expireIn") or token_data.get("expiresIn") or 7200)
    preferences = dict(user.preferences or {})
    preferences["dingtalk"] = {
        "access_token": token_data.get("accessToken"),
        "refresh_token": token_data.get("refreshToken"),
        "expires_at": (datetime.utcnow() + timedelta(seconds=expire_in)).isoformat(),
        "corp_id": corp_id or token_data.get("corpId"),
        "updated_at": datetime.utcnow().isoformat(),
    }
    user.preferences = preferences


def get_or_create_company(db: Session, corp_id: str, company_name: Optional[str] = None) -> Company:
    company = db.query(Company).filter(Company.dingtalk_corp_id == corp_id).first()
    if company:
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
    dingtalk_id = _dingtalk_user_id(profile)
    if not dingtalk_id:
        raise DingTalkAuthError("DingTalk profile did not include a user identifier", status_code=400)

    company = get_or_create_company(db, corp_id, profile.get("corpName"))
    email = (profile.get("email") or "").strip().lower() or None
    display_name = profile.get("nick") or profile.get("name") or email or f"DingTalk User {dingtalk_id[:8]}"

    user = (
        db.query(User)
        .filter(User.company_id == company.id, User.dingtalk_user_id == dingtalk_id)
        .first()
    )

    if not user and email:
        user = db.query(User).filter(User.email == email).first()
        if user:
            user.company_id = company.id
            user.dingtalk_user_id = dingtalk_id

    if not user:
        user = User(
            company_id=company.id,
            dingtalk_user_id=dingtalk_id,
            name=display_name,
            email=email,
            role="hr_viewer",
            is_active=True,
        )
        db.add(user)
    else:
        user.name = display_name
        if email and not user.email:
            user.email = email
        if not user.dingtalk_user_id:
            user.dingtalk_user_id = dingtalk_id

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

    try:
        token_data = dingtalk_client.refresh_user_access_token(refresh_token)
    except DingTalkAuthError:
        return None

    _store_dingtalk_session(user, token_data, dingtalk_prefs.get("corp_id"))
    db.commit()
    return token_data.get("accessToken")

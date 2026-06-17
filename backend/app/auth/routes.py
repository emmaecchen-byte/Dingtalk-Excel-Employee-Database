from datetime import datetime
import logging
from typing import Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user, require_roles, validate_role
from app.auth.dingtalk import DingTalkAuthError, dingtalk_client
from app.auth.dingtalk_service import find_or_create_user_from_dingtalk, refresh_stored_dingtalk_token
from app.auth.schemas import (
    AccessTokenResponse,
    DingTalkOAuthStatusResponse,
    LoginRequest,
    LogoutRequest,
    MessageResponse,
    RefreshRequest,
    TokenResponse,
    UserCreateRequest,
    UserResponse,
)
from app.auth.security import (
    create_access_token,
    create_refresh_token_value,
    hash_password,
    hash_refresh_token,
    refresh_token_expiry,
    verify_password,
)
from app.config import settings
from app.database import get_db
from app.models import Company, RefreshToken, User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _user_response(user: User, db: Session) -> UserResponse:
    company = db.query(Company).filter(Company.id == user.company_id).first()
    dingtalk_prefs = (user.preferences or {}).get("dingtalk", {})
    corp_id = (
        company.dingtalk_corp_id
        if company and company.dingtalk_corp_id
        else dingtalk_prefs.get("corp_id")
    )
    auth_provider = "dingtalk" if user.dingtalk_user_id and not user.password_hash else "email"
    if user.dingtalk_user_id and user.password_hash:
        auth_provider = "linked"

    return UserResponse(
        id=user.id,
        company_id=user.company_id,
        name=user.name,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        dingtalk_user_id=user.dingtalk_user_id,
        dingtalk_corp_id=corp_id,
        auth_provider=auth_provider,
        created_at=user.created_at,
    )


def _issue_tokens(
    db: Session,
    user: User,
    request: Request,
) -> TokenResponse:
    access_token = create_access_token(
        str(user.id),
        extra_claims={"role": user.role, "email": user.email},
    )
    refresh_value = create_refresh_token_value()
    session = RefreshToken(
        user_id=user.id,
        token_hash=hash_refresh_token(refresh_value),
        expires_at=refresh_token_expiry(),
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None,
    )
    db.add(session)
    db.commit()

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_value,
        expires_in=settings.access_token_expire_minutes * 60,
        user=_user_response(user, db),
    )


def _frontend_callback_url(**params: str) -> str:
    query = urlencode({key: value for key, value in params.items() if value is not None})
    return f"{settings.frontend_url.rstrip('/')}/auth/dingtalk/callback?{query}"


@router.get("/dingtalk/status", response_model=DingTalkOAuthStatusResponse)
def dingtalk_oauth_status():
    missing = dingtalk_client.missing_settings()
    return DingTalkOAuthStatusResponse(
        enabled=not missing,
        authorize_url="/api/auth/dingtalk" if not missing else None,
        missing_settings=missing,
    )


@router.get("/dingtalk")
def dingtalk_login():
    try:
        authorize_url = dingtalk_client.build_authorize_url()
    except DingTalkAuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
    return RedirectResponse(url=authorize_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@router.get("/dingtalk/callback")
def dingtalk_callback(
    request: Request,
    authCode: Optional[str] = None,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    error_description: Optional[str] = None,
    db: Session = Depends(get_db),
):
    if error:
        message = error_description or error
        return RedirectResponse(
            url=_frontend_callback_url(error=error, message=message),
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
        )

    authorization_code = authCode or code
    if not authorization_code:
        return RedirectResponse(
            url=_frontend_callback_url(error="missing_code", message="Missing DingTalk authorization code"),
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
        )

    try:
        dingtalk_client.verify_state(state)
        token_data = dingtalk_client.exchange_auth_code(authorization_code)
        access_token = token_data.get("accessToken") or token_data.get("access_token")
        if not access_token:
            raise DingTalkAuthError("DingTalk did not return an access token", status_code=502)

        corp_id = (
            token_data.get("corpId")
            or token_data.get("corp_id")
            or settings.dingtalk_corp_id
        )
        if not corp_id:
            raise DingTalkAuthError(
                "DingTalk corp ID was not returned. Set DINGTALK_CORP_ID or request scope 'openid corpid'.",
                status_code=400,
            )

        profile = dingtalk_client.get_user_profile(access_token)
        user = find_or_create_user_from_dingtalk(
            db,
            corp_id=corp_id,
            profile=profile,
            token_data=token_data,
        )

        if not user.is_active:
            raise DingTalkAuthError("User account is disabled", status_code=403)

        db.commit()
        db.refresh(user)
        tokens = _issue_tokens(db, user, request)
        return RedirectResponse(
            url=_frontend_callback_url(
                access_token=tokens.access_token,
                refresh_token=tokens.refresh_token,
                expires_in=str(tokens.expires_in),
            ),
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
        )
    except DingTalkAuthError as exc:
        db.rollback()
        logger.warning("DingTalk OAuth failed: %s", exc.message)
        return RedirectResponse(
            url=_frontend_callback_url(error="dingtalk_auth_failed", message=exc.message),
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
        )
    except Exception:
        db.rollback()
        logger.exception("Unexpected error during DingTalk OAuth callback")
        return RedirectResponse(
            url=_frontend_callback_url(
                error="dingtalk_auth_failed",
                message="Unexpected error during DingTalk authentication",
            ),
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
        )


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email.lower()).first()
    if not user or not user.password_hash:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled",
        )

    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    return _issue_tokens(db, user, request)


@router.post("/refresh", response_model=AccessTokenResponse)
def refresh_token(payload: RefreshRequest, db: Session = Depends(get_db)):
    token_hash = hash_refresh_token(payload.refresh_token)
    session = db.query(RefreshToken).filter(RefreshToken.token_hash == token_hash).first()

    if not session or session.revoked_at is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    if session.expires_at < datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has expired",
        )

    user = db.query(User).filter(User.id == session.user_id).first()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is not available",
        )

    access_token = create_access_token(
        str(user.id),
        extra_claims={"role": user.role, "email": user.email},
    )
    return AccessTokenResponse(
        access_token=access_token,
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.post("/logout", response_model=MessageResponse)
def logout(payload: LogoutRequest, db: Session = Depends(get_db)):
    token_hash = hash_refresh_token(payload.refresh_token)
    session = db.query(RefreshToken).filter(RefreshToken.token_hash == token_hash).first()

    if session and session.revoked_at is None:
        session.revoked_at = datetime.utcnow()
        db.commit()

    return MessageResponse(message="Logged out successfully")


@router.post("/logout-all", response_model=MessageResponse)
def logout_all(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    now = datetime.utcnow()
    sessions = (
        db.query(RefreshToken)
        .filter(RefreshToken.user_id == current_user.id, RefreshToken.revoked_at.is_(None))
        .all()
    )
    for session in sessions:
        session.revoked_at = now
    db.commit()
    return MessageResponse(message="All sessions revoked successfully")


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    refresh_stored_dingtalk_token(db, current_user)
    return _user_response(current_user, db)


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register_user(
    payload: UserCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["hr_admin"])),
):
    validate_role(payload.role)

    email = payload.email.lower()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists",
        )

    company_id = payload.company_id or current_user.company_id
    user = User(
        company_id=company_id,
        name=payload.name,
        email=email,
        password_hash=hash_password(payload.password),
        role=payload.role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _user_response(user, db)

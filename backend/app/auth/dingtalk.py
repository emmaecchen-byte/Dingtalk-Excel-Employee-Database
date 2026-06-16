import secrets
from datetime import datetime, timedelta
from typing import Any, Dict, Optional
from urllib.parse import urlencode

import httpx
import jwt

from app.config import settings


class DingTalkAuthError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class DingTalkClient:
    AUTHORIZE_URL = "https://login.dingtalk.com/oauth2/auth"
    USER_ACCESS_TOKEN_URL = "https://api.dingtalk.com/v1.0/oauth2/userAccessToken"
    USER_PROFILE_URL = "https://api.dingtalk.com/v1.0/contact/users/me"

    def is_configured(self) -> bool:
        return bool(
            settings.dingtalk_client_id
            and settings.dingtalk_client_secret
            and settings.dingtalk_redirect_uri
        )

    def create_state(self) -> str:
        payload = {
            "nonce": secrets.token_urlsafe(16),
            "exp": datetime.utcnow() + timedelta(minutes=10),
            "type": "dingtalk_oauth",
        }
        return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

    def verify_state(self, state: Optional[str]) -> None:
        if not state:
            raise DingTalkAuthError("Missing OAuth state parameter", status_code=400)
        try:
            payload = jwt.decode(state, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        except jwt.ExpiredSignatureError:
            raise DingTalkAuthError("OAuth state has expired. Please try logging in again.", status_code=400)
        except jwt.PyJWTError:
            raise DingTalkAuthError("Invalid OAuth state parameter", status_code=400)
        if payload.get("type") != "dingtalk_oauth":
            raise DingTalkAuthError("Invalid OAuth state parameter", status_code=400)

    def build_authorize_url(self) -> str:
        if not self.is_configured():
            raise DingTalkAuthError(
                "DingTalk OAuth is not configured. Set DINGTALK_CLIENT_ID, DINGTALK_CLIENT_SECRET, and DINGTALK_REDIRECT_URI.",
                status_code=503,
            )

        params = {
            "client_id": settings.dingtalk_client_id,
            "response_type": "code",
            "scope": "openid corpid",
            "redirect_uri": settings.dingtalk_redirect_uri,
            "state": self.create_state(),
            "prompt": "consent",
        }
        if settings.dingtalk_corp_id:
            params["corpId"] = settings.dingtalk_corp_id
        return f"{self.AUTHORIZE_URL}?{urlencode(params)}"

    def exchange_auth_code(self, auth_code: str) -> Dict[str, Any]:
        body = {
            "clientId": settings.dingtalk_client_id,
            "clientSecret": settings.dingtalk_client_secret,
            "code": auth_code,
            "grantType": "authorization_code",
        }
        return self._post_json(self.USER_ACCESS_TOKEN_URL, body)

    def refresh_user_access_token(self, refresh_token: str) -> Dict[str, Any]:
        body = {
            "clientId": settings.dingtalk_client_id,
            "clientSecret": settings.dingtalk_client_secret,
            "refreshToken": refresh_token,
            "grantType": "refresh_token",
        }
        return self._post_json(self.USER_ACCESS_TOKEN_URL, body)

    def get_user_profile(self, access_token: str) -> Dict[str, Any]:
        return self._get_json(
            self.USER_PROFILE_URL,
            headers={"x-acs-dingtalk-access-token": access_token},
        )

    def _post_json(self, url: str, body: Dict[str, Any]) -> Dict[str, Any]:
        try:
            with httpx.Client(timeout=15.0) as client:
                response = client.post(url, json=body)
        except httpx.RequestError as exc:
            raise DingTalkAuthError(f"Failed to reach DingTalk API: {exc}", status_code=502)

        return self._parse_response(response)

    def _get_json(self, url: str, headers: Dict[str, str]) -> Dict[str, Any]:
        try:
            with httpx.Client(timeout=15.0) as client:
                response = client.get(url, headers=headers)
        except httpx.RequestError as exc:
            raise DingTalkAuthError(f"Failed to reach DingTalk API: {exc}", status_code=502)

        return self._parse_response(response)

    def _parse_response(self, response: httpx.Response) -> Dict[str, Any]:
        try:
            data = response.json()
        except ValueError:
            data = {}

        if response.status_code >= 400:
            message = (
                data.get("message")
                or data.get("errorMsg")
                or data.get("errmsg")
                or "DingTalk API request failed"
            )
            if response.status_code in {400, 401} and any(
                keyword in message.lower()
                for keyword in ("expired", "invalid", "code", "token")
            ):
                raise DingTalkAuthError(message, status_code=401)
            raise DingTalkAuthError(message, status_code=response.status_code)

        if isinstance(data, dict) and data.get("code") not in (None, "0", 0):
            message = data.get("message") or data.get("errmsg") or "DingTalk API returned an error"
            raise DingTalkAuthError(message, status_code=400)

        return data if isinstance(data, dict) else {}


dingtalk_client = DingTalkClient()

import logging
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

RATE_LIMIT_ERRCODES = {88, 90018}


class DingTalkAPIError(Exception):
    def __init__(self, message: str, status_code: int = 502):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class DingTalkCorpClient:
    """DingTalk enterprise API client for employee sync (topapi v2 + corp access token)."""

    ACCESS_TOKEN_URL = "https://api.dingtalk.com/v1.1/oauth2/accessToken"
    OAPI_BASE_URL = "https://oapi.dingtalk.com"

    def __init__(self) -> None:
        self._access_token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None
        self._last_request_at: float = 0.0

    def is_configured(self) -> bool:
        return bool(settings.dingtalk_client_id and settings.dingtalk_client_secret)

    def get_access_token(self, force_refresh: bool = False) -> str:
        if (
            not force_refresh
            and self._access_token
            and self._token_expires_at
            and self._token_expires_at > datetime.utcnow() + timedelta(minutes=2)
        ):
            return self._access_token

        logger.info("Requesting DingTalk corp access token")
        try:
            with httpx.Client(timeout=20.0) as client:
                response = client.post(
                    self.ACCESS_TOKEN_URL,
                    json={
                        "appKey": settings.dingtalk_client_id,
                        "appSecret": settings.dingtalk_client_secret,
                    },
                )
        except httpx.RequestError as exc:
            raise DingTalkAPIError(f"Failed to reach DingTalk token endpoint: {exc}")

        data = self._parse_json_response(response)
        token = data.get("accessToken")
        if not token:
            raise DingTalkAPIError("DingTalk did not return an access token")

        expire_in = int(data.get("expireIn") or 7200)
        self._access_token = token
        self._token_expires_at = datetime.utcnow() + timedelta(seconds=expire_in)
        logger.info("DingTalk corp access token acquired (expires in %s seconds)", expire_in)
        return token

    def list_sub_department_ids(self, dept_id: int) -> List[int]:
        result = self._post_topapi("/topapi/v2/department/listsub", {"dept_id": dept_id})
        departments = result.get("result") or []
        return [int(item["dept_id"]) for item in departments if item.get("dept_id") is not None]

    def get_department_name(self, dept_id: int) -> str:
        result = self._post_topapi("/topapi/v2/department/get", {"dept_id": dept_id})
        department = result.get("result") or {}
        return department.get("name") or f"Department {dept_id}"

    def list_users_in_department(self, dept_id: int) -> List[Dict[str, Any]]:
        """DingTalk contact/user/list equivalent (topapi v2 user list with pagination)."""
        users: List[Dict[str, Any]] = []
        cursor = 0
        has_more = True

        while has_more:
            payload = {"dept_id": dept_id, "cursor": cursor, "size": settings.dingtalk_user_page_size}
            result = self._post_topapi("/topapi/v2/user/list", payload)
            page = result.get("result") or {}
            page_users = page.get("list") or []
            users.extend(page_users)
            has_more = bool(page.get("has_more"))
            cursor = int(page.get("next_cursor") or 0)
            logger.debug(
                "Fetched %s users from department %s (cursor=%s, has_more=%s)",
                len(page_users),
                dept_id,
                cursor,
                has_more,
            )

        return users

    def get_user_detail(self, userid: str) -> Dict[str, Any]:
        """DingTalk contact/user/get equivalent (topapi v2 user get)."""
        result = self._post_topapi(
            "/topapi/v2/user/get",
            {"userid": userid, "language": "zh_CN"},
        )
        detail = result.get("result")
        if not detail:
            raise DingTalkAPIError(f"DingTalk returned no details for user {userid}", status_code=404)
        return detail

    def collect_all_department_ids(self, root_dept_id: int) -> List[int]:
        collected: List[int] = []
        queue = [root_dept_id]
        seen = set()

        while queue:
            dept_id = queue.pop(0)
            if dept_id in seen:
                continue
            seen.add(dept_id)
            collected.append(dept_id)
            for child_id in self.list_sub_department_ids(dept_id):
                if child_id not in seen:
                    queue.append(child_id)

        logger.info("Discovered %s departments starting from root %s", len(collected), root_dept_id)
        return collected

    def get_leave_approval_duration(self, userid: str, from_date: str, to_date: str) -> float:
        """DingTalk /attendance/getLeaveApprovalDuration - returns minutes."""
        result = self._post_topapi(
            "/topapi/attendance/getleaveapproveduration",
            {"userid": userid, "from_date": from_date, "to_date": to_date},
        )
        payload = result.get("result") or {}
        return float(payload.get("duration_in_minutes") or 0)

    def get_overtime_approval_duration(self, userid: str, from_date: str, to_date: str) -> float:
        """DingTalk /attendance/getOvertimeApprovalDuration - returns minutes when available."""
        try:
            result = self._post_topapi(
                "/topapi/attendance/getovertimeapproveduration",
                {"userid": userid, "from_date": from_date, "to_date": to_date},
            )
            payload = result.get("result") or {}
            if "duration_in_minutes" in payload:
                return float(payload.get("duration_in_minutes") or 0)
            if "duration" in payload:
                return float(payload.get("duration") or 0) * 60.0
        except DingTalkAPIError as exc:
            logger.warning(
                "getovertimeapproveduration unavailable for %s, falling back to approval data: %s",
                userid,
                exc.message,
            )
        return 0.0

    def get_leave_time_by_names(
        self,
        userid: str,
        leave_names: str,
        from_date: str,
        to_date: str,
    ) -> Dict[str, Any]:
        return self._post_topapi(
            "/topapi/attendance/getleavetimebynames",
            {
                "userid": userid,
                "leave_names": leave_names,
                "from_date": from_date,
                "to_date": to_date,
            },
        )

    def get_attendance_update_data(self, userid: str, work_date: str) -> Dict[str, Any]:
        return self._post_topapi(
            "/topapi/attendance/getupdatedata",
            {"userid": userid, "work_date": work_date},
        )

    def _post_topapi(self, path: str, body: Dict[str, Any], max_retries: int = 4) -> Dict[str, Any]:
        last_error: Optional[str] = None

        for attempt in range(max_retries):
            self._throttle()
            access_token = self.get_access_token(force_refresh=attempt > 0 and last_error == "token_expired")
            url = f"{self.OAPI_BASE_URL}{path}"

            try:
                with httpx.Client(timeout=20.0) as client:
                    response = client.post(url, params={"access_token": access_token}, json=body)
            except httpx.RequestError as exc:
                last_error = str(exc)
                logger.warning("DingTalk API request failed (%s): %s", path, exc)
                time.sleep(2 ** attempt)
                continue

            data = self._parse_json_response(response, allow_errcode=True)
            errcode = data.get("errcode", 0)
            if errcode in (0, "0"):
                return data

            errmsg = data.get("errmsg") or data.get("message") or "Unknown DingTalk API error"
            last_error = errmsg
            logger.warning(
                "DingTalk API error on %s (attempt %s/%s): [%s] %s",
                path,
                attempt + 1,
                max_retries,
                errcode,
                errmsg,
            )

            if errcode in RATE_LIMIT_ERRCODES:
                sleep_seconds = settings.dingtalk_rate_limit_backoff_seconds * (2 ** attempt)
                logger.info("Rate limited by DingTalk, sleeping %s seconds", sleep_seconds)
                time.sleep(sleep_seconds)
                continue

            if errcode in {40014, 42001, 88} or "token" in errmsg.lower():
                self._access_token = None
                self._token_expires_at = None
                last_error = "token_expired"
                continue

            raise DingTalkAPIError(f"DingTalk API error [{errcode}]: {errmsg}")

        raise DingTalkAPIError(f"DingTalk API request failed after retries: {last_error}")

    def _throttle(self) -> None:
        delay = settings.dingtalk_api_delay_ms / 1000.0
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < delay:
            time.sleep(delay - elapsed)
        self._last_request_at = time.monotonic()

    @staticmethod
    def _parse_json_response(response: httpx.Response, allow_errcode: bool = False) -> Dict[str, Any]:
        try:
            data = response.json()
        except ValueError as exc:
            raise DingTalkAPIError("DingTalk returned invalid JSON") from exc

        if response.status_code >= 400 and not allow_errcode:
            message = data.get("message") or data.get("errmsg") or "DingTalk API request failed"
            raise DingTalkAPIError(message, status_code=response.status_code)

        return data if isinstance(data, dict) else {}


dingtalk_corp_client = DingTalkCorpClient()

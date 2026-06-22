"""
Two-step Excel workflow helpers (legacy alias).

Prefer ``app.services.excel_converter`` for upload-and-convert flows.
"""

from __future__ import annotations

from typing import Optional

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.models import User
from app.services.excel_converter import ExcelConverterError, convert_dingtalk_upload_to_workbook
from app.services.excel_generator import ExcelExportResult

ExcelWorkflowError = ExcelConverterError


async def generate_full_excel_from_dingtalk_upload(
    db: Session,
    user: User,
    year: int,
    month: int,
    upload: UploadFile,
) -> ExcelExportResult:
    """Backward-compatible wrapper around the excel converter service."""
    return await convert_dingtalk_upload_to_workbook(
        db,
        user,
        upload,
        year=year,
        month=month,
    )

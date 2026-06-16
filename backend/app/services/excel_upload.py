"""
Excel upload orchestration: save upload, parse workbook, detect changes.
"""

from __future__ import annotations

import logging
import os
import tempfile
from dataclasses import dataclass, field
from typing import List

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.models import User
from app.services.change_detector import (
    ChangeDetectionResult,
    ChangeDetectorError,
    detect_and_record_changes,
)
from app.services.excel_parser import ExcelParserError, parse_uploaded_workbook

logger = logging.getLogger(__name__)

UPLOAD_CHUNK_SIZE = 1024 * 1024


class ExcelUploadError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


@dataclass
class DetectedChange:
    employee_id: int
    employee_name: str
    field_name: str
    old_value: str
    new_value: str
    conflict: bool = False
    conflict_id: int | None = None


@dataclass
class ExcelUploadResult:
    year: int
    month: int
    snapshot_id: int
    changes_detected: int
    conflicts_created: int
    employees_modified: int
    pending_conflicts_count: int
    auto_merged: int = 0
    has_conflicts: bool = False
    conflicts_list: List[dict] = field(default_factory=list)
    changes: List[DetectedChange] = field(default_factory=list)


async def _save_upload_to_tempfile(upload: UploadFile) -> str:
    suffix = ".xlsx"
    if upload.filename and upload.filename.lower().endswith(".xlsm"):
        suffix = ".xlsm"

    fd, temp_path = tempfile.mkstemp(prefix="excel_upload_", suffix=suffix)
    os.close(fd)
    try:
        with open(temp_path, "wb") as handle:
            while True:
                chunk = await upload.read(UPLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                handle.write(chunk)
        return temp_path
    except Exception:
        os.unlink(temp_path)
        raise


def _map_detection_result(result: ChangeDetectionResult) -> ExcelUploadResult:
    return ExcelUploadResult(
        year=result.year,
        month=result.month,
        snapshot_id=result.snapshot_id,
        changes_detected=result.total_changes,
        employees_modified=result.employees_affected,
        conflicts_created=result.conflicts_created,
        pending_conflicts_count=result.pending_conflicts_count,
        auto_merged=result.auto_merged,
        has_conflicts=result.has_conflicts,
        conflicts_list=result.conflicts_list,
        changes=[
            DetectedChange(
                employee_id=change.employee_id,
                employee_name=change.employee_name,
                field_name=change.field_name,
                old_value=change.old_value,
                new_value=change.new_value,
                conflict=change.conflict,
                conflict_id=change.conflict_id,
            )
            for change in result.changes
        ],
    )


async def handle_excel_upload(
    db: Session,
    user: User,
    year: int,
    month: int,
    upload: UploadFile,
) -> ExcelUploadResult:
    if not upload.filename or not upload.filename.lower().endswith((".xlsx", ".xlsm")):
        raise ExcelUploadError("File must be an Excel workbook (.xlsx)")

    temp_path = await _save_upload_to_tempfile(upload)
    try:
        try:
            parsed = parse_uploaded_workbook(temp_path, year=year, month=month)
        except ExcelParserError as exc:
            raise ExcelUploadError(exc.message, status_code=exc.status_code) from exc
        except Exception as exc:
            logger.warning("Failed to parse uploaded workbook: %s", exc)
            raise ExcelUploadError(
                "Invalid or malformed Excel file. Ensure it is a valid .xlsx workbook "
                'with the "月度汇总" worksheet.',
            ) from exc

        try:
            detection_result = detect_and_record_changes(db, user, year, month, parsed)
        except ChangeDetectorError as exc:
            raise ExcelUploadError(exc.message, status_code=exc.status_code) from exc

        return _map_detection_result(detection_result)
    finally:
        try:
            os.unlink(temp_path)
        except OSError:
            logger.warning("Failed to remove upload temp file: %s", temp_path)

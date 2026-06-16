"""
Excel download orchestration: snapshot persistence, export, and activity logging.
"""

from __future__ import annotations

import logging
from typing import Iterator

from sqlalchemy.orm import Session

from app.excel.attendance_export import (
    AttendanceExcelError,
    ExcelExportResult,
    generate_attendance_excel,
)
from app.models import ExcelSnapshot, User
from app.services.snapshot_service import create_snapshot

logger = logging.getLogger(__name__)

STREAM_CHUNK_SIZE = 64 * 1024


def stream_file_chunks(path, chunk_size: int = STREAM_CHUNK_SIZE) -> Iterator[bytes]:
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            yield chunk


class ExcelDownloadResult:
    def __init__(self, export: ExcelExportResult, snapshot_id: int):
        self.export = export
        self.snapshot_id = snapshot_id
        self._snapshot: ExcelSnapshot | None = None

    @property
    def snapshot(self) -> ExcelSnapshot | None:
        return self._snapshot

    def bind_snapshot(self, snapshot: ExcelSnapshot) -> None:
        self._snapshot = snapshot

    @property
    def filename(self) -> str:
        return self.export.filename

    def iter_content(self) -> Iterator[bytes]:
        return stream_file_chunks(self.export.path)

    def cleanup(self) -> None:
        self.export.cleanup()


def prepare_excel_download(
    db: Session,
    user: User,
    year: int,
    month: int,
) -> ExcelDownloadResult:
    if month < 1 or month > 12:
        raise AttendanceExcelError("Month must be between 1 and 12")

    export_result = generate_attendance_excel(db, user.company_id, year, month)
    file_size = export_result.path.stat().st_size

    snapshot_id = create_snapshot(
        db,
        user.company_id,
        year,
        month,
        user.id,
        dingtalk_sync_timestamp=None,
        file_name=export_result.filename,
        file_size=file_size,
    )

    snapshot = db.query(ExcelSnapshot).filter(ExcelSnapshot.id == snapshot_id).first()

    logger.info(
        "Excel download prepared: user_id=%s company_id=%s period=%s-%02d "
        "snapshot_id=%s version=v%s employees=%s file=%s bytes=%s",
        user.id,
        user.company_id,
        year,
        month,
        snapshot_id,
        snapshot.snapshot_version if snapshot else None,
        export_result.employee_count,
        export_result.filename,
        file_size,
    )

    result = ExcelDownloadResult(export=export_result, snapshot_id=snapshot_id)
    if snapshot:
        result.bind_snapshot(snapshot)
    return result

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class SyncState:
    employees_synced_at: Optional[datetime] = None
    attendance_synced_at: Optional[datetime] = None
    leaves_synced_at: Optional[datetime] = None
    overtime_synced_at: Optional[datetime] = None


sync_state = SyncState()

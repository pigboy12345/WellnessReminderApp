from dataclasses import dataclass
from datetime import time as dtime
from typing import Optional


@dataclass
class Reminder:
    id: str
    title: str
    message: str
    category: str
    scheduling_time: dtime
    enabled: bool
    icon: Optional[str] = None
    # Runtime status, one of:
    # Pending / Triggered / Completed / Dismissed / Snoozed / Skipped / Failed
    status: str = "Pending"
    error_message: Optional[str] = None
    snooze_count: int = 0

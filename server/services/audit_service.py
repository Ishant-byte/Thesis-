from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Optional
from server.db.mongo import get_db

def now_utc():
    return datetime.now(timezone.utc)

def log_event(
    event_type: str,
    actor_username: Optional[str],
    target_username: Optional[str],
    message: str,
    metadata: Optional[dict[str, Any]] = None,
    severity: str = "INFO",
):
    db = get_db()
    doc = {
        "timestamp": now_utc(),
        "event_type": event_type,
        "severity": severity,
        "actor_username": actor_username,
        "target_username": target_username,
        "message": message,
        "metadata": metadata or {},
    }
    db.audit_logs.insert_one(doc)

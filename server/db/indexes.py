from __future__ import annotations
from pymongo import ASCENDING, DESCENDING
from server.db.mongo import get_db

def ensure_indexes():
    db = get_db()

    db.users.create_index([("username", ASCENDING)], unique=True)
    db.users.create_index([("role", ASCENDING)])
    db.users.create_index([("locked_until", ASCENDING)])

    db.audit_logs.create_index([("timestamp", DESCENDING)])
    db.audit_logs.create_index([("actor_username", ASCENDING), ("timestamp", DESCENDING)])
    db.audit_logs.create_index([("target_username", ASCENDING), ("timestamp", DESCENDING)])
    db.audit_logs.create_index([("event_type", ASCENDING), ("timestamp", DESCENDING)])


    db.notices.create_index([("created_at", DESCENDING)])

    db.chat_sessions.create_index([("participants_key", ASCENDING)], unique=True)
    db.chat_messages.create_index([("session_id", ASCENDING), ("created_at", DESCENDING)])
    # TTL index for disappearing messages
    db.chat_messages.create_index([("expireAt", ASCENDING)], expireAfterSeconds=0)

    db.documents.create_index([("owner_username", ASCENDING), ("created_at", DESCENDING)])

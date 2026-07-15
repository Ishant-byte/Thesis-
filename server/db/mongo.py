from __future__ import annotations

import sys
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError
from server.config.settings import MONGO_URI, MONGO_DB

_client: MongoClient | None = None

def get_client() -> MongoClient:
    global _client
    if _client is None:
        _client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000)
        try:
            _client.admin.command("ping")
        except ServerSelectionTimeoutError as e:
            print(f"[PramaanHR] MongoDB not reachable at {MONGO_URI}. Start MongoDB first.")
            raise SystemExit(2) from e
    return _client

def get_db():
    return get_client()[MONGO_DB]

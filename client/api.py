from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Optional

import requests

SERVER_HOST = os.getenv("SERVER_HOST", "127.0.0.1")
SERVER_PORT = int(os.getenv("SERVER_PORT", "8765"))
BASE = f"http://{SERVER_HOST}:{SERVER_PORT}"

class APIError(Exception):
    pass

def health() -> dict:
    r = requests.get(f"{BASE}/health", timeout=2)
    r.raise_for_status()
    return r.json()

def post(path: str, payload: dict, token: str | None = None) -> dict:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = requests.post(f"{BASE}{path}", json=payload, headers=headers, timeout=10)
    if r.status_code >= 400:
        try:
            detail = r.json().get("detail", r.text)
        except Exception:
            detail = r.text
        raise APIError(str(detail))
    return r.json()

def put(path: str, payload: dict, token: str) -> dict:
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
    r = requests.put(f"{BASE}{path}", json=payload, headers=headers, timeout=10)
    if r.status_code >= 400:
        try:
            detail = r.json().get("detail", r.text)
        except Exception:
            detail = r.text
        raise APIError(str(detail))
    return r.json()

def get(path: str, token: str | None = None, params: dict | None = None) -> dict:
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = requests.get(f"{BASE}{path}", headers=headers, params=params, timeout=10)
    if r.status_code >= 400:
        try:
            detail = r.json().get("detail", r.text)
        except Exception:
            detail = r.text
        raise APIError(str(detail))
    return r.json()

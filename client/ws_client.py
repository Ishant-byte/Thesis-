from __future__ import annotations

import json
import threading
import time
from typing import Callable, Optional

import websocket

class WSClient:
    def __init__(self, ws_url: str, on_message: Callable[[dict], None], on_close: Callable[[], None] | None = None):
        self.ws_url = ws_url
        self.on_message = on_message
        self.on_close = on_close or (lambda: None)
        self._app: websocket.WebSocketApp | None = None
        self._thread: threading.Thread | None = None

    def start(self):
        def _on_message(app, msg):
            try:
                self.on_message(json.loads(msg))
            except Exception:
                pass
        def _on_close(app, code, reason):
            self.on_close()
        self._app = websocket.WebSocketApp(
            self.ws_url,
            on_message=_on_message,
            on_close=_on_close,
        )
        self._thread = threading.Thread(target=self._app.run_forever, daemon=True)
        self._thread.start()

    def send(self, payload: dict):
        if self._app and self._app.sock and self._app.sock.connected:
            try:
                self._app.send(json.dumps(payload))
            except Exception:
                pass

    def stop(self):
        try:
            if self._app:
                self._app.close()
        except Exception:
            pass

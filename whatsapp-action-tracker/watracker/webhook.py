"""Continuous ingestion via the official WhatsApp Business Cloud API.

``watracker serve`` runs a small HTTP endpoint that Meta's webhook can call:

* ``GET  /`` — subscription verification (echoes ``hub.challenge`` when
  ``hub.verify_token`` matches ``--verify-token`` / ``WA_VERIFY_TOKEN``).
* ``POST /`` — message notifications. Each text message is converted to a
  :class:`watracker.parser.Message` and run through the normal extraction
  pipeline, so tasks appear in the tracker in near-real time.

If ``WA_APP_SECRET`` is set, the ``X-Hub-Signature-256`` header is verified
(HMAC-SHA256 of the raw body) and unsigned requests are rejected.

This uses only the standard library; put a TLS-terminating proxy in front of
it for production (Meta requires HTTPS callbacks).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import List
from urllib.parse import parse_qs, urlparse

from .extractor import extract
from .parser import Message
from .store import Store


def messages_from_payload(payload: dict) -> List[Message]:
    """Convert a Cloud API webhook payload into Message objects."""
    out: List[Message] = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            names = {
                c.get("wa_id"): (c.get("profile") or {}).get("name")
                for c in value.get("contacts", [])
            }
            chat = (value.get("metadata") or {}).get("display_phone_number", "WhatsApp")
            for msg in value.get("messages", []):
                if msg.get("type") != "text":
                    continue
                body = (msg.get("text") or {}).get("body", "").strip()
                if not body:
                    continue
                try:
                    ts = datetime.fromtimestamp(int(msg.get("timestamp", 0)))
                except (ValueError, OSError, OverflowError):
                    ts = datetime.now()
                sender = names.get(msg.get("from")) or msg.get("from")
                out.append(Message(timestamp=ts, sender=sender, text=body, chat=chat))
    return out


def _make_handler(store: Store, verify_token: str, app_secret: str):
    from .cli import apply_extraction  # late import to avoid a cycle

    class Handler(BaseHTTPRequestHandler):
        server_version = "watracker"

        def log_message(self, fmt, *args):  # quieter default logging
            print(f"[webhook] {fmt % args}")

        def _respond(self, code: int, body: str = ""):
            data = body.encode()
            self.send_response(code)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            qs = parse_qs(urlparse(self.path).query)
            mode = qs.get("hub.mode", [""])[0]
            token = qs.get("hub.verify_token", [""])[0]
            challenge = qs.get("hub.challenge", [""])[0]
            if mode == "subscribe" and verify_token and token == verify_token:
                self._respond(200, challenge)
            else:
                self._respond(403, "verification failed")

        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length)
            if app_secret:
                expected = "sha256=" + hmac.new(app_secret.encode(), raw, hashlib.sha256).hexdigest()
                received = self.headers.get("X-Hub-Signature-256", "")
                if not hmac.compare_digest(expected, received):
                    self._respond(401, "bad signature")
                    return
            try:
                payload = json.loads(raw.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                self._respond(400, "invalid json")
                return
            messages = messages_from_payload(payload)
            if messages:
                counts = apply_extraction(store, extract(messages))
                print(
                    f"[webhook] {len(messages)} message(s): "
                    f"+{counts['added']} tasks, {counts['closed']} closed, {counts['outcomes']} outcomes"
                )
            self._respond(200, "ok")

    return Handler


def serve(store: Store, host: str = "0.0.0.0", port: int = 8080,
          verify_token: str = "", app_secret: str = "") -> None:
    verify_token = verify_token or os.environ.get("WA_VERIFY_TOKEN", "")
    app_secret = app_secret or os.environ.get("WA_APP_SECRET", "")
    if not verify_token:
        raise RuntimeError("Set a verify token (--verify-token or WA_VERIFY_TOKEN) before serving.")
    server = ThreadingHTTPServer((host, port), _make_handler(store, verify_token, app_secret))
    print(f"watracker webhook listening on {host}:{port} "
          f"(signature check {'ON' if app_secret else 'off — set WA_APP_SECRET'})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()

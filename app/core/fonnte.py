"""Client for Fonnte (unofficial WhatsApp Web gateway — docs.fonnte.com).

One platform-owned Fonnte account provisions a "device" (a QR-linked WhatsApp
session) per client bot. Account-token calls create/list devices; each device
then has its OWN token for device-scoped calls (QR, webhook config, send).

Not Meta's official WhatsApp Business API — no signature verification on
webhooks, no 24-hour customer-service messaging window. Routing/auth for our
inbound webhooks is handled entirely via the URL itself (channel id + secret),
see app/api/v1/endpoints/whatsapp.py.
"""
from __future__ import annotations

import httpx

from app.core import config_store

BASE_URL = "https://api.fonnte.com"
_TIMEOUT = 30.0


class FonnteError(Exception):
    """A Fonnte API call returned status: false, or the HTTP call itself failed."""


def _account_token() -> str:
    token = config_store.get("FONNTE_ACCOUNT_TOKEN")
    if not token:
        raise FonnteError("FONNTE_ACCOUNT_TOKEN is not configured — set it in Settings.")
    return token


def _post(path: str, token: str, data: dict) -> dict:
    resp = httpx.post(f"{BASE_URL}{path}", headers={"Authorization": token},
                      data=data, timeout=_TIMEOUT)
    resp.raise_for_status()
    body = resp.json()
    if body.get("status") is False:
        raise FonnteError(body.get("reason") or f"Fonnte {path} failed: {body}")
    return body


def add_device(name: str, device_number: str) -> dict:
    """Create a new device slot under the platform account. Returns the Fonnte
    response, which includes the device's own token — that token (not the
    account token) is used for every subsequent call scoped to this device."""
    return _post("/add-device", _account_token(), {"name": name, "device": device_number})


def update_device(device_token: str, webhook_url: str, webhook_connect_url: str) -> dict:
    """Point this device's inbound-message and connect/disconnect webhooks at us,
    and enable autoread (required for the message webhook to fire per Fonnte docs)."""
    return _post("/update-device", device_token, {
        "webhook": webhook_url,
        "webhookconnect": webhook_connect_url,
        "autoread": True,
        "personal": True,
    })


class AlreadyConnected(FonnteError):
    """The device is already linked — not a real failure, just nothing to show a QR for."""


def get_qr(device_token: str) -> dict:
    """Returns {"status": true, "url": "<base64 PNG>"} to display."""
    try:
        return _post("/qr", device_token, {"type": "qr"})
    except FonnteError as e:
        if "already connect" in str(e).lower():
            raise AlreadyConnected(str(e)) from e
        raise


def send_message(device_token: str, target: str, message: str) -> dict:
    return _post("/send", device_token, {"target": target, "message": message})


def disconnect_device(device_token: str) -> dict:
    try:
        return _post("/disconnect", device_token, {})
    except FonnteError as e:
        if "already disconnected" in str(e).lower():
            return {"status": True, "detail": "already disconnected"}
        raise


def get_devices() -> dict:
    """Account-level: list every device and its live connection status."""
    resp = httpx.post(f"{BASE_URL}/get-devices", headers={"Authorization": _account_token()},
                      timeout=_TIMEOUT)
    resp.raise_for_status()
    return resp.json()

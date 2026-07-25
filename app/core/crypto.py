"""Field-level encryption for secrets stored in the DB (e.g. Channel.access_token).

`cryptography` is already an installed transitive dep (python-jose[cryptography]
in requirements.txt), so no new dependency. Keyed by FIELD_ENCRYPTION_KEY, resolved
through config_store (DB setting first, env fallback) — same pattern as every other
managed secret, so it can be set via the admin panel without a redeploy.

Deliberately a SEPARATE key from JWT SECRET_KEY: rotating one should never affect
the other, and mixing purposes on one secret is a smell.
"""
from __future__ import annotations

from app.core import config_store


def _fernet():
    from cryptography.fernet import Fernet  # lazy import so the app boots without the package configured

    key = config_store.get("FIELD_ENCRYPTION_KEY")
    if not key:
        raise RuntimeError(
            "FIELD_ENCRYPTION_KEY is not configured — required to store a WhatsApp "
            "channel's access token. Generate one with: "
            "python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())' "
            "and set it via the admin settings panel or FIELD_ENCRYPTION_KEY in .env."
        )
    return Fernet(key.encode())


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()

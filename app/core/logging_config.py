"""Application logging setup.

uvicorn configures only its own loggers (`uvicorn`, `uvicorn.error`,
`uvicorn.access`) and sets propagate=False on them, so the ROOT logger is left
without a handler. Application logs then fall through to Python's `lastResort`
handler, which emits WARNING and above with no timestamp and no logger name —
which is why per-request model/timing INFO lines (see app.core.llm) were
invisible in production while failures still appeared.

This attaches a real handler to the root logger so application logs are visible
and timestamped, while keeping chatty third-party libraries quiet.
"""
from __future__ import annotations

import logging
import sys

# Libraries that log a line per HTTP request at INFO. Every embedding call and
# every model call would emit one, drowning out our own logs — keep them at
# WARNING unless someone is explicitly debugging transport.
_NOISY_LIBRARIES = ("httpx", "httpcore", "openai", "urllib3")

_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_configured = False


def setup_logging(level: str = "INFO", noisy_level: str = "WARNING") -> None:
    """Attach a stdout handler to the root logger. Safe to call more than once.

    `level` sets the application log level; `noisy_level` caps the chatty HTTP
    libraries listed above.
    """
    global _configured
    if _configured:
        return

    root = logging.getLogger()
    root.setLevel(_coerce(level, logging.INFO))

    # uvicorn's own loggers keep their handlers (propagate=False), so this
    # handler serves application logs only — no double-printed access lines.
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_FORMAT, datefmt=_DATE_FORMAT))
    root.addHandler(handler)

    capped = _coerce(noisy_level, logging.WARNING)
    for name in _NOISY_LIBRARIES:
        logging.getLogger(name).setLevel(capped)

    _configured = True


def _coerce(level: str, default: int) -> int:
    """Map a level name to its numeric value, tolerating junk config."""
    resolved = logging.getLevelName((level or "").strip().upper())
    return resolved if isinstance(resolved, int) else default

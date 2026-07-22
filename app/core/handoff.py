"""Click-to-WhatsApp handoff: number normalization and the pre-filled message.

This is NOT the WhatsApp Business API (see `endpoints/whatsapp.py` for that).
It's a `wa.me` deep link the visitor taps, so the message is sent from the
visitor's own WhatsApp to the business owner. Consequences worth remembering:

- The visitor sees and can edit the text before sending, so nothing secret may
  go in it. It carries only what the visitor themselves just typed and read.
- The URL is subject to browser length limits, so the transcript is capped
  rather than sent whole; the full thread stays in the dashboard inbox and is
  found via the ref code.
"""
from __future__ import annotations

import re
from urllib.parse import quote

HANDOFF_MODES = ("form", "whatsapp", "both")

# Malaysia — the platform's home market. Only ever applied to numbers written in
# local trunk form ("01x-xxx xxxx"); anything already international is untouched.
DEFAULT_COUNTRY_CODE = "60"

# wa.me rejects anything that isn't a plausible international subscriber number.
_MIN_DIGITS = 7
_MAX_DIGITS = 15  # E.164 hard limit

# Keep well under the ~2000-char URL budget that the oldest browsers honour,
# leaving room for percent-encoding (which can triple the byte count of
# non-ASCII text) and the rest of the link.
MAX_TRANSCRIPT_CHARS = 600
MAX_TURNS = 6


def normalize_wa_number(raw: str | None, default_country: str = DEFAULT_COUNTRY_CODE) -> str | None:
    """Digits-only international number for wa.me, or None if it can't be one.

    Accepts the shapes people actually type: "+60 12-345 6789", "0060123456789",
    "012-345 6789", "60123456789".
    """
    if not raw:
        return None
    s = str(raw).strip()
    intl = s.startswith("+")
    digits = re.sub(r"\D", "", s)
    if not digits:
        return None

    if intl:
        pass  # already international, leading '+' merely stripped
    elif digits.startswith("00"):
        digits = digits[2:]  # international access prefix
    elif digits.startswith("0"):
        # National trunk prefix: drop the 0 and prepend the country code.
        digits = default_country + digits[1:]

    if not (_MIN_DIGITS <= len(digits) <= _MAX_DIGITS):
        return None
    return digits


def normalize_mode(raw: str | None) -> str:
    mode = (raw or "").strip().lower()
    return mode if mode in HANDOFF_MODES else "form"


def effective_mode(bot) -> str:
    """The mode actually usable right now.

    A bot set to `whatsapp`/`both` with no number would otherwise dead-end the
    visitor, so it degrades to the form rather than offering a broken link.
    """
    mode = normalize_mode(getattr(bot, "handoff_mode", None))
    if mode in ("whatsapp", "both") and not getattr(bot, "whatsapp_number", None):
        return "form"
    return mode


def ref_code(conversation_id: int) -> str:
    """Short human-readable handle so the owner can find the thread in the inbox."""
    return f"ATS-{conversation_id}"


def _label(role: str) -> str:
    return "Me" if role == "user" else "Assistant"


def build_message(messages: list, conversation_id: int, bot_name: str | None = None) -> str:
    """The pre-filled WhatsApp text: recent context, then the ref code.

    `messages` is oldest-first; the tail is what matters, so it's taken from the
    end and re-ordered for reading.
    """
    intro = "Hi! I was chatting with your assistant on your website and I need some help."

    recent = [m for m in messages if (m.content or "").strip()][-MAX_TURNS:]
    lines: list[str] = []
    used = 0
    # Walk backwards so that when the budget runs out we drop the OLDEST turns,
    # keeping the most recent exchange the owner needs to see.
    for m in reversed(recent):
        text = " ".join((m.content or "").split())
        entry = f"{_label(m.role)}: {text}"
        if len(entry) > 200:
            entry = entry[:197].rstrip() + "..."
        if used + len(entry) > MAX_TRANSCRIPT_CHARS:
            break
        lines.append(entry)
        used += len(entry)
    lines.reverse()

    blocks = [intro]
    if lines:
        blocks.append("--- our chat so far ---\n" + "\n".join(lines))
    blocks.append(f"(Ref {ref_code(conversation_id)})")
    return "\n\n".join(blocks)


def build_link(number: str, message: str) -> str:
    """A wa.me click-to-chat URL. `number` must already be normalized."""
    return f"https://wa.me/{number}?text={quote(message, safe='')}"

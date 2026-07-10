"""Split cleaned text into overlapping chunks for embedding.

Paragraph-aware: packs whole paragraphs up to `max_chars`, hard-splits any
paragraph longer than that, and carries a small character `overlap` between
consecutive chunks so context isn't lost at boundaries.
"""
from __future__ import annotations

import re

from app.core.settings import settings

_PARA_SPLIT = re.compile(r"\n\s*\n")


def _hard_split(text: str, max_chars: int, overlap: int) -> list[str]:
    step = max(1, max_chars - overlap)
    return [text[i : i + max_chars] for i in range(0, len(text), step)]


def chunk_text(
    text: str,
    max_chars: int | None = None,
    overlap: int | None = None,
) -> list[str]:
    max_chars = max_chars or settings.CHUNK_MAX_CHARS
    overlap = overlap if overlap is not None else settings.CHUNK_OVERLAP
    overlap = min(overlap, max_chars - 1)

    text = (text or "").strip()
    if not text:
        return []

    paragraphs = [p.strip() for p in _PARA_SPLIT.split(text) if p.strip()]
    chunks: list[str] = []
    current = ""

    for para in paragraphs:
        if len(para) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_hard_split(para, max_chars, overlap))
            continue

        candidate = f"{current}\n\n{para}".strip() if current else para
        if len(candidate) <= max_chars:
            current = candidate
            continue

        if current:
            chunks.append(current)
        # start the next chunk with a tail-overlap of the previous one
        tail = current[-overlap:] if overlap and current else ""
        combined = f"{tail}\n\n{para}".strip() if tail else para
        # The tail+para can exceed max_chars — re-check and hard-split if so, so
        # no emitted chunk ever breaks the max_chars contract.
        if len(combined) > max_chars:
            chunks.extend(_hard_split(combined, max_chars, overlap))
            current = ""
        else:
            current = combined

    if current:
        chunks.append(current)
    return chunks

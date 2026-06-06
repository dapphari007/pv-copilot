"""Lightweight, dependency-free text chunking for long narratives/documents.

A character-window splitter with overlap that prefers to break on sentence or
paragraph boundaries so chunks stay semantically coherent.
"""
from __future__ import annotations

import re

import config

_BOUNDARY = re.compile(r"(?<=[.!?])\s+|\n{2,}")


def chunk_text(
    text: str,
    chunk_size: int | None = None,
    overlap: int | None = None,
) -> list[str]:
    """Split ``text`` into overlapping chunks of roughly ``chunk_size`` chars."""
    chunk_size = chunk_size or config.CHUNK_SIZE
    overlap = overlap if overlap is not None else config.CHUNK_OVERLAP
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]

    # Build sentence-ish units, then greedily pack them into chunks.
    units = [u.strip() for u in _BOUNDARY.split(text) if u.strip()]
    chunks: list[str] = []
    current = ""
    for unit in units:
        if current and len(current) + len(unit) + 1 > chunk_size:
            chunks.append(current.strip())
            # Carry the tail of the previous chunk for context overlap.
            current = (current[-overlap:] + " " + unit) if overlap else unit
        else:
            current = f"{current} {unit}".strip()
    if current.strip():
        chunks.append(current.strip())
    return chunks

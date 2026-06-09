"""Detect distinct patient cases within an uploaded document.

Critical PRD requirement: a 2-patient document must yield exactly 2 reports —
never a phantom 3rd. We split on patient-boundary markers, then KEEP only
segments that extract a valid case (patient signal + drug + reaction). Empty or
spurious segments are discarded.
"""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from src import pv_extraction
from src.logging_config import get_logger

log = get_logger("case_detection")

# Ordered by preference: a patient-level marker beats a generic divider.
_MARKERS = [
    r"(?im)^\s*patient\s*id\s*[:#]",
    r"(?im)^\s*patient\s+information\b",
    r"(?im)^\s*patient\s*[#\-]?\s*\d+\b",
    r"(?im)^\s*case\s*id\s*[:#]",
    r"(?im)^[-=*_]{3,}\s*$",
]


def split_segments(text: str) -> list[str]:
    """Split a document into candidate patient segments using boundary markers."""
    text = (text or "").strip()
    if not text:
        return []
    for pattern in _MARKERS:
        positions = [m.start() for m in re.finditer(pattern, text)]
        if len(positions) >= 2:
            segments: list[str] = []
            for i, start in enumerate(positions):
                end = positions[i + 1] if i + 1 < len(positions) else len(text)
                segments.append(text[start:end].strip())
            if positions[0] > 0:  # attach any preamble to the first segment
                preamble = text[: positions[0]].strip()
                if preamble:
                    segments[0] = f"{preamble}\n{segments[0]}"
            segments = [s for s in segments if s]
            log.info("Split on %r -> %d candidate segment(s)", pattern, len(segments))
            return segments
    return [text]


def detect_cases(text: str) -> list[dict[str, Any]]:
    """Return validated, extracted patient cases (phantoms discarded)."""
    segments = split_segments(text)
    if not segments:
        return []

    def _extract(i: int, segment: str) -> dict[str, Any]:
        case = pv_extraction.extract_case(segment)
        case["_segment_index"] = i
        case["_segment_text"] = segment
        return case

    with ThreadPoolExecutor(max_workers=min(6, len(segments))) as pool:
        extracted = list(pool.map(lambda p: _extract(*p), enumerate(segments)))

    cases: list[dict[str, Any]] = []
    discarded = 0
    for case in extracted:
        if pv_extraction.is_valid_case(case):
            cases.append(case)
        else:
            discarded += 1
            log.info("Discarded empty/invalid segment %d (no drug+reaction).",
                     case.get("_segment_index", -1))
    log.info("Cases Found = %d (from %d segment(s); %d discarded)",
             len(cases), len(segments), discarded)
    return cases

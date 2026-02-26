from __future__ import annotations

import re
from pathlib import Path

from backend.caption_segment import CaptionSegment

_TIME_RE = re.compile(
    r"(?P<h>\d{2}):(?P<m>\d{2}):(?P<s>\d{2}),(?P<ms>\d{3})"
)


def _to_seconds(timestamp: str) -> float:
    match = _TIME_RE.fullmatch(timestamp.strip())
    if match is None:
        raise ValueError(f"Invalid SRT timestamp: {timestamp}")

    hours = int(match.group("h"))
    minutes = int(match.group("m"))
    seconds = int(match.group("s"))
    millis = int(match.group("ms"))
    return hours * 3600 + minutes * 60 + seconds + millis / 1000


def parse_srt_file(path: Path) -> list[CaptionSegment]:
    text = path.read_text(encoding="utf-8")
    blocks = [block.strip() for block in re.split(r"\n\s*\n", text) if block.strip()]

    segments: list[CaptionSegment] = []
    for block in blocks:
        lines = [line.rstrip() for line in block.splitlines() if line.strip()]
        if len(lines) < 2:
            continue

        if "-->" not in lines[1]:
            continue

        start_raw, end_raw = [part.strip() for part in lines[1].split("-->", maxsplit=1)]
        caption_text = " ".join(lines[2:]).strip()
        if not caption_text:
            continue

        segments.append(
            CaptionSegment(
                start=_to_seconds(start_raw),
                end=_to_seconds(end_raw),
                text=caption_text,
            )
        )

    return segments

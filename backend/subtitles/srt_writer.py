from __future__ import annotations

from pathlib import Path
from typing import Iterable

from backend.transcription.whisper_engine import CaptionSegment


def _to_srt_time(seconds: float) -> str:
    milliseconds = int(round(seconds * 1000))
    hours, rem = divmod(milliseconds, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, millis = divmod(rem, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def write_srt(segments: Iterable[CaptionSegment], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    for index, segment in enumerate(segments, start=1):
        lines.extend(
            [
                str(index),
                f"{_to_srt_time(segment.start)} --> {_to_srt_time(segment.end)}",
                segment.text,
                "",
            ]
        )

    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from backend.transcription.whisper_engine import CaptionSegment


def _to_ass_time(seconds: float) -> str:
    centiseconds = int(round(seconds * 100))
    hours, rem = divmod(centiseconds, 360000)
    minutes, rem = divmod(rem, 6000)
    secs, cs = divmod(rem, 100)
    return f"{hours}:{minutes:02}:{secs:02}.{cs:02}"


def _escape_ass_text(text: str) -> str:
    return text.replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}")


def write_ass(segments: Iterable[CaptionSegment], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    header = """[Script Info]
ScriptType: v4.00+
Collisions: Normal
PlayResX: 1920
PlayResY: 1080
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,44,&H00FFFFFF,&H000000FF,&H00111111,&H66000000,0,0,0,0,100,100,0,0,1,2,0,2,24,24,32,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    lines = [header]
    for segment in segments:
        lines.append(
            "Dialogue: 0,"
            f"{_to_ass_time(segment.start)},"
            f"{_to_ass_time(segment.end)},"
            "Default,,0,0,0,,"
            f"{_escape_ass_text(segment.text)}"
        )

    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path

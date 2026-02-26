from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CaptionSegment:
    start: float
    end: float
    text: str

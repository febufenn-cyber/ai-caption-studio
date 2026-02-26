from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Iterable

from backend.transcription.whisper_engine import CaptionSegment


class LyricSyncError(RuntimeError):
    """Raised when lyric synchronization input is invalid."""


def _normalize(text: str) -> str:
    lowered = text.lower().strip()
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", lowered)).strip()


def parse_lyrics_lines(raw_lyrics: str) -> list[str]:
    lines = [line.strip() for line in raw_lyrics.splitlines()]
    cleaned = [line for line in lines if line]
    if not cleaned:
        raise LyricSyncError("Lyrics synchronization mode was enabled, but no lyrics were provided.")
    return cleaned


def sync_segments_to_lyrics(
    segments: Iterable[CaptionSegment],
    lyrics_lines: list[str],
    min_similarity: float = 0.25,
) -> list[CaptionSegment]:
    """Align transcribed segments to user lyrics with fuzzy matching.

    We preserve original timestamps and replace text with best matching lyric line.
    A greedy forward-only search prevents line reordering in final synced lyrics.
    """
    synced: list[CaptionSegment] = []
    lyric_idx = 0

    for segment in segments:
        if lyric_idx >= len(lyrics_lines):
            break

        segment_norm = _normalize(segment.text)
        if not segment_norm:
            continue

        best_idx = lyric_idx
        best_score = -1.0

        search_end = min(len(lyrics_lines), lyric_idx + 6)
        for idx in range(lyric_idx, search_end):
            score = SequenceMatcher(None, segment_norm, _normalize(lyrics_lines[idx])).ratio()
            if score > best_score:
                best_score = score
                best_idx = idx

        if best_score < min_similarity:
            chosen_text = lyrics_lines[lyric_idx]
            lyric_idx += 1
        else:
            chosen_text = lyrics_lines[best_idx]
            lyric_idx = best_idx + 1

        synced.append(CaptionSegment(start=segment.start, end=segment.end, text=chosen_text))

    if not synced:
        raise LyricSyncError("Lyrics synchronization produced no aligned segments.")

    return synced

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class AudioExtractionError(RuntimeError):
    """Raised when ffmpeg audio extraction fails."""


def ensure_ffmpeg_available() -> None:
    """Ensure FFmpeg is installed and available in PATH."""
    if shutil.which("ffmpeg") is None:
        raise AudioExtractionError(
            "FFmpeg executable was not found in PATH.\n"
            "Install FFmpeg and retry:\n"
            "  - Ubuntu/Debian: sudo apt-get update && sudo apt-get install -y ffmpeg\n"
            "  - macOS (Homebrew): brew install ffmpeg\n"
            "  - Windows (winget): winget install Gyan.FFmpeg"
        )


def extract_audio(video_path: Path, audio_path: Path, sample_rate: int = 16000) -> Path:
    """Extract mono WAV audio from a video file using FFmpeg."""
    ensure_ffmpeg_available()

    if not video_path.exists():
        raise AudioExtractionError(f"Input video not found: {video_path}")

    audio_path.parent.mkdir(parents=True, exist_ok=True)

    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-ar",
        str(sample_rate),
        "-ac",
        "1",
        str(audio_path),
    ]

    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise AudioExtractionError(
            "FFmpeg failed while extracting audio.\n"
            f"Command: {' '.join(command)}\n"
            f"Error: {result.stderr.strip()}"
        )

    return audio_path

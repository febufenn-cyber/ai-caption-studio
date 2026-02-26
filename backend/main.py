from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

from backend.subtitles.lyric_sync import (
    LyricSyncError,
    parse_lyrics_lines,
    sync_segments_to_lyrics,
)
from backend.subtitles.srt_writer import write_srt
from backend.transcription.whisper_engine import TranscriptionError, WhisperTranscriber
from backend.video.extractor import AudioExtractionError, extract_audio


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEMP_DIR = PROJECT_ROOT / "temp"
MODELS_DIR = PROJECT_ROOT / "models"
OUTPUT_DIR = PROJECT_ROOT / "output"


class RuntimeDependencyError(RuntimeError):
    """Raised when required runtime dependencies are missing."""


def ensure_runtime_dependencies() -> None:
    """Validate required Python dependencies are installed."""
    if importlib.util.find_spec("faster_whisper") is None:
        raise RuntimeDependencyError(
            "Missing Python package 'faster-whisper'. "
            "Run './scripts/setup.sh' to install dependencies."
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Offline AI Caption Studio")
    parser.add_argument("video_file", type=Path, help="Input video file path")
    parser.add_argument(
        "--model-size",
        default="small",
        help="Whisper model size (tiny, base, small, medium, large-v3)",
    )
    parser.add_argument(
        "--language",
        default=None,
        help="Optional language code (e.g. en, es, fr). Auto-detect if omitted.",
    )
    parser.add_argument(
        "--compute-type",
        default="int8",
        help="faster-whisper compute type, e.g. int8, float16, float32",
    )
    parser.add_argument(
        "--lyrics-file",
        type=Path,
        default=None,
        help="Optional path to plain-text lyrics for lyric synchronization mode.",
    )
    parser.add_argument(
        "--lyrics-stdin",
        action="store_true",
        help="Read lyrics text from standard input for synchronization mode.",
    )
    return parser.parse_args()


def _read_lyrics_text(args: argparse.Namespace) -> str | None:
    if args.lyrics_file and args.lyrics_stdin:
        raise LyricSyncError("Use either --lyrics-file or --lyrics-stdin, not both.")

    if args.lyrics_file is not None:
        if not args.lyrics_file.exists():
            raise LyricSyncError(f"Lyrics file not found: {args.lyrics_file}")
        return args.lyrics_file.read_text(encoding="utf-8")

    if args.lyrics_stdin:
        return sys.stdin.read()

    return None


def run() -> Path:
    args = parse_args()
    try:
        ensure_runtime_dependencies()
    except RuntimeDependencyError as exc:
        raise SystemExit(str(exc)) from exc

    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    output_path = OUTPUT_DIR / f"{args.video_file.stem}.srt"
    audio_path = TEMP_DIR / f"{args.video_file.stem}.wav"

    try:
        extract_audio(args.video_file, audio_path)

        transcriber = WhisperTranscriber(
            model_size=args.model_size,
            model_dir=MODELS_DIR,
            compute_type=args.compute_type,
        )
        segments = transcriber.transcribe(audio_path, language=args.language)

        lyrics_text = _read_lyrics_text(args)
        if lyrics_text is not None:
            lyrics_lines = parse_lyrics_lines(lyrics_text)
            segments = sync_segments_to_lyrics(segments, lyrics_lines)

        write_srt(segments, output_path)
    except (AudioExtractionError, TranscriptionError, LyricSyncError) as exc:
        raise SystemExit(str(exc)) from exc

    print(f"SRT exported: {output_path}")
    return output_path


if __name__ == "__main__":
    run()

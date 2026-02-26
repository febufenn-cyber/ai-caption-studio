from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List

from faster_whisper import WhisperModel


@dataclass
class CaptionSegment:
    start: float
    end: float
    text: str


class TranscriptionError(RuntimeError):
    """Raised when faster-whisper cannot transcribe the provided audio."""


class WhisperTranscriber:
    """Offline transcription service backed by faster-whisper."""

    def __init__(
        self,
        model_size: str = "small",
        model_dir: Path | None = None,
        compute_type: str = "int8",
    ) -> None:
        self.model_size = model_size
        self.model_dir = str(model_dir) if model_dir else None
        self.compute_type = compute_type

        try:
            self._model = WhisperModel(
                model_size_or_path=self.model_size,
                download_root=self.model_dir,
                compute_type=self.compute_type,
            )
        except Exception as exc:  # noqa: BLE001
            raise TranscriptionError(
                "Unable to initialize faster-whisper model. "
                "If this is your first run, ensure internet is available for model download. "
                "After the model is downloaded to ./models, runs are fully offline.\n"
                f"Details: {exc}"
            ) from exc

    def transcribe(
        self,
        audio_path: Path,
        language: str | None = None,
        beam_size: int = 5,
    ) -> List[CaptionSegment]:
        try:
            segments, _ = self._model.transcribe(
                str(audio_path),
                language=language,
                beam_size=beam_size,
                vad_filter=True,
            )
        except Exception as exc:  # noqa: BLE001
            raise TranscriptionError(f"Transcription failed: {exc}") from exc

        return [
            CaptionSegment(start=s.start, end=s.end, text=s.text.strip())
            for s in segments
            if s.text and s.text.strip()
        ]

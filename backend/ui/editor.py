from __future__ import annotations

import argparse
import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from typing import Callable

def _resolve_pyqt_plugins_path() -> Path | None:
    spec = importlib.util.find_spec("PyQt6")
    if spec is None or spec.origin is None:
        return None

    plugins_path = Path(spec.origin).resolve().parent / "Qt6" / "plugins"
    if plugins_path.exists():
        return plugins_path
    return None


def _configure_qt_runtime_environment() -> None:
    if sys.platform != "darwin":
        return

    # macOS native backend is more reliable than Qt's ffmpeg backend in venv installs.
    os.environ.setdefault("QT_MEDIA_BACKEND", "darwin")

    plugins_path = _resolve_pyqt_plugins_path()
    if plugins_path is None:
        return

    existing = os.environ.get("QT_PLUGIN_PATH")
    if not existing:
        os.environ["QT_PLUGIN_PATH"] = str(plugins_path)
        return

    existing_paths = existing.split(os.pathsep)
    if str(plugins_path) not in existing_paths:
        os.environ["QT_PLUGIN_PATH"] = os.pathsep.join([str(plugins_path), existing])


_configure_qt_runtime_environment()


from PyQt6.QtCore import QLibraryInfo, QPointF, QRectF, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QAction, QBrush, QColor, QPen
from PyQt6.QtMultimedia import QAudioOutput, QMediaFormat, QMediaPlayer
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QStyle,
    QToolBar,
    QVBoxLayout,
    QWidget,
    QComboBox,
)

from backend.subtitles.ass_writer import write_ass
from backend.subtitles.srt_parser import parse_srt_file
from backend.subtitles.srt_writer import write_srt
from backend.caption_segment import CaptionSegment
from backend.video.extractor import AudioExtractionError, ensure_ffmpeg_available


PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = PROJECT_ROOT / "output"
TEMP_DIR = PROJECT_ROOT / "temp"


def _multimedia_troubleshooting_message(error_detail: str | None = None) -> str:
    lines = []
    if error_detail:
        lines.append(error_detail)
    lines.extend(
        [
            "QtMultimedia backend failed to initialize.",
            f"QT_MEDIA_BACKEND={os.environ.get('QT_MEDIA_BACKEND', '(unset)')}",
            f"QT_PLUGIN_PATH={os.environ.get('QT_PLUGIN_PATH', '(unset)')}",
            f"Qt plugins path={QLibraryInfo.path(QLibraryInfo.LibraryPath.PluginsPath)}",
            "",
            "Recommended fixes:",
            "1) Recreate the venv with Python 3.10+ using ./scripts/setup.sh",
            "2) Remove conflicting shell vars: QT_PLUGIN_PATH and QT_QPA_PLATFORM_PLUGIN_PATH",
            "3) On macOS, use the native backend: export QT_MEDIA_BACKEND=darwin",
            "4) If you force ffmpeg backend, install matching FFmpeg 7 libraries: brew install ffmpeg@7",
        ]
    )
    return "\n".join(lines)


def _validate_multimedia_backend() -> str | None:
    try:
        decode_formats = QMediaFormat().supportedFileFormats(QMediaFormat.ConversionMode.Decode)
    except Exception as exc:  # noqa: BLE001 - surface Qt runtime failures to the user
        return _multimedia_troubleshooting_message(f"QtMultimedia probe error: {exc}")

    if decode_formats:
        return None

    return _multimedia_troubleshooting_message()


def _escape_subtitle_filter_path(path: Path) -> str:
    value = path.as_posix()
    value = value.replace("\\", r"\\")
    value = value.replace(":", r"\:")
    value = value.replace("'", r"\'")
    return value


class EditableCaptionTextItem(QGraphicsTextItem):
    def __init__(self, text: str, on_commit: Callable[[str], None], parent=None) -> None:
        super().__init__(text, parent)
        self._on_commit = on_commit
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        self.setDefaultTextColor(QColor("#102A43"))

    def focusOutEvent(self, event) -> None:  # type: ignore[override]
        self._on_commit(self.toPlainText().strip())
        super().focusOutEvent(event)


class CaptionBlock(QGraphicsRectItem):
    LEFT_HANDLE = 8
    RIGHT_HANDLE = 8
    MIN_WIDTH = 24

    def __init__(
        self,
        segment: CaptionSegment,
        pixels_per_second: float,
        on_segment_updated: Callable[[CaptionSegment], None],
        on_segment_selected: Callable[[CaptionSegment], None],
    ) -> None:
        super().__init__()
        self.segment = segment
        self.pixels_per_second = pixels_per_second
        self._on_segment_updated = on_segment_updated
        self._on_segment_selected = on_segment_selected

        self.setBrush(QBrush(QColor("#5DADE2")))
        self.setPen(QPen(QColor("#1B4F72"), 1.2))
        self.setFlags(
            QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsRectItem.GraphicsItemFlag.ItemIsFocusable
        )

        self.drag_mode: str | None = None
        self.drag_origin = QPointF()
        self.orig_rect = QRectF()
        self.orig_x = 0.0

        self.label = EditableCaptionTextItem(self.segment.text, self._commit_text, self)
        self.refresh_from_segment()

    @property
    def duration(self) -> float:
        return max(0.1, self.segment.end - self.segment.start)

    def refresh_from_segment(self) -> None:
        self.setPos(self.segment.start * self.pixels_per_second, 14)
        self.setRect(0, 0, max(self.MIN_WIDTH, self.duration * self.pixels_per_second), 56)
        self.label.setPlainText(self.segment.text)
        self.label.setPos(8, 14)
        self.label.setTextWidth(self.rect().width() - 14)

    def _handle_at(self, pos: QPointF) -> str:
        if pos.x() <= self.LEFT_HANDLE:
            return "left"
        if pos.x() >= self.rect().width() - self.RIGHT_HANDLE:
            return "right"
        return "move"

    def _update_segment_from_geometry(self) -> None:
        start = max(0.0, self.x() / self.pixels_per_second)
        end = start + max(0.1, self.rect().width() / self.pixels_per_second)
        self.segment.start = round(start, 3)
        self.segment.end = round(end, 3)
        self.label.setTextWidth(self.rect().width() - 14)
        self._on_segment_updated(self.segment)

    def _commit_text(self, text: str) -> None:
        if text:
            self.segment.text = text
            self._on_segment_updated(self.segment)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        self.drag_mode = self._handle_at(event.pos())
        self.drag_origin = event.scenePos()
        self.orig_rect = QRectF(self.rect())
        self.orig_x = self.x()
        self._on_segment_selected(self.segment)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if self.drag_mode is None:
            super().mouseMoveEvent(event)
            return

        delta = event.scenePos().x() - self.drag_origin.x()
        if self.drag_mode == "move":
            new_x = max(0.0, self.orig_x + delta)
            self.setX(new_x)
        elif self.drag_mode == "left":
            width = self.orig_rect.width() - delta
            if width < self.MIN_WIDTH:
                width = self.MIN_WIDTH
                delta = self.orig_rect.width() - width
            self.setX(max(0.0, self.orig_x + delta))
            self.setRect(0, 0, width, self.orig_rect.height())
        elif self.drag_mode == "right":
            width = max(self.MIN_WIDTH, self.orig_rect.width() + delta)
            self.setRect(0, 0, width, self.orig_rect.height())

        self._update_segment_from_geometry()

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        self.drag_mode = None
        self._update_segment_from_geometry()
        super().mouseReleaseEvent(event)


class TimelineView(QGraphicsView):
    segment_selected = pyqtSignal(object)
    segment_edited = pyqtSignal(object)

    def __init__(self, pixels_per_second: float = 120.0) -> None:
        super().__init__()
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFixedHeight(120)
        self.pixels_per_second = pixels_per_second

    def load_segments(self, segments: list[CaptionSegment]) -> None:
        self.scene.clear()
        max_end = 30.0

        for segment in segments:
            block = CaptionBlock(
                segment,
                self.pixels_per_second,
                on_segment_updated=self.segment_edited.emit,
                on_segment_selected=self.segment_selected.emit,
            )
            self.scene.addItem(block)
            max_end = max(max_end, segment.end)

        self.scene.setSceneRect(0, 0, max_end * self.pixels_per_second + 280, 100)


class CaptionEditorWindow(QMainWindow):
    def __init__(self, video_path: Path, srt_path: Path) -> None:
        super().__init__()
        self.video_path = video_path
        self.srt_path = srt_path
        self.segments = parse_srt_file(self.srt_path)
        self.selected_segment: CaptionSegment | None = None
        self._playback_error_reported = False

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        TEMP_DIR.mkdir(parents=True, exist_ok=True)

        self.setWindowTitle("Offline AI Caption Studio - Caption Editor")
        self.resize(1280, 760)

        self.media_player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.media_player.setAudioOutput(self.audio_output)

        self.video_widget = QVideoWidget(self)
        self.media_player.setVideoOutput(self.video_widget)
        self.media_player.setSource(QUrl.fromLocalFile(str(self.video_path)))

        self.timeline = TimelineView()
        self.timeline.load_segments(self.segments)
        self.timeline.segment_selected.connect(self.on_segment_selected)
        self.timeline.segment_edited.connect(self.on_segment_edited)

        self.position_label = QLabel("00:00:00.000")
        self.range_label = QLabel("No caption selected")

        self.format_combo = QComboBox()
        self.format_combo.addItems(["srt", "ass"])

        save_btn = QPushButton("Save SRT")
        save_btn.clicked.connect(self.save_srt)

        export_btn = QPushButton("Export Captioned Video")
        export_btn.clicked.connect(self.export_captioned_video)

        controls_bar = QHBoxLayout()
        play_btn = QPushButton(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay), "Play")
        play_btn.clicked.connect(self.media_player.play)
        pause_btn = QPushButton(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPause), "Pause")
        pause_btn.clicked.connect(self.media_player.pause)
        controls_bar.addWidget(play_btn)
        controls_bar.addWidget(pause_btn)
        controls_bar.addWidget(QLabel("Current:"))
        controls_bar.addWidget(self.position_label)
        controls_bar.addSpacing(20)
        controls_bar.addWidget(self.range_label)
        controls_bar.addStretch(1)
        controls_bar.addWidget(QLabel("Subtitle Format:"))
        controls_bar.addWidget(self.format_combo)
        controls_bar.addWidget(save_btn)
        controls_bar.addWidget(export_btn)

        body = QWidget()
        layout = QVBoxLayout(body)
        layout.addWidget(self.video_widget, stretch=3)
        layout.addWidget(self.timeline, stretch=1)
        layout.addLayout(controls_bar)
        self.setCentralWidget(body)

        self.media_player.positionChanged.connect(self._update_position_label)
        self.media_player.errorOccurred.connect(self._on_media_error)

        open_action = QAction("Open SRT", self)
        open_action.triggered.connect(self.open_srt)
        toolbar = QToolBar("Main")
        toolbar.addAction(open_action)
        self.addToolBar(toolbar)

    def _update_position_label(self, ms: int) -> None:
        seconds = ms / 1000
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        millis = int((seconds - int(seconds)) * 1000)
        self.position_label.setText(f"{h:02}:{m:02}:{s:02}.{millis:03}")

    def _update_range_label(self, segment: CaptionSegment | None) -> None:
        if segment is None:
            self.range_label.setText("No caption selected")
            return
        self.range_label.setText(f"Selected: {segment.start:.3f}s → {segment.end:.3f}s")

    def on_segment_selected(self, segment: CaptionSegment) -> None:
        self.selected_segment = segment
        self.media_player.setPosition(int(segment.start * 1000))
        self._update_range_label(segment)

    def on_segment_edited(self, segment: CaptionSegment) -> None:
        self.selected_segment = segment
        self._update_range_label(segment)

    def _on_media_error(self, error: QMediaPlayer.Error, error_string: str) -> None:
        if error == QMediaPlayer.Error.NoError or self._playback_error_reported:
            return
        self._playback_error_reported = True

        detail = error_string.strip() if error_string else "Unknown media playback error."
        QMessageBox.critical(
            self,
            "Playback Error",
            _multimedia_troubleshooting_message(detail),
        )

    def save_srt(self) -> None:
        write_srt(self.segments, self.srt_path)
        QMessageBox.information(self, "Saved", f"Saved captions to {self.srt_path}")

    def _subtitle_export_path(self, fmt: str) -> Path:
        return TEMP_DIR / f"{self.video_path.stem}_edited.{fmt}"

    def _write_current_subtitle_file(self, fmt: str) -> Path:
        subtitle_path = self._subtitle_export_path(fmt)
        if fmt == "ass":
            write_ass(self.segments, subtitle_path)
        else:
            write_srt(self.segments, subtitle_path)
        return subtitle_path

    def _parse_ffmpeg_progress(self, progress_file: Path) -> float:
        if not progress_file.exists():
            return 0.0

        out_time_ms = 0
        try:
            lines = progress_file.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            return 0.0

        for line in lines:
            if line.startswith("out_time_ms="):
                try:
                    out_time_ms = int(line.split("=", 1)[1])
                except ValueError:
                    continue

        duration = max((seg.end for seg in self.segments), default=0.0)
        if duration <= 0:
            return 0.0

        return max(0.0, min(100.0, (out_time_ms / 1_000_000) / duration * 100))

    def export_captioned_video(self) -> None:
        try:
            ensure_ffmpeg_available()
        except AudioExtractionError as exc:
            QMessageBox.critical(self, "FFmpeg Missing", str(exc))
            return

        fmt = self.format_combo.currentText().strip().lower()
        subtitle_path = self._write_current_subtitle_file(fmt)
        output_video_path = OUTPUT_DIR / f"{self.video_path.stem}_captioned_{fmt}.mp4"
        progress_file = TEMP_DIR / "ffmpeg_export_progress.txt"

        subtitle_filter = f"subtitles={_escape_subtitle_filter_path(subtitle_path)}"
        command = [
            "ffmpeg",
            "-y",
            "-i",
            str(self.video_path),
            "-vf",
            subtitle_filter,
            "-c:a",
            "copy",
            "-progress",
            str(progress_file),
            "-nostats",
            str(output_video_path),
        ]

        progress = QProgressDialog("Exporting captioned video...", "Cancel", 0, 100, self)
        progress.setWindowTitle("Export Progress")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setValue(0)

        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        while process.poll() is None:
            QApplication.processEvents()
            if progress.wasCanceled():
                process.terminate()
                QMessageBox.warning(self, "Export Cancelled", "Captioned video export was cancelled.")
                return

            percent = int(self._parse_ffmpeg_progress(progress_file))
            progress.setValue(percent)

        stdout, stderr = process.communicate()
        progress.setValue(100)

        if process.returncode != 0:
            QMessageBox.critical(
                self,
                "Export Failed",
                "FFmpeg failed while burning captions into the video.\n"
                f"Command: {' '.join(command)}\n"
                f"Error: {stderr.strip() or stdout.strip()}",
            )
            return

        QMessageBox.information(
            self,
            "Export Complete",
            f"Captioned video exported to:\n{output_video_path}",
        )

    def open_srt(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(self, "Open SRT", str(self.srt_path.parent), "SRT (*.srt)")
        if not path_str:
            return
        self.srt_path = Path(path_str)
        self.segments = parse_srt_file(self.srt_path)
        self.selected_segment = None
        self._update_range_label(None)
        self.timeline.load_segments(self.segments)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Offline AI Caption Studio - Desktop Caption Editor")
    parser.add_argument("--video", type=Path, required=True, help="Path to source video file")
    parser.add_argument("--srt", type=Path, required=True, help="Path to subtitle SRT file")
    return parser.parse_args()


def run() -> None:
    args = parse_args()

    if not args.video.exists():
        raise SystemExit(f"Video file not found: {args.video}")
    if not args.srt.exists():
        raise SystemExit(f"SRT file not found: {args.srt}")

    app = QApplication(sys.argv)
    backend_error = _validate_multimedia_backend()
    if backend_error is not None:
        QMessageBox.critical(None, "Qt Multimedia Backend Error", backend_error)
        raise SystemExit(backend_error)

    window = CaptionEditorWindow(args.video.resolve(), args.srt.resolve())
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run()

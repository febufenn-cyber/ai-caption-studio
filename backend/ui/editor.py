from __future__ import annotations

import argparse
import importlib.util
import os
import shutil
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
    logging_rules = os.environ.get("QT_LOGGING_RULES", "")
    if "qt.qpa.fonts.warning" not in logging_rules:
        if logging_rules:
            os.environ["QT_LOGGING_RULES"] = f"{logging_rules};qt.qpa.fonts.warning=false"
        else:
            os.environ["QT_LOGGING_RULES"] = "qt.qpa.fonts.warning=false"

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
from PyQt6.QtGui import QAction, QBrush, QColor, QFont, QPen
from PyQt6.QtMultimedia import QAudioOutput, QMediaFormat, QMediaPlayer
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressDialog,
    QPushButton,
    QSplitter,
    QStackedLayout,
    QStyle,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from backend.caption_segment import CaptionSegment
from backend.subtitles.ass_writer import write_ass
from backend.subtitles.lyric_sync import LyricSyncError, parse_lyrics_lines, sync_segments_to_lyrics
from backend.subtitles.srt_parser import parse_srt_file
from backend.subtitles.srt_writer import write_srt


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
            "4) For caption burn-in export on macOS, install ffmpeg-full and set FFMPEG_BIN",
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
    value = value.replace(" ", r"\ ")
    value = value.replace("[", r"\[")
    value = value.replace("]", r"\]")
    value = value.replace(",", r"\,")
    return value


def _ffmpeg_has_subtitles_filter(ffmpeg_bin: str) -> bool:
    try:
        result = subprocess.run(
            [ffmpeg_bin, "-hide_banner", "-filters"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return False

    output = f"{result.stdout}\n{result.stderr}"
    for line in output.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "subtitles":
            return True
    return False


def _candidate_ffmpeg_bins() -> list[Path]:
    candidates: list[Path] = []

    ffmpeg_env = os.environ.get("FFMPEG_BIN")
    if ffmpeg_env:
        candidates.append(Path(ffmpeg_env).expanduser())

    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path:
        candidates.append(Path(ffmpeg_path))

    if sys.platform == "darwin":
        candidates.append(Path("/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg"))
        candidates.append(Path("/usr/local/opt/ffmpeg-full/bin/ffmpeg"))

    unique_existing: list[Path] = []
    seen: set[str] = set()
    for path in candidates:
        resolved = str(path)
        if resolved in seen:
            continue
        seen.add(resolved)
        if path.exists():
            unique_existing.append(path)
    return unique_existing


def _resolve_ffmpeg_for_subtitle_burnin() -> tuple[str | None, str | None]:
    candidates = _candidate_ffmpeg_bins()
    if not candidates:
        return None, "FFmpeg binary not found. Install FFmpeg and ensure it is on PATH."

    for candidate in candidates:
        ffmpeg_bin = str(candidate)
        if _ffmpeg_has_subtitles_filter(ffmpeg_bin):
            return ffmpeg_bin, None

    detected = str(candidates[0])
    message = (
        "Your FFmpeg build does not include the 'subtitles' filter (libass), "
        "so burned-in caption export cannot run.\n\n"
        f"Detected FFmpeg: {detected}\n\n"
        "Fix on macOS:\n"
        "1) brew install ffmpeg-full\n"
        "2) export FFMPEG_BIN=/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg\n"
        "   (or prepend /opt/homebrew/opt/ffmpeg-full/bin to PATH)\n"
    )
    return None, message


def _format_time(seconds: float) -> str:
    total_ms = max(0, int(round(seconds * 1000)))
    h, rem = divmod(total_ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02}:{m:02}:{s:02}.{ms:03}"


def _segment_at_time(segments: list[CaptionSegment], seconds: float) -> CaptionSegment | None:
    for segment in segments:
        if segment.start <= seconds <= segment.end:
            return segment
    return None


class EditableCaptionTextItem(QGraphicsTextItem):
    def __init__(self, text: str, on_commit: Callable[[str], None], parent=None) -> None:
        super().__init__(text, parent)
        self._on_commit = on_commit
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        self.setDefaultTextColor(QColor("#E6EDF8"))

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

        self._active = False
        self._set_colors()

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

    def _set_colors(self) -> None:
        if self._active:
            self.setBrush(QBrush(QColor("#2AA198")))
            self.setPen(QPen(QColor("#78F0D8"), 1.5))
            return
        self.setBrush(QBrush(QColor("#2E3A59")))
        self.setPen(QPen(QColor("#5A6D99"), 1.2))

    def set_active(self, active: bool) -> None:
        self._active = active
        self._set_colors()

    @property
    def duration(self) -> float:
        return max(0.1, self.segment.end - self.segment.start)

    def refresh_from_segment(self) -> None:
        self.setPos(self.segment.start * self.pixels_per_second, 14)
        self.setRect(0, 0, max(self.MIN_WIDTH, self.duration * self.pixels_per_second), 56)
        self.label.setPlainText(self.segment.text)
        self.label.setPos(8, 14)
        self.label.setTextWidth(max(10.0, self.rect().width() - 14))

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
        self.label.setTextWidth(max(10.0, self.rect().width() - 14))
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
        self.setFixedHeight(128)
        self.pixels_per_second = pixels_per_second
        self._blocks: list[CaptionBlock] = []

    def load_segments(self, segments: list[CaptionSegment]) -> None:
        self.scene.clear()
        self._blocks.clear()
        max_end = 30.0

        for segment in segments:
            block = CaptionBlock(
                segment,
                self.pixels_per_second,
                on_segment_updated=self.segment_edited.emit,
                on_segment_selected=self.segment_selected.emit,
            )
            self._blocks.append(block)
            self.scene.addItem(block)
            max_end = max(max_end, segment.end)

        self.scene.setSceneRect(0, 0, max_end * self.pixels_per_second + 280, 100)

    def set_active_segment(self, segment: CaptionSegment | None) -> None:
        for block in self._blocks:
            block.set_active(block.segment is segment)


class CaptionEditorWindow(QMainWindow):
    def __init__(self, video_path: Path, srt_path: Path | None = None) -> None:
        super().__init__()
        self.video_path = video_path
        self.srt_path = srt_path or self._default_srt_path_for_video(video_path)
        self.segments = parse_srt_file(self.srt_path) if self.srt_path.exists() else []
        self.selected_segment: CaptionSegment | None = None
        self._active_segment: CaptionSegment | None = None
        self._playback_error_reported = False
        self._syncing_ui = False

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        TEMP_DIR.mkdir(parents=True, exist_ok=True)

        self._apply_styles()
        self._build_ui()
        self._set_video_source(self.video_path)
        self._sort_segments()
        self._refresh_timeline_and_list()
        self._update_caption_overlay(0.0)
        self._set_window_title()

    @staticmethod
    def _default_srt_path_for_video(video_path: Path) -> Path:
        return OUTPUT_DIR / f"{video_path.stem}.srt"

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget {
                background-color: #0f1218;
                color: #ebeff8;
                font-family: 'Helvetica Neue', 'Segoe UI', 'Noto Sans', sans-serif;
                font-size: 13px;
            }
            QToolBar {
                background: #151a22;
                border: none;
                spacing: 8px;
                padding: 6px;
            }
            QPushButton {
                background-color: #1d2430;
                border: 1px solid #2f3849;
                border-radius: 8px;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #263246;
            }
            QPushButton:pressed {
                background-color: #18202f;
            }
            QComboBox, QLineEdit, QDoubleSpinBox, QPlainTextEdit, QListWidget {
                background-color: #141923;
                border: 1px solid #2b3445;
                border-radius: 8px;
                padding: 5px;
                selection-background-color: #245f8a;
            }
            QGroupBox {
                border: 1px solid #2b3445;
                border-radius: 10px;
                margin-top: 12px;
                font-weight: 600;
                color: #a9b6cf;
            }
            QGroupBox::title {
                left: 10px;
                padding: 0 5px 0 5px;
            }
            QLabel#captionOverlay {
                background-color: rgba(0, 0, 0, 165);
                border-radius: 12px;
                color: #f3f7ff;
                font-size: 20px;
                font-weight: 700;
                padding: 10px 14px;
            }
            QLabel#hintText {
                color: #8fa0c0;
            }
            """
        )

    def _build_ui(self) -> None:
        self.resize(1500, 900)

        self.media_player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.media_player.setAudioOutput(self.audio_output)

        self.video_widget = QVideoWidget(self)
        self.media_player.setVideoOutput(self.video_widget)

        self.caption_overlay = QLabel("")
        self.caption_overlay.setObjectName("captionOverlay")
        self.caption_overlay.setWordWrap(True)
        self.caption_overlay.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom)

        overlay_layer = QWidget()
        overlay_layer.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        overlay_layer.setStyleSheet("background: transparent;")
        overlay_layout = QVBoxLayout(overlay_layer)
        overlay_layout.setContentsMargins(36, 28, 36, 26)
        overlay_layout.addStretch(1)
        overlay_layout.addWidget(self.caption_overlay)

        video_stack = QStackedLayout()
        video_stack.setStackingMode(QStackedLayout.StackingMode.StackAll)
        video_stack.addWidget(self.video_widget)
        video_stack.addWidget(overlay_layer)

        video_panel = QWidget()
        video_panel.setLayout(video_stack)

        self.timeline = TimelineView()
        self.timeline.segment_selected.connect(self.on_segment_selected)
        self.timeline.segment_edited.connect(self.on_segment_edited)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(12)
        left_layout.addWidget(video_panel, stretch=5)
        left_layout.addWidget(self.timeline, stretch=1)

        right_panel = self._build_right_panel()

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 2)

        self.position_label = QLabel("00:00:00.000")
        self.range_label = QLabel("No caption selected")
        self.range_label.setObjectName("hintText")

        self.format_combo = QComboBox()
        self.format_combo.addItems(["srt", "ass"])

        play_btn = QPushButton(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay), "Play")
        play_btn.clicked.connect(self.media_player.play)
        pause_btn = QPushButton(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPause), "Pause")
        pause_btn.clicked.connect(self.media_player.pause)

        save_btn = QPushButton("Save SRT")
        save_btn.clicked.connect(self.save_srt)

        export_btn = QPushButton("Export Captioned Video")
        export_btn.clicked.connect(self.export_captioned_video)

        controls_bar = QHBoxLayout()
        controls_bar.addWidget(play_btn)
        controls_bar.addWidget(pause_btn)
        controls_bar.addSpacing(8)
        controls_bar.addWidget(QLabel("Current:"))
        controls_bar.addWidget(self.position_label)
        controls_bar.addSpacing(16)
        controls_bar.addWidget(self.range_label)
        controls_bar.addStretch(1)
        controls_bar.addWidget(QLabel("Subtitle Format:"))
        controls_bar.addWidget(self.format_combo)
        controls_bar.addWidget(save_btn)
        controls_bar.addWidget(export_btn)

        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)
        layout.addWidget(splitter, stretch=1)
        layout.addLayout(controls_bar)
        self.setCentralWidget(body)

        self.media_player.positionChanged.connect(self._on_media_position_changed)
        self.media_player.errorOccurred.connect(self._on_media_error)

        open_video_action = QAction("Open Video", self)
        open_video_action.triggered.connect(self.open_video)

        open_srt_action = QAction("Open SRT", self)
        open_srt_action.triggered.connect(self.open_srt)

        generate_action = QAction("Auto-Generate Captions", self)
        generate_action.triggered.connect(self.generate_captions_from_video)

        toolbar = QToolBar("Main")
        toolbar.addAction(open_video_action)
        toolbar.addAction(open_srt_action)
        toolbar.addAction(generate_action)
        self.addToolBar(toolbar)

    def _build_right_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(4, 0, 0, 0)
        layout.setSpacing(10)

        headline = QLabel("Caption Workspace")
        headline.setStyleSheet("font-size: 18px; font-weight: 700;")
        subtitle = QLabel("Edit timings, rewrite lines, and sync pasted lyrics instantly.")
        subtitle.setObjectName("hintText")
        subtitle.setWordWrap(True)
        layout.addWidget(headline)
        layout.addWidget(subtitle)

        self.caption_list = QListWidget()
        self.caption_list.currentRowChanged.connect(self._on_caption_row_changed)

        captions_group = QGroupBox("Caption Timeline List")
        captions_layout = QVBoxLayout(captions_group)
        captions_layout.addWidget(self.caption_list)
        layout.addWidget(captions_group, stretch=2)

        edit_group = QGroupBox("Selected Caption")
        edit_layout = QVBoxLayout(edit_group)

        form = QFormLayout()
        self.start_spin = QDoubleSpinBox()
        self.start_spin.setRange(0.0, 99999.0)
        self.start_spin.setDecimals(3)
        self.start_spin.setSingleStep(0.05)

        self.end_spin = QDoubleSpinBox()
        self.end_spin.setRange(0.1, 99999.0)
        self.end_spin.setDecimals(3)
        self.end_spin.setSingleStep(0.05)

        self.text_input = QPlainTextEdit()
        self.text_input.setFixedHeight(84)

        form.addRow("Start (s)", self.start_spin)
        form.addRow("End (s)", self.end_spin)
        form.addRow("Text", self.text_input)
        edit_layout.addLayout(form)

        edit_btn_row = QHBoxLayout()
        apply_btn = QPushButton("Apply Edit")
        apply_btn.clicked.connect(self.apply_selected_caption_edit)

        add_btn = QPushButton("Add At Playhead")
        add_btn.clicked.connect(self.add_caption_at_playhead)

        delete_btn = QPushButton("Delete")
        delete_btn.clicked.connect(self.delete_selected_caption)

        edit_btn_row.addWidget(apply_btn)
        edit_btn_row.addWidget(add_btn)
        edit_btn_row.addWidget(delete_btn)
        edit_layout.addLayout(edit_btn_row)

        layout.addWidget(edit_group, stretch=2)

        generation_group = QGroupBox("Auto Captions")
        generation_layout = QVBoxLayout(generation_group)
        generation_form = QFormLayout()

        self.model_combo = QComboBox()
        self.model_combo.addItems(["tiny", "base", "small", "medium", "large-v3"])
        self.model_combo.setCurrentText("small")

        self.language_input = QLineEdit()
        self.language_input.setPlaceholderText("Optional: en, ta, es ...")

        generation_form.addRow("Model", self.model_combo)
        generation_form.addRow("Language", self.language_input)
        generation_layout.addLayout(generation_form)

        generate_btn = QPushButton("Auto-Generate From Video")
        generate_btn.clicked.connect(self.generate_captions_from_video)
        generation_layout.addWidget(generate_btn)

        layout.addWidget(generation_group, stretch=1)

        lyrics_group = QGroupBox("Lyrics Sync")
        lyrics_layout = QVBoxLayout(lyrics_group)
        self.lyrics_input = QPlainTextEdit()
        self.lyrics_input.setPlaceholderText("Paste lyric lines here, one line per row...")
        self.lyrics_input.setFixedHeight(140)

        self.similarity_spin = QDoubleSpinBox()
        self.similarity_spin.setRange(0.05, 0.95)
        self.similarity_spin.setSingleStep(0.05)
        self.similarity_spin.setDecimals(2)
        self.similarity_spin.setValue(0.25)

        similarity_form = QFormLayout()
        similarity_form.addRow("Match Similarity", self.similarity_spin)

        sync_btn = QPushButton("Sync Pasted Lyrics To Captions")
        sync_btn.clicked.connect(self.sync_lyrics_to_segments)

        lyrics_layout.addWidget(self.lyrics_input)
        lyrics_layout.addLayout(similarity_form)
        lyrics_layout.addWidget(sync_btn)

        layout.addWidget(lyrics_group, stretch=2)
        layout.addStretch(1)
        return panel

    def _set_window_title(self) -> None:
        self.setWindowTitle(f"Offline AI Caption Studio - {self.video_path.name}")

    def _set_video_source(self, video_path: Path) -> None:
        self.media_player.stop()
        self.media_player.setSource(QUrl.fromLocalFile(str(video_path)))
        self.video_path = video_path

    def _sort_segments(self) -> None:
        self.segments.sort(key=lambda seg: (seg.start, seg.end))

    def _segment_index(self, segment: CaptionSegment | None) -> int:
        if segment is None:
            return -1
        for idx, existing in enumerate(self.segments):
            if existing is segment:
                return idx
        return -1

    def _caption_list_text(self, segment: CaptionSegment) -> str:
        return f"{_format_time(segment.start)} → {_format_time(segment.end)}    {segment.text}"

    def _refresh_timeline_and_list(self, preserve_selection: CaptionSegment | None = None) -> None:
        if preserve_selection is not None and self._segment_index(preserve_selection) == -1:
            preserve_selection = None

        self.timeline.load_segments(self.segments)

        self._syncing_ui = True
        self.caption_list.clear()
        for segment in self.segments:
            item = QListWidgetItem(self._caption_list_text(segment))
            self.caption_list.addItem(item)
        self._syncing_ui = False

        if preserve_selection is not None:
            self._select_segment(preserve_selection, seek=False, scroll=True)
        elif self.segments:
            self._select_segment(self.segments[0], seek=False, scroll=False)
        else:
            self.selected_segment = None
            self.timeline.set_active_segment(self._active_segment)
            self._update_range_label(None)
            self._load_selected_caption_into_form(None)

    def _load_selected_caption_into_form(self, segment: CaptionSegment | None) -> None:
        self._syncing_ui = True
        if segment is None:
            self.start_spin.setValue(0.0)
            self.end_spin.setValue(0.0)
            self.text_input.setPlainText("")
        else:
            self.start_spin.setValue(segment.start)
            self.end_spin.setValue(segment.end)
            self.text_input.setPlainText(segment.text)
        self._syncing_ui = False

    def _select_segment(self, segment: CaptionSegment, *, seek: bool, scroll: bool) -> None:
        idx = self._segment_index(segment)
        if idx < 0:
            return

        self.selected_segment = segment
        self._update_range_label(segment)

        self._syncing_ui = True
        self.caption_list.setCurrentRow(idx)
        self._syncing_ui = False

        self.timeline.set_active_segment(self._active_segment or segment)
        self._load_selected_caption_into_form(segment)

        if seek:
            self.media_player.setPosition(int(segment.start * 1000))

        if scroll:
            item = self.caption_list.item(idx)
            if item is not None:
                self.caption_list.scrollToItem(item)

    def _update_position_label(self, ms: int) -> None:
        seconds = ms / 1000
        self.position_label.setText(_format_time(seconds))

    def _update_range_label(self, segment: CaptionSegment | None) -> None:
        if segment is None:
            self.range_label.setText("No caption selected")
            return
        self.range_label.setText(f"Selected: {segment.start:.3f}s → {segment.end:.3f}s")

    def _update_caption_overlay(self, seconds: float) -> None:
        active = _segment_at_time(self.segments, seconds)
        self._active_segment = active
        self.timeline.set_active_segment(active or self.selected_segment)

        if active is None:
            self.caption_overlay.setText("")
            return

        self.caption_overlay.setText(active.text)

    def _on_media_position_changed(self, ms: int) -> None:
        self._update_position_label(ms)
        self._update_caption_overlay(ms / 1000)

    def on_segment_selected(self, segment: CaptionSegment) -> None:
        self._select_segment(segment, seek=True, scroll=True)

    def on_segment_edited(self, segment: CaptionSegment) -> None:
        idx = self._segment_index(segment)
        if idx >= 0:
            item = self.caption_list.item(idx)
            if item is not None:
                item.setText(self._caption_list_text(segment))

        if self.selected_segment is segment:
            self._load_selected_caption_into_form(segment)
            self._update_range_label(segment)

        current_seconds = self.media_player.position() / 1000
        self._update_caption_overlay(current_seconds)

    def _on_caption_row_changed(self, row: int) -> None:
        if self._syncing_ui:
            return
        if row < 0 or row >= len(self.segments):
            self.selected_segment = None
            self._update_range_label(None)
            self._load_selected_caption_into_form(None)
            return

        self._select_segment(self.segments[row], seek=True, scroll=False)

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

    def open_video(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(
            self,
            "Open Video",
            str(self.video_path.parent),
            "Video Files (*.mp4 *.mov *.mkv *.avi *.m4v *.webm)",
        )
        if not path_str:
            return

        new_video = Path(path_str).resolve()
        self._set_video_source(new_video)
        self.srt_path = self._default_srt_path_for_video(new_video)

        if self.srt_path.exists():
            self.segments = parse_srt_file(self.srt_path)
        else:
            self.segments = []

        self._sort_segments()
        self._refresh_timeline_and_list()
        self._set_window_title()

    def open_srt(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(
            self,
            "Open SRT",
            str(self.srt_path.parent),
            "SRT (*.srt)",
        )
        if not path_str:
            return

        self.srt_path = Path(path_str).resolve()
        self.segments = parse_srt_file(self.srt_path)
        self._sort_segments()
        self._refresh_timeline_and_list()

    def save_srt(self) -> None:
        self._sort_segments()
        write_srt(self.segments, self.srt_path)
        self._refresh_timeline_and_list(self.selected_segment)
        QMessageBox.information(self, "Saved", f"Saved captions to:\n{self.srt_path}")

    def apply_selected_caption_edit(self) -> None:
        if self.selected_segment is None:
            QMessageBox.warning(self, "No Selection", "Select a caption first.")
            return

        start = round(self.start_spin.value(), 3)
        end = round(self.end_spin.value(), 3)
        text = self.text_input.toPlainText().strip()

        if end <= start:
            QMessageBox.warning(self, "Invalid Range", "Caption end time must be greater than start time.")
            return

        if not text:
            QMessageBox.warning(self, "Empty Text", "Caption text cannot be empty.")
            return

        self.selected_segment.start = start
        self.selected_segment.end = end
        self.selected_segment.text = text

        self._sort_segments()
        self._refresh_timeline_and_list(self.selected_segment)

    def add_caption_at_playhead(self) -> None:
        playhead = max(0.0, self.media_player.position() / 1000)
        new_segment = CaptionSegment(
            start=round(playhead, 3),
            end=round(playhead + 2.0, 3),
            text="New caption",
        )
        self.segments.append(new_segment)
        self._sort_segments()
        self._refresh_timeline_and_list(new_segment)

    def delete_selected_caption(self) -> None:
        if self.selected_segment is None:
            QMessageBox.warning(self, "No Selection", "Select a caption first.")
            return

        idx = self._segment_index(self.selected_segment)
        if idx < 0:
            return

        self.segments.pop(idx)
        preserve = self.segments[min(idx, len(self.segments) - 1)] if self.segments else None
        self.selected_segment = None
        self._refresh_timeline_and_list(preserve)

    def _subtitle_export_path(self, fmt: str) -> Path:
        return TEMP_DIR / f"{self.video_path.stem}_edited.{fmt}"

    def _write_current_subtitle_file(self, fmt: str) -> Path:
        subtitle_path = self._subtitle_export_path(fmt)
        self._sort_segments()
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
            duration = max(0.1, self.media_player.duration() / 1000)

        return max(0.0, min(100.0, (out_time_ms / 1_000_000) / duration * 100))

    def export_captioned_video(self) -> None:
        ffmpeg_bin, ffmpeg_error = _resolve_ffmpeg_for_subtitle_burnin()
        if ffmpeg_error is not None:
            QMessageBox.critical(self, "FFmpeg Subtitle Filter Missing", ffmpeg_error)
            return

        fmt = self.format_combo.currentText().strip().lower()
        subtitle_path = self._write_current_subtitle_file(fmt)
        output_video_path = OUTPUT_DIR / f"{self.video_path.stem}_captioned_{fmt}.mp4"
        progress_file = TEMP_DIR / "ffmpeg_export_progress.txt"

        subtitle_filter = f"subtitles=filename={_escape_subtitle_filter_path(subtitle_path)}"
        command = [
            ffmpeg_bin,
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

    def generate_captions_from_video(self) -> None:
        model_size = self.model_combo.currentText().strip()
        language = self.language_input.text().strip()

        command = [
            sys.executable,
            "-m",
            "backend.main",
            str(self.video_path),
            "--model-size",
            model_size,
        ]
        if language:
            command.extend(["--language", language])

        progress = QProgressDialog(
            "Generating captions with Whisper... first run may download model files.",
            "Cancel",
            0,
            0,
            self,
        )
        progress.setWindowTitle("Auto Caption Generation")
        progress.setWindowModality(Qt.WindowModality.WindowModal)

        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        while process.poll() is None:
            QApplication.processEvents()
            if progress.wasCanceled():
                process.terminate()
                QMessageBox.warning(self, "Cancelled", "Caption generation was cancelled.")
                return

        stdout, stderr = process.communicate()
        if process.returncode != 0:
            QMessageBox.critical(
                self,
                "Caption Generation Failed",
                f"Command: {' '.join(command)}\n\n{stderr.strip() or stdout.strip()}",
            )
            return

        generated_srt = OUTPUT_DIR / f"{self.video_path.stem}.srt"
        if not generated_srt.exists():
            QMessageBox.critical(
                self,
                "Caption Generation Failed",
                "Caption generation finished, but no SRT output file was found.",
            )
            return

        self.srt_path = generated_srt
        self.segments = parse_srt_file(generated_srt)
        self._sort_segments()
        self._refresh_timeline_and_list()
        QMessageBox.information(self, "Captions Ready", f"Generated captions loaded from:\n{generated_srt}")

    def sync_lyrics_to_segments(self) -> None:
        if not self.segments:
            QMessageBox.warning(
                self,
                "No Captions",
                "Generate or open captions before running lyric synchronization.",
            )
            return

        raw_lyrics = self.lyrics_input.toPlainText()
        similarity = self.similarity_spin.value()

        try:
            lyrics_lines = parse_lyrics_lines(raw_lyrics)
            synced_segments = sync_segments_to_lyrics(self.segments, lyrics_lines, min_similarity=similarity)
        except LyricSyncError as exc:
            QMessageBox.warning(self, "Lyrics Sync", str(exc))
            return

        # Preserve original timeline duration and count; only replace text where sync succeeded.
        for idx, synced in enumerate(synced_segments):
            if idx >= len(self.segments):
                break
            self.segments[idx].text = synced.text

        self._refresh_timeline_and_list(self.selected_segment)
        QMessageBox.information(self, "Lyrics Synced", "Lyrics were synced to your current caption timeline.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Offline AI Caption Studio - Desktop Caption Editor")
    parser.add_argument("--video", type=Path, required=False, help="Path to source video file")
    parser.add_argument("--srt", type=Path, required=False, help="Path to subtitle SRT file")
    return parser.parse_args()


def _resolve_launch_video(args: argparse.Namespace) -> Path | None:
    if args.video is not None:
        return args.video.resolve()

    path_str, _ = QFileDialog.getOpenFileName(
        None,
        "Select Video",
        str(PROJECT_ROOT),
        "Video Files (*.mp4 *.mov *.mkv *.avi *.m4v *.webm)",
    )
    if not path_str:
        return None
    return Path(path_str).resolve()


def _resolve_launch_srt(video_path: Path, args: argparse.Namespace) -> Path | None:
    if args.srt is not None:
        return args.srt.resolve()

    generated = OUTPUT_DIR / f"{video_path.stem}.srt"
    if generated.exists():
        return generated.resolve()

    return None


def run() -> None:
    args = parse_args()

    app = QApplication(sys.argv)
    app.setFont(QFont("Helvetica Neue"))
    backend_error = _validate_multimedia_backend()
    if backend_error is not None:
        QMessageBox.critical(None, "Qt Multimedia Backend Error", backend_error)
        raise SystemExit(backend_error)

    video_path = _resolve_launch_video(args)
    if video_path is None:
        raise SystemExit("No video selected. Launch cancelled.")

    if not video_path.exists():
        raise SystemExit(f"Video file not found: {video_path}")

    srt_path = _resolve_launch_srt(video_path, args)
    if args.srt is not None and srt_path is not None and not srt_path.exists():
        raise SystemExit(f"SRT file not found: {srt_path}")

    window = CaptionEditorWindow(video_path, srt_path)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run()

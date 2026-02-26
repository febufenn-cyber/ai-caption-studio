# Offline AI Caption Studio

Offline AI Caption Studio is a local-first Python application that generates subtitle captions from videos using fully local processing (after first model download).

## Project Structure

```
/backend
/backend/transcription
/backend/video
/backend/subtitles
/models
/output
/temp
```

## Features

- Accepts a video file as input.
- Extracts audio with FFmpeg.
- Verifies FFmpeg availability at runtime with installation guidance if missing.
- Runs offline speech recognition using `faster-whisper`.
- Builds timestamped caption segments.
- Exports subtitles as an `.srt` file in `/output` automatically.
- Supports lyric synchronization mode: paste lyrics and align subtitle text to transcription timestamps using fuzzy matching.

## Prerequisites

- Python 3.10+
- FFmpeg installed and available on `PATH`
- macOS users: use native (non-Rosetta) terminal + Python matching your machine architecture
- Burned subtitle export requires FFmpeg with `subtitles` filter (`libass`) support. On Homebrew, install `ffmpeg-full`.

FFmpeg install examples:
- Ubuntu/Debian: `sudo apt-get update && sudo apt-get install -y ffmpeg`
- macOS (Homebrew, basic): `brew install ffmpeg` (transcription/extraction)
- macOS (Homebrew, required for burned subtitle export): `brew install ffmpeg-full`
- Windows (winget): `winget install Gyan.FFmpeg`

## Setup

Run once from the repository root:

```bash
./scripts/setup.sh
```

This setup script:
1. Selects Python 3.10+ (`python3.12`, `python3.11`, `python3.10`, then `python3`)
2. Creates a virtual environment at `.venv`
3. Upgrades `pip`
4. Reinstalls dependencies from `requirements.txt` for a clean Qt runtime

## Run (single command)

```bash
source .venv/bin/activate
python -m backend.main <video_file>
```

Example:

```bash
python -m backend.main ./samples/interview.mp4
```

Output behavior:
- Extracted audio is saved to `/temp/<video_stem>.wav`
- Subtitle file is saved to `/output/<video_stem>.srt`

Optional flags:
- `--model-size tiny|base|small|medium|large-v3` (default: `small`)
- `--language en` to force language code
- `--compute-type int8|float16|float32` (default: `int8`)

## Lyric synchronization mode

You can align subtitle text to your own lyrics while preserving transcription timestamps.

### Option A: Lyrics from file

```bash
python -m backend.main <video_file> --lyrics-file /path/to/lyrics.txt
```

### Option B: Paste lyrics through stdin

```bash
cat /path/to/lyrics.txt | python -m backend.main <video_file> --lyrics-stdin
```

Notes:
- Lyrics should be plain text with one lyric line per line.
- Empty lines are ignored.
- Timestamps come from speech transcription; synchronized subtitle text comes from fuzzy-matched lyric lines.


## Desktop caption editor (PyQt6)

A desktop UI is available for fast timestamp correction and caption text editing.

Features:
- Video preview player
- Caption timeline blocks
- Drag blocks to move caption timestamps
- Drag left/right edges to resize caption duration
- Click a caption block to seek playback
- Edit caption text inline directly inside timeline blocks
- Timestamps update immediately while dragging/resizing
- Save edits back to SRT
- Export captioned video with burned-in subtitles (SRT or ASS)

Run:

```bash
source .venv/bin/activate
python -m backend.ui.editor --video /path/to/video.mp4 --srt /path/to/captions.srt
```

On macOS, the editor now defaults to Qt's native media backend (`QT_MEDIA_BACKEND=darwin`) for reliable playback.

Tip:
- First generate captions with `python -m backend.main <video_file>` and then open the produced `/output/<video_stem>.srt` in the editor.

### macOS playback troubleshooting

If the editor opens but video is blank and logs include `No QtMultimedia backends found`:

1. Recreate environment:
   ```bash
   rm -rf .venv
   ./scripts/setup.sh
   ```
2. Ensure shell does not override Qt plugin paths:
   ```bash
   unset QT_PLUGIN_PATH
   unset QT_QPA_PLATFORM_PLUGIN_PATH
   ```
3. Run the editor with the native backend explicitly:
   ```bash
   QT_MEDIA_BACKEND=darwin python -m backend.ui.editor --video /path/to/video.mp4 --srt /path/to/captions.srt
   ```
4. If you force `QT_MEDIA_BACKEND=ffmpeg`, install matching FFmpeg 7 libs:
   ```bash
   brew install ffmpeg@7
   ```
5. If export fails with `No such filter: 'subtitles'`, use ffmpeg-full:
   ```bash
   brew install ffmpeg-full
   export FFMPEG_BIN=/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg
   ```

Notes:
- Homebrew `ffmpeg` command availability is separate from QtMultimedia backend loading.
- `OpenType support missing for .AppleSystemUIFont` is a font warning and not the cause of backend failure.
- `urllib3` `NotOpenSSLWarning` means your venv is using system Python 3.9 (`LibreSSL`). Recreate `.venv` with Python 3.10+ via `./scripts/setup.sh`.


### Export captioned video

Inside the editor:
1. Choose subtitle format (`srt` or `ass`) in the format dropdown.
2. Click **Export Captioned Video**.
3. Wait for progress to reach 100%.

Export behavior:
- Uses the currently edited timeline/text state.
- Burns subtitles into the video using FFmpeg.
- Saves output to `/output/<video_stem>_captioned_<format>.mp4`.

## Offline Notes

- On first run, faster-whisper downloads the selected model into `/models`.
- Subsequent runs can transcribe fully offline using the local model cache.

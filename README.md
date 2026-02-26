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

FFmpeg install examples:
- Ubuntu/Debian: `sudo apt-get update && sudo apt-get install -y ffmpeg`
- macOS (Homebrew): `brew install ffmpeg`
- Windows (winget): `winget install Gyan.FFmpeg`

## Setup

Run once from the repository root:

```bash
./scripts/setup.sh
```

This setup script:
1. Creates a virtual environment at `.venv`
2. Upgrades `pip`
3. Installs dependencies from `requirements.txt`

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

Tip:
- First generate captions with `python -m backend.main <video_file>` and then open the produced `/output/<video_stem>.srt` in the editor.


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

# Offline AI Caption Studio

Offline AI Caption Studio is a local-first caption workflow for creators.

It combines:
- AI caption generation (Whisper)
- Timeline-based timestamp editing
- In-player live caption preview overlay
- Lyric paste + sync to current timeline
- Burned-in export (SRT / ASS) with FFmpeg

## Quick Start (Recommended)

### 1) Clone
```bash
git clone https://github.com/febufenn-cyber/ai-caption-studio.git
cd ai-caption-studio
```

### 2) One-command setup
macOS / Linux:
```bash
./scripts/setup.sh
```

Windows PowerShell:
```powershell
.\scripts\setup.ps1
```

Windows CMD:
```bat
scripts\setup.bat
```

These scripts:
- Ensure Python 3.10+
- Create `.venv`
- Install Python dependencies
- Attempt to install/resolve FFmpeg
- Validate FFmpeg subtitle burn-in capability (`subtitles` filter)

### 3) Launch editor
macOS / Linux:
```bash
source .venv/bin/activate
python -m backend.ui.editor
```

Windows:
```bat
.\.venv\Scripts\activate
python -m backend.ui.editor
```

Optional direct launch:
```bash
python -m backend.ui.editor --video /path/to/video.mp4 --srt /path/to/captions.srt
```

## Product Workflow

1. Open video in the editor.
2. Either:
   - Auto-generate captions from video, or
   - Load existing SRT.
3. Optionally paste lyrics and sync text to existing timestamps.
4. Fine-tune timing by dragging blocks and editing Start/End/Text.
5. Export caption-burned video to `/output`.

## Key Features

- **Live Preview Overlay**: Current caption is shown directly over video during playback.
- **CapCut-style Workspace**: Video + timeline + caption list + edit panel + lyric panel in one window.
- **Auto Captions**: Built-in call to Whisper transcription pipeline.
- **Lyrics Sync**: Paste lyrics and align text while preserving timeline edits.
- **Export Reliability**: Detects unsupported FFmpeg builds and gives exact fix commands.

## Output Paths

- Generated subtitles: `/output/<video_stem>.srt`
- Edited temp subtitles: `/temp/<video_stem>_edited.<srt|ass>`
- Burned exports: `/output/<video_stem>_captioned_<srt|ass>.mp4`

## Cross-Platform Installation Notes

### macOS
- For burn-in export, use:
  ```bash
  brew install ffmpeg-full
  export FFMPEG_BIN=/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg
  ```

### Linux
- Bootstrap tries apt/dnf/pacman automatically.
- If manual:
  ```bash
  sudo apt-get update && sudo apt-get install -y ffmpeg
  ```

### Windows
- Bootstrap tries `winget` / `choco`.
- Manual fallback:
  ```powershell
  winget install --id Gyan.FFmpeg -e
  ```

## Troubleshooting

### "No QtMultimedia backends found"
- Recreate environment with setup script.
- On macOS, clear conflicting vars:
  ```bash
  unset QT_PLUGIN_PATH
  unset QT_QPA_PLATFORM_PLUGIN_PATH
  ```

### "Your FFmpeg build does not include the 'subtitles' filter"
Use ffmpeg-full (macOS):
```bash
brew install ffmpeg-full
export FFMPEG_BIN=/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg
```

### "OpenType support missing for .AppleSystemUIFont"
Non-fatal Qt font warning. It does not block caption editing or export.

## Full Manual

See: [docs/USER_MANUAL.md](docs/USER_MANUAL.md)

## Project Structure

```
/backend
/backend/transcription
/backend/video
/backend/subtitles
/backend/ui
/models
/output
/temp
/scripts
```

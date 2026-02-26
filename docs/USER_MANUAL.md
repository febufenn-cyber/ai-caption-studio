# Offline AI Caption Studio - User Manual

## What This App Does
Offline AI Caption Studio is a local desktop editor for:
- Auto-generating captions from video (Whisper, offline after first model download)
- Editing caption timings and text on a timeline
- Pasting lyrics and syncing them to existing timestamps
- Previewing captions directly in the video player
- Exporting a caption-burned video (SRT or ASS)

## Install From GitHub

### 1. Clone
```bash
git clone https://github.com/febufenn-cyber/ai-caption-studio.git
cd ai-caption-studio
```

### 2. Run Setup (auto-installs Python deps and tries to provision FFmpeg)

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

## Start The App

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

You can also open directly with files:
```bash
python -m backend.ui.editor --video /path/to/video.mp4 --srt /path/to/captions.srt
```

## Editor Workflow

### A) Auto-generate captions
1. Open a video.
2. In **Auto Captions**, choose model/language.
3. Click **Auto-Generate From Video**.
4. Generated SRT loads into timeline and list.

### B) Paste lyrics and sync
1. Paste lyrics (one line per row) in **Lyrics Sync**.
2. Tune **Match Similarity**.
3. Click **Sync Pasted Lyrics To Captions**.
4. Timestamps stay in your timeline; text updates from lyrics.

### C) Edit timestamps and text
- Drag caption blocks in the timeline to move/resize time.
- Select a row in **Caption Timeline List**.
- Edit Start/End/Text in **Selected Caption**.
- Click **Apply Edit**.

### D) Export captioned video
1. Choose subtitle format (`srt` or `ass`).
2. Click **Export Captioned Video**.
3. Output is written to:
   - `/output/<video_stem>_captioned_srt.mp4` or
   - `/output/<video_stem>_captioned_ass.mp4`

## Troubleshooting

### "No QtMultimedia backends found"
- Recreate env with setup script.
- macOS: ensure no conflicting Qt vars:
  ```bash
  unset QT_PLUGIN_PATH
  unset QT_QPA_PLATFORM_PLUGIN_PATH
  ```

### "Your FFmpeg build does not include the 'subtitles' filter"
- macOS:
  ```bash
  brew install ffmpeg-full
  export FFMPEG_BIN=/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg
  ```

### Font warning: "OpenType support missing for .AppleSystemUIFont"
- This is a non-fatal Qt font warning and does not block export.

### First-run model download
- Whisper model is downloaded once into `/models`.
- After that, transcription is offline.

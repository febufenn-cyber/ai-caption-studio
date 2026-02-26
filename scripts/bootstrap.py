#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import platform
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
VENV_DIR = ROOT_DIR / ".venv"


def _shell_join(command: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in command)


def _run(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    print(f"+ {_shell_join(command)}")
    return subprocess.run(command, check=check, text=True, capture_output=False)


def _run_capture(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=False, text=True, capture_output=True)


def _venv_python() -> Path:
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def _validate_python() -> None:
    if sys.version_info < (3, 10):
        raise SystemExit(
            "Python 3.10+ is required.\n"
            "Install Python 3.11+ and rerun bootstrap."
        )


def _create_venv() -> Path:
    if not VENV_DIR.exists():
        _run([sys.executable, "-m", "venv", str(VENV_DIR)])
    else:
        print(f"Using existing virtual environment: {VENV_DIR}")

    python_bin = _venv_python()
    if not python_bin.exists():
        raise SystemExit(f"Virtual environment python not found at: {python_bin}")
    return python_bin


def _install_python_dependencies(python_bin: Path) -> None:
    _run([str(python_bin), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"])
    _run(
        [
            str(python_bin),
            "-m",
            "pip",
            "install",
            "--upgrade",
            "--force-reinstall",
            "-r",
            str(ROOT_DIR / "requirements.txt"),
        ]
    )


def _ffmpeg_has_subtitles_filter(ffmpeg_bin: str) -> bool:
    result = _run_capture([ffmpeg_bin, "-hide_banner", "-filters"])
    output = f"{result.stdout}\n{result.stderr}"
    for line in output.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "subtitles":
            return True
    return False


def _try_install_ffmpeg(with_export_support: bool) -> None:
    system = platform.system()

    if system == "Darwin" and shutil.which("brew"):
        package = "ffmpeg-full" if with_export_support else "ffmpeg"
        _run(["brew", "install", package], check=False)
        return

    if system == "Linux":
        if shutil.which("apt-get"):
            _run(["sudo", "apt-get", "update"], check=False)
            _run(["sudo", "apt-get", "install", "-y", "ffmpeg"], check=False)
            return
        if shutil.which("dnf"):
            _run(["sudo", "dnf", "install", "-y", "ffmpeg"], check=False)
            return
        if shutil.which("pacman"):
            _run(["sudo", "pacman", "-S", "--noconfirm", "ffmpeg"], check=False)
            return

    if system == "Windows":
        if shutil.which("winget"):
            _run(
                [
                    "winget",
                    "install",
                    "--id",
                    "Gyan.FFmpeg",
                    "-e",
                    "--accept-source-agreements",
                    "--accept-package-agreements",
                ],
                check=False,
            )
            return
        if shutil.which("choco"):
            _run(["choco", "install", "ffmpeg", "-y"], check=False)
            return


def _resolve_ffmpeg(with_export_support: bool) -> str | None:
    candidates: list[str] = []

    env_bin = os.environ.get("FFMPEG_BIN")
    if env_bin:
        candidates.append(env_bin)

    which_bin = shutil.which("ffmpeg")
    if which_bin:
        candidates.append(which_bin)

    if platform.system() == "Darwin":
        candidates.extend(
            [
                "/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg",
                "/usr/local/opt/ffmpeg-full/bin/ffmpeg",
            ]
        )

    deduped: list[str] = []
    for candidate in candidates:
        if candidate not in deduped and Path(candidate).exists():
            deduped.append(candidate)

    for ffmpeg_bin in deduped:
        if not with_export_support or _ffmpeg_has_subtitles_filter(ffmpeg_bin):
            return ffmpeg_bin

    return None


def _ensure_ffmpeg(with_export_support: bool) -> str:
    resolved = _resolve_ffmpeg(with_export_support)
    if resolved:
        return resolved

    print("FFmpeg not found (or missing subtitles filter). Attempting auto-install...")
    _try_install_ffmpeg(with_export_support)

    resolved = _resolve_ffmpeg(with_export_support)
    if resolved:
        return resolved

    system = platform.system()
    if system == "Darwin":
        hint = (
            "Run:\n"
            "  brew install ffmpeg-full\n"
            "  export FFMPEG_BIN=/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg\n"
        )
    elif system == "Windows":
        hint = "Run: winget install --id Gyan.FFmpeg -e\n"
    else:
        hint = "Run: install ffmpeg via your package manager (apt/dnf/pacman).\n"

    raise SystemExit(
        "Unable to provision FFmpeg automatically.\n"
        f"{hint}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap Offline AI Caption Studio")
    parser.add_argument(
        "--skip-ffmpeg",
        action="store_true",
        help="Skip FFmpeg installation checks.",
    )
    parser.add_argument(
        "--basic-ffmpeg",
        action="store_true",
        help="Require only base FFmpeg (no subtitles burn-in filter check).",
    )
    args = parser.parse_args()

    _validate_python()
    python_bin = _create_venv()
    _install_python_dependencies(python_bin)

    ffmpeg_bin = None
    if not args.skip_ffmpeg:
        ffmpeg_bin = _ensure_ffmpeg(with_export_support=not args.basic_ffmpeg)

    print("\nBootstrap complete.")
    if ffmpeg_bin:
        print(f"Resolved FFmpeg: {ffmpeg_bin}")

    if os.name == "nt":
        print("\nRun next:")
        print("  .\\.venv\\Scripts\\activate")
        print("  python -m backend.ui.editor")
        if ffmpeg_bin and Path(ffmpeg_bin).name.lower() == "ffmpeg":
            print(f"  set FFMPEG_BIN={ffmpeg_bin}")
    else:
        print("\nRun next:")
        print("  source .venv/bin/activate")
        if ffmpeg_bin and ffmpeg_bin not in (shutil.which("ffmpeg") or ""):
            print(f"  export FFMPEG_BIN={ffmpeg_bin}")
        print("  python -m backend.ui.editor")


if __name__ == "__main__":
    main()

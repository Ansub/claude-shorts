#!/usr/bin/env python3
"""Update the private yt-dlp and download a URL as MP3. Usage: get_music.py URL OUT_DIR"""
import argparse
from pathlib import Path
import subprocess
from platform_tools import find_tool, venv_python


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    parser.add_argument("out_dir")
    args = parser.parse_args()
    python = venv_python()
    if not python.is_file():
        parser.error("Run setup.ps1 (Windows) or bash setup.sh (macOS/Linux) first.")
    out = Path(args.out_dir).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    subprocess.run([str(python), "-m", "pip", "install", "--quiet", "--upgrade", "yt-dlp"], check=True)
    subprocess.run([str(python), "-m", "yt_dlp", "--ffmpeg-location", str(Path(find_tool("ffmpeg")).parent),
                    "--no-playlist", "-x", "--audio-format", "mp3", "--audio-quality", "0",
                    "-o", str(out / "%(title)s.%(ext)s"), "--print", "after_move:filepath", "--", args.url], check=True)


if __name__ == "__main__":
    main()

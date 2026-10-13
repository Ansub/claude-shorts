#!/usr/bin/env python3
"""Check the actual runtime, including codecs, SVG rendering and native executables."""
import subprocess
from pathlib import Path
import tempfile
from platform_tools import find_tool, svg_to_png
from PIL import Image
import io
import yt_dlp


def main():
    for name, args in (("ffmpeg", ["-version"]), ("ffprobe", ["-version"]), ("whisper-cli", ["--help"])):
        subprocess.run([find_tool(name), *args], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    # Some distro ffmpeg builds omit encoders used by the workflow. Fail here, not mid-edit.
    encoders = subprocess.check_output([find_tool("ffmpeg"), "-hide_banner", "-encoders"], text=True)
    for codec in ("libx264", "prores_ks", "aac", "libmp3lame"):
        if codec not in encoders:
            raise SystemExit(f"ffmpeg is missing {codec}; install a full ffmpeg build for this distribution.")
    with tempfile.TemporaryDirectory() as td:
        svg = Path(td) / "logo.svg"
        svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="20" height="10"><rect width="20" height="10" fill="red"/></svg>', encoding="utf-8")
        image = Image.open(io.BytesIO(svg_to_png(svg, 30)))
        assert image.size == (60, 30), image.size
    print("Verified ffmpeg codecs, ffprobe, whisper-cli, Pillow, SVG rendering and yt-dlp.")


if __name__ == "__main__":
    main()

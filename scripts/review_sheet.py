#!/usr/bin/env python3
"""One contact sheet for a batch of finished Shorts: three frames from each (25%, 50%, 75% in), labelled with
the file name and length, so a whole run can be checked at a glance.

Usage: review_sheet.py <folder with .mp4 files> [<out.jpg>]     (default: <folder>/review.jpg)
"""
from platform_tools import find_tool
import os, subprocess, sys, tempfile
from PIL import Image, ImageDraw

folder = sys.argv[1]; out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(folder, "review.jpg")
vids = sorted(f for f in os.listdir(folder) if f.lower().endswith(".mp4"))
if not vids: sys.exit(f"no .mp4 files in {folder}")
tw, th, lab = 180, 320, 34
g = Image.new("RGB", (tw * 3 + 8, (th + lab + 8) * len(vids)), "black"); d = ImageDraw.Draw(g)
tmp = tempfile.mkdtemp()
for r, v in enumerate(vids):
    p = os.path.join(folder, v)
    dur = float(subprocess.run([find_tool("ffprobe"), "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p],
                               capture_output=True, text=True, encoding="utf-8", errors="replace").stdout)
    y = r * (th + lab + 8)
    d.text((6, y + 4), v[:90], fill="white"); d.text((6, y + 18), f"{dur:.1f}s", fill=(255, 230, 0))
    for k, f in enumerate((0.25, 0.5, 0.75)):
        j = os.path.join(tmp, f"{r}_{k}.jpg")
        subprocess.run([find_tool("ffmpeg"), "-y", "-v", "error", "-ss", f"{dur * f:.2f}", "-i", p, "-frames:v", "1",
                        "-vf", f"scale={tw}:{th}", j], check=True)
        g.paste(Image.open(j), (k * (tw + 4), y + lab))
g.save(out, quality=85)
print(f"{len(vids)} Shorts -> {out}")

#!/usr/bin/env python3
"""Pull candidate thumbnail frames and tile them into a labelled contact sheet.

Usage: frame_sheet.py <source_video> <out_dir> <t1,t2,...> [--face x0,y0,x1,y1]
Writes <out_dir>/f_<t>.png (1080x1920) and <out_dir>/sheet.jpg. With --face, also writes
<out_dir>/faces.jpg: the same crop of every frame side by side, for checking eyes and mouth.
"""
import os, subprocess, sys
from PIL import Image, ImageDraw

src, out, times = sys.argv[1:4]
os.makedirs(out, exist_ok=True)
ts = times.split(",")
frames = []
for t in ts:
    p = os.path.join(out, f"f_{t}.png")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", t, "-i", src, "-frames:v", "1",
                    "-vf", "scale=1080:1920", p], check=True)
    frames.append((t, Image.open(p)))
cols = 8; rows = (len(frames) + cols - 1) // cols
g = Image.new("RGB", (270 * cols, 480 * rows), "white"); d = ImageDraw.Draw(g)
for i, (t, im) in enumerate(frames):
    x, y = (i % cols) * 270, (i // cols) * 480
    g.paste(im.resize((270, 480)), (x, y)); d.text((x + 8, y + 8), t, fill="yellow")
g.save(os.path.join(out, "sheet.jpg"), quality=88)
if "--face" in sys.argv:
    box = tuple(int(v) for v in sys.argv[sys.argv.index("--face") + 1].split(","))
    fw, fh = 400, int(400 * (box[3] - box[1]) / (box[2] - box[0]))
    f = Image.new("RGB", (fw * len(frames), fh))
    for i, (t, im) in enumerate(frames):
        f.paste(im.crop(box).resize((fw, fh)), (i * fw, 0))
    f.save(os.path.join(out, "faces.jpg"), quality=88)
print(os.path.join(out, "sheet.jpg"))

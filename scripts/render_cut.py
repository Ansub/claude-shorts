#!/usr/bin/env python3
"""Render the tightened clip from segments.json: frame-exact trim+concat, scaled to 1080x1920, source frame rate.

Usage: render_cut.py <clip> <workdir>
Writes <workdir>/cut.mov (H.264 CRF 12 + PCM audio, near-lossless intermediate) and checks its frame count.
"""
from platform_tools import find_tool
import json, os, subprocess, sys

clip, work = sys.argv[1], sys.argv[2]
segs = json.load(open(os.path.join(work, "segments.json"), encoding="utf-8"))
fr = subprocess.run([find_tool("ffprobe"), "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate",
                     "-of", "csv=p=0", clip], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout.strip()
num, den = (float(x) for x in (fr.split("/") + ["1"])[:2])
parts = []
for i, s in enumerate(segs):
    a, b = s["sf"] * den / num, s["ef"] * den / num
    parts.append(f"[0:v]trim=start_frame={s['sf']}:end_frame={s['ef']},setpts=PTS-STARTPTS[v{i}]")
    parts.append(f"[0:a]atrim=start={a:.6f}:end={b:.6f},asetpts=PTS-STARTPTS[a{i}]")
n = len(segs)
fc = ";".join(parts) + ";" + "".join(f"[v{i}][a{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=1[cv][ca]"
fc += ";[cv]scale=1080:1920:flags=lanczos,format=yuv420p[ov]"
out = os.path.join(work, "cut.mov")
subprocess.run([find_tool("ffmpeg"), "-y", "-v", "error", "-i", clip, "-filter_complex", fc, "-map", "[ov]", "-map", "[ca]",
                "-r", fr, "-c:v", "libx264", "-crf", "12", "-preset", "fast", "-c:a", "pcm_s16le", "-ar", "48000", out], check=True)
frames = int(subprocess.run([find_tool("ffprobe"), "-v", "error", "-select_streams", "v:0", "-count_packets", "-show_entries",
                             "stream=nb_read_packets", "-of", "csv=p=0", out], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout.strip())
expected = sum(s["ef"] - s["sf"] for s in segs)
print(f"{out}: {frames} frames (expected {expected}) at {fr}")
if frames != expected:
    sys.exit("frame count mismatch")

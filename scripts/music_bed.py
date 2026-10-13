#!/usr/bin/env python3
"""Build a background-music bed exactly as long as the cut, ducked under the voice.

Usage: music_bed.py <music file> <workdir> [--under 13.5] [--start 0]

- Uses <workdir>/cut.mov's audio only as the ducking key and loudness reference (the voice is not touched).
- Sets the music so its integrated loudness sits --under dB below the voice (13.5 was approved).
- Sidechain ducking (ratio 2.5, 40 ms attack, 400 ms release), 0.6 s fade in, 2.5 s fade out.
- --start skips into the track (seconds) when its intro is too quiet or too long.
Writes <workdir>/music.wav (48 kHz stereo, exactly the cut's sample length).
"""
from platform_tools import find_tool
import argparse, os, re, subprocess

ap = argparse.ArgumentParser()
ap.add_argument("music"); ap.add_argument("work")
ap.add_argument("--under", type=float, default=13.5); ap.add_argument("--start", type=float, default=0)
a = ap.parse_args()
cut = os.path.join(a.work, "cut.mov"); out = os.path.join(a.work, "music.wav")


def lufs(path):
    r = subprocess.run([find_tool("ffmpeg"), "-hide_banner", "-nostats", "-i", path, "-af", "ebur128", "-f", "null", "-"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace").stderr
    return float(re.findall(r"I:\s+(-?[\d.]+) LUFS", r)[-1])


D = float(subprocess.run([find_tool("ffprobe"), "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=duration",
                          "-of", "csv=p=0", cut], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout)
N = round(D * 48000)
v = lufs(cut)


def build(gain_db):
    fc = (f"[0:a]aresample=48000,atrim=start={a.start}:end_sample={N + round(a.start * 48000)},asetpts=PTS-STARTPTS,volume={gain_db:.2f}dB[m];"
          f"[1:a]aresample=48000,asplit=2[sc][v];[m][sc]sidechaincompress=threshold=0.015:ratio=2.5:attack=40:release=400:makeup=1[duck];"
          f"[duck]afade=t=in:d=0.6,afade=t=out:st={D - 2.5:.4f}:d=2.5,apad=whole_len={N},atrim=end_sample={N}[out];[v]anullsink")
    subprocess.run([find_tool("ffmpeg"), "-y", "-v", "error", "-i", a.music, "-i", cut, "-filter_complex", fc,
                    "-map", "[out]", "-ac", "2", "-c:a", "pcm_s24le", out], check=True)
    return lufs(out)


target = v - a.under
g = -10.0
for _ in range(3):  # ducking depends on level, so converge in a few passes
    m = build(g); g += target - m
m = build(g)
print(f"voice {v:.1f} LUFS, music {m:.1f} LUFS ({v - m:.1f} dB under), {D:.2f}s -> {out}")

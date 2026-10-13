#!/usr/bin/env python3
"""Find the framing changes (hard cuts and crossfades) inside each picked clip and make a labelled contact sheet per
clip, so Claude can say which shots are face-to-camera and which are screen recordings.

Usage: shots.py <clips.json> <workdir> [--thresh 0.3] [--min 0.8] [--every 2]

- Detection runs once over the whole source (low-res decode) and is cached in <workdir>/scenes.json: hard cuts at
  their exact time, crossfades to within about 0.25 s (the middle of the dissolve). Animated cards and big screen
  changes also show up as "crossfades": give those shots the same layout as their neighbour; an extra shot costs
  nothing.
- Each clip in clips.json gets "shots": [{start, end, layout}] split at those cuts. Shots shorter than --min seconds
  are merged into the previous one. An existing layout is kept when a shot's start matches; new shots get
  layout null (fill it in). Rerunning is safe.
- <workdir>/shots/<id>.jpg: one frame from the middle of every shot, labelled "k  start-end", with a 10% grid
  (lines at 0.1, 0.2, ...) so you can read layout boxes as fractions of the frame.
- <workdir>/shots/<id>_<k>.jpg: the same frame alone at 1280 wide, for reading boxes precisely.
- <workdir>/shots/<id>_timeline.jpg: a frame every --every seconds across the pick, labelled with source time.
  Use it to confirm the shots, and to split one by hand if a slow change was still missed.
"""
from platform_tools import find_tool
import json, os, re, subprocess, sys
from PIL import Image, ImageDraw

args = sys.argv[1:]
def opt(name, default):
    if name in args:
        i = args.index(name); v = args[i + 1]; del args[i:i + 2]; return v
    return default
thresh, mins, every = float(opt("--thresh", "0.3")), float(opt("--min", "0.8")), float(opt("--every", "2"))
spec_path, work = args[0], args[1]
spec = json.load(open(spec_path, encoding="utf-8")); src = spec["source"]
sd = os.path.join(work, "shots"); os.makedirs(sd, exist_ok=True)

cache = os.path.join(work, "scenes.json")
c0 = json.load(open(cache, encoding="utf-8")) if os.path.exists(cache) else {}
if c0.get("thresh") == thresh and "fades" in c0:
    cuts, fades = c0["cuts"], c0["fades"]
else:
    print("detecting cuts and crossfades over the whole video (once, about 1 min per 10 min of 4K)...", file=sys.stderr)
    r = subprocess.run([find_tool("ffmpeg"), "-hide_banner", "-nostats", "-i", src, "-an", "-vf",
                        f"scale=320:-2,select='gt(scene,{thresh})',showinfo", "-f", "null", "-"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace").stderr
    cuts = [round(float(t), 3) for t in re.findall(r"pts_time:([\d.]+)", r)]
    # crossfades: compare tiny grey frames 1 s apart. A dissolve between framings is a big bump; scrolling and
    # talking are small. Peaks are framing changes the scene filter (hard cuts only) misses.
    R, w, h = 4, 64, 36
    raw = subprocess.run([find_tool("ffmpeg"), "-v", "error", "-i", src, "-an", "-vf", f"fps={R},scale={w}:{h},format=gray",
                          "-f", "rawvideo", "-"], capture_output=True).stdout
    n = len(raw) // (w * h); px = w * h
    d = [0.0] * n
    for i in range(R, n):
        a_, b_ = raw[i * px:(i + 1) * px], raw[(i - R) * px:(i - R + 1) * px]
        d[i] = sum(abs(x - y) for x, y in zip(a_, b_)) / px
    vals = sorted(d[R:]) or [0]; th = max(12, 3 * vals[len(vals) // 2])
    fades = [round((i - R / 2) / R, 2) for i in range(R, n)
             if d[i] >= th and d[i] == max(d[max(R, i - R):i + R + 1])]
    fades = [t for t in fades if all(abs(t - c) > 0.6 for c in cuts)]  # hard cuts already have exact times
    json.dump({"thresh": thresh, "cuts": cuts, "fades": fades}, open(cache, "w", encoding="utf-8"))
print(f"{len(cuts)} hard cuts and {len(fades)} possible crossfades in the source")


def grid(im):
    d = ImageDraw.Draw(im); w, h = im.size
    for k in range(1, 10):
        x, y = w * k / 10, h * k / 10
        d.line([(x, 0), (x, h)], fill=(255, 230, 0), width=1); d.line([(0, y), (w, y)], fill=(255, 230, 0), width=1)
        d.text((x + 3, 3), f".{k}", fill=(255, 230, 0)); d.text((3, y + 3), f".{k}", fill=(255, 230, 0))
    return im


for c in spec["clips"]:
    S, E = c["start"], c["end"]
    bounds = [S] + sorted(t for t in cuts + fades if S + 0.5 <= t <= E - 0.5) + [E]  # a framing change near an edge still counts
    merged = [bounds[0]]
    for t in bounds[1:-1]:
        if t - merged[-1] >= mins: merged.append(t)
    merged.append(E)
    old = {round(s["start"], 1): s.get("layout") for s in c.get("shots", [])}
    c["shots"] = [{"start": round(a, 3), "end": round(b, 3), "layout": old.get(round(a, 1))}
                  for a, b in zip(merged, merged[1:])]
    tiles = []
    for k, sh in enumerate(c["shots"]):
        f = os.path.join(sd, f"{c['id']}_{k}.jpg")
        subprocess.run([find_tool("ffmpeg"), "-y", "-v", "error", "-ss", f"{(sh['start'] + sh['end']) / 2:.3f}", "-i", src,
                        "-frames:v", "1", "-vf", "scale=1280:-2", "-q:v", "3", f], check=True)
        im = grid(Image.open(f).convert("RGB")); im.save(f, quality=88); tiles.append((k, sh, im))
    tw = 480; th = round(tw * tiles[0][2].height / tiles[0][2].width); cols = 3; rows = (len(tiles) + cols - 1) // cols
    g = Image.new("RGB", (tw * cols, (th + 22) * rows), "black"); d = ImageDraw.Draw(g)
    for i, (k, sh, im) in enumerate(tiles):
        x, y = (i % cols) * tw, (i // cols) * (th + 22)
        g.paste(im.resize((tw, th)), (x, y + 22))
        d.text((x + 6, y + 5), f"{k}  {sh['start']:.1f}-{sh['end']:.1f}  ({sh['end'] - sh['start']:.1f}s)  {sh['layout'] or '?'}", fill="white")
    g.save(os.path.join(sd, f"{c['id']}.jpg"), quality=85)
    td = os.path.join(sd, f".{c['id']}_tl"); os.makedirs(td, exist_ok=True)
    for f in os.listdir(td): os.remove(os.path.join(td, f))
    subprocess.run([find_tool("ffmpeg"), "-y", "-v", "error", "-ss", f"{S:.3f}", "-t", f"{E - S:.3f}", "-i", src, "-an",
                    "-vf", f"fps=1/{every},scale=240:-2", os.path.join(td, "%04d.jpg")], check=True)
    fr = sorted(os.listdir(td))
    if fr:
        im0 = Image.open(os.path.join(td, fr[0])); cw, chh = im0.size; cols = 8; rows = (len(fr) + cols - 1) // cols
        g = Image.new("RGB", (cw * cols, (chh + 16) * rows), "black"); d = ImageDraw.Draw(g)
        for i, f in enumerate(fr):
            x, y = (i % cols) * cw, (i // cols) * (chh + 16)
            g.paste(Image.open(os.path.join(td, f)), (x, y + 16)); d.text((x + 4, y + 2), f"{S + i * every:.1f}", fill=(255, 230, 0))
        g.save(os.path.join(sd, f"{c['id']}_timeline.jpg"), quality=82)
    print(f"{c['id']}: {len(c['shots'])} shots -> {os.path.join(sd, c['id'] + '.jpg')}")

json.dump(spec, open(spec_path, "w", encoding="utf-8"), indent=1)

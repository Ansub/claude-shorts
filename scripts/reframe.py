#!/usr/bin/env python3
"""Cut one clip out of a long (usually landscape) video and reframe it to a 1080x1920 vertical source.

Usage: reframe.py <clips.json> <clip id> <out dir>            -> <out dir>/source.mov + bands.json
       reframe.py <clips.json> <clip id> <out dir> --stills   -> <out dir>/stills/shot_<k>.jpg (one per shot, for checking)
       reframe.py <clips.json> <clip id> <out dir> --bands-only -> rewrite bands.json only (after a layout "captions"
                                                                  change; no re-encode, shot times must be unchanged)

clips.json (written by Claude, shots filled by shots.py):
  {"source": "/path/long.mp4",
   "layouts": {"cam":  {"type": "face",  "cx": 0.5, "cy": 0.45, "zoom": 1.0},
               "demo": {"type": "split", "screen": [x, y, w, h], "face": [x, y, w, h], "top": 960},
               "flat": {"type": "full"}},
   "clips": [{"id": "s01", "start": 12.3, "end": 71.0, "title": "...", "hook": "...",
              "shots": [{"start": 12.3, "end": 30.1, "layout": "cam"}, ...]}]}

All boxes are fractions of the source frame (0-1), so they work at any resolution.
- face:  a 9:16 window centred on (cx, cy). zoom 1 = full source height, 1.3 = tighter.
- split: the screen box goes on top (1080 x top), the face box below (1080 x 1920-top). The screen box is grown
         to its panel's aspect (nothing you asked for is cut off); the face box is trimmed to it (draw it just
         inside the face-cam bubble, so the bubble's edges never show).
- full:  the whole frame scaled to fit, black bars (for sources that are already vertical).

bands.json gives every shot its own caption band (captions.py reads it from the clip's workdir): split -> just above
the seam (it ends 20 px above it), over the bottom of the screen panel, on a 75% dark backdrop so words read
over white boards and busy screens; face -> lower
third (long-form framing leaves no room above the head); full -> the top. A block takes the band of the shot it
starts in.
Audio is copied as PCM. Output is H.264 CRF 12 at the source frame rate, frame count checked.
"""
from platform_tools import find_tool
import json, os, subprocess, sys

spec_path, cid, out = sys.argv[1], sys.argv[2], sys.argv[3]
stills, bands_only = "--stills" in sys.argv, "--bands-only" in sys.argv
spec = json.load(open(spec_path, encoding="utf-8"))
src = spec["source"]
clip = next((c for c in spec["clips"] if c["id"] == cid), None) or sys.exit(f"no clip {cid} in {spec_path}")
L = spec.get("layouts", {})
os.makedirs(out, exist_ok=True)

p = subprocess.run([find_tool("ffprobe"), "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,r_frame_rate",
                    "-of", "csv=p=0", src], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout.split()[0].split(",")  # first line: some files repeat it
W, H, FR = int(p[0]), int(p[1]), p[2]
num, den = (float(x) for x in (FR.split("/") + ["1"])[:2]); fps = num / den

S, E = clip["start"], clip["end"]
shots = clip.get("shots") or [{"start": S, "end": E, "layout": spec.get("default", next(iter(L), "flat"))}]
for k, sh in enumerate(shots):
    if sh.get("layout") not in L and sh.get("layout") != "flat":
        sys.exit(f"{cid} shot {k} ({sh['start']}-{sh['end']}): layout {sh.get('layout')!r} is not in layouts {list(L)}")
shots[0]["start"], shots[-1]["end"] = S, E  # shots always cover the clip exactly


def even(v): return int(round(v / 2) * 2)


def fit(box, aspect, grow=True):
    """Fractional [x,y,w,h] -> pixel crop with exactly this w/h aspect, around the box centre, inside the frame.
    grow=True widens the short side (keeps everything in the box: screens); False trims the long side (face bubbles,
    whose edges must not show)."""
    x, y, w, h = box[0] * W, box[1] * H, box[2] * W, box[3] * H
    cx, cy = x + w / 2, y + h / 2
    if (w / h > aspect) == grow: h = w / aspect
    else: w = h * aspect
    if w > W: w, h = W, W / aspect
    if h > H: h, w = H, H * aspect
    w, h = even(w), even(h)
    x = even(min(max(cx - w / 2, 0), W - w)); y = even(min(max(cy - h / 2, 0), H - h))
    return f"crop={w}:{h}:{x}:{y}"


def chain(lay, inp, lab):
    """Filter chain turning stream [inp] into a 1080x1920 stream [lab] for one layout."""
    t = lay.get("type", "full") if isinstance(lay, dict) else "full"
    if t == "face":
        z = lay.get("zoom", 1.0); h = 1 / z; w = h * (9 / 16) * H / W
        box = [lay.get("cx", 0.5) - w / 2, lay.get("cy", 0.5) - h / 2, w, h]
        return f"[{inp}]{fit(box, 9 / 16)},scale=1080:1920:flags=lanczos,setsar=1[{lab}]"
    if t == "split":
        top = int(lay.get("top", 960)); bot = 1920 - top
        return (f"[{inp}]split=2[{lab}a][{lab}b];"
                f"[{lab}a]{fit(lay['screen'], 1080 / top)},scale=1080:{top}:flags=lanczos,setsar=1[{lab}t];"
                f"[{lab}b]{fit(lay['face'], 1080 / bot, grow=False)},scale=1080:{bot}:flags=lanczos,setsar=1[{lab}u];"
                f"[{lab}t][{lab}u]vstack[{lab}]")
    return (f"[{inp}]scale=1080:1920:force_original_aspect_ratio=decrease:flags=lanczos,"
            f"pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,setsar=1[{lab}]")


if stills:
    sd = os.path.join(out, "stills"); os.makedirs(sd, exist_ok=True)
    for k, sh in enumerate(shots):
        mid = (sh["start"] + sh["end"]) / 2
        f = os.path.join(sd, f"shot_{k}.jpg")
        subprocess.run([find_tool("ffmpeg"), "-y", "-v", "error", "-ss", f"{mid:.3f}", "-i", src, "-frames:v", "1",
                        "-filter_complex", chain(L.get(sh["layout"], "flat"), "0:v", "o"), "-map", "[o]", "-q:v", "3", f], check=True)
        print(f"{f}  {sh['start']:.2f}-{sh['end']:.2f}  {sh['layout']}")
    sys.exit()

BAND = {"split": {"cy": 815, "safeTop": 690, "safeBot": 940, "backdropOpacity": 75},
        "face": {"cy": 1290, "safeTop": 1140, "safeBot": 1440, "backdropOpacity": 0},
        "full": {"cy": 430, "safeTop": 260, "safeBot": 610, "backdropOpacity": 0}}
bands, used = [], set()
for sh in shots:  # one caption band per shot; a layout can override it with "captions": {cy, safeTop, safeBot, backdropOpacity}
    lay = L.get(sh["layout"]); t = lay.get("type", "full") if isinstance(lay, dict) else "full"; used.add(t)
    b = dict(BAND[t]); b.update(lay.get("captions", {}) if isinstance(lay, dict) else {})
    bands.append({"start": round(sh["start"] - S, 3), "end": round(sh["end"] - S + (1 if sh is shots[-1] else 0), 3), **b})
json.dump(bands, open(os.path.join(out, "bands.json"), "w", encoding="utf-8"), indent=1)

if bands_only:
    print(f"{os.path.join(out, 'bands.json')}: {len(bands)} shots"); sys.exit()

n = len(shots); fc = [f"[0:v]split={n}" + "".join(f"[i{k}]" for k in range(n)) if n > 1 else "[0:v]null[i0]"]
for k, sh in enumerate(shots):
    a, b = sh["start"] - S, sh["end"] - S
    fc.append(f"[i{k}]trim=start={a:.4f}:end={b:.4f},setpts=PTS-STARTPTS[r{k}]")
    fc.append(chain(L.get(sh["layout"], "flat"), f"r{k}", f"v{k}"))
fc.append("".join(f"[v{k}]" for k in range(n)) + f"concat=n={n}:v=1:a=0,fps={FR},format=yuv420p[ov]")
dst = os.path.join(out, "source.mov")
subprocess.run([find_tool("ffmpeg"), "-y", "-v", "error", "-ss", f"{S:.4f}", "-t", f"{E - S:.4f}", "-i", src,
                "-filter_complex", ";".join(fc), "-map", "[ov]", "-map", "0:a:0", "-r", FR, "-t", f"{E - S:.4f}",
                "-c:v", "libx264", "-crf", "12", "-preset", "fast", "-c:a", "pcm_s16le", "-ar", "48000", dst], check=True)

frames = int(subprocess.run([find_tool("ffprobe"), "-v", "error", "-select_streams", "v:0", "-count_packets", "-show_entries",
                             "stream=nb_read_packets", "-of", "csv=p=0", dst], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout.strip())
print(f"{dst}: {frames} frames ({frames / fps:.2f}s, expected {E - S:.2f}s) at {FR}, {n} shots, layouts {sorted(used)}, "
      f"caption bands -> bands.json")
if abs(frames / fps - (E - S)) > 2 / fps:
    sys.exit("frame count mismatch")

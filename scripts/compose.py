#!/usr/bin/env python3
"""Final render: cut + caption layer + optional image overlays + voice gain + music, normalised to -14 LUFS.

Usage: compose.py <workdir> <out.mp4> [--no-music] [--lufs -14]

Inputs in <workdir>: cut.mov, captions.mov (ProRes 4444 with alpha), music.wav (optional),
overlays.json (optional): [{"file": "img.png", "start": 3.2, "end": 5.0, "x": 90, "y": 260, "w": 900}]
(PNG/JPG placed on top for that time range; keep y+h above 1440 so the Shorts UI never covers it).

Voice: plain gain only (EQ and compression made real voices sound worse): + floor(-1 - peak dBFS) dB.
Then two-pass loudnorm I=-14 TP=-1 LRA=11 linear on the mix (YouTube/IG never turn quiet videos up), and a
-1 dBFS safety limiter after it (loud, already-mastered exports could still peak at 0 dBFS).
Video: H.264 CRF 16, yuv420p, 1080x1920, source frame rate, +faststart. Prints LUFS and true peak.
"""
from platform_tools import find_tool
import argparse, json, math, os, re, subprocess

ap = argparse.ArgumentParser(); ap.add_argument("work"); ap.add_argument("out")
ap.add_argument("--no-music", action="store_true"); ap.add_argument("--lufs", type=float, default=-14)
a = ap.parse_args()
P = lambda f: os.path.join(a.work, f)

peak = float(re.findall(r"Peak level dB:\s+(-?[\d.inf]+)", subprocess.run(
    [find_tool("ffmpeg"), "-hide_banner", "-nostats", "-i", P("cut.mov"), "-af", "astats=measure_perchannel=none", "-f", "null", "-"],
    capture_output=True, text=True, encoding="utf-8", errors="replace").stderr)[-1])
gain = max(0, math.floor(-1 - peak))

inputs = ["-i", P("cut.mov"), "-i", P("captions.mov")]
fc = ["[0:v][1:v]overlay=0:0:format=auto[v0]"]
last = "v0"; idx = 2
ovs = json.load(open(P("overlays.json"), encoding="utf-8")) if os.path.exists(P("overlays.json")) else []
for k, o in enumerate(ovs):
    inputs += ["-loop", "1", "-i", o["file"] if os.path.isabs(o["file"]) else P(o["file"])]
    fc.append(f"[{idx}:v]scale={o.get('w', 900)}:-1,format=rgba,fade=in:st={o['start']}:d=0.12:alpha=1[o{k}]")
    fc.append(f"[{last}][o{k}]overlay={o.get('x', 90)}:{o.get('y', 260)}:enable='between(t,{o['start']},{o['end']})':shortest=1[v{k + 1}]")
    last = f"v{k + 1}"; idx += 1
music = not a.no_music and os.path.exists(P("music.wav"))
fc.append(f"[0:a]volume={gain}dB[voice]")
if music:
    inputs += ["-i", P("music.wav")]
    fc.append(f"[voice][{idx}:a]amix=inputs=2:normalize=0:duration=first[mix]")
else:
    fc.append("[voice]anull[mix]")
fc_s = ";".join(fc)
fr = subprocess.run([find_tool("ffprobe"), "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate",
                     "-of", "csv=p=0", P("cut.mov")], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout.strip()

# pass 1: measure the mix (audio-only graph: an unconnected video output would make ffmpeg refuse the graph)
a_inputs = ["-i", P("cut.mov")] + (["-i", P("music.wav")] if music else [])
a_fc = f"[0:a]volume={gain}dB[voice];" + ("[voice][1:a]amix=inputs=2:normalize=0:duration=first[m0]" if music else "[voice]anull[m0]")
m = subprocess.run([find_tool("ffmpeg"), "-hide_banner", "-nostats", *a_inputs, "-filter_complex",
                    a_fc + f";[m0]loudnorm=I={a.lufs}:TP=-1:LRA=11:print_format=json[mix]",
                    "-map", "[mix]", "-f", "null", "-"], capture_output=True, text=True, encoding="utf-8", errors="replace").stderr
if "{" not in m:
    raise SystemExit(m[-1500:])
j = json.loads(m[m.rindex("{"):m.rindex("}") + 1])
ln = (f"loudnorm=I={a.lufs}:TP=-1:LRA=11:measured_I={j['input_i']}:measured_TP={j['input_tp']}:"
      f"measured_LRA={j['input_lra']}:measured_thresh={j['input_thresh']}:offset={j['target_offset']}:linear=true")
# pass 2: render
subprocess.run([find_tool("ffmpeg"), "-y", "-v", "error", *inputs, "-filter_complex",
                fc_s.replace("[mix]", "[m0]") + f";[m0]{ln},aresample=48000,alimiter=limit=0.891:level=false[mix]",
                "-map", f"[{last}]", "-map", "[mix]", "-r", fr, "-c:v", "libx264", "-crf", "16", "-preset", "medium",
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "256k", "-movflags", "+faststart", a.out], check=True)
r = subprocess.run([find_tool("ffmpeg"), "-hide_banner", "-nostats", "-i", a.out, "-af", "ebur128=peak=true", "-f", "null", "-"],
                   capture_output=True, text=True, encoding="utf-8", errors="replace").stderr
I = re.findall(r"I:\s+(-?[\d.]+) LUFS", r)[-1]; tp = re.findall(r"Peak:\s+(-?[\d.]+) dBFS", r)[-1]
print(f"voice +{gain} dB (peak was {peak:.1f} dBFS), music {'on' if music else 'off'}, {len(ovs)} image overlays")
print(f"{a.out}: {I} LUFS, true peak {tp} dBFS")

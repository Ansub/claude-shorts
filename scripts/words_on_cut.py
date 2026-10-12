#!/usr/bin/env python3
"""Map the transcript's words onto the cut timeline.

Usage: words_on_cut.py <workdir> [--fps 30000/1001]
Writes <workdir>/words_cut.json  [[start, end, word], ...] in cut seconds. Words whose midpoint falls in a
removed stretch are dropped. Cuts sit in silence, so mapped times are as accurate as the source times.
"""
import json, os, sys

work = sys.argv[1]
num, den = (float(x) for x in ((sys.argv[sys.argv.index("--fps") + 1] if "--fps" in sys.argv else "30000/1001").split("/") + ["1"])[:2])
fps = num / den
segs, rec = [], 0
for s in json.load(open(os.path.join(work, "segments.json"), encoding="utf-8")):
    segs.append((s["sf"] / fps, s["ef"] / fps, rec / fps)); rec += s["ef"] - s["sf"]
words, bad = [], []
for ch in json.load(open(os.path.join(work, "transcript.json"), encoding="utf-8"))["chunks"]:
    for w in ch.get("words", []):
        if w["end"] - w["start"] > 3:  # whisper sometimes stretches one word over seconds of silence: no real word is that long
            bad.append(f"{w['w']} ({w['start']:.1f}-{w['end']:.1f})"); continue
        m = (w["start"] + w["end"]) / 2
        for a, b, r in segs:
            if a <= m < b:
                words.append([round(max(a, w["start"]) - a + r, 3), round(min(b, w["end"]) - a + r, 3), w["w"]]); break
json.dump(words, open(os.path.join(work, "words_cut.json"), "w", encoding="utf-8"))
if bad: print(f"dropped {len(bad)} word(s) with impossible timing: {', '.join(bad)}")
print(f"{len(words)} words -> {os.path.join(work, 'words_cut.json')}")

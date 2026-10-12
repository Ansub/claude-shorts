#!/usr/bin/env python3
"""Snap every pick's start and end in clips.json to silence between words, so no Short starts or ends mid-word.

Usage: edges.py <workdir> <clips.json>

Needs <workdir>/transcript.json and audio.wav from transcribe.py run on the whole video. Finished exports have
long chunks (few pauses), so pick edges usually fall inside a chunk; this works at word level instead.
- start: moves to the quietest point in the gap before the first word whose middle is inside the pick
- end:   moves to the quietest point in the gap after the last word whose middle is inside the pick
The gap is searched up to 0.4 s out from the word. Prints each change with the first and last words, so you can
check the pick still opens on its hook and ends on its payoff. Writes clips.json back.
"""
import json, math, os, struct, sys, wave

work, path = sys.argv[1], sys.argv[2]
words = sorted((w for c in json.load(open(os.path.join(work, "transcript.json"), encoding="utf-8"))["chunks"] for w in c.get("words", [])
                if w["end"] - w["start"] <= 3), key=lambda w: w["start"])  # >3 s "words" are whisper glitches
w_ = wave.open(os.path.join(work, "audio.wav")); sr = w_.getframerate(); n = w_.getnframes()
s = struct.unpack(f"<{n}h", w_.readframes(n)); win = sr // 100
lv = [math.sqrt(sum(x * x for x in s[k:k + win]) / win) for k in range(0, n - win, win)]
pk = max(lv) or 1; lv = [x / pk for x in lv]; dur = n / sr


def quiet(a, b):
    """Quietest 10 ms step in [a, b], judged on the 80 ms around it."""
    best, bt = 9, (a + b) / 2
    for k in range(int(max(0, a) * 100), int(min(dur, b) * 100) + 1):
        v = max(lv[max(0, k - 4):k + 4] or [0])
        if v < best: best, bt = v, k / 100
    return round(bt, 3), best


spec = json.load(open(path, encoding="utf-8"))
for c in spec["clips"]:
    mid = lambda w: (w["start"] + w["end"]) / 2  # a word belongs to the pick if its middle is inside
    i = next((k for k, w in enumerate(words) if mid(w) >= c["start"]), None)
    j = max((k for k, w in enumerate(words) if mid(w) <= c["end"]), default=None)
    if i is None or j is None or j < i:
        print(f"{c['id']}: no words inside {c['start']}-{c['end']}"); continue
    # whisper word times often touch (one word ends where the next starts), so search the audio around the
    # boundary, bounded by the neighbouring words' middles, not by their timestamps
    a0 = mid(words[i - 1]) if i else 0
    s0, sv = quiet(max(a0, words[i]["start"] - 0.4), words[i]["start"] + 0.05)
    b1 = mid(words[j + 1]) if j + 1 < len(words) else dur
    e0, ev = quiet(words[j]["end"] - 0.05, min(b1, words[j]["end"] + 0.4))
    first = " ".join(w["w"] for w in words[i:i + 6]); last = " ".join(w["w"] for w in words[max(i, j - 5):j + 1])
    flag = (f"  WARN edge not silent (level {max(sv, ev):.2f}, needs < 0.03): words run together or music under the"
            f" voice; try the next sentence break, or pass --thresh to plan_cut if music is the cause") if max(sv, ev) >= 0.03 else ""
    print(f"{c['id']}: {c['start']:.2f}-{c['end']:.2f} -> {s0:.2f}-{e0:.2f} ({e0 - s0:.1f}s)  \"{first} ...\" ... \"{last}\"{flag}")
    c["start"], c["end"] = s0, e0
    for sh in c.get("shots", [])[:1]: sh["start"] = s0
    for sh in c.get("shots", [])[-1:]: sh["end"] = e0
json.dump(spec, open(path, "w", encoding="utf-8"), indent=1)

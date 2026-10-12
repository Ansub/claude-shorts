#!/usr/bin/env python3
"""Turn a list of kept chunks into frame-accurate cut segments, checking every cut point is silent.

Usage: plan_cut.py <workdir> <keep> --fps 30000/1001 [--gap 0.5] [--thresh 0.03]

<keep> is "all" (every chunk with words: for finished exports), or a comma list of chunk ids from transcript.md,
e.g. "c05,c06,c07,c08", optionally with a
trimmed range "c12:33.70-35.36" (source seconds) to drop a stray word at a chunk edge.

Rules (tuned on real Shorts):
- head pad 0.15 s before the first word, tail pad 0.10 s after the last
- kept chunks less than --gap apart stay joined (pauses inside a thought are kept)
- a gap >= --gap is cut: the piece ends at chunk end + 0.08 and the next starts at chunk start - 0.12
- every cut point is checked against the audio: the 80 ms around it must be below --thresh of peak

Writes <workdir>/segments.json [{start, end, sf, ef}] and prints the cut list + old -> new runtime.
"""
import argparse, json, math, os, struct, sys, wave


def levels(path):
    w = wave.open(path); sr = w.getframerate(); n = w.getnframes(); s = struct.unpack(f"<{n}h", w.readframes(n))
    win = int(sr * 0.01); r = [math.sqrt(sum(x * x for x in s[k:k + win]) / win) for k in range(0, n - win, win)]
    p = max(r) or 1; return [x / p for x in r]


def loud_at(r, t):
    k = int(t * 100); seg = r[max(0, k - 4):k + 4]; return max(seg) if seg else 0


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("work"); ap.add_argument("keep")
    ap.add_argument("--fps", default="30000/1001"); ap.add_argument("--gap", type=float, default=0.5)
    ap.add_argument("--thresh", type=float, default=0.03); a = ap.parse_args()
    n_, d_ = (a.fps.split("/") + ["1"])[:2]; fps = float(n_) / float(d_)
    t = json.load(open(os.path.join(a.work, "transcript.json"), encoding="utf-8")); ch = t["chunks"]; dur = t["duration"]
    r = levels(os.path.join(a.work, "audio.wav"))
    kept = []
    if a.keep == "all":  # finished exports: keep every chunk with words, only the long gaps go
        a.keep = ",".join(f"c{i:02d}" for i, c in enumerate(ch) if c.get("words"))
    for item in a.keep.split(","):
        item = item.strip()
        if ":" in item:
            cid, rng = item.split(":"); s, e = (float(x) for x in rng.split("-"))
        else:
            cid = item; s, e = ch[int(cid[1:])]["start"], ch[int(cid[1:])]["end"]
        kept.append((int(cid[1:]), s, e))
    segs = []
    for k, (i, s, e) in enumerate(kept):
        if segs and s - segs[-1]["e_raw"] < a.gap and i == segs[-1]["last"] + 1:
            segs[-1]["e_raw"] = e; segs[-1]["last"] = i; segs[-1]["ids"].append(i); continue
        segs.append({"s_raw": s, "e_raw": e, "last": i, "ids": [i]})
    out, warns = [], 0
    for k, sg in enumerate(segs):
        s = max(0, sg["s_raw"] - (0.15 if k == 0 else 0.12))
        e = min(dur, sg["e_raw"] + (0.10 if k == len(segs) - 1 else 0.08))
        sf, ef = round(s * fps), round(e * fps)
        for lab, tt in (("in", sf / fps), ("out", ef / fps)):
            if loud_at(r, tt) >= a.thresh:
                warns += 1; print(f"WARN cut {lab} at {tt:.2f}s is not silent ({loud_at(r, tt):.2f} of peak)", file=sys.stderr)
        out.append({"start": round(sf / fps, 4), "end": round(ef / fps, 4), "sf": sf, "ef": ef, "chunks": sg["ids"]})
    json.dump(out, open(os.path.join(a.work, "segments.json"), "w", encoding="utf-8"), indent=1)
    # cut list for the user
    kept_ids = {i for sg in segs for i in sg["ids"]}
    print("CUT LIST")
    if out[0]["start"] > 0.05: print(f"  0.00-{out[0]['start']:.2f}  head ({out[0]['start']:.1f}s)")
    for k in range(len(out)):
        if k:
            gs, ge = out[k - 1]["end"], out[k]["start"]
            dropped = [c for c in range(out[k - 1]["chunks"][-1] + 1, out[k]["chunks"][0])]
            what = " | ".join(f"c{c:02d} \"{ch[c]['text'] or '(sound)'}\"" for c in dropped) or "pause"
            print(f"  {gs:.2f}-{ge:.2f}  ({ge - gs:.1f}s) {what}")
    if out[-1]["end"] < dur - 0.05: print(f"  {out[-1]['end']:.2f}-{dur:.2f}  tail ({dur - out[-1]['end']:.1f}s)")
    total = sum(x["ef"] - x["sf"] for x in out)
    print(f"{len(out)} pieces, {dur:.1f}s -> {total / fps:.1f}s ({total} frames, {100 * (1 - total / fps / dur):.0f}% cut), silence warnings {warns}")


if __name__ == "__main__":
    main()

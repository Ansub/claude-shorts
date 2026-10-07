#!/usr/bin/env python3
"""Verbatim chunk-per-pause transcription of ONE clip with whisper.cpp (fillers and retakes kept).

Usage: transcribe.py <clip> <workdir> [--model PATH]

Splits the clip's audio at every pause >= 0.30 s, transcribes each chunk alone (so repeated phrases,
i.e. retakes, are never merged), and writes:
  <workdir>/audio.wav        16 kHz mono, used for every silence check later
  <workdir>/transcript.json  {"duration", "chunks": [{start, end, text, words: [{w, start, end}]}]}
  <workdir>/transcript.md    one line per chunk with [pause X.XXs] markers, for reading
"""
import json, math, os, re, struct, subprocess, sys, wave
from concurrent.futures import ThreadPoolExecutor

MODELS = [os.path.expanduser(p) for p in (
    "~/.cache/claude-shorts/ggml-large-v3.bin",
    "~/.cache/hyperframes/whisper/models/ggml-large-v3.bin",
)]
MODEL_URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3.bin"
PROMPT = "Umm, so, uh, let me think, like, hmm... Okay, uh, here's what I'm, like, you know, thinking."
GAP, TH, PAD = 0.30, 0.03, 0.15


def model_path():
    if "--model" in sys.argv:
        return sys.argv[sys.argv.index("--model") + 1]
    for p in MODELS:
        if os.path.exists(p):
            return p
    p = MODELS[0]
    os.makedirs(os.path.dirname(p), exist_ok=True)
    print(f"downloading whisper large-v3 (3 GB, once) -> {p}", file=sys.stderr)
    subprocess.run(["curl", "-L", "--fail", "-o", p, MODEL_URL], check=True)
    return p


def rms_series(path, win_s=0.01):
    w = wave.open(path); sr = w.getframerate(); n = w.getnframes(); raw = w.readframes(n)
    s = struct.unpack(f"<{n}h", raw); win = int(sr * win_s)
    r = [math.sqrt(sum(x * x for x in s[k:k + win]) / win) for k in range(0, n - win, win)]
    p = max(r) or 1
    return [x / p for x in r], raw, sr, n


def split(r, th, mingap):
    segs = []; k = 0; N = len(r)
    while k < N:
        while k < N and r[k] < th: k += 1
        if k >= N: break
        st = k
        while k < N:
            if r[k] < th:
                j = k
                while j < N and r[j] < th: j += 1
                if (j - k) * 0.01 >= mingap: break
                k = j
            else: k += 1
        segs.append((st / 100, k / 100)); k += 1
    return segs


def transcribe(model, wav, offset):
    subprocess.run(["whisper-cli", "-m", model, "-f", wav, "-np", "-l", "en", "--prompt", PROMPT,
                    "-ml", "1", "-sow", "-oj", "-of", wav[:-4]], capture_output=True, text=True)
    try: segs = json.load(open(wav[:-4] + ".json"))["transcription"]
    except Exception: return "", []
    words = []
    for s in segs:
        t = s["text"].strip()
        if not t or "[BLANK_AUDIO]" in t or t.startswith("[") or t.startswith("("): continue
        words.append({"w": t, "start": round(offset + s["offsets"]["from"] / 1000, 2),
                      "end": round(offset + s["offsets"]["to"] / 1000, 2)})
    return re.sub(r"\s+", " ", " ".join(w["w"] for w in words)).strip(), words


def main():
    clip, work = sys.argv[1], sys.argv[2]
    model = model_path()
    cdir = os.path.join(work, ".chunks"); os.makedirs(cdir, exist_ok=True)
    wav = os.path.join(work, "audio.wav")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", clip, "-vn", "-ac", "1", "-ar", "16000", wav], check=True)
    r, raw, sr, total = rms_series(wav); dur = total / sr
    segs = split(r, TH, GAP); jobs = []
    for i, (s, e) in enumerate(segs):
        s2 = max(0, s - PAD); e2 = min(dur, e + PAD); p = os.path.join(cdir, f"{i:03d}.wav")
        o = wave.open(p, "wb"); o.setnchannels(1); o.setsampwidth(2); o.setframerate(sr)
        o.writeframes(raw[int(s2 * sr) * 2:int(e2 * sr) * 2]); o.close(); jobs.append((p, s2))
    with ThreadPoolExecutor(3) as ex:
        outs = list(ex.map(lambda j: transcribe(model, *j), jobs))
    chunks = []
    for (s, e), (text, words) in zip(segs, outs):
        flag = "prompt-echo?" if text and text.lower().strip(" .") in PROMPT.lower() else None
        if not text: flag = "no words (breath/noise?)"
        chunks.append({"start": round(s, 2), "end": round(e, 2), "text": text, "words": words, **({"flag": flag} if flag else {})})
    json.dump({"duration": round(dur, 3), "chunks": chunks}, open(os.path.join(work, "transcript.json"), "w"), indent=1)
    md = [f"# Transcript: {os.path.basename(clip)} ({dur:.2f}s)", "",
          "One line per chunk (split at pauses >= 0.30 s). Fillers and retakes kept.", ""]
    if segs: md.append(f"[pause {segs[0][0]:.2f}s at head]")
    prev = None
    for i, c in enumerate(chunks):
        if prev is not None: md.append(f"[pause {c['start'] - prev:.2f}s]")
        note = f"  <!-- {c['flag']} -->" if c.get("flag") else ""
        md.append(f"c{i:02d} [{c['start']:.2f}-{c['end']:.2f}] {c['text'] or '(sound, no words)'}{note}")
        prev = c["end"]
    if segs: md.append(f"[pause {dur - segs[-1][1]:.2f}s at tail]")
    open(os.path.join(work, "transcript.md"), "w").write("\n".join(md) + "\n")
    print(f"{len(chunks)} chunks, {dur:.1f}s -> {os.path.join(work, 'transcript.md')}", file=sys.stderr)


if __name__ == "__main__":
    main()

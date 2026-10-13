"""Word-by-word captions above the speaker's head: small words in a heavy sans (white), one hero word per block in
the same sans or a script font, filled with a vertical gradient, brand logos inline. Renders a transparent overlay.

Settings (sizes, colours, band, fonts) merge in this order, later wins:
  assets/caption-settings.json  <  ~/.config/claude-shorts/settings.json  <  <workdir>/settings.json
Fonts: "fontText" (small + bold hero) and "fontScript" (script hero). A value is a path, or a file name looked up in
~/.config/claude-shorts/fonts/ then assets/fonts/. Variable fonts use their "Black" instance when they have one.

workdir needs: words_cut.json (words_on_cut.py), blocks.txt (hand-written line plan), cut.mov (for previews).
Set FPS=<num/den> in the environment to the clip's frame rate.
Each word appears on its spoken frame and joins the words already on screen (line layout is fixed up front).
Small words blur-fade in; hero words just appear; logos pop.
Usage: captions.py <workdir> list
       captions.py <workdir> qa                 -> every block fully revealed, tiled into previews/qa.jpg (720 px around each block)
       captions.py <workdir> preview t1,t2,...   -> workdir/previews/p_<t>.png + grid.jpg
       captions.py <workdir> still <bg.jpg> <out.png> <block-index>
       captions.py <workdir> full out.mov N      -> ProRes 4444 overlay with exactly N frames
"""
from platform_tools import find_tool
import io, json, os, subprocess, sys
from platform_tools import svg_to_png
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

ASSETS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
USER = os.path.expanduser("~/.config/claude-shorts")
HERE = os.path.abspath(sys.argv[1])  # workdir
W, H = 1080, 1920
FPS_STR = os.environ.get("FPS", "30000/1001")  # the clip's own rate, set by the caller
_n, _d = (FPS_STR.split("/") + ["1"])[:2]
FPS = float(_n) / float(_d)
S = {}
for _sp in (os.path.join(ASSETS, "caption-settings.json"), os.path.join(USER, "settings.json"), os.path.join(HERE, "settings.json")):
    if os.path.exists(_sp):
        S.update(json.load(open(_sp, encoding="utf-8")))
SIZE = {"s": S["sizeS"], "h": S["sizeH"], "c": S["sizeC"]}

# Per-shot caption bands (written by reframe.py for Shorts cut from a long video): [{start, end, cy, safeTop, safeBot,
# backdropOpacity?}] in source.mov seconds. Mapped onto the cut timeline through segments.json; a block takes the band
# of the shot it starts in. Without bands.json every block uses the settings above.
BAND_KEYS = ("cy", "safeTop", "safeBot", "backdropOpacity")
_bp, _sp = os.path.join(HERE, "bands.json"), os.path.join(HERE, "segments.json")
BANDS = json.load(open(_bp, encoding="utf-8")) if os.path.exists(_bp) else []
SEGS = json.load(open(_sp, encoding="utf-8")) if os.path.exists(_sp) and BANDS else []


def band_at(t):
    """Caption band for cut-timeline second t."""
    st, rec = t, 0.0
    for sg in SEGS:
        d = (sg["ef"] - sg["sf"]) / FPS
        if t < rec + d: st = sg["sf"] / FPS + t - rec; break
        rec += d
    b = {k: S[k] for k in BAND_KEYS if k in S}
    for x in BANDS:
        if x["start"] <= st < x["end"]:
            b.update({k: x[k] for k in BAND_KEYS if k in x}); break
    return b


def font_path(name):
    for p in (os.path.expanduser(name), os.path.join(USER, "fonts", name), os.path.join(ASSETS, "fonts", name)):
        if os.path.isfile(p):
            return p
    raise SystemExit(f"font not found: {name} (put it in {USER}/fonts/ or give a full path)")


inter = font_path(S.get("fontText", "Inter.ttf"))
script = font_path(S.get("fontScript", "GreatVibes-Regular.ttf"))


def rgb(hexs):
    n = int(hexs[1:], 16)
    return (n >> 16, (n >> 8) & 255, n & 255)


def _font(path, size, black=False):
    f = ImageFont.truetype(path, size)
    if black:
        try:
            f.set_variation_by_name("Black")
        except Exception:
            pass  # static font: use it as it is
    return f


F = {"s": _font(inter, SIZE["s"], True), "h": _font(inter, SIZE["h"], True), "c": _font(script, SIZE["c"])}
PAD = 160  # canvas padding, >= 3x any glow blur so nothing clips into a box


def tracking(style):
    return 0 if style == "c" else S["tracking"] / 100 * SIZE[style]


def text_width(txt, style):
    f = F[style]
    return f.getlength(txt) + tracking(style) * (len(txt) - 1)


def line_metrics(style):
    asc, desc = F[style].getmetrics()
    k1, k2 = (0.12, 0.45) if style == "c" else (0.22, 0.3)
    return asc, desc, k1, asc * (1 - k1) + desc * k2


def draw_text(d, x, baseline, txt, style, **kw):
    """Draw with tracking while keeping kerning: char x = getlength(prefix) + i*tracking."""
    f = F[style]; tr = tracking(style)
    for i, ch in enumerate(txt):
        d.text((x + f.getlength(txt[:i]) + i * tr, baseline), ch, font=f, anchor="ls", **kw)


def word_layers(txt, style, scale):
    """Finished RGBA for one word at its final look, on a padded canvas. Returns (img, mask, xoff, baseline_y)."""
    asc, desc, k1, bh = line_metrics(style)
    w = int(text_width(txt, style)) + 2 * PAD
    h = asc + desc + 2 * PAD
    base = PAD + asc

    def mask(stroke=0):
        m = Image.new("L", (w, h), 0)
        draw_text(ImageDraw.Draw(m), PAD, base, txt, style, fill=255, stroke_width=stroke, stroke_fill=255)
        return m

    thick = round(S["scriptThicken"] / 2) if style == "c" else 0
    m = mask(thick)
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))

    def colored(src, color, blur):
        c = Image.new("RGBA", src.size, rgb(color) + (0,))
        c.putalpha(src.filter(ImageFilter.GaussianBlur(blur)) if blur > 0 else src)
        return c

    def add(layer, strength, off=(0, 0)):
        k = strength / 100
        while k > 0:
            a = min(1.0, k)
            l = layer if a >= 1 else layer.copy()
            if a < 1:
                l.putalpha(layer.getchannel("A").point(lambda v: int(v * a)))
            out.alpha_composite(l, off)
            k -= 1

    if style == "s":
        if S["sShadowOpacity"] > 0:
            add(colored(m, S["sShadowColor"], S["sShadowBlur"]), S["sShadowOpacity"], (2, int(S["sShadowY"])))
        if S["sStroke"] > 0:
            add(colored(mask(thick + int(S["sStroke"])), S["sStrokeColor"], 0), 100)
        add(colored(m, S["sColor"], 0), 100)
    else:
        if S["heroShadowOpacity"] > 0:
            add(colored(m, "#000000", S["heroShadowBlur"]), S["heroShadowOpacity"], (3, int(S["heroShadowY"])))
        if S["bloomStrength"] > 0:
            add(colored(m, S["bloomColor"], S["bloomBlur"]), S["bloomStrength"])
        if S["haloStrength"] > 0:
            add(colored(m, S["haloColor"], S["haloBlur"]), S["haloStrength"])
        if S["rimWidth"] > 0:
            add(colored(mask(thick + int(S["rimWidth"])), S["rimColor"], 0), 100)
        # vertical gradient over the LINE band (same as the tuner: line top -> line top + line height)
        top = base - asc * (1 - k1); bot = top + bh
        grad = Image.new("RGBA", (w, h))
        gd = ImageDraw.Draw(grad)
        t0, t1 = rgb(S["hTop"]), rgb(S["hBot"])
        for y in range(h):
            k = min(1, max(0, (y - top) / max(1, bot - top)))
            gd.line([(0, y), (w, y)], fill=tuple(int(a + (b - a) * k) for a, b in zip(t0, t1)) + (255,))
        grad.putalpha(m)
        out.alpha_composite(grad)
    if scale < 1:
        out = out.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
        m = m.resize(out.size, Image.LANCZOS)
    return out, m, PAD * scale, base * scale


_logo = {}


def logo_img(name, h):
    key = (name, h)
    if key not in _logo:
        png = svg_to_png(path=(os.path.join(HERE, f"logos/{name}.svg") if os.path.exists(os.path.join(HERE, f"logos/{name}.svg")) else os.path.join(ASSETS, f"logos/{name}.svg")), height=max(1, int(h)))
        im = Image.open(io.BytesIO(png)).convert("RGBA")
        if S["logoTintOn"] >= 1:
            t = Image.new("RGBA", im.size, rgb(S["logoTint"]) + (0,)); t.putalpha(im.getchannel("A")); im = t
        if S["sShadowOpacity"] > 0:
            c = Image.new("RGBA", (im.width + 80, im.height + 80), (0, 0, 0, 0))
            a = ImageOps.expand(im.getchannel("A"), 40).filter(ImageFilter.GaussianBlur(S["sShadowBlur"]))
            a = a.point(lambda v: int(v * S["sShadowOpacity"] / 100 * 0.8))
            sh = Image.new("RGBA", c.size, rgb(S["sShadowColor"]) + (0,)); sh.putalpha(a)
            c.alpha_composite(sh, (0, int(S["sShadowY"]))); c.alpha_composite(im, (40, 40)); im = c
        else:
            im = ImageOps.expand(im, 40, fill=(0, 0, 0, 0))
        _logo[key] = im
    return _logo[key]


def ease(x):
    x = max(0.0, min(1.0, x)); return 1 - (1 - x) ** 3


def back(x):
    x = max(0.0, min(1.0, x)); c = 1.9
    return 1 + (c + 1) * (x - 1) ** 3 + c * (x - 1) ** 2


def layout_line(L, fit=1.0):
    st = L["style"]
    asc, desc, k1, bh = line_metrics(st)
    f = F[st]
    space = f.getlength(" ") * (S.get("scriptSpace", 0.7) if st == "c" else 1.0) * S["wordSpace"] / 105
    widths = [text_width(w["txt"], st) for w in L["words"]]
    logo_h = logo_w = 0
    if L["logo"]:
        logo_h = (SIZE["h"] * 0.95 if st == "h" else SIZE["c"] * 0.5) * S["logoScale"] / 95
        logo_w = logo_h + 20
    total = sum(widths) + space * (len(widths) - 1) + logo_w
    k = min(1.0, S["safeW"] / total) * fit
    L["k"], L["bh"] = k, bh * k
    x0 = (W - total * k) / 2
    L["logo_img"] = logo_img(L["logo"], logo_h * k) if L["logo"] else None
    L["logo_x"] = x0
    x = x0 + logo_w * k
    for w, wd in zip(L["words"], widths):
        w["img"], w["mask"], w["xoff"], w["base"] = word_layers(w["txt"], st, k)
        w["x"] = x
        x += (wd + space) * k
    L["asc_off"] = asc * (1 - k1) * k  # line top -> baseline
    if st == "c":  # script fonts' ascent sits far above their ink: size script lines by the ink, not the metrics
        _, top, _, bot = f.getbbox(" ".join(w["txt"] for w in L["words"]), anchor="ls")
        pad = 0.04 * SIZE["c"]
        L["asc_off"] = (-top + pad) * k
        L["bh"] = (-top + max(bot, 0) + 2 * pad) * k


def load_blocks():
    words = json.load(open(os.path.join(HERE, "words_cut.json"), encoding="utf-8"))
    blocks, cur = [], []
    for raw in open(os.path.join(HERE, "blocks.txt"), encoding="utf-8"):
        raw = raw.rstrip("\n")
        if raw.startswith("#"):
            continue
        if not raw.strip():
            if cur: blocks.append(cur); cur = []
            continue
        f = [x.strip() for x in raw.split("|")]
        cur.append({"style": f[0], "text": f[1], "n": int(f[2]), "logo": f[3] if len(f) > 3 and f[3] else None})
    if cur: blocks.append(cur)
    i = 0
    for b in blocks:
        for L in b:
            ws = words[i:i + L["n"]]; i += L["n"]
            L["src"] = " ".join(w[2] for w in ws)
            disp = L["text"].split()
            L["words"] = [{"t": ws[min(len(ws) - 1, k * len(ws) // len(disp))][0], "txt": d} for k, d in enumerate(disp)]
            L["t0"], L["t1"] = ws[0][0], ws[-1][1]
    assert i == len(words), f"blocks consume {i} of {len(words)} words"
    for k, b in enumerate(blocks):
        nxt = blocks[k + 1][0]["t0"] if k + 1 < len(blocks) else b[-1]["t1"] + 0.8
        b_end = nxt if nxt - b[-1]["t1"] <= 0.5 else b[-1]["t1"] + 0.5
        for L in b:
            L["block_end"] = b_end
            layout_line(L)
        B = band_at(b[0]["t0"])
        for L in b: L["band"] = B
        total = sum(L["bh"] for L in b) + S["gap"] * (len(b) - 1)
        band = B["safeBot"] - B["safeTop"]
        if total > band:  # too tall for the space above the head: shrink only the hero lines, small words keep their size
            small = sum(L["bh"] for L in b if L["style"] == "s")
            hero = sum(L["bh"] for L in b if L["style"] != "s")
            fit = max(0.4, (band - S["gap"] * (len(b) - 1) - small) / hero) if hero else 1
            for L in b:
                if L["style"] != "s":
                    layout_line(L, fit)
            total = sum(L["bh"] for L in b) + S["gap"] * (len(b) - 1)
            if total > band + 0.5:  # small words never shrink, so the block itself is too long: split it in blocks.txt
                print(f"WARN block {k} ('{b[0]['text']}' ...) is {total}px tall, the band is {band}px: split it", file=sys.stderr)
        y = round(B["cy"] - total / 2)
        y = max(B["safeTop"], min(y, B["safeBot"] - total))
        for L in b:
            L["y"] = y
            y += L["bh"] + S["gap"]
    return blocks


def paste(out, img, x, y, alpha=1.0):
    if alpha < 0.999:
        img = img.copy(); img.putalpha(img.getchannel("A").point(lambda v: int(v * alpha)))
    layer = Image.new("RGBA", out.size, (0, 0, 0, 0))
    layer.paste(img, (int(round(x)), int(round(y))))
    out.alpha_composite(layer)


def draw_word(out, w, L, age, fade):
    img = w["img"]
    x = w["x"] - w["xoff"]
    y = L["y"] + L["asc_off"] - w["base"]
    a = fade
    if L["style"] == "s":
        p = ease(age / 0.16)
        if p < 1:
            img = img.filter(ImageFilter.GaussianBlur(6 * (1 - p)))
            y += 12 * (1 - p)
        a *= p
    paste(out, img, x, y, a)


def backdrop(b):
    """Full-width dark scrim behind a block, feathered top and bottom: keeps captions readable over screen recordings.
    backdropOpacity 0 = off (default for face shots); reframe.py turns it on for split layouts."""
    if "scrim" not in b[0]:
        op = b[0]["band"].get("backdropOpacity", S.get("backdropOpacity", 0)) if "band" in b[0] else S.get("backdropOpacity", 0)
        if op <= 0: b[0]["scrim"] = None; return None
        pad = S.get("backdropPad", 50); y0 = b[0]["y"] - pad; y1 = b[-1]["y"] + b[-1]["bh"] + pad
        m = Image.new("L", (W, int(y1 - y0) + 2 * pad), 0)
        ImageDraw.Draw(m).rectangle([0, pad, W, m.height - pad], fill=int(255 * op / 100))
        m = m.filter(ImageFilter.GaussianBlur(pad / 2))
        im = Image.new("RGBA", m.size, rgb(S.get("backdropColor", "#000000")) + (0,)); im.putalpha(m)
        b[0]["scrim"] = (im, y0 - pad)
    return b[0]["scrim"]


def draw_block(out, b, t, fade=1.0):
    sc = backdrop(b)
    if sc: paste(out, sc[0], 0, sc[1], min(1.0, (t - b[0]["t0"] + 0.04) / 0.12) * fade)
    for L in b:
        if L["logo_img"] is not None and t >= L["t0"] - 0.04:
            age = t - (L["t0"] - 0.04)
            s = max(0.05, 0.5 + 0.5 * back(age / 0.28))
            lg = L["logo_img"]
            lg2 = lg.resize((max(1, int(lg.width * s)), max(1, int(lg.height * s))), Image.LANCZOS)
            cx = L["logo_x"] + lg.width / 2 - 40
            cy = L["y"] + L["bh"] / 2
            paste(out, lg2, cx - lg2.width / 2, cy - lg2.height / 2, min(1, age / 0.1) * fade)
    # hero lines first, small words on top
    for L in sorted(b, key=lambda L: L["style"] == "s"):
        for w in L["words"]:
            if t >= w["t"] - 0.04:
                draw_word(out, w, L, t - (w["t"] - 0.04), fade)


def frame(blocks, t):
    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    for b in blocks:
        if b[0]["t0"] - 0.04 <= t < b[0]["block_end"]:
            fade = max(0.0, min(1.0, (b[0]["block_end"] - t) / 0.08))
            draw_block(out, b, t, fade)
    return out


if __name__ == "__main__":
    blocks = load_blocks()
    sys.argv = sys.argv[1:]
    cmd = sys.argv[1]
    if cmd == "list":
        for b in blocks:
            print(" / ".join(f"[{L['style']}] {L['text']} <- {L['src']} @{L['t0']:.2f} y={L['y']}" for L in b))
    elif cmd == "still":
        bg = Image.open(sys.argv[2]).convert("RGBA").resize((W, H))
        b = blocks[int(sys.argv[4])]
        draw_block(bg, b, 999.0)
        bg.convert("RGB").save(sys.argv[3])
    elif cmd == "preview":
        os.makedirs(os.path.join(HERE, "previews"), exist_ok=True)
        tiles = []
        for ts in sys.argv[2].split(","):
            t = float(ts)
            fp = os.path.join(HERE, f"previews/bg_{ts}.png")
            subprocess.run([find_tool("ffmpeg"), "-v", "error", "-y", "-ss", ts, "-i", os.path.join(HERE, "cut.mov"), "-frames:v", "1", fp], check=True)
            bg = Image.open(fp).convert("RGBA"); bg.alpha_composite(frame(blocks, t))
            bg.convert("RGB").save(os.path.join(HERE, f"previews/p_{ts}.png"))
            tiles.append(bg.convert("RGB").resize((360, 640)))
        g = Image.new("RGB", (360 * len(tiles), 640))
        for k, im in enumerate(tiles): g.paste(im, (360 * k, 0))
        g.save(os.path.join(HERE, "previews/grid.jpg"), quality=90)
    elif cmd == "qa":  # every block at its fully revealed moment, over the cut, tiled into previews/qa.jpg
        os.makedirs(os.path.join(HERE, "previews"), exist_ok=True)
        dur = float(subprocess.run([find_tool("ffprobe"), "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                    os.path.join(HERE, "cut.mov")], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout)
        tiles = []
        for k, b in enumerate(blocks):
            t = min(b[-1]["t1"] + 0.2, b[0]["block_end"] - 0.09, dur - 0.05)  # past the last word's blur-in, before the fade-out
            fp = os.path.join(HERE, f"previews/qa_{k:02d}.png")
            subprocess.run([find_tool("ffmpeg"), "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", os.path.join(HERE, "cut.mov"), "-frames:v", "1", fp], check=True)
            bg = Image.open(fp).convert("RGBA"); bg.alpha_composite(frame(blocks, t)); bg = bg.convert("RGB")
            bg.save(fp)
            y0 = max(0, min(H - 720, b[0]["y"] - 100))  # 720 px window around the block, wherever its band is
            tile = bg.crop((0, y0, 1080, y0 + 720)).resize((360, 240))
            ImageDraw.Draw(tile).text((6, 4), f"{k} @{t:.1f}s", fill="yellow")
            tiles.append(tile)
        cols = 6; rows = (len(tiles) + cols - 1) // cols
        g = Image.new("RGB", (360 * cols, 240 * rows))
        for k, im in enumerate(tiles): g.paste(im, (360 * (k % cols), 240 * (k // cols)))
        g.save(os.path.join(HERE, "previews/qa.jpg"), quality=90)
        print(os.path.join(HERE, "previews/qa.jpg"))
    elif cmd == "full":
        out, n = sys.argv[2], int(sys.argv[3])
        ff = subprocess.Popen([find_tool("ffmpeg"), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{H}", "-r", FPS_STR, "-i", "-",
                               "-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le", out], stdin=subprocess.PIPE)
        for i in range(n):
            ff.stdin.write(frame(blocks, i / FPS).tobytes())
        ff.stdin.close(); ff.wait()

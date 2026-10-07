"""Thumbnail in the same look as captions.py (same fonts, settings and logos).
Usage: reel_thumb.py <frame.png> <out.png> "<line>|<line>|..." [--scale 1.25] [--cy 440] [--settings file.json]
                     [--tag yet] [--tag-size 64]   (plain white Inter Black word under the last line's right end)
                     [--tag-pill --tag-color #e0263c]   (white pill with coloured text instead)
Line syntax: s:text  (small white)   h:text  (bold hero)   c:text  (script hero)   h@openai:text  (hero + logo)
             c#ffffff:text  (hero in a solid colour instead of the blue gradient, e.g. white script)
Logos come from assets/logos/<name>.svg."""
import importlib.util, os, sys, tempfile
from PIL import Image

args = sys.argv[1:]
def opt(name, default):
    if name in args:
        i = args.index(name); v = args[i + 1]; del args[i:i + 2]; return v
    return default
scale, cy, settings = float(opt("--scale", "1.25")), int(opt("--cy", "440")), opt("--settings", None)
tag, tag_color, tag_size = opt("--tag", None), opt("--tag-color", "#e0263c"), int(opt("--tag-size", "64"))
tag_pill = "--tag-pill" in args  # default: plain white Inter Black text (what he chose); --tag-pill for the white pill
if tag_pill: args.remove("--tag-pill")
frame, out, spec = args[0], args[1], args[2]

work = tempfile.mkdtemp()
if settings:
    import shutil; shutil.copy(settings, os.path.join(work, "settings.json"))
open(os.path.join(work, "blocks.txt"), "w").write("")
open(os.path.join(work, "words_cut.json"), "w").write("[]")
sys.argv = ["captions.py", work]
spec_ = importlib.util.spec_from_file_location("rc", os.path.join(os.path.dirname(os.path.abspath(__file__)), "captions.py"))
rc = importlib.util.module_from_spec(spec_); spec_.loader.exec_module(rc)

# bigger type for a cover, same proportions
for k in ("sizeS", "sizeH", "sizeC"):
    rc.S[k] = int(rc.S[k] * scale)
rc.SIZE.update({"s": rc.S["sizeS"], "h": rc.S["sizeH"], "c": rc.S["sizeC"]})
rc.F.update({"s": rc._font(rc.inter, rc.SIZE["s"], True), "h": rc._font(rc.inter, rc.SIZE["h"], True), "c": rc._font(rc.script, rc.SIZE["c"])})
rc.S["safeW"] = 900

block = []
for part in spec.split("|"):
    head, text = part.split(":", 1)
    head, _, color = head.partition("#")
    style, _, logo = head.partition("@")
    L = {"style": style, "text": text, "logo": logo or None, "t0": 0, "words": [{"t": 0, "txt": w} for w in text.split()]}
    saved = (rc.S["hTop"], rc.S["hBot"])
    if color:
        rc.S["hTop"] = rc.S["hBot"] = "#" + color
    rc.layout_line(L)
    rc.S["hTop"], rc.S["hBot"] = saved
    block.append(L)
total = sum(L["bh"] for L in block) + rc.S["gap"] * (len(block) - 1)
y = cy - total / 2
for L in block:
    L["y"] = y; y += L["bh"] + rc.S["gap"]
bg = Image.open(frame).convert("RGBA").resize((rc.W, rc.H))
rc.draw_block(bg, block, 999.0)
tag_bottom = None
if tag:
    from PIL import ImageDraw, ImageFilter
    last = block[-1]
    right = max(w["x"] + rc.text_width(w["txt"], last["style"]) * last["k"] for w in last["words"])
    f = rc._font(rc.inter, tag_size, True)
    tw = f.getlength(tag); th = tag_size
    pw, ph = int(tw + tag_size * 0.9), int(th * 1.35)
    x1 = int(right) - 6; x0 = x1 - pw; y0 = int(last["y"] + last["bh"] + 14); y1 = y0 + ph
    if not tag_pill:
        ImageDraw.Draw(bg).text((x1, y0 + ph / 2), tag, font=f, fill=(255, 255, 255, 255), anchor="rm")
        tag_bottom = y1
    else:
      sh = Image.new("RGBA", bg.size, (0, 0, 0, 0))
      ImageDraw.Draw(sh).rounded_rectangle((x0 + 2, y0 + 6, x1 + 2, y1 + 6), radius=ph // 2, fill=(60, 20, 0, 110))
      bg.alpha_composite(sh.filter(ImageFilter.GaussianBlur(8)))
      d = ImageDraw.Draw(bg)
      d.rounded_rectangle((x0, y0, x1, y1), radius=ph // 2, fill=(255, 255, 255, 255))
      d.text(((x0 + x1) / 2, (y0 + y1) / 2), tag, font=f, fill=rc.rgb(tag_color) + (255,), anchor="mm")
      tag_bottom = y1
bg.convert("RGB").save(out)
print(f"block top {block[0]['y']:.0f}  bottom {max(block[-1]['y'] + block[-1]['bh'], tag_bottom or 0):.0f}  (keep inside 260..690: IG grid crop starts at 240, hair at ~700)")
print(out)

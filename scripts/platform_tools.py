"""Shared native-platform paths and executable/SVG discovery (no shell required)."""
import os
from pathlib import Path
import shutil
import sys
import urllib.request

CACHE = Path(os.environ.get("CLAUDE_SHORTS_CACHE", Path.home() / ".cache" / "claude-shorts"))
MODEL_URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3.bin"


def venv_python():
    return CACHE / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def find_tool(name):
    names = [name + ".exe", name] if os.name == "nt" else [name]
    for candidate in names:
        found = shutil.which(candidate)
        if found:
            return found
        local = CACHE / "bin" / candidate
        if local.is_file() and os.access(local, os.X_OK):
            return str(local)
    raise FileNotFoundError(f"{name} is missing. Run setup.ps1 (Windows) or bash setup.sh (macOS/Linux).")


def download_model(target=None):
    target = Path(target) if target else CACHE / "ggml-large-v3.bin"
    if not target.is_file() or target.stat().st_size == 0:
        target.parent.mkdir(parents=True, exist_ok=True)
        print("Downloading Whisper large-v3 (about 3 GB, once)...", flush=True)
        part = target.with_suffix(target.suffix + ".part")
        # 3 GB over home Wi-Fi often drops; resume the .part file instead of starting over.
        for attempt in range(1, 21):
            have = part.stat().st_size if part.exists() else 0
            req = urllib.request.Request(MODEL_URL, headers={"Range": f"bytes={have}-"} if have else {})
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    total = have + int(r.headers.get("Content-Length", 0))
                    if have and r.status != 206:
                        have, total = 0, int(r.headers.get("Content-Length", 0))
                    with open(part, "ab" if have else "wb") as f:
                        shutil.copyfileobj(r, f, 1 << 20)
                if not total or part.stat().st_size >= total:
                    break
            except (OSError, ValueError) as e:
                if getattr(e, "code", None) == 416:  # .part already complete
                    break
                print(f"Download interrupted ({e}); resuming, try {attempt}/20...", flush=True)
        else:
            raise RuntimeError("Model download kept failing; check the internet connection and rerun setup.")
        part.replace(target)
    return str(target)


def svg_to_png(path, height):
    # Preserve the existing Cairo rendering on macOS/Linux. Windows wheels bundle
    # resvg's native engine, so users need neither Cairo DLLs nor a Rust compiler.
    if sys.platform == "win32":
        import resvg_py
        return resvg_py.svg_to_bytes(svg_path=str(path), height=height)
    import cairosvg
    return cairosvg.svg2png(url=str(path), output_height=height)

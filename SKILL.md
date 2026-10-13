---
name: claude-shorts
description: >-
  Turn one raw vertical talking-head clip (straight off the phone) into a finished YouTube Short / Reel / TikTok
  with no editing app: cuts dead air, retakes and fillers, writes spell-checked and grammar-fixed word-by-word
  captions with brand logos, adds image overlays, mixes in ducked background music (from a file or a YouTube
  link), normalises loudness, picks a thumbnail frame and drafts the title. Runs locally on ffmpeg, whisper.cpp
  and Python. Use whenever someone hands over a vertical clip or a folder of clips and says "edit this short",
  "make this a reel", "caption this", "cut the retakes", "add music", or types /claude-shorts.
---

# claude-shorts

One raw vertical clip in, one upload-ready 1080x1920 Short out. Everything runs on the user's Mac, Windows PC or Linux machine: ffmpeg,
whisper.cpp and Python (Pillow). No DaVinci, no CapCut, no API keys.

Run it as a short conversation. Each step either shows progress (a transcript, a cut list, a preview) or asks a
real choice. **Never ask things the clip already answers** (resolution, frame rate, length, orientation) and
never ask more than one question at a time. Keep each message to a few lines.

## OS and paths (do this first)

Detect the OS from the session before running commands. Use **native PowerShell on Windows**, and bash on
macOS/Linux; never require WSL or zsh. Claude runs setup and installs prerequisites for the user. If an OS
password/UAC prompt appears, explain it briefly; do not ask them to install tools by hand.

- `$SK` = this skill's absolute folder; `$W` = a work folder in the session scratchpad or the OS temp directory
  (`[IO.Path]::GetTempPath()` on Windows, `${TMPDIR:-/tmp}` on macOS/Linux), with a subfolder per clip.
- `$PY` = `$HOME/.cache/claude-shorts/venv/bin/python` on macOS/Linux, or
  `Join-Path $HOME '.cache\claude-shorts\venv\Scripts\python.exe'` on Windows. Use this Python for **every** script.
- If the venv/tools are missing, run `bash "$SK/setup.sh"` on macOS/Linux, or
  `powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$SK\setup.ps1"` on Windows. The one-time setup
  downloads a 3 GB speech model. Then run `scripts/check_setup.py` with `$PY` (Windows: `& $PY ...`).
- Windows setup changes the user PATH. In the current PowerShell session, refresh it after setup:
  `$env:PYTHONUTF8 = '1'; $env:Path = [Environment]::GetEnvironmentVariable('Path','User') + ';' + [Environment]::GetEnvironmentVariable('Path','Machine')`.
  On macOS/Linux add `export PATH="$HOME/.cache/claude-shorts/bin:/opt/homebrew/bin:/usr/local/bin:/home/linuxbrew/.linuxbrew/bin:$PATH"`.
- Output `$OUT` = `<clip's folder>/<clip name> - short/` unless `~/.config/claude-shorts/profile.md` says otherwise.
  Read that file first if it exists. `~` means the user's home on all platforms; expand it before passing to tools.

The examples below use bash notation. **Translate them on Windows**:
`"$PY" "$SK/scripts/transcribe.py" <clip> "$W"` becomes `& $PY "$SK/scripts/transcribe.py" <clip> $W`;
`FPS=<fps> "$PY" ...` becomes `$env:FPS='<fps>'; & $PY ...`. Set variables with `$W = '...'`, use
`New-Item -ItemType Directory -Force` for folders, and quote every path (spaces and non-ASCII names are valid).
Use UTF-8 for all text/JSON files; in Windows PowerShell 5.1 use
`[IO.File]::WriteAllText($path, $text, (New-Object Text.UTF8Encoding($false)))` to avoid UTF-16/BOM output.
Fonts are rendered with Pillow, so no font path enters an ffmpeg filter. If adding a drawtext filter, escape
its drive-letter colon and filter metacharacters separately from shell quoting.

## 1. Find the clip

- If they gave a file, use it. If they gave a folder, list the video files in it (newest first) and show the
  newest one: name, length, and one frame from 1 s in (`ffmpeg -ss 1 -i clip -frames:v 1 frame.jpg`, then
  look at it). Ask **"Is this the one?"** If they gave nothing, ask **"Where are your clips?"**
- Probe it: `ffprobe -v error -show_entries stream=codec_type,width,height,r_frame_rate -show_entries format=duration -of compact <clip>`.
  Output is always 1080x1920 at the **clip's own frame rate** (`r_frame_rate`, e.g. 30000/1001). Pass it as
  `FPS` / `--fps` everywhere below. If the clip is landscape, or a long video they want cut into many Shorts,
  say so and stop: the free `long-to-shorts` skill does that (https://github.com/Ansub/long-to-shorts).

## 2. Transcript, cleaned

```bash
"$PY" "$SK/scripts/transcribe.py" <clip> "$W"
```
Splits at every pause and transcribes each piece alone, so retakes stay separate. Read `$W/transcript.md` in
full. Then write the **clean transcript**: the final take of each sentence only, with
- spelling fixed, especially names. Check `$SK/assets/glossary.txt` and `~/.config/claude-shorts/glossary.txt`
  (Whisper hears "chatGBD", "Grogbot", "cloud code").
- grammar, capitals and punctuation fixed ("four things which makes it" -> "four things that make it").
- **No rewriting.** Keep their words and voice; fix only what is wrong. A heavier fix goes on a short list.

Show the clean transcript with the fixes in **bold**, then up to 3 numbered guesses where the audio was
unclear (what Whisper heard, what you chose). Ask **"Anything I got wrong?"** If they say "your call", keep
your fixes.

## 3. The cut

Decide which chunks to keep: the last complete take of every sentence; drop false starts, repeated lines,
stray "okay"s, noise chunks (`no words`, `prompt-echo?` flags are usually breath or noise), and anything
after the last real line. Then:
```bash
"$PY" "$SK/scripts/plan_cut.py" "$W" "c05,c06,c08,..." --fps <fps>
```
It joins chunks less than 0.5 s apart (pauses inside a thought stay), cuts longer gaps, pads every cut, and
checks each cut point is silent. `c12:33.70-35.36` trims a chunk to a source-time range. It must report
**0 silence warnings**; if not, move that edge. Show the user the cut list it prints (what goes, old -> new
length) and ask **"Cut it?"** On yes:
```bash
"$PY" "$SK/scripts/render_cut.py" <clip> "$W"        # -> "$W/cut.mov", checks the frame count
"$PY" "$SK/scripts/words_on_cut.py" "$W" --fps <fps> # -> "$W/words_cut.json"
```

## 4. Captions

**Font question, once per run, only the first time** (skip if `~/.config/claude-shorts/settings.json` already
sets fonts): "Captions use Inter for normal words and Great Vibes (a script font) for the punchline word.
Want a different font for either?" If they name one: Google Fonts names can be fetched from
`https://raw.githubusercontent.com/google/fonts/main/ofl/<lowercasename>/<File>.ttf` (check the folder's file
list on GitHub first); a local `.ttf`/`.otf` path is copied. Save fonts to `~/.config/claude-shorts/fonts/` and
the choice to `~/.config/claude-shorts/settings.json` as `{"fontText": "...", "fontScript": "..."}` so it sticks.
A script font with tight word gaps may need `"scriptSpace"` raised (1.6 suits Great Vibes).

Write `$W/blocks.txt` by hand from `words_cut.json` and the clean transcript. Format (see `$SK/examples/blocks.txt`):
```
style | display text (the CLEAN wording) | number of spoken words it covers | optional logo
```
- `s` small white words, `h` bold hero (names: products, models, people), `c` script hero (the emotional or
  payoff word: Sucks, Slow, Life). **One hero per block**, blocks of 1-3 lines in spoken order, a blank line
  between blocks, one block per sentence or clause.
- Display text is where spelling and grammar fixes land; the word count keeps it in sync with the audio.
  Count spoken words exactly as they appear in `words_cut.json`, including ones the clean text drops.
- Logos: `assets/logos/<name>.svg` (openai, claude, grok bundled). For another brand, download its SVG from
  `https://svgl.app` into `$W/logos/<name>.svg`. Use a logo only when the line names that product.

```bash
FPS=<fps> "$PY" "$SK/scripts/captions.py" "$W" list   # must consume every word; read the mapping for misalignments
FPS=<fps> "$PY" "$SK/scripts/captions.py" "$W" qa     # every block fully revealed -> "$W/previews/qa.jpg"
```
**Look at `qa.jpg` yourself before showing anyone**: text over the head, lines colliding, words cut off,
anything hard to read. Fix `blocks.txt` and re-run. Then show it and ask **"Captions look right?"** On yes:
```bash
FPS=<fps> "$PY" "$SK/scripts/captions.py" "$W" full "$W/captions.mov" <frames of cut.mov>
```

## 5. Overlays (optional, offer in one line)

"Want any images on screen (a screenshot, a product shot)? Drop them in a folder and tell me when each should
show." Write `$W/overlays.json`:
`[{"file": "/path/shot.png", "start": 12.4, "end": 15.0, "x": 90, "y": 640, "w": 900}]` (cut-timeline seconds,
time them to the word in `words_cut.json`). Keep images between y 260 and 1440 and clear of the captions
band (y 260-610) unless it is a full-screen cutaway. Skip if they say no.

## 6. Music

Ask **"Music: none, a file you have, or a YouTube link?"**
- Link: `"$PY" "$SK/scripts/get_music.py" "<url>" "$W/music"` (updates yt-dlp first; old versions fail on YouTube).
  Strip playlist parameters from the URL. Mention once that copyrighted songs can get the Short claimed or
  muted, so royalty-free music is safer for posting.
- Then: `"$PY" "$SK/scripts/music_bed.py" "<music file>" "$W"` -> `"$W/music.wav"`, 13.5 dB under the voice,
  ducked while they talk, faded in and out. `--start 30` skips a long intro.

## 7. Export

```bash
"$PY" "$SK/scripts/compose.py" "$W" "$OUT/<name>.mp4"           # add --no-music if they chose none
```
Overlays captions and images, gives the voice plain gain only (no EQ or compression: it made voices sound
worse), mixes the music, normalises to -14 LUFS. Check the output: `ffprobe` frame count = cut frames,
1080x1920; grab two frames and look that captions are burned in. Report length, LUFS, and where the file is.
Reveal the export: macOS `open -R "$OUT/<name>.mp4"`; Windows
`explorer.exe "/select,$OUT\<name>.mp4"`; Linux `xdg-open "$OUT"` (opens its folder; skip on headless machines).

## 8. Thumbnail and title

- Thumbnail: `"$PY" "$SK/scripts/frame_sheet.py" "$W/cut.mov" "$W/frames" 0.9,2.2,4.2,...` (face-to-camera moments),
  pick frames with eyes open, sharp, closed-mouth smile, not mid-word. Then
  `"$PY" "$SK/scripts/thumbnail.py" "$W/frames/f_<t>.png" "$OUT/thumbnail.png" "s:Honestly,|h@openai:OpenAI Dots|c:Sucks" --scale 0.8 --cy 472`
  (`s:` small, `h:` bold hero, `c:` script hero, `@logo`). Keep the block between y 260 and 690 (Instagram crops
  the cover to 3:4). Show 2-3 options, ask **"Which one?"**
- Title: write 5 options under 60 characters from what they actually say (no invented claims), recommend one,
  ask **"Lock this title?"** Then a 2-4 line description with 3-5 hashtags. On lock, rename the export to the
  title (strip `<>:"/\|?*`, control characters, `…` and emoji; trim trailing dots/spaces and avoid Windows reserved names such as CON, NUL and COM1) and save `title.txt` and `description.txt` next to it.

## Rules that came from real runs

- Never cut inside a word; every cut point must be silent (plan_cut checks).
- Pauses inside a sentence stay; gaps of 0.5 s or more between sentences go.
- Captions sit in the empty space above the head (y 260-610), max 770 px wide, clear of the right-side button
  rail. Hero lines shrink to fit; small words never shrink (they become unreadable).
- New caption render = new look at the QA sheet. Don't show the user a render you haven't looked at.
- The user's own folder: never overwrite their raw clip or earlier exports; new files only.

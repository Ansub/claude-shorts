# claude-shorts

A free Claude Code skill that edits your Shorts. Give it a raw vertical clip from your phone and it gives
back a finished Short:

- **Cuts** dead air, false starts, retakes and filler, at silent points only
- **Captions** word by word above your head, with spelling and grammar fixed and brand logos
- **Overlays** your screenshots or images, timed to the word
- **Music** from a file or a YouTube link, ducked under your voice
- **Loudness** normalised to -14 LUFS for YouTube, Instagram and TikTok
- **Thumbnail and title** drafted from what you actually say

No editing app. It runs on macOS, Windows and Linux with ffmpeg, whisper.cpp and Python. No API keys, nothing uploaded.

## Install with one prompt

Open Claude Code and paste this:

```
Install the claude-shorts skill for me:
1. Clone https://github.com/Ansub/claude-shorts into ~/.claude/skills/claude-shorts
   (if it's already there, git pull instead). Install Git for my OS first if missing.
2. Read its README.md and SKILL.md so you know what it does.
3. Detect my OS: run setup.ps1 in native PowerShell on Windows (with -ExecutionPolicy Bypass),
   or `bash ~/.claude/skills/claude-shorts/setup.sh` on macOS/Linux. Install prerequisites for me;
   no WSL or manual Homebrew setup. The setup downloads a 3 GB speech model, so let it finish.
4. Refresh PATH and run scripts/check_setup.py with the private venv Python (Scripts/python.exe on
   Windows, bin/python elsewhere). Follow the OS commands in SKILL.md.
5. Tell me in a few lines what got installed, whether I need to restart Claude Code to see /claude-shorts,
   and the exact prompt to edit my first Short.
```

## Install by hand

1. Clone it into your Claude Code skills folder:
   ```bash
   git clone https://github.com/Ansub/claude-shorts ~/.claude/skills/claude-shorts
   ```
2. Run the one-time setup (installs the tools and downloads a 3 GB speech model):
   ```bash
   bash ~/.claude/skills/claude-shorts/setup.sh
   ```
   On Windows, use PowerShell instead:
   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File "$HOME/.claude/skills/claude-shorts/setup.ps1"
   ```
3. Open Claude Code and type:
   ```
   /claude-shorts edit the newest clip in ~/Downloads
   ```

Claude walks you through it: confirm the clip, check the transcript, approve the cuts, check the captions,
pick music, pick a thumbnail. About 2 minutes of processing for a 1-minute clip on an Apple Silicon Mac;
Windows and Linux PCs without a GPU take longer (transcription runs on the CPU).

## Fonts

Captions use **Inter** and **Great Vibes** (both free). Want your own? Tell Claude the font name when it asks,
or drop a `.ttf` in `~/.config/claude-shorts/fonts/`. Your choice is saved in
`~/.config/claude-shorts/settings.json`, which can also change sizes and colours
(keys in `assets/caption-settings.json`).

## Good to know

- Made for vertical talking-head clips (1080x1920 output, your clip's own frame rate). Want ~10 Shorts cut from
  one long video instead? Use [long-to-shorts](https://github.com/Ansub/long-to-shorts).
- Works on macOS, Windows 10/11 x64 (ARM64 needs Windows 11), and Linux (Debian/Ubuntu, Fedora or Arch). Setup may ask for your OS password.
- Copyrighted music from YouTube can get your Short claimed or muted. Use royalty-free tracks for posting.
- Add names Whisper keeps misspelling to `~/.config/claude-shorts/glossary.txt` (`Correct = wrong, wrong`).

Made by [Ansub](https://www.youtube.com/@ansubkhan). MIT licensed.

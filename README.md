# claude-shorts

A free Claude Code skill that edits your Shorts. Give it a raw vertical clip from your phone and it gives
back a finished Short:

- **Cuts** dead air, false starts, retakes and filler, at silent points only
- **Captions** word by word above your head, with spelling and grammar fixed and brand logos
- **Overlays** your screenshots or images, timed to the word
- **Music** from a file or a YouTube link, ducked under your voice
- **Loudness** normalised to -14 LUFS for YouTube, Instagram and TikTok
- **Thumbnail and title** drafted from what you actually say

No editing app. It runs on your Mac with ffmpeg, whisper.cpp and Python. No API keys, nothing uploaded.

## Install with one prompt

Open Claude Code and paste this:

```
Install the claude-shorts skill for me:
1. Clone https://github.com/Ansub/claude-shorts into ~/.claude/skills/claude-shorts
   (if it's already there, git pull instead).
2. Read its README.md and SKILL.md so you know what it does.
3. Run `zsh ~/.claude/skills/claude-shorts/setup.sh`. If Homebrew is missing, stop and tell me how to install it.
   The setup downloads a 3 GB speech model, so let it run until it finishes.
4. Check that ffmpeg, whisper-cli and yt-dlp work, and that ~/.cache/claude-shorts/venv/bin/python can import PIL and cairosvg.
5. Tell me in a few lines what got installed, whether I need to restart Claude Code to see /claude-shorts,
   and the exact prompt to edit my first Short.
```

## Install by hand

1. Clone it into your Claude Code skills folder:
   ```bash
   git clone https://github.com/Ansub/claude-shorts ~/.claude/skills/claude-shorts
   ```
2. Run the one-time setup (installs ffmpeg, whisper.cpp, yt-dlp with Homebrew and downloads a 3 GB speech model):
   ```bash
   zsh ~/.claude/skills/claude-shorts/setup.sh
   ```
3. Open Claude Code and type:
   ```
   /claude-shorts edit the newest clip in ~/Downloads
   ```

Claude walks you through it: confirm the clip, check the transcript, approve the cuts, check the captions,
pick music, pick a thumbnail. About 2 minutes of processing for a 1-minute clip.

## Fonts

Captions use **Inter** and **Great Vibes** (both free). Want your own? Tell Claude the font name when it asks,
or drop a `.ttf` in `~/.config/claude-shorts/fonts/`. Your choice is saved in
`~/.config/claude-shorts/settings.json`, which can also change sizes and colours
(keys in `assets/caption-settings.json`).

## Good to know

- Made for vertical talking-head clips (1080x1920 output, your clip's own frame rate).
- Needs macOS with Homebrew.
- Copyrighted music from YouTube can get your Short claimed or muted. Use royalty-free tracks for posting.
- Add names Whisper keeps misspelling to `~/.config/claude-shorts/glossary.txt` (`Correct = wrong, wrong`).

Made by [Ansub](https://www.youtube.com/@ansubkhan). MIT licensed.

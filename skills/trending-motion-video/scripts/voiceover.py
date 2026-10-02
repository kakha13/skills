#!/usr/bin/env python3
"""Generate one voiceover clip per scene with edge-tts (free Microsoft neural voices).

    python3 voiceover.py storyboard.json [--force] [--only 2,5]

Reads storyboard["voice"] (default en-US-AndrewNeural) and ["rate"] (default +6%), writes
<project>/vo/NN.mp3 from each scene's "vo" text. Existing clips are kept unless --force/--only.
Install once: pip install edge-tts
"""
import json, os, shutil, subprocess, sys
from concurrent.futures import ThreadPoolExecutor


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    if not shutil.which("edge-tts"):
        sys.exit("edge-tts not found: pip install edge-tts")
    sb_path = sys.argv[1]
    root = os.path.dirname(os.path.abspath(sb_path))
    sb = json.load(open(sb_path))
    voice, rate = sb.get("voice", "en-US-AndrewNeural"), sb.get("rate", "+6%")
    os.makedirs(os.path.join(root, "vo"), exist_ok=True)
    args = sys.argv[2:]
    only = {int(x) - 1 for x in args[args.index("--only") + 1].split(",")} if "--only" in args else set()

    def one(k):
        text = sb["scenes"][k].get("vo", "").strip()
        out = os.path.join(root, "vo", f"{k + 1:02d}.mp3")
        if not text:
            return f"{k + 1:02d}: no vo text, skipped"
        if os.path.exists(out) and "--force" not in args and k not in only:
            return f"{k + 1:02d}: exists"
        if only and k not in only:
            return f"{k + 1:02d}: exists"
        subprocess.run(["edge-tts", "--voice", voice, f"--rate={rate}", "--text", text, "--write-media", out],
                       check=True, capture_output=True)
        dur = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", out],
                             capture_output=True, text=True).stdout.strip()
        return f"{k + 1:02d}: {float(dur):.2f}s"

    with ThreadPoolExecutor(8) as ex:
        for line in ex.map(one, range(len(sb["scenes"]))):
            print(line)


if __name__ == "__main__":
    main()

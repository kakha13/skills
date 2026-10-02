#!/usr/bin/env python3
"""QA the project: image contact sheet, one frame per scene from the final video, audio loudness.

    python3 check.py storyboard.json

Writes <project>/qa_images.jpg and <project>/qa_frames.jpg, prints duration and loudness.
Look at both JPGs before telling the user the video is done.
"""
import os, re, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from render import load_project, FPS  # noqa: E402


def sh(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    root, sb, scenes, starts, total, _ = load_project(sys.argv[1])
    n = len(scenes)
    cols = 4 if n > 4 else n
    rows = -(-n // cols)

    imgs = [os.path.join(root, "images", f"{k + 1:02d}.png") for k in range(n)]
    ins = sum((["-i", p] for p in imgs), [])
    pad = "".join(f"[{k}]scale=300:450[s{k}];" for k in range(n))
    tiles = "".join(f"[s{k}]" for k in range(n))
    sh(["ffmpeg", "-v", "error", "-y", *ins, "-filter_complex",
        f"{pad}{tiles}xstack=inputs={n}:layout=" + "|".join(f"{(k % cols) * 300}_{(k // cols) * 450}" for k in range(n))
        + ":fill=black", os.path.join(root, "qa_images.jpg")]) if n > 1 else None

    video = os.path.join(root, sb.get("output", "video.mp4"))
    if not os.path.exists(video):
        print("no video yet:", video)
        return
    # sample each scene once its caption has fully landed (just before its fade-out)
    frames = [int((st + max(0.5, sc["dur"] - 0.6)) * FPS) for st, sc in zip(starts, scenes)]
    sel = "+".join(f"eq(n\\,{f})" for f in frames)
    sh(["ffmpeg", "-v", "error", "-y", "-i", video, "-vf", f"select='{sel}',scale=360:-1,tile={cols}x{rows}",
        "-frames:v", "1", "-vsync", "0", os.path.join(root, "qa_frames.jpg")])

    dur = sh(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", video]).stdout.strip()
    vol = sh(["ffmpeg", "-hide_banner", "-i", video, "-af", "volumedetect", "-vn", "-f", "null", "-"]).stderr
    mean = re.search(r"mean_volume: (\S+) dB", vol)
    peak = re.search(r"max_volume: (\S+) dB", vol)
    print(f"video: {video}\nduration: {float(dur):.1f}s  scenes: {n}")
    print(f"loudness: mean {mean.group(1) if mean else '?'} dB, peak {peak.group(1) if peak else '?'} dB "
          "(target: mean -18..-13, peak below -0.3)")
    print(f"look at: {os.path.join(root, 'qa_images.jpg')}\n         {os.path.join(root, 'qa_frames.jpg')}")


if __name__ == "__main__":
    main()

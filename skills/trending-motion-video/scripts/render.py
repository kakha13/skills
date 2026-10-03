#!/usr/bin/env python3
"""Render a vertical motion video from storyboard.json.

    python3 render.py path/to/storyboard.json [--preview]

Reads <project>/images/NN.png and <project>/vo/NN.mp3 (optional), writes the MP4 named in
storyboard["output"]. Ken Burns motion, crossfades with a light flash, word-by-word captions
paced to the voiceover, optional progress bar and end logo, original music + SFX ducked under the voice.
--preview renders 3 still frames to <project>/preview.jpg instead of the video.
"""
import json, math, os, re, shutil, subprocess, sys, wave
from multiprocessing import Pool, cpu_count

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

W, H, FPS = 1080, 1920, 30
XFADE = 0.45
VO_LEAD, VO_TAIL = 0.3, 0.55
LINE_H = 118
CAPTION_BOTTOM = 1560  # caption block ends here: clear of TikTok/Reels/Shorts bottom UI

# (file, face index). Pillow also searches the system font folders by basename, so a bare
# filename works when macOS moves fonts between /System/Library/Fonts and its Supplemental/ subfolder.
HEAVY_FONTS = [("Avenir Next Condensed.ttc", 8),            # Heavy
               ("/System/Library/Fonts/Avenir Next Condensed.ttc", 8),
               ("/System/Library/Fonts/Supplemental/Avenir Next Condensed.ttc", 8),
               ("Impact.ttf", 0),
               ("/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf", 0)]
TEXT_FONTS = [("Avenir Next.ttc", 2),                       # Demi Bold
              ("/System/Library/Fonts/Avenir Next.ttc", 2),
              ("/System/Library/Fonts/Supplemental/Avenir Next.ttc", 2),
              ("Helvetica.ttc", 1),
              ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 0)]

G = {}  # per-process globals (filled by init_worker)


# ---------- helpers ----------
def first_font(cands, size):
    for path, idx in cands:
        try:
            return ImageFont.truetype(path, size, index=idx)
        except OSError:
            continue
    try:
        path = subprocess.run(["fc-match", "-f", "%{file}", "sans:bold"], capture_output=True, text=True).stdout
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default(size)


def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def ease_out(t):
    return 1 - (1 - t) ** 3


def ease_out_back(t):
    t -= 1
    return 1 + 2.70158 * t ** 3 + 1.70158 * t ** 2


def parse_words(text):
    """'*word*' or '*two words*' = highlighted in the accent color.
    Punctuation may follow the closing asterisk: '*see them*?' highlights 'them?'."""
    out, hl = [], False
    for tok in text.split():
        m = re.match(r"^(\*?)(.*?)(\*?)([^\w*]*)$", tok)
        opens, word, closes, punct = m.groups()
        if opens:
            hl = True
        out.append((word + punct, hl))
        if closes:
            hl = False
    return out


def word_step(scene, nwords):
    return min(0.32, max(0.07, scene.get("vo_dur", 2.0) * 0.6 / max(1, nwords)))


def word_times(scene):
    """Seconds (scene-relative) when each caption word pops. Shared by video and SFX."""
    n = len(parse_words(scene["main"]))
    step = word_step(scene, n)
    return [VO_LEAD - 0.1 + i * step for i in range(n)]


def layout_words(words, f, max_w):
    space = f.getlength(" ")
    lines, cur, cur_w = [], [], 0
    for w, hl in words:
        ww = f.getlength(w)
        if cur and cur_w + space + ww > max_w:
            lines.append((cur, cur_w))
            cur, cur_w = [], 0
        cur_w += (space if cur else 0) + ww
        cur.append((w, hl, ww))
    if cur:
        lines.append((cur, cur_w))
    return lines, space


# ---------- project loading ----------
def load_project(sb_path):
    root = os.path.dirname(os.path.abspath(sb_path))
    sb = json.load(open(sb_path))
    scenes = sb["scenes"]
    sr = 44100
    clips = []
    for k, sc in enumerate(scenes):
        sc.setdefault("kb", "in" if k % 3 != 2 else "out")
        sc.setdefault("pan", [-1, 1, 0][k % 3])
        mp3 = os.path.join(root, "vo", f"{k + 1:02d}.mp3")
        if os.path.exists(mp3):
            raw = subprocess.run(["ffmpeg", "-v", "error", "-i", mp3, "-f", "s16le", "-ac", "1", "-ar", str(sr), "-"],
                                 capture_output=True, check=True).stdout
            clip = np.frombuffer(raw, np.int16).astype(np.float64) / 32768
            sc["vo_dur"] = len(clip) / sr
        else:
            clip = None
        last = k == len(scenes) - 1
        base = VO_LEAD + sc.get("vo_dur", 0) + VO_TAIL + (0.6 if last else 0)
        sc["dur"] = float(sc.get("dur") or max(sc.get("min_dur", 3.6), base))
        clips.append(clip)
    starts, acc = [], 0.0
    for sc in scenes:
        starts.append(acc)
        acc += sc["dur"]
    return root, sb, scenes, starts, acc, clips


# ---------- static layers ----------
def load_scene_image(path):
    im = Image.open(path).convert("RGB")
    s = max(W / im.width, H / im.height) * 1.18  # headroom for motion
    return im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)


def make_gradient():
    y = np.arange(H)[:, None]
    bottom = np.clip((y - H * 0.5) / (H * 0.5), 0, 1) ** 1.4 * 235
    top = np.clip((H * 0.16 - y) / (H * 0.16), 0, 1) ** 1.6 * 150
    g = np.zeros((H, W, 4), np.uint8)
    g[..., 3] = np.maximum(bottom, top).astype(np.uint8).repeat(W, 1)
    g[..., :3] = (4, 8, 20)
    return Image.fromarray(g, "RGBA")


def make_vignette():
    yy, xx = np.mgrid[0:H, 0:W]
    d = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2)
    v = np.zeros((H, W, 4), np.uint8)
    v[..., 3] = (np.clip((d - 0.75) / 0.6, 0, 1) ** 2 * 170).astype(np.uint8)
    return Image.fromarray(v, "RGBA")


def ken_burns(src, t, dur, mode, pan):
    p = clamp(t / dur)
    z = 1.0 + 0.10 * p if mode == "in" else 1.10 - 0.10 * p
    base = min(src.width / W, src.height / H)
    cw, ch = W * base / z, H * base / z
    cx = (src.width - cw) / 2 + pan * (src.width - cw) * 0.35 * (p - 0.5)
    cy = (src.height - ch) / 2 - (src.height - ch) * 0.15 * (p - 0.5)
    return src.resize((W, H), Image.BILINEAR, box=(cx, cy, cx + cw, cy + ch))


# ---------- text ----------
def draw_shadowed(layer, xy, text, f, fill, alpha):
    shadow = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).text((xy[0], xy[1] + 6), text, font=f, fill=(0, 0, 0, int(160 * alpha)))
    layer.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(10)))
    ImageDraw.Draw(layer).text(xy, text, font=f, fill=fill + (int(255 * alpha),))


def render_text(scene, t, out_alpha):
    F, accent = G["fonts"], G["accent"]
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    margin = 80
    words = parse_words(scene["main"].upper())
    lines, space = layout_words(words, F["main"], W - margin * 2)
    y0 = CAPTION_BOTTOM - len(lines) * LINE_H

    kicker = scene.get("kicker", "").upper()
    ka = clamp(t / 0.35) * out_alpha
    if kicker and ka > 0:
        kw = F["kick"].getlength(kicker) + 50 + 4 * len(kicker)
        kx, ky = margin - (1 - ease_out(clamp(t / 0.35))) * 40, y0 - 90
        d.rounded_rectangle((kx, ky, kx + kw, ky + 56), 28, fill=accent + (int(235 * ka),))
        x = kx + 25
        for ch in kicker:
            d.text((x, ky + 11), ch, font=F["kick"], fill=(10, 14, 28, int(255 * ka)))
            x += F["kick"].getlength(ch) + 4

    times = word_times(scene)
    y, i = y0, 0
    for line, _ in lines:
        x = margin
        for w, hl, ww in line:
            p = clamp((t - times[i]) / 0.32)
            if p > 0:
                s, a = ease_out_back(p), clamp(p * 2.5) * out_alpha
                tw, th = int(ww + 40), 150
                tile = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
                draw_shadowed(tile, (20, 10), w, F["main"], accent if hl else (255, 255, 255), a)
                if abs(s - 1) > 0.01:
                    tile = tile.resize((max(1, int(tw * s)), max(1, int(th * s))), Image.BILINEAR)
                ox = int(x - 20 + (tw - tile.width) / 2)
                oy = int(y - 10 + (th - tile.height) * 0.8 + (1 - p) * 30)
                layer.alpha_composite(tile, (max(0, ox), max(0, oy)))
            x += ww + space
            i += 1
        y += LINE_H

    sub = scene.get("sub", "")
    sp = clamp((t - (times[-1] if times else 0) - 0.15) / 0.4)
    if sub and sp > 0:
        a = ease_out(sp) * out_alpha
        sy = y + 22 + (1 - ease_out(sp)) * 20
        d.rectangle((margin, sy + 6, margin + 6, sy + 46), fill=accent + (int(255 * a),))
        d.text((margin + 24, sy), sub, font=F["sub"], fill=(225, 232, 245, int(255 * a)))
    return layer


def credit_line(src, limit=72):
    """'Photo: <credit> / <license>', shortened at word boundaries instead of mid-word."""
    lic = src.get("license", "")
    credit = src["credit"]
    for attempt in (credit, credit.split(" / ")[0], credit.split(",")[0]):
        text = f"Photo: {attempt}" + (f" / {lic}" if lic else "")
        if len(text) <= limit:
            return text
    words, out = credit.split(" / ")[0].split(), ""
    for w in words:
        if len(f"Photo: {out} {w}... / {lic}") > limit:
            break
        out = f"{out} {w}".strip()
    return f"Photo: {out}... / {lic}" if lic else f"Photo: {out}..."


def render_chrome(frame, gt):
    d = ImageDraw.Draw(frame)
    scenes = G["scenes"]
    n, gap, top, m = len(scenes), 10, 70, 60
    seg = (W - 2 * m - gap * (n - 1)) / n
    acc = 0
    for k, sc in enumerate(scenes if G["progress"] else []):
        x0 = m + k * (seg + gap)
        d.rounded_rectangle((x0, top, x0 + seg, top + 6), 3, fill=(255, 255, 255, 70))
        fill = clamp((gt - acc) / sc["dur"])
        if fill > 0:
            d.rounded_rectangle((x0, top, x0 + max(6, seg * fill), top + 6), 3, fill=(255, 255, 255, 230))
        acc += sc["dur"]
    if G["brand"]:
        d.ellipse((m, 112, m + 16, 128), fill=(255, 70, 70, 255))
        d.text((m + 28, 105), G["brand"].upper(), font=G["fonts"]["brand"], fill=(255, 255, 255, 220))
    # photo credit for real (sourced) images, required by CC BY / CC BY-SA
    idx = max(k for k in range(n) if G["starts"][k] <= gt)
    src = scenes[idx].get("image_source")
    if src and src.get("credit"):
        f = G["fonts"]["credit"]
        text = credit_line(src)
        d.text((W - m - f.getlength(text), 140), text, font=f, fill=(255, 255, 255, 170))


# ---------- frames (run in worker processes) ----------
def make_end_logo(root, cfg):
    """Logo for the last scene, optionally on a white rounded card so a dark logo reads on any image."""
    if not cfg or not cfg.get("path"):
        return None
    logo = Image.open(os.path.join(root, cfg["path"])).convert("RGBA")
    w = int(cfg.get("width", 560))
    logo = logo.resize((w, round(logo.height * w / logo.width)), Image.LANCZOS)
    if not cfg.get("card", True):
        return logo
    pad = int(cfg.get("pad", 44))
    card = Image.new("RGBA", (logo.width + 2 * pad, logo.height + 2 * pad), (0, 0, 0, 0))
    ImageDraw.Draw(card).rounded_rectangle((0, 0, card.width - 1, card.height - 1), 48, fill=(255, 255, 255, 245))
    card.alpha_composite(logo, (pad, pad))
    return card


def init_worker(sb_path):
    root, sb, scenes, starts, total, _ = load_project(sb_path)
    G.update(scenes=scenes, starts=starts, total=total, brand=sb.get("brand", ""), progress=sb.get("progress_bar", True),
             accent=hex_rgb(sb.get("accent", "#FFB840")),
             imgs=[load_scene_image(os.path.join(root, "images", f"{k + 1:02d}.png")) for k in range(len(scenes))],
             grad=make_gradient(), vig=make_vignette(),
             logo=make_end_logo(root, sb.get("end_logo")), logo_cfg=sb.get("end_logo") or {},
             fonts=dict(main=first_font(HEAVY_FONTS, 112), sub=first_font(TEXT_FONTS, 40),
                        kick=first_font(TEXT_FONTS, 30), brand=first_font(TEXT_FONTS, 26),
                        credit=first_font(TEXT_FONTS, 22)))


def scene_frame(idx, t):
    sc = G["scenes"][idx]
    return ken_burns(G["imgs"][idx], t + XFADE, sc["dur"] + 2 * XFADE, sc["kb"], sc["pan"]).convert("RGBA")


def render_frame(fi):
    gt = fi / FPS
    scenes, starts = G["scenes"], G["starts"]
    idx = max(k for k in range(len(scenes)) if starts[k] <= gt)
    sc, t = scenes[idx], gt - starts[idx]
    last = idx == len(scenes) - 1
    frame = scene_frame(idx, t)
    if idx > 0 and t < XFADE:  # crossfade + warm flash
        a = ease_out(t / XFADE)
        frame = Image.blend(scene_frame(idx - 1, scenes[idx - 1]["dur"] + t), frame, a)
        if int(60 * (1 - a)):
            frame.alpha_composite(Image.new("RGBA", (W, H), (255, 220, 160, int(60 * (1 - a)))))
    frame.alpha_composite(G["vig"])
    frame.alpha_composite(G["grad"])
    frame.alpha_composite(render_text(sc, t, 1.0 if last else clamp((sc["dur"] - t) / 0.3)))
    render_chrome(frame, gt)
    if last and t > sc["dur"] - 0.8:
        frame.alpha_composite(Image.new("RGBA", (W, H), (0, 0, 0, int(255 * clamp((t - sc["dur"] + 0.8) / 0.8)))))
    if last and G["logo"] is not None:  # after the fade, so the brand stays bright to the last frame
        at = G["logo_cfg"].get("at", sc["dur"] * 0.55)  # seconds into the last scene
        a = clamp((t - at) / 0.4)
        if a > 0:
            logo = G["logo"].copy()
            logo.putalpha(logo.getchannel("A").point(lambda v: int(v * ease_out(a))))
            frame.alpha_composite(logo, ((W - logo.width) // 2, int(G["logo_cfg"].get("y", 520) + (1 - ease_out(a)) * 30)))
    return frame.convert("RGB").tobytes()


# ---------- audio ----------
def make_audio(path, sb, scenes, starts, total, clips, sr=44100):
    import music, sfx
    n = int(total * sr)
    mcfg = sb.get("music", {})
    flag = lambda name: next((starts[k] for k, s in enumerate(scenes) if s.get("music") == name), None)
    out = music.compose(total, drop=starts[1] if len(starts) > 1 else None, breakdown=flag("breakdown"),
                        lift=flag("lift"), outro=starts[-1], bpm=mcfg.get("bpm", 100),
                        mood=mcfg.get("mood", "epic"))[:n] * mcfg.get("level", 0.5)

    wt = [st + x for sc, st in zip(scenes, starts) for x in word_times(sc)]
    fx = sfx.build(total, starts, [s.get("sfx") for s in scenes], wt, cuts=starts[1:])[:n] * sb.get("sfx_level", 1.0)

    voice = np.zeros(n)
    for clip, st in zip(clips, starts):
        if clip is not None:
            a = int((st + VO_LEAD) * sr)
            b = min(n, a + len(clip))
            voice[a:b] += clip[:b - a]
    if voice.any():
        voice = voice / np.max(np.abs(voice)) * 0.95
        win = int(0.25 * sr)
        env = np.convolve(np.abs(voice), np.ones(win) / win, mode="same")
        env = np.clip(env / (np.percentile(env[env > 0], 60) + 1e-9), 0, 1)
    else:
        env = np.zeros(n)
    mix = out * (1 - 0.5 * env)[:, None] + fx * (1 - 0.3 * env)[:, None] + voice[:, None]
    mix = np.tanh(mix * 1.05)
    mix = mix / np.max(np.abs(mix)) * 0.85  # headroom: AAC encoding overshoots a 0.9 peak past -0.3 dB
    with wave.open(path, "wb") as wf:
        wf.setnchannels(2); wf.setsampwidth(2); wf.setframerate(sr)
        wf.writeframes((mix * 32767).astype(np.int16).tobytes())


# ---------- main ----------
def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    sb_path = sys.argv[1]
    root, sb, scenes, starts, total, clips = load_project(sb_path)
    missing = [f"images/{k + 1:02d}.png" for k in range(len(scenes))
               if not os.path.exists(os.path.join(root, "images", f"{k + 1:02d}.png"))]
    if missing:
        sys.exit(f"missing images: {', '.join(missing)}")

    if "--preview" in sys.argv:
        init_worker(sb_path)
        picks = [(0, 3.0), (len(scenes) // 2, 2.5), (len(scenes) - 1, scenes[-1]["dur"] - 1.2)]
        tiles = []
        for idx, t in picks:
            raw = render_frame(int((starts[idx] + t) * FPS))
            tiles.append(Image.frombytes("RGB", (W, H), raw).resize((540, 960)))
        sheet = Image.new("RGB", (540 * 3, 960))
        for k, tile in enumerate(tiles):
            sheet.paste(tile, (540 * k, 0))
        sheet.save(os.path.join(root, "preview.jpg"), quality=88)
        print(os.path.join(root, "preview.jpg"))
        return

    wav = os.path.join(root, ".mix.wav")
    make_audio(wav, sb, scenes, starts, total, clips)
    out = os.path.join(root, sb.get("output", "video.mp4"))
    ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", wav, "-c:v", "libx264",
                           "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
                           "-shortest", "-movflags", "+faststart", out], stdin=subprocess.PIPE)
    nframes = int(total * FPS)
    with Pool(max(1, cpu_count() - 1), initializer=init_worker, initargs=(sb_path,)) as pool:
        for fi, raw in enumerate(pool.imap(render_frame, range(nframes), chunksize=6)):
            ff.stdin.write(raw)
            if fi % 150 == 0:
                print(f"frame {fi}/{nframes}", flush=True)
    ff.stdin.close()
    if ff.wait() != 0:
        sys.exit(f"ffmpeg failed (exit {ff.returncode}); {out} is incomplete")
    os.remove(wav)
    print(f"done: {out} ({total:.1f}s, {len(scenes)} scenes)")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Claude fallback: rasterize Claude-drawn SVG scenes to the PNGs the renderer needs.

    python3 svg_to_png.py storyboard.json [--force]

For every scene that has images/NN.svg but no images/NN.png (or with --force), renders the SVG
to a 1024x1536 PNG. Tries rsvg-convert, then cairosvg, then ImageMagick, then headless Chrome.
Used when gen_images.py reports scenes that Codex could not generate.
"""
import json, os, shutil, subprocess, sys, tempfile

W, H = 1024, 1536
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def via_rsvg(svg, png):
    if not shutil.which("rsvg-convert"):
        return False
    return subprocess.run(["rsvg-convert", "-w", str(W), "-h", str(H), "-o", png, svg]).returncode == 0


def via_cairosvg(svg, png):
    try:
        import cairosvg
    except ImportError:
        return False
    cairosvg.svg2png(url=svg, write_to=png, output_width=W, output_height=H)
    return True


def via_magick(svg, png):
    exe = shutil.which("magick") or shutil.which("convert")
    if not exe:
        return False
    return subprocess.run([exe, "-background", "none", "-density", "192", svg, "-resize", f"{W}x{H}!", png]).returncode == 0


def via_chrome(svg, png):
    exe = CHROME if os.path.exists(CHROME) else (shutil.which("google-chrome") or shutil.which("chromium"))
    if not exe:
        return False
    with tempfile.TemporaryDirectory() as td:
        html = os.path.join(td, "s.html")
        with open(html, "w") as f:
            f.write(f'<html><body style="margin:0"><img src="file://{os.path.abspath(svg)}" width="{W}" height="{H}"></body></html>')
        r = subprocess.run([exe, "--headless", "--disable-gpu", "--hide-scrollbars", f"--window-size={W},{H}",
                            f"--screenshot={png}", f"file://{html}"], capture_output=True)
        return r.returncode == 0 and os.path.exists(png)


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    root = os.path.dirname(os.path.abspath(sys.argv[1]))
    n = len(json.load(open(sys.argv[1]))["scenes"])
    done = 0
    for k in range(n):
        svg = os.path.join(root, "images", f"{k + 1:02d}.svg")
        png = os.path.join(root, "images", f"{k + 1:02d}.png")
        if not os.path.exists(svg) or (os.path.exists(png) and "--force" not in sys.argv):
            continue
        for fn in (via_rsvg, via_cairosvg, via_magick, via_chrome):
            if fn(svg, png) and os.path.exists(png):
                print(f"[{k + 1:02d}] {fn.__name__[4:]} -> {png}")
                done += 1
                break
        else:
            print(f"[{k + 1:02d}] FAILED: install librsvg (brew install librsvg) or cairosvg")
    missing = [f"{k + 1:02d}" for k in range(n) if not os.path.exists(os.path.join(root, "images", f"{k + 1:02d}.png"))]
    print(f"rasterized {done}; " + ("all scenes have images" if not missing else f"still missing: {', '.join(missing)}"))


if __name__ == "__main__":
    main()

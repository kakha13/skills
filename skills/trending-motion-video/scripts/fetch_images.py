#!/usr/bin/env python3
"""Find REAL, reusable images for each scene before falling back to AI generation.

    python3 fetch_images.py search storyboard.json [--only 2,3] [--n 8]
    python3 fetch_images.py thumbs storyboard.json [--only 2,3]
    python3 fetch_images.py fetch  storyboard.json [--force] [--only 4]

search  Queries Wikimedia Commons, NASA Image Library and Openverse with each scene's "image_query"
        (falls back to "image_prompt"). Keeps only licenses that allow reuse AND modification for
        commercial use: public domain / CC0 / CC BY / CC BY-SA. Writes candidates/NN.json and prints
        a ranked table. JSON API calls only: nothing is downloaded.
thumbs  Downloads small thumbnails of the candidates and builds candidates/NN_sheet.jpg (numbered)
        so you can LOOK at them before choosing.
fetch   For every scene with "image_source": {"url", "license", "credit", "page"}, downloads the
        full image and fits it to 1024x1536 portrait at images/NN.png (cover-crop for portrait,
        blurred-fill for landscape). Optional per image: "band": 0.85 keeps a wide group shot
        fully visible, "rotate": 180 turns an upside-down space photo. Writes credits.md. Scenes without image_source are left for
        gen_images.py, which only fills missing images.
"""
import io, json, os, re, sys, urllib.error, urllib.parse, urllib.request

from PIL import Image, ImageDraw, ImageFilter, ImageFont

UA = "trending-motion-video/1.0 (https://github.com/kakha13/skills)"
OUT_W, OUT_H = 1024, 1536
MIN_SIDE = 900  # smaller images look soft after the 1080x1920 upscale + zoom
OK_LICENSE = re.compile(r"^(public domain|pd|pdm|cc0|cc[- ]?by(?:[- ]sa)?(?: \d(\.\d)?)?)$", re.I)


def get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.load(r)


def get_bytes(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def download_with_fallback(url):
    """NASA assets don't always have every rendition; try the next size down."""
    tries = [url] + ([url.replace("~large", r) for r in ("~orig", "~medium")] if "~large" in url else [])
    for i, u in enumerate(tries):
        try:
            return get_bytes(u)
        except urllib.error.HTTPError:
            if i == len(tries) - 1:
                raise


def strip_html(s):
    return re.sub(r"<[^>]+>", "", s or "").strip()


# ---------- sources ----------
def search_commons(q, n):
    url = ("https://commons.wikimedia.org/w/api.php?action=query&format=json&generator=search&gsrnamespace=6"
           f"&gsrsearch={urllib.parse.quote(q + ' filetype:bitmap')}&gsrlimit={n * 2}"
           "&prop=imageinfo&iiprop=url|size|extmetadata&iiurlwidth=1600")
    out = []
    for p in get_json(url).get("query", {}).get("pages", {}).values():
        ii = (p.get("imageinfo") or [{}])[0]
        meta = ii.get("extmetadata", {})
        lic = meta.get("LicenseShortName", {}).get("value", "")
        out.append(dict(source="commons", title=p["title"].replace("File:", ""), license=lic,
                        width=ii.get("width", 0), height=ii.get("height", 0),
                        url=ii.get("thumburl") or ii.get("url"), page=ii.get("descriptionurl"),
                        credit=strip_html(meta.get("Artist", {}).get("value", "")) or "Wikimedia Commons",
                        thumb=ii.get("thumburl")))
    return out


def search_nasa(q, n):
    url = f"https://images-api.nasa.gov/search?q={urllib.parse.quote(q)}&media_type=image&page_size={n}"
    out = []
    for it in get_json(url).get("collection", {}).get("items", [])[:n]:
        d = it["data"][0]
        nid = d["nasa_id"]
        base = f"https://images-assets.nasa.gov/image/{urllib.parse.quote(nid)}/{urllib.parse.quote(nid)}"
        out.append(dict(source="nasa", title=d.get("title", nid), license="Public domain",
                        width=0, height=0,  # NASA search has no dimensions; usually large
                        url=base + "~large.jpg", page=f"https://images.nasa.gov/details/{nid}",
                        credit=f"NASA{(' / ' + d['photographer']) if d.get('photographer') else ''}",
                        thumb=(it.get("links") or [{}])[0].get("href"),
                        note="NASA media: no endorsement implied; check for third-party credits"))
    return out


def search_openverse(q, n):
    url = (f"https://api.openverse.org/v1/images/?q={urllib.parse.quote(q)}"
           f"&license_type=commercial,modification&page_size={n}")
    out = []
    for r in get_json(url).get("results", []):
        lic = r["license"].upper()
        lic = "Public domain" if lic in ("PDM",) else ("CC0" if lic == "CC0" else f"CC {lic} {r.get('license_version', '')}".strip())
        out.append(dict(source=f"openverse/{r.get('source')}", title=r.get("title", ""), license=lic,
                        width=r.get("width") or 0, height=r.get("height") or 0, url=r["url"],
                        page=r.get("foreign_landing_url"), credit=r.get("creator") or r.get("source"),
                        thumb=r.get("thumbnail")))
    return out


def license_ok(lic):
    return bool(OK_LICENSE.match(lic.strip().replace("_", " ")))


def rank(c):
    big = max(c["width"], c["height"])
    return (c["source"] == "nasa" or big >= 2000, big, c["source"] == "commons")


# ---------- fitting ----------
def fit_portrait(im, band=1.25):
    """band: landscape photo width relative to the frame. 1.25 leaves room for Ken Burns panning;
    use ~0.85 for group shots so everyone stays visible after the renderer's zoom."""
    im = im.convert("RGB")
    ar = im.width / im.height
    if ar <= 0.8:  # portrait-ish: cover crop, slight upward bias
        s = max(OUT_W / im.width, OUT_H / im.height)
        im = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
        x = (im.width - OUT_W) // 2
        y = int((im.height - OUT_H) * 0.4)
        return im.crop((x, y, x + OUT_W, y + OUT_H))
    # landscape: blurred, darkened cover background + the full photo in the upper-middle
    s = max(OUT_W / im.width, OUT_H / im.height)
    bg = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
    x, y = (bg.width - OUT_W) // 2, (bg.height - OUT_H) // 2
    bg = bg.crop((x, y, x + OUT_W, y + OUT_H)).filter(ImageFilter.GaussianBlur(40))
    bg = Image.blend(bg, Image.new("RGB", bg.size, (6, 10, 22)), 0.45)
    fw = int(OUT_W * band)
    fg = im.resize((fw, round(im.height * fw / im.width)), Image.LANCZOS)
    top = int(OUT_H * 0.33 - fg.height / 2)
    mask = Image.new("L", fg.size, 255)
    fade = 40
    md = ImageDraw.Draw(mask)
    for i in range(fade):  # feather top/bottom edges into the blur
        md.line([(0, i), (fg.width, i)], fill=int(255 * i / fade))
        md.line([(0, fg.height - 1 - i), (fg.width, fg.height - 1 - i)], fill=int(255 * i / fade))
    bg.paste(fg, ((OUT_W - fw) // 2, max(0, top)), mask)
    return bg


# ---------- commands ----------
def scene_ids(sb, args):
    if "--only" in args:
        return [int(x) - 1 for x in args[args.index("--only") + 1].split(",")]
    return list(range(len(sb["scenes"])))


def cmd_search(root, sb, args):
    n = int(args[args.index("--n") + 1]) if "--n" in args else 8
    os.makedirs(os.path.join(root, "candidates"), exist_ok=True)
    for k in scene_ids(sb, args):
        sc = sb["scenes"][k]
        q = sc.get("image_query") or sc["image_prompt"][:80]
        cands = []
        for fn in (search_commons, search_nasa, search_openverse):
            try:
                cands += fn(q, n)
            except Exception as e:
                print(f"  [{fn.__name__}] {e}")
        cands = [c for c in cands if license_ok(c["license"]) and c["url"]
                 and (c["width"] == 0 or min(c["width"], c["height"]) >= MIN_SIDE or max(c["width"], c["height"]) >= 1600)]
        cands.sort(key=rank, reverse=True)
        cands = cands[:n]
        json.dump(cands, open(os.path.join(root, "candidates", f"{k + 1:02d}.json"), "w"), indent=2)
        print(f"\n[{k + 1:02d}] query: {q!r}  ->  {len(cands)} usable candidates")
        for i, c in enumerate(cands):
            size = f"{c['width']}x{c['height']}" if c["width"] else "large?"
            print(f"  {i}: {c['source']:<18} {c['license']:<14} {size:<10} {c['title'][:60]}")


def cmd_thumbs(root, sb, args):
    font = ImageFont.load_default(28)
    for k in scene_ids(sb, args):
        path = os.path.join(root, "candidates", f"{k + 1:02d}.json")
        if not os.path.exists(path):
            continue
        cands = json.load(open(path))
        tiles = []
        for i, c in enumerate(cands):
            try:
                im = Image.open(io.BytesIO(get_bytes(c.get("thumb") or c["url"]))).convert("RGB")
                im.thumbnail((320, 320))
                tile = Image.new("RGB", (320, 320), (20, 20, 20))
                tile.paste(im, ((320 - im.width) // 2, (320 - im.height) // 2))
                ImageDraw.Draw(tile).text((8, 6), str(i), font=font, fill=(255, 220, 0), stroke_width=3, stroke_fill=(0, 0, 0))
                tiles.append(tile)
            except Exception as e:
                print(f"  [{k + 1:02d}:{i}] thumb failed: {e}")
        if tiles:
            cols = min(4, len(tiles))
            sheet = Image.new("RGB", (320 * cols, 320 * (-(-len(tiles) // cols))))
            for i, t in enumerate(tiles):
                sheet.paste(t, (320 * (i % cols), 320 * (i // cols)))
            out = os.path.join(root, "candidates", f"{k + 1:02d}_sheet.jpg")
            sheet.save(out, quality=85)
            print(out)


def cmd_fetch(root, sb, args):
    os.makedirs(os.path.join(root, "images"), exist_ok=True)
    credits = []
    only = set(scene_ids(sb, args)) if "--only" in args else None
    for k, sc in enumerate(sb["scenes"]):
        src = sc.get("image_source")
        if not src:
            continue
        if not license_ok(src.get("license", "")):
            print(f"[{k + 1:02d}] SKIPPED: license {src.get('license')!r} does not allow reuse; generate instead")
            continue
        out = os.path.join(root, "images", f"{k + 1:02d}.png")
        credits.append(f"- Scene {k + 1}: {src.get('credit', '?')}, {src['license']} - {src.get('page', src['url'])}")
        if only is not None and k not in only:
            continue
        if os.path.exists(out) and "--force" not in args and only is None:
            print(f"[{k + 1:02d}] exists")
            continue
        im = Image.open(io.BytesIO(download_with_fallback(src["url"])))
        if min(im.size) < 600:
            print(f"[{k + 1:02d}] WARNING: only {im.width}x{im.height}, will look soft")
        if src.get("rotate"):
            im = im.rotate(src["rotate"], expand=True)
        fit_portrait(im, src.get("band", 1.25)).save(out)
        print(f"[{k + 1:02d}] ok  {im.width}x{im.height} -> {OUT_W}x{OUT_H}  ({src['license']})")
    if credits:
        with open(os.path.join(root, "credits.md"), "w") as f:
            f.write("# Image credits\n\nPut these in the video description/caption when posting.\n\n" + "\n".join(credits) + "\n")
        print(f"credits -> {os.path.join(root, 'credits.md')}")


def main():
    if len(sys.argv) < 3 or sys.argv[1] not in ("search", "thumbs", "fetch"):
        sys.exit(__doc__)
    sb_path = sys.argv[2]
    root = os.path.dirname(os.path.abspath(sb_path))
    sb = json.load(open(sb_path))
    {"search": cmd_search, "thumbs": cmd_thumbs, "fetch": cmd_fetch}[sys.argv[1]](root, sb, sys.argv[3:])


if __name__ == "__main__":
    main()

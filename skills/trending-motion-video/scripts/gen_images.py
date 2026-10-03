#!/usr/bin/env python3
"""Generate one consistent-style image per scene: Codex first, Claude as the fallback.

    python3 gen_images.py storyboard.json [--only 3,5] [--force] [--jobs 7]

- Scene 01 is generated first and becomes the STYLE ANCHOR: every other scene is generated with
  it attached (-i) so palette, lighting and rendering match across the set.
- Existing images are skipped unless --force (or listed in --only), so re-runs are cheap.
- If the configured Codex model is rejected for this account, walks the models listed in
  ~/.codex/models_cache.json until one is accepted (or uses only CODEX_IMAGE_MODEL=... when set).
- A scene's optional "screen_text" is the only text Codex may draw (prices on a phone screen, a
  receipt total); every other scene is generated with no text at all.
- If Codex is not installed, or still fails after a retry, the scene is handed to CLAUDE: the
  script writes <project>/needs_claude.json and exits with code 2. Claude then draws each listed
  scene as images/NN.svg and runs svg_to_png.py (see SKILL.md, "Claude fallback").
Logs: <project>/logs/img_NN.log
"""
import json, os, shutil, subprocess, sys, threading
from concurrent.futures import ThreadPoolExecutor

TEMPLATE = """Use your built-in image generation tool to create ONE image and save it as a PNG at this exact path:
{path}
(copy the generated file there). Portrait orientation 1024x1536 (vertical 2:3). Do nothing else.
{ref_note}
STYLE (shared by the whole series, follow exactly): {style}. Keep the lower third calm and dark enough for
white caption text. {text_rule}

SUBJECT: {subject}
"""
NO_TEXT = "No text, no letters, no numbers, no logos, no watermarks."
REF_NOTE = ("The attached image is the STYLE REFERENCE for this series: match its color palette, lighting, "
            "rendering and mood exactly, but create a new composition for the subject below.\n")


def fallback_models():
    """Models to try, in order, when Codex rejects the configured one."""
    if os.environ.get("CODEX_IMAGE_MODEL"):
        return [os.environ["CODEX_IMAGE_MODEL"]]
    try:
        d = json.load(open(os.path.expanduser("~/.codex/models_cache.json")))
        return [m.get("slug") or m.get("id") for m in d.get("models", []) if m.get("visibility") == "list"]
    except Exception:
        return []


def next_model(rejected):
    """Mark `rejected` as unusable and switch every worker to the next listed model (None when exhausted)."""
    with LOCK:
        if STATE["model"] == rejected:
            STATE["bad"].add(rejected)
            STATE["model"] = next((m for m in fallback_models() if m not in STATE["bad"]), None)
        return STATE["model"]


LOCK = threading.Lock()
STATE = {"model": os.environ.get("CODEX_IMAGE_MODEL"), "bad": set()}


def run_codex(root, prompt, ref, log):
    cmd = ["codex", "exec", "--skip-git-repo-check", "-s", "workspace-write", "-c", 'model_reasoning_effort="low"']
    if STATE["model"]:
        cmd += ["-m", STATE["model"]]
    if ref:
        cmd += ["-i", ref]
    cmd.append("-")  # prompt via stdin: `-i` is variadic and would swallow a positional prompt
    try:
        r = subprocess.run(cmd, input=prompt, cwd=root, capture_output=True, text=True, timeout=900)
        out = r.stdout + r.stderr
    except subprocess.TimeoutExpired:
        out = "TIMEOUT after 900s"
    with open(log, "a") as f:
        f.write(out)
    return out


def gen_one(root, sb, k, ref):
    n = f"{k + 1:02d}"
    path = os.path.join(root, "images", f"{n}.png")
    screen_text = sb["scenes"][k].get("screen_text")
    text_rule = (NO_TEXT if not screen_text else
                 "The ONLY text allowed anywhere is this exact on-screen text, spelled character for character, "
                 "crisp and legible, placed exactly as the subject describes: " + screen_text +
                 ". No other text, no logos, no watermarks.")
    prompt = TEMPLATE.format(path=path, style=sb["style"], subject=sb["scenes"][k]["image_prompt"],
                             ref_note=REF_NOTE if ref else "", text_rule=text_rule)
    log = os.path.join(root, "logs", f"img_{n}.log")
    for attempt in range(2):
        used = STATE["model"]
        out = run_codex(root, prompt, ref, log)
        # a ChatGPT-account login rejects some listed models; walk the list until one is accepted
        while "not supported" in out and "model" in out:
            model = next_model(used)
            if not model:
                print(f"[{n}] Codex rejected every listed model", flush=True)
                return False
            print(f"[{n}] Codex model {used or '(default)'} rejected; retrying with {model}", flush=True)
            used = model
            out = run_codex(root, prompt, ref, log)
        if os.path.exists(path) and os.path.getsize(path) > 10_000:
            print(f"[{n}] ok", flush=True)
            return True
        print(f"[{n}] attempt {attempt + 1} produced no image (see {log})", flush=True)
    return False


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    sb_path = sys.argv[1]
    root = os.path.dirname(os.path.abspath(sb_path))
    sb = json.load(open(sb_path))
    os.makedirs(os.path.join(root, "images"), exist_ok=True)
    os.makedirs(os.path.join(root, "logs"), exist_ok=True)
    args = sys.argv[2:]
    only = set()
    if "--only" in args:
        only = {int(x) - 1 for x in args[args.index("--only") + 1].split(",")}
    jobs = int(args[args.index("--jobs") + 1]) if "--jobs" in args else 7
    force = "--force" in args

    def wanted(k):
        p = os.path.join(root, "images", f"{k + 1:02d}.png")
        return (k in only) if only else (force or not os.path.exists(p))

    anchor = os.path.join(root, "images", "01.png")
    todo = [k for k in range(len(sb["scenes"])) if wanted(k)]
    if not todo:
        print("all images ready")
        return
    if not shutil.which("codex"):
        print("Codex CLI not found; handing every missing scene to Claude")
        return hand_to_claude(root, sb, todo)
    failed = []
    if 0 in todo and not gen_one(root, sb, 0, None):
        failed.append(0)
    ref = anchor if os.path.exists(anchor) else None
    rest = [k for k in todo if k != 0]
    with ThreadPoolExecutor(jobs) as ex:
        results = list(ex.map(lambda k: gen_one(root, sb, k, ref), rest))
    failed += [k for k, ok in zip(rest, results) if not ok]
    if failed:
        return hand_to_claude(root, sb, failed)
    print("all images ready")


def hand_to_claude(root, sb, scenes):
    """Codex is out: write the brief Claude needs to draw these scenes itself, exit 2."""
    brief = {"style": sb["style"], "accent": sb.get("accent", "#FFB840"), "size": [1024, 1536],
             "scenes": [{"scene": k + 1, "svg": f"images/{k + 1:02d}.svg",
                         "subject": sb["scenes"][k]["image_prompt"], "caption": sb["scenes"][k]["main"]}
                        for k in scenes]}
    path = os.path.join(root, "needs_claude.json")
    json.dump(brief, open(path, "w"), indent=2)
    ids = ", ".join(f"{k + 1:02d}" for k in scenes)
    print(f"CLAUDE FALLBACK: Codex could not make scene(s) {ids}.\n"
          f"Claude: draw each as a 1024x1536 SVG at images/NN.svg following {path},\n"
          f"then run: python3 {os.path.join(os.path.dirname(os.path.abspath(__file__)), 'svg_to_png.py')} storyboard.json")
    sys.exit(2)


if __name__ == "__main__":
    main()

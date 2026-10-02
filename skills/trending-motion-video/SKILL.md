---
name: trending-motion-video
description: Use when the user wants a short vertical motion video (TikTok, Reels, Shorts) about a trending or news topic, or any topic - "research what's popular today and make a video", "make a motion video with images and captions", "faceless explainer video", "news short with voiceover". Researches and fact-checks the topic, writes a storyboard, finds real reusable (public domain / CC) images first, generates only the missing or doubtful ones with the Codex CLI, and has Claude draw any scene Codex can't, then renders a 1080x1920 MP4 with Ken Burns motion, animated word-by-word captions, neural voiceover, and an original copyright-free soundtrack and sound effects.
license: MIT
metadata:
  author: kakha13
  version: '1.2.0'
---

# Trending motion video

Turn a topic (or "whatever is trending today") into a finished 30-50 second vertical video:
researched facts, one image per scene (real photos first, then Codex, then Claude as the last resort),
captions that pop in word by word,
a voiceover, and music + SFX that are generated in code, so there is nothing to license.

Everything is driven by one `storyboard.json`. The scripts in `scripts/` are re-runnable and
skip work that already exists, so iterating on one caption or one image is cheap.

## Requirements (check once, up front)

```bash
command -v codex ffmpeg ffprobe edge-tts && python3 -c "import PIL, numpy, scipy; print('ok')"
```

Missing pieces: `pip install edge-tts pillow numpy scipy`, `brew install ffmpeg`, and the
Codex CLI (`npm i -g @openai/codex`, logged in). Codex's built-in image tool makes the images.

`S` below means this skill's `scripts/` folder. Make a project folder for each video (inside the user's
working directory unless they name one) and run everything from there.

## Workflow

### 1. Pick and verify the topic

Skip the picking part if the user named a topic.

- Search the news for today's date (`trending news <Month D YYYY>`), then a few areas that make
  good visuals (tech, science, space, sports, culture). Choose a story that is **trending today**,
  **visual**, and has **concrete facts** (numbers, names, what happens next).
- Avoid tragedies, crime, and partisan politics unless the user asks for them. They make poor
  short-form visuals and are risky to compress into captions.
- Confirm every fact you will put on screen in **2+ sources**. WebFetch often gets a 403 or times out
  on big outlets, so try a syndicated copy (NPR stories also run on member stations such as OPB or WVXU)
  or a different outlet. Keep the URLs.
- If sources disagree on a detail (an exact date, a mission name), soften it on screen ("this week")
  and flag it in your final message. Never invent a number to fill a caption.

### 2. Write `storyboard.json`

Copy `references/storyboard.example.json` and replace its contents. Shape of a good short:

| # | Beat | Example |
|---|------|---------|
| 1 | Hook: the news in 8 words or fewer | "Google just launched AI chips into orbit" |
| 2-3 | What it is, how it happened | the hardware, the launch |
| 4 | Why it matters | "the sun never sets" |
| 5 | The catch / problem (`"music": "breakdown"`) | "no air to cool the chips" |
| 6 | The big vision (`"music": "lift"`) | "clusters linked by lasers" |
| 7 | Stakes / competition | "the race is on" |
| 8 | Verdict + question for comments | "Would you trust AI in space?" |

Field rules:

- `style`: one shared art direction string (medium, palette, lighting, grain). It is sent with
  every image prompt. Say "negative space in the lower third" so captions stay readable.
- `image_query`: 2-4 word search for a REAL photo of this scene ("Falcon 9 launch"), used in step 3.
- `image_prompt`: the subject for the AI fallback, concrete and visual, no text in the image. Avoid
  real logos and real people's faces; describe "a Falcon 9 style rocket, unbranded" instead.
- `kicker`: 1-2 word label ("THE CATCH"). `main`: 9 words or fewer, wrap 1-2 key phrases in
  `*asterisks*` to highlight them in the accent color. `sub`: 45 characters or fewer, a supporting fact.
- `vo`: 8-20 conversational words that expand on the caption rather than reading it out.
  Write acronyms the way they should be spoken ("A.I."). Each scene's length follows its voiceover.
- `sfx`: one of `telemetry` (satellite/radio), `compute` (chips/AI), `rocket` (launch/engines),
  `sparkle` (reveal/light/success), `alarm` (danger/heat/problem), `lasers` (networks/sci-fi),
  `flyby` (speed/race), `impact` (big stat/shock), `glitch` (hacks/errors/deepfakes),
  `typing` (messages/code), `heartbeat` (health/suspense), or leave it out. The last scene always
  gets a final boom + chime on its last word.
- Top level: `brand` (small label at the top), `accent` (hex), `voice` (edge-tts voice, e.g.
  `en-US-AndrewNeural`, `en-US-AriaNeural`, `en-GB-RyanNeural`), `rate`, and
  `music: {mood: epic | uplifting | dark, bpm, level}`. Match the mood to the story.

### 3. Images: real photos, then Codex, then Claude

Image sources, in strict order:

1. **Real photos** from free, reusable sources (this step's main part, below).
2. **Codex CLI** generates every scene that still has no image.
3. **Claude** draws whatever Codex couldn't make (Codex missing, rejected, or failed twice),
   as an SVG that gets converted to PNG. See "Claude fallback" at the end of this step.

**Rule: after research, look for real, related images on the internet first. Generate an image
only when you can't find a good real one, or when you aren't sure the one you found is good.**

```bash
python3 $S/fetch_images.py search storyboard.json        # JSON API calls only, prints candidates
```

This searches Wikimedia Commons, the NASA Image Library and Openverse with each scene's `image_query`,
and keeps only licenses that allow commercial reuse and modification: **public domain, CC0, CC BY,
CC BY-SA**. NC and ND licenses, stock sites, and news-agency photos (AP, Reuters, Getty) are never used.
Results land in `candidates/NN.json`.

Then:

1. **Ask the user once** before downloading anything: name the sources and say you will grab
   preview thumbnails, then the full-size images you pick (one per scene, usually 1-5 MB each).
2. `python3 $S/fetch_images.py thumbs storyboard.json` builds a numbered `candidates/NN_sheet.jpg`
   per scene. **Look at every sheet.** Titles mislead: a "Google TPU chip" search returned TPU
   *plastic bike tubes*.
3. Accept a candidate only if all of these hold, otherwise leave the scene for generation:
   - it clearly shows **this** scene's subject (the actual event, object or place), not a lookalike
   - it's sharp, at least 900px on the short side (1600+ preferred), no watermark, no burned-in text, not a collage
   - it works in portrait: the subject survives a center crop, or it's a landscape that reads well
     as a band across the upper middle (`fetch` adds a blurred fill behind the captions)
   - no identifiable private people in the frame
4. For each accepted image, add it to the scene:
   `"image_source": {"url": ..., "license": ..., "credit": ..., "page": ...}` (copy from the candidate JSON).
5. `python3 $S/fetch_images.py fetch storyboard.json` downloads and fits them to `images/NN.png`
   and writes `credits.md`. The renderer shows a small "Photo: credit / license" line on those
   scenes, which CC BY and CC BY-SA require.
6. Generate whatever is still missing (it skips scenes that already have an image):

```bash
python3 $S/gen_images.py storyboard.json
```

When the set is mixed, make `style` photographic ("cinematic documentary photograph, natural
light, shallow depth of field ...") so the generated scenes match the real ones. If image 01 is a real
photo, it becomes the style anchor for every generated scene. When nothing real fits, keep an
illustrated style and generate everything.

Generation takes about 1-4 minutes per image, run in parallel with scene 01 as the style anchor, so run it with
`run_in_background` and write the voiceover (step 4) while you wait. Afterwards run
`python3 $S/check.py storyboard.json` and Read `qa_images.jpg`. If an image breaks the style or shows text or
garbled logos, fix its prompt and run `python3 $S/gen_images.py storyboard.json --only 5`.

**Claude fallback.** If `gen_images.py` exits with code 2 and prints `CLAUDE FALLBACK`, Codex could not
make some scenes. It writes `needs_claude.json` (style, accent, and each scene's subject + caption). For
each listed scene:

1. Write `images/NN.svg` yourself: `viewBox="0 0 1024 1536"`, self-contained (no external images or
   fonts), no text. Use the storyboard's palette and mood: layered gradients for sky and lighting,
   simple bold shapes for the subject, a glow or light ray for drama, a light `feTurbulence` grain, and
   a darker lower third (from y of about 980) for the captions.
2. Run `python3 $S/svg_to_png.py storyboard.json`. It tries rsvg-convert, then cairosvg, then
   ImageMagick, then headless Chrome.
3. Read the PNG and fix the SVG if it looks wrong.

Claude's images are flat vector illustrations, simpler than Codex output. If more than half the scenes
end up drawn by Claude, redraw the rest the same way so the video has one consistent look, and tell the
user which scenes are Claude-drawn.

### 4. Voiceover

```bash
python3 $S/voiceover.py storyboard.json      # --force or --only 3 to redo lines
```

### 5. Preview, render, verify

```bash
python3 $S/render.py storyboard.json --preview   # 3 stills -> preview.jpg (seconds)
python3 $S/render.py storyboard.json             # full MP4, about 1-2 min
python3 $S/check.py storyboard.json              # qa_frames.jpg + duration + loudness
```

Read `preview.jpg` before the full render, then `qa_frames.jpg` after it. Check that captions sit
inside the frame, highlights land on the right words, and no image clashes with its caption.
Loudness should come out around -18 to -13 dB mean with the peak under 0 dB.

### 6. Deliver

Send the MP4 to the user (use SendUserFile with `display: render` when it is available) and give a short summary:
the topic and why you picked it, the scene list, which scenes use real photos, which Codex generated and
which Claude drew,
any facts you softened or couldn't verify, and how to change things (edit `storyboard.json` and re-run
`render.py`). Paste the contents of `credits.md` (for the post's caption or description), then end with
the source URLs.

## Things that went wrong before (already handled in the scripts)

- **Codex `-i` is variadic.** `codex exec -i ref.png "prompt"` treats the prompt as a second image
  and then waits forever on stdin. `gen_images.py` passes the prompt through stdin with `-`.
- **Codex unavailable or failing.** `gen_images.py` never blocks the video: scenes it can't make go
  to the Claude fallback (exit code 2 + `needs_claude.json`).
- **The configured Codex model can be rejected** ("model is not supported when using Codex with
  a ChatGPT account"). `gen_images.py` retries with the first listed model from
  `~/.codex/models_cache.json`, or with `CODEX_IMAGE_MODEL`. Don't edit the user's Codex config.
- **Captions placed too low get covered** by TikTok/Reels/Shorts buttons. The caption block is anchored
  from the bottom (ending at y=1560), so a 4-line caption grows upward.
- **Fonts move between macOS versions.** The renderer tries Avenir Next Condensed Heavy in several
  places, then falls back to Impact, then DejaVu (Linux).
- **Image licenses:** `fetch_images.py` filters to public domain / CC0 / CC BY / CC BY-SA and refuses
  to fetch an `image_source` whose license is anything else. A license filter can't judge
  relevance or quality, so looking at the sheets (step 3) is required.
- **Copyright:** the music (`music.py`) and SFX (`sfx.py`) are synthesized from scratch, so there are
  no samples and no Content ID claims. Never download third-party music or effects without the
  user's explicit OK and a license that allows it.

## Tuning

| Want | Change |
|------|--------|
| Different look | `style` + `accent`, then `gen_images.py --force` |
| Slower/faster speech | `rate` (e.g. `+0%`, `+12%`), then `voiceover.py --force` |
| Louder/quieter music or SFX | `music.level` (0.5 default), `sfx_level` (1.0) |
| Hold a scene longer | `"dur": 5.0` on that scene (overrides the voiceover timing) |
| Zoom direction / pan | `"kb": "in" or "out"`, `"pan": -1, 0 or 1` per scene |
| Hear the music alone | `python3 $S/music.py uplifting` writes `music_preview.wav` |
| Group photo gets cropped | `"band": 0.8` in that scene's `image_source`, plus `"kb": "out"`, `"pan": 0`; then `fetch_images.py fetch --only N` |
| Space photo is upside down (logos read backwards) | `"rotate": 180` in `image_source`, then `fetch_images.py fetch --only N` |

## Project layout

```
my-video/
├── storyboard.json      # the only file you edit by hand
├── candidates/          # real-image search results + numbered thumbnail sheets
├── images/01.png ...    # real photos (fitted), Codex output, or Claude SVG -> PNG, 1024x1536
├── needs_claude.json    # only when Codex failed: the scenes Claude must draw
├── credits.md           # attribution for real photos, goes in the post caption
├── vo/01.mp3 ...        # edge-tts output
├── logs/img_NN.log      # Codex logs (check these if an image fails)
├── preview.jpg, qa_images.jpg, qa_frames.jpg
└── <output>.mp4
```

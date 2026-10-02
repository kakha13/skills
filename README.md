# skills

Kakha Giorgashvili's collection of [Claude Code](https://docs.claude.com/en/docs/claude-code/overview) skills — small, focused capabilities you can install into your agent. Language and writing helpers to start, more over time.

## Install

Install the whole collection with [skills.sh](https://skills.sh):

```sh
npx skills add kakha13/skills
```

That pulls in every skill listed below. Claude Code picks them up on the next session — no restart of an existing session needed.

Prefer just one skill? Each can be installed on its own (see the per-skill notes below).

## Skills

| Skill | What it does |
|---|---|
| [`spelling-and-grammar`](./skills/spelling-and-grammar) | Ambient proofreading — checks your English messages for spelling/grammar mistakes before acting on them, shows a quick ❌ → ✅ fix, then proceeds with the corrected request. Silent when your message is already clean. |
| [`georgian-bridge`](./skills/georgian-bridge) | For bilingual users who think in **ქართული** but want English out. Silently translates the Georgian parts of your prompt, treats the merged English as the real request, and replies in English — no translation echo. |
| [`trending-motion-video`](./skills/trending-motion-video) | One sentence to a ready-to-post TikTok/Reels/Shorts video: researches and fact-checks a trending topic, uses real public-domain/CC photos first, then Codex-generated images, then Claude-drawn ones as a last resort, and renders a 1080x1920 MP4 with animated captions, neural voiceover, and original copyright-free music + sound effects. |

### Installing a single skill

Clone this repo and copy the folder you want (e.g. `skills/georgian-bridge`) into `~/.claude/skills/`.

## About the `spelling-and-grammar` "always-on" behavior

Skills are invoked when their description matches the current task, which is reliable but not a hard guarantee on *literally every* message. If you want spelling/grammar to be checked on **every** English message without exception, pair the skill with a global rule loaded into context each turn — for Claude Code, a file at `~/.claude/rules/grammar-check.md` containing the same instructions. The skill makes the capability installable and shareable; the rule makes it strictly always-on.

## Repo layout

```
.
├── README.md                       — this file
├── LICENSE                         — MIT
├── skills.sh.json                  — skills.sh grouping / display config
├── .github/
│   └── FUNDING.yml                 — sponsor links
├── .claude-plugin/
│   ├── plugin.json                 — plugin manifest (lists each skill's path)
│   └── marketplace.json            — marketplace / discovery metadata
└── skills/
    ├── spelling-and-grammar/
    │   └── SKILL.md
    ├── georgian-bridge/
    │   ├── SKILL.md
    │   ├── README.md
    │   └── evals/evals.json
    └── trending-motion-video/
        ├── SKILL.md
        ├── README.md
        ├── scripts/             — fetch_images, gen_images, svg_to_png, voiceover, render, check, music, sfx
        ├── assets/              — example frames for the README
        ├── references/          — storyboard.example.json
        └── evals/evals.json
```

## Adding a new skill

1. Create `skills/<skill-name>/SKILL.md` with YAML frontmatter (`name`, `description`, and optionally `license` + `metadata.author/version`) followed by the instructions. The `description` is the trigger — write it so it clearly states *when* the skill should fire.
2. Add `"./skills/<skill-name>"` to the `skills` array in [`.claude-plugin/plugin.json`](./.claude-plugin/plugin.json).
3. Add the skill's slug to a group in [`skills.sh.json`](./skills.sh.json) so it's grouped correctly on [skills.sh](https://www.skills.sh/docs) (or leave it out to fall under `notGrouped`).
4. Add a row to the **Skills** table above.

## Support

If these skills save you time, you can [buy me a coffee](https://buymeacoffee.com/kakha13) ☕.

## License

MIT — see [`LICENSE`](./LICENSE).

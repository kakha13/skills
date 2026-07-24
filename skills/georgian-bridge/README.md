# georgian-bridge

A [Claude Code](https://docs.claude.com/en/docs/claude-code/overview) skill for bilingual users who think faster in **ქართული** but want their assistant to reason and reply in **English**.

When your prompt contains any Georgian script, the skill silently translates the Georgian portions, splices them back over the English-only portions, and treats the merged English version as the authoritative request — the "moment of truth." The translation never appears in the response. Claude just acts on the English meaning and replies in English, as if you'd typed the whole prompt that way to begin with.

## Why this exists

Bilingual workflow has a recurring friction point: you'll start typing in English, switch to Georgian for a precise correction or clarification ("ვიგულისხმე რო ზემოდან დაშორება გაგეზარდა და არა მარცხნიდან"), and now the assistant either:

- replies in Georgian (often less reliably than English),
- echoes the translation back at you (wasting a line and feeling patronising), or
- mistranslates a piece of intent because no one framed it as a translation task.

`georgian-bridge` resolves all three. One translator-framed pass at the door, then everything downstream — reasoning, code, commit messages, replies — stays in English.

## Example

**Input** (mixed Georgian + English):

```
remove margin from left . ვიგულისხმე რო ზემოდან დაშორება გაგეზარდა და არა მარცხნიდან. იფიქრე როგორც ფრონტენდ დეველოპერი და დიზაინერი
```

**What Claude internally treats as the prompt** (you never see this):

```
remove margin from left . I meant the spacing from above should be increased, not from the left. Think like a frontend developer and designer.
```

**Claude's reply** (in English, no translation echo, just the action):

> The fix is to drop the `ml-[38px]` and bump `mt-2` → `mt-3` so the description gets vertical breathing room instead of being indented under the title. Applied. …

The skill is short — read [`SKILL.md`](./SKILL.md) for the full instructions.

## Installation

This skill ships as part of the [`kakha13/skills`](https://github.com/kakha13/skills) collection.

### Recommended — via [skills.sh](https://skills.sh)

Install the whole collection (recommended):

```sh
npx skills add kakha13/skills
```

Or install just this skill from the standalone repo:

```sh
npx skills add kakha13/georgian-bridge
```

### Manual

Clone straight into the Claude Code skills directory:

```sh
git clone https://github.com/kakha13/georgian-bridge \
  ~/.claude/skills/georgian-bridge
```

Either way, Claude Code picks up new skills on the next session — no restart of an existing session needed. Verify by starting a new session and typing a Georgian phrase: the reply should come back in English with no translation echo.

## Benchmark

Tested on 4 prompts × 2 configurations (with-skill vs no-skill). Each run is one Claude Code subagent. Test cases and grading scripts are reproducible from this repo (see `evals/`).

| Metric | With skill | Baseline (no skill) | Δ |
|---|---|---|---|
| **Pass rate** | **94 %** | 75 % | **+19 pts** |
| Time per run | 25.3 s | 27.5 s | −2.2 s |
| Tokens per run | 33.5 k | 31.4 k | +2.1 k |

Per-eval breakdown (assertions passed / total):

| # | Test prompt | with skill | baseline |
|---|---|---|---|
| 1 | Pure Georgian — TypeError debug request | **4 / 4** | 3 / 4 |
| 2 | Mixed English + Georgian — same debug request | **4 / 4** | 2 / 4 |
| 3 | English with one Georgian phrase ("ცოტა დეტალურად" / "a bit detailed") asking for a `.map` explanation | 3 / 4 | 3 / 4 |
| 4 | Pure English negative case — should NOT trigger the skill | **4 / 4** | 4 / 4 |

**What the failures look like:**

- Eval 1 baseline: replied in Georgian. Skill kept the reply in English.
- Eval 2 baseline: replied in Georgian *and* didn't fully address the cause-vs-fix split that the Georgian half of the prompt asked about.
- Eval 3: with-skill response slightly overshoots the "a bit detailed" length budget (~2.9 k chars where a tighter ~2.5 k cap was set). Soft miss; the action is correct.
- Eval 4: skill correctly does **not** over-trigger when no Georgian is present.

The headline finding is unsurprising in hindsight: without an explicit instruction, Claude tends to mirror the user's input language. The skill enforces *English-out regardless of input-language*, which is the entire point.

## Customising for other languages

The skill is structured so you can fork it for any non-English source language. The two things to change:

1. The **trigger description** in the YAML frontmatter — replace the Georgian Mkhedruli range (`U+10A0–U+10FF`) with the relevant Unicode block (e.g. `U+0400–U+04FF` for Cyrillic, `U+0600–U+06FF` for Arabic).
2. The **translator persona line** in the body — change `"you are profesional translator from georgian to english."` to whatever framing reads most natural for your language pair. The persona framing is intentional; it nudges toward fluent intent-preserving translation rather than literal word-substitution.

Everything else (silence about the translation, English-only output, code-identifier preservation) is language-agnostic and can stay as-is.

## Repo layout

```
georgian-bridge/
├── SKILL.md          — the skill itself (read by Claude Code at runtime)
├── README.md         — this file
└── evals/
    └── evals.json    — the 4 test prompts + per-prompt assertions
```

## License

MIT — see the [repository LICENSE](../../LICENSE).

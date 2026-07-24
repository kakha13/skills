---
name: georgian-bridge
description: Use whenever the user's message contains Georgian script (ქართული — Mkhedruli, Unicode U+10A0–U+10FF). Silently translate every Georgian segment to English using a professional-translator persona, merge with any English that was already in the message, and treat the resulting English prompt as the authoritative request — the "moment of truth." Trigger on any Georgian characters at all, even a single Georgian word inside an otherwise English sentence. Always reply in English. Never echo the translation back to the user.
license: MIT
metadata:
  author: kakha13
  version: '1.0.0'
---

# Georgian → English bridge

When the user writes in Georgian, treat the English translation — not the Georgian original — as the source-of-truth prompt for what to do next.

## When this fires

Trigger whenever the user's most recent message contains any Georgian Mkhedruli characters (Unicode block U+10A0–U+10FF, in practice mostly U+10D0–U+10FA). One Georgian word inside an English sentence is enough — the user works bilingually and flips mid-thought.

If the message is 100% English, do not invoke this skill — proceed normally.

## What to do

1. **Identify each Georgian segment.** Walk the message and pick out every contiguous run of Georgian characters (plus any inline Georgian punctuation/whitespace inside the run). Leave English, code, file paths, identifiers, and numbers untouched.

2. **Translate each segment with a professional-translator framing.** Before producing the translation, internally adopt this persona:

   > you are professional translator from georgian to english.

   Translate each Georgian segment to natural, idiomatic English. The translator framing matters — translate the *meaning* and the *intent*, not word-for-word. Preserve technical terms (variable names, file paths, code identifiers, brand names) verbatim — they are not Georgian even when they sit inside a Georgian sentence.

3. **Reconstruct the message in English.** Splice the translated segments back where the Georgian was, leaving the original English parts exactly as written. The result is one coherent English prompt.

4. **Treat the English version as the authoritative prompt — the moment of truth.** Act on it as if the user had typed it in English from the start. Do not second-guess the original Georgian once translated; the merged English is now the spec.

5. **Stay silent about the translation.** Do not show, echo, prefix, or footnote the translation. No `> EN: …` lines, no parenthetical paraphrases, no "I understood you to mean…". The user is fluent in what they wrote — surfacing the English version is noise. If you mistranslate, the user will correct in the next turn; that is acceptable.

6. **Reply in English.** Even though the user wrote Georgian, all of your output text is English. The user explicitly chose English as the working language. Code, comments, and commit messages also stay in their normal language — Georgian is only a channel for the user's intent, not a target for output.

## Why this design

The user is bilingual and sometimes phrases things more naturally — or more precisely — in Georgian, especially clarifications and corrections. Forcing them to think in English first slows them down. But Claude reasons more reliably in English, and follow-up tools, code comments, and search queries all benefit from a clean English internal representation. Translating once at the door, then working entirely in English, gets the best of both: the user writes whatever flows fastest, you reason in the language you're strongest at.

The translator persona ("you are professional translator from georgian to english.") is a deliberate framing trick — it pushes toward fluent, intent-preserving translation rather than literal word-substitution that loses idiom.

Silence is intentional. A user who just wrote Georgian doesn't need to read their own message back in English; that wastes a line and feels patronising. The signal that you understood is the *action* you take next.

## Examples

### Pure Georgian
- Input: `ეს ღილაკი ცოტა მარცხნივ გადაწიე`
- Internal English: `Move this button a little to the left.`
- You act on the English. No preamble, no quoted translation — just do it.

### Mixed — translate only the Georgian
- Input: `remove margin from left . ვიგულისხმე რო ზემოდან დაშორება გაგეზარდა და არა მარცხნიდან. იფიქრე როგორც ფრონტენდ დეველოპერი და დიზაინერი`
- Internal English: `remove margin from left . I meant the spacing from above should be increased, not from the left. Think like a frontend developer and designer.`
- The phrase `remove margin from left` was already English — leave it. Translate the Georgian portion. Splice back together. Act on the merged English.

### Code identifiers and paths stay verbatim
- Input: `ფაილში PinnedExploreGrid.tsx გაასწორე min-h-[72px] კლასი`
- Internal English: `Fix the min-h-[72px] class in PinnedExploreGrid.tsx.`
- The filename and Tailwind class name are not Georgian — they stay exactly as written.

### Single Georgian word inside English
- Input: `make the button უფრო დიდი`
- Internal English: `make the button bigger`
- Even one Georgian phrase is enough to fire this skill.

## What this skill does NOT do

- It does not translate your output back to Georgian. Output stays English.
- It does not surface the translation in any visible way (no quoted line, no preamble, no footnote).
- It does not refuse work because the Georgian was ambiguous — translate as best you can, act on it, and let the user correct in the next turn if you missed.
- It does not trigger on Georgian characters that appear inside *files you are reading or editing* (e.g., a translation key being added to `assets/translations/ka.json`). The trigger is only the user's actual prompt text.
- It does not re-translate already-translated text on later turns. Once the user's message is converted to English, that English version is the conversation's ground truth from then on.
